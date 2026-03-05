"""Social feed system design — news feed generation, ranking, pagination, content moderation."""

PAIRS = [
    (
        "system-design/news-feed-fanout",
        "Design a news feed system comparing fan-out on write vs fan-out on read approaches, with hybrid strategies for high-follower accounts and feed materialization.",
        '''News feed generation — fan-out on write vs read with hybrid approach:

```python
# feed/fanout_write.py — Fan-out on write: precompute feeds at post time
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class Post:
    post_id: str
    author_id: str
    content: str
    media_urls: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class FanoutConfig:
    """Configuration for hybrid fan-out strategy."""
    celebrity_threshold: int = 10_000   # Followers above this use fan-out on read
    feed_max_size: int = 1000           # Max posts in a user's feed cache
    feed_ttl_seconds: int = 86400 * 7  # Feed cache TTL: 7 days
    fanout_batch_size: int = 500        # Process followers in batches
    fanout_workers: int = 10            # Concurrent fan-out workers


class FanoutOnWrite:
    """
    Fan-out on write: when a user posts, push to all followers' feeds.

    Pros: Read is fast (feed is pre-computed), simple read path
    Cons: Write is expensive for popular users, wasted work for inactive users
    """

    def __init__(self, redis_client: redis.Redis, config: FanoutConfig):
        self.redis = redis_client
        self.config = config

    async def publish_post(self, post: Post) -> dict:
        """Publish a post and fan out to follower feeds."""
        start = time.time()

        # Store the post itself
        post_key = f"post:{post.post_id}"
        await self.redis.hset(post_key, mapping={
            "post_id": post.post_id,
            "author_id": post.author_id,
            "content": post.content,
            "media_urls": json.dumps(post.media_urls),
            "created_at": str(post.created_at),
        })
        await self.redis.expire(post_key, self.config.feed_ttl_seconds)

        # Get follower count to decide strategy
        follower_count = await self.redis.scard(f"followers:{post.author_id}")

        if follower_count > self.config.celebrity_threshold:
            # Celebrity: don't fan out, use fan-out on read for their posts
            await self.redis.zadd(
                f"celebrity_posts:{post.author_id}",
                {post.post_id: post.created_at},
            )
            strategy = "celebrity_skip"
            fanout_count = 0
        else:
            # Normal user: fan out to all followers
            fanout_count = await self._fanout_to_followers(post)
            strategy = "fanout_write"

        # Also add to author's own feed
        await self.redis.zadd(
            f"feed:{post.author_id}",
            {post.post_id: post.created_at},
        )
        await self._trim_feed(post.author_id)

        elapsed = time.time() - start
        return {
            "strategy": strategy,
            "followers": follower_count,
            "fanout_count": fanout_count,
            "elapsed_ms": elapsed * 1000,
        }

    async def _fanout_to_followers(self, post: Post) -> int:
        """Push post to all followers' feeds using batched concurrent writes."""
        cursor = 0
        total = 0
        batch_size = self.config.fanout_batch_size

        while True:
            cursor, follower_ids = await self.redis.sscan(
                f"followers:{post.author_id}",
                cursor=cursor,
                count=batch_size,
            )

            if follower_ids:
                # Batch pipeline for efficiency
                async with self.redis.pipeline(transaction=False) as pipe:
                    for fid in follower_ids:
                        follower_id = fid.decode() if isinstance(fid, bytes) else fid
                        pipe.zadd(
                            f"feed:{follower_id}",
                            {post.post_id: post.created_at},
                        )
                    await pipe.execute()
                total += len(follower_ids)

            if cursor == 0:
                break

        return total

    async def _trim_feed(self, user_id: str) -> None:
        """Keep feed within max size by removing oldest entries."""
        feed_key = f"feed:{user_id}"
        count = await self.redis.zcard(feed_key)
        if count > self.config.feed_max_size:
            await self.redis.zremrangebyrank(
                feed_key, 0, count - self.config.feed_max_size - 1
            )


class FeedReader:
    """
    Read a user's feed with hybrid fan-out strategy.
    Merges pre-computed feed with celebrity posts (fan-out on read).
    """

    def __init__(self, redis_client: redis.Redis, config: FanoutConfig):
        self.redis = redis_client
        self.config = config

    async def get_feed(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get user's feed, merging materialized feed with celebrity posts.

        1. Get pre-computed feed (fan-out on write posts)
        2. Get celebrity posts from followed celebrities (fan-out on read)
        3. Merge, sort by timestamp, paginate
        """
        # 1. Pre-computed feed (already has non-celebrity posts)
        feed_key = f"feed:{user_id}"
        post_ids_with_scores = await self.redis.zrevrangebyscore(
            feed_key,
            max="+inf",
            min="-inf",
            start=0,
            num=limit + 50,  # Over-fetch for merge headroom
            withscores=True,
        )

        merged: list[tuple[str, float]] = [
            (pid.decode() if isinstance(pid, bytes) else pid, score)
            for pid, score in post_ids_with_scores
        ]

        # 2. Celebrity posts (fan-out on read)
        celebrity_ids = await self._get_followed_celebrities(user_id)
        for celeb_id in celebrity_ids:
            celeb_posts = await self.redis.zrevrangebyscore(
                f"celebrity_posts:{celeb_id}",
                max="+inf",
                min="-inf",
                start=0,
                num=20,
                withscores=True,
            )
            for pid, score in celeb_posts:
                merged.append(
                    (pid.decode() if isinstance(pid, bytes) else pid, score)
                )

        # 3. Sort by timestamp (score), deduplicate, paginate
        seen: set[str] = set()
        unique: list[tuple[str, float]] = []
        for pid, score in sorted(merged, key=lambda x: -x[1]):
            if pid not in seen:
                seen.add(pid)
                unique.append((pid, score))

        page = unique[offset:offset + limit]

        # 4. Hydrate post data
        posts = []
        if page:
            async with self.redis.pipeline(transaction=False) as pipe:
                for pid, _ in page:
                    pipe.hgetall(f"post:{pid}")
                results = await pipe.execute()

            for (pid, score), data in zip(page, results):
                if data:
                    post = {
                        k.decode() if isinstance(k, bytes) else k:
                        v.decode() if isinstance(v, bytes) else v
                        for k, v in data.items()
                    }
                    post["score"] = score
                    posts.append(post)

        return posts

    async def _get_followed_celebrities(self, user_id: str) -> list[str]:
        """Get celebrity accounts this user follows."""
        following = await self.redis.smembers(f"following:{user_id}")
        celebrities = []
        for uid in following:
            uid_str = uid.decode() if isinstance(uid, bytes) else uid
            count = await self.redis.scard(f"followers:{uid_str}")
            if count > self.config.celebrity_threshold:
                celebrities.append(uid_str)
        return celebrities
```

```python
# feed/feed_service.py — Complete feed service with caching layers
import asyncio
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis


@dataclass
class FeedServiceConfig:
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 300          # Pre-rendered feed cache: 5 min
    feed_page_size: int = 20
    celebrity_threshold: int = 10_000


class FeedService:
    """High-level feed service combining write and read paths."""

    def __init__(self, config: FeedServiceConfig):
        self.config = config
        self.redis: redis.Redis | None = None
        self.fanout_config = FanoutConfig(
            celebrity_threshold=config.celebrity_threshold,
        )

    async def initialize(self) -> None:
        self.redis = redis.from_url(self.config.redis_url)
        self._writer = FanoutOnWrite(self.redis, self.fanout_config)
        self._reader = FeedReader(self.redis, self.fanout_config)

    async def create_post(self, author_id: str, content: str,
                          media_urls: list[str] | None = None) -> dict:
        """Create a post and fan out to followers."""
        import uuid
        post = Post(
            post_id=str(uuid.uuid4()),
            author_id=author_id,
            content=content,
            media_urls=media_urls or [],
        )
        result = await self._writer.publish_post(post)
        # Invalidate author's cached rendered feed
        await self.redis.delete(f"feed_cache:{author_id}")
        return {"post": post, "fanout": result}

    async def get_feed(self, user_id: str, cursor: str | None = None,
                       limit: int = 20) -> dict:
        """Get user's feed with cursor-based pagination."""
        # Check rendered feed cache
        cache_key = f"feed_cache:{user_id}:{cursor or 'start'}:{limit}"
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        offset = int(cursor) if cursor else 0
        posts = await self._reader.get_feed(user_id, offset, limit + 1)

        has_more = len(posts) > limit
        if has_more:
            posts = posts[:limit]

        result = {
            "posts": posts,
            "next_cursor": str(offset + limit) if has_more else None,
            "has_more": has_more,
        }

        # Cache the rendered feed
        await self.redis.setex(
            cache_key,
            self.config.cache_ttl,
            json.dumps(result, default=str),
        )

        return result

    async def follow(self, follower_id: str, followee_id: str) -> None:
        """Follow a user and backfill recent posts."""
        await self.redis.sadd(f"following:{follower_id}", followee_id)
        await self.redis.sadd(f"followers:{followee_id}", follower_id)

        # Backfill: add followee's recent posts to follower's feed
        recent_posts = await self.redis.zrevrangebyscore(
            f"feed:{followee_id}", "+inf", "-inf",
            start=0, num=20, withscores=True,
        )
        if recent_posts:
            mapping = {
                pid: score
                for pid, score in recent_posts
            }
            await self.redis.zadd(f"feed:{follower_id}", mapping)

        await self.redis.delete(f"feed_cache:{follower_id}")

    async def unfollow(self, follower_id: str, followee_id: str) -> None:
        await self.redis.srem(f"following:{follower_id}", followee_id)
        await self.redis.srem(f"followers:{followee_id}", follower_id)
        await self.redis.delete(f"feed_cache:{follower_id}")
```

```text
Architecture diagram:

  User posts          Fan-out Decision         Feed Storage
  ┌──────────┐       ┌──────────────┐        ┌───────────┐
  │  Author   │──────>│ Follower     │──Yes──>│  Redis    │
  │  creates  │      │ count <10K?  │        │  ZSET     │
  │  post     │      └──────┬───────┘        │  per user │
  └──────────┘             │ No              └───────────┘
                           v                        │
                    ┌──────────────┐                │
                    │ Store in     │                │
                    │ celebrity    │                │
                    │ timeline     │                │
                    └──────────────┘                │
                                                    │
  User reads feed                                   │
  ┌──────────┐       ┌──────────────┐        ┌─────v─────┐
  │  Reader   │──────>│ Merge        │<───────│ Pre-built │
  │  requests │      │ materialized │        │ feed ZSET │
  │  /feed    │      │ + celebrity  │        └───────────┘
  └──────────┘      │ posts        │               ^
                    └──────────────┘               │
                           │              ┌────────┴──────┐
                           └──────────────│ Celebrity     │
                                          │ post ZSETs    │
                                          └───────────────┘

  Fan-out on Write (normal users):
    Post -> Push to each follower's feed ZSET
    Read -> Simply read user's feed ZSET

  Fan-out on Read (celebrities):
    Post -> Store only in celebrity's timeline
    Read -> Merge user's feed ZSET with followed celebrities' timelines
```

| Approach | Write Latency | Read Latency | Storage | Best For |
|---|---|---|---|---|
| Fan-out on Write | O(followers) | O(1) | High (N copies) | Small/medium accounts |
| Fan-out on Read | O(1) | O(following) | Low (1 copy) | Celebrity accounts |
| Hybrid | O(non-celeb followers) | O(celeb following) | Medium | Production systems |
| Pull-based | O(1) | O(following * posts) | Low | Simple apps, <100K users |

| Component | Technology | Purpose |
|---|---|---|
| Feed cache | Redis Sorted Sets | O(log N) insert, O(log N + K) range query |
| Post storage | Redis Hashes | O(1) lookup by post_id |
| Social graph | Redis Sets | O(1) follow/unfollow, O(N) scan |
| Rendered cache | Redis Strings | Pre-serialized feed pages |
| Persistent store | PostgreSQL | Source of truth, search, analytics |
| Async fan-out | Kafka/SQS | Decouple post creation from fan-out |

Key patterns:
1. Hybrid fan-out: write for normal users (<10K followers), read for celebrities
2. Redis ZSET with timestamp as score enables efficient time-ordered pagination
3. Pipeline batched writes during fan-out to reduce round trips
4. Backfill recent posts when following a new user for immediate feed population
5. Cached rendered feeds (5-min TTL) absorb read spikes without re-computation
6. Trim feeds to max 1000 posts per user to bound memory usage'''
    ),
    (
        "system-design/content-ranking",
        "Design a content ranking and recommendation system for social feeds with engagement scoring, time decay, diversity enforcement, and personalization.",
        '''Content ranking and recommendation for social feeds:

```python
# ranking/scorer.py — Multi-signal content ranking engine
import math
import time
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"
    POLL = "poll"


@dataclass
class PostSignals:
    """Engagement signals for a post."""
    post_id: str
    author_id: str
    content_type: ContentType
    created_at: float
    # Engagement counts
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    impressions: int = 0
    # Content quality
    report_count: int = 0
    avg_watch_time_pct: float = 0.0   # For video
    completion_rate: float = 0.0       # Scroll-through rate
    # Author signals
    author_followers: int = 0
    author_quality_score: float = 0.5  # 0-1, based on history
    # Relationship
    is_following: bool = False
    is_close_friend: bool = False
    interaction_count: int = 0         # Past interactions with author


@dataclass
class RankingConfig:
    """Tunable weights for the ranking formula."""
    # Engagement weights
    w_like: float = 1.0
    w_comment: float = 3.0      # Comments are higher signal
    w_share: float = 5.0        # Shares are strongest signal
    w_save: float = 4.0         # Saves indicate high value
    w_click: float = 0.5

    # Time decay
    decay_halflife_hours: float = 6.0  # Post loses half its score every 6 hours
    freshness_boost_minutes: int = 30   # Extra boost for very new posts

    # Relationship weights
    w_following: float = 2.0
    w_close_friend: float = 5.0
    w_interaction: float = 0.5  # Per past interaction

    # Content type multipliers
    content_multipliers: dict[ContentType, float] = field(default_factory=lambda: {
        ContentType.TEXT: 1.0,
        ContentType.IMAGE: 1.2,
        ContentType.VIDEO: 1.5,
        ContentType.LINK: 0.8,
        ContentType.POLL: 1.3,
    })

    # Quality and safety
    report_penalty: float = -10.0
    min_quality_score: float = 0.1

    # Diversity
    max_consecutive_same_author: int = 2
    max_same_type_pct: float = 0.5


class ContentRanker:
    """
    Multi-factor content ranking with time decay and personalization.

    Score = (Engagement * Quality * Relationship) * TimeDecay * ContentBoost
    """

    def __init__(self, config: RankingConfig | None = None):
        self.config = config or RankingConfig()

    def score_post(self, post: PostSignals, viewer_id: str) -> float:
        """Compute a ranking score for a single post."""
        c = self.config

        # 1. Engagement score (weighted sum of interactions)
        engagement = (
            post.likes * c.w_like
            + post.comments * c.w_comment
            + post.shares * c.w_share
            + post.saves * c.w_save
            + post.clicks * c.w_click
        )

        # Normalize by impressions (engagement rate) to avoid popularity bias
        if post.impressions > 100:
            engagement_rate = engagement / post.impressions
            engagement = engagement * (1 + engagement_rate)

        # 2. Quality score
        quality = post.author_quality_score
        quality += post.report_count * c.report_penalty
        quality = max(c.min_quality_score, quality)

        # Video-specific quality
        if post.content_type == ContentType.VIDEO:
            quality *= (0.5 + post.avg_watch_time_pct * 0.5)

        # 3. Relationship score (personalization)
        relationship = 1.0
        if post.is_close_friend:
            relationship += c.w_close_friend
        elif post.is_following:
            relationship += c.w_following
        relationship += min(post.interaction_count * c.w_interaction, 5.0)

        # 4. Time decay (exponential)
        age_hours = (time.time() - post.created_at) / 3600.0
        halflife = c.decay_halflife_hours
        time_factor = math.pow(0.5, age_hours / halflife)

        # Freshness boost for very new posts
        age_minutes = age_hours * 60
        if age_minutes < c.freshness_boost_minutes:
            freshness_ratio = 1 - (age_minutes / c.freshness_boost_minutes)
            time_factor *= (1 + freshness_ratio * 2)

        # 5. Content type boost
        content_boost = c.content_multipliers.get(post.content_type, 1.0)

        # Final score
        score = engagement * quality * relationship * time_factor * content_boost
        return max(0.0, score)

    def rank_feed(
        self,
        posts: list[PostSignals],
        viewer_id: str,
        limit: int = 50,
    ) -> list[tuple[PostSignals, float]]:
        """
        Rank and diversify a feed.

        Steps:
            1. Score all posts
            2. Sort by score
            3. Apply diversity constraints
            4. Return top N
        """
        # Score all posts
        scored = [(post, self.score_post(post, viewer_id)) for post in posts]
        scored.sort(key=lambda x: -x[1])

        # Apply diversity constraints
        diversified = self._apply_diversity(scored, limit)

        return diversified

    def _apply_diversity(
        self,
        scored: list[tuple[PostSignals, float]],
        limit: int,
    ) -> list[tuple[PostSignals, float]]:
        """
        Diversity enforcement:
        - No more than N consecutive posts from same author
        - No more than X% of same content type
        """
        c = self.config
        result: list[tuple[PostSignals, float]] = []
        author_streak: dict[str, int] = {}
        type_counts: dict[ContentType, int] = {}
        skipped: list[tuple[PostSignals, float]] = []

        for post, score in scored:
            if len(result) >= limit:
                break

            # Check consecutive same-author limit
            if result:
                last_author = result[-1][0].author_id
                if post.author_id == last_author:
                    streak = author_streak.get(post.author_id, 0) + 1
                    if streak >= c.max_consecutive_same_author:
                        skipped.append((post, score))
                        continue
                    author_streak[post.author_id] = streak
                else:
                    author_streak.clear()
                    author_streak[post.author_id] = 1

            # Check content type diversity
            current_count = type_counts.get(post.content_type, 0)
            if len(result) > 0:
                type_pct = current_count / len(result)
                if type_pct >= c.max_same_type_pct and len(result) > 5:
                    skipped.append((post, score))
                    continue

            type_counts[post.content_type] = current_count + 1
            result.append((post, score))

        # Fill remaining slots from skipped
        for post, score in skipped:
            if len(result) >= limit:
                break
            result.append((post, score))

        return result
```

```python
# ranking/personalization.py — User preference model for personalized ranking
import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class UserPreferences:
    """Learned user preferences from interaction history."""
    user_id: str
    # Content type affinities (0-1)
    type_affinities: dict[str, float] = field(default_factory=lambda: {
        "text": 0.5, "image": 0.5, "video": 0.5, "link": 0.5, "poll": 0.5,
    })
    # Topic affinities
    topic_affinities: dict[str, float] = field(default_factory=dict)
    # Author affinities (interaction-based)
    author_affinities: dict[str, float] = field(default_factory=dict)
    # Time-of-day activity pattern (24 buckets)
    hourly_activity: list[float] = field(default_factory=lambda: [0.0] * 24)
    # Interaction counts
    total_interactions: int = 0


class PreferenceTracker:
    """Track and update user preferences based on interactions."""

    LEARNING_RATE = 0.1
    DECAY_RATE = 0.99  # Slow decay to forget old preferences

    def __init__(self):
        self.preferences: dict[str, UserPreferences] = {}

    def get_or_create(self, user_id: str) -> UserPreferences:
        if user_id not in self.preferences:
            self.preferences[user_id] = UserPreferences(user_id=user_id)
        return self.preferences[user_id]

    def record_interaction(
        self,
        user_id: str,
        content_type: str,
        author_id: str,
        topics: list[str],
        interaction_type: str,  # "like", "comment", "share", "view", "skip"
        hour_of_day: int,
    ) -> None:
        """Update preferences based on user interaction."""
        prefs = self.get_or_create(user_id)
        prefs.total_interactions += 1

        # Interaction strength
        strengths = {
            "like": 1.0, "comment": 2.0, "share": 3.0,
            "save": 2.5, "view": 0.3, "skip": -0.5,
            "report": -5.0,
        }
        strength = strengths.get(interaction_type, 0.0)
        lr = self.LEARNING_RATE

        # Update content type affinity
        if content_type in prefs.type_affinities:
            current = prefs.type_affinities[content_type]
            target = 1.0 if strength > 0 else 0.0
            prefs.type_affinities[content_type] = current + lr * (target - current) * abs(strength)

        # Update topic affinities
        for topic in topics:
            current = prefs.topic_affinities.get(topic, 0.5)
            target = 1.0 if strength > 0 else 0.0
            prefs.topic_affinities[topic] = current + lr * (target - current) * abs(strength)

        # Update author affinity
        current = prefs.author_affinities.get(author_id, 0.0)
        prefs.author_affinities[author_id] = min(1.0, current + strength * lr)

        # Update hourly activity
        prefs.hourly_activity[hour_of_day] += 1.0

    def get_personalization_multiplier(
        self,
        user_id: str,
        content_type: str,
        author_id: str,
        topics: list[str],
    ) -> float:
        """Get a personalization multiplier for ranking."""
        prefs = self.get_or_create(user_id)

        if prefs.total_interactions < 10:
            return 1.0  # Not enough data

        multiplier = 1.0

        # Content type boost
        type_aff = prefs.type_affinities.get(content_type, 0.5)
        multiplier *= (0.5 + type_aff)  # Range: 0.5 - 1.5

        # Topic boost
        if topics:
            topic_scores = [prefs.topic_affinities.get(t, 0.5) for t in topics]
            avg_topic = sum(topic_scores) / len(topic_scores)
            multiplier *= (0.5 + avg_topic)

        # Author boost
        author_aff = prefs.author_affinities.get(author_id, 0.0)
        multiplier *= (1.0 + author_aff)  # Range: 1.0 - 2.0

        return multiplier
```

```text
Ranking Formula:

  FinalScore = EngagementScore * QualityScore * RelationshipScore
               * TimeDecayFactor * ContentBoost * PersonalizationMultiplier

  Where:
    EngagementScore = likes*1 + comments*3 + shares*5 + saves*4 + clicks*0.5
                      * (1 + engagement_rate if impressions > 100)

    QualityScore = author_quality - reports*10
                   * (0.5 + watch_time_pct*0.5 for video)

    RelationshipScore = 1.0 + (5.0 if close_friend else 2.0 if following)
                        + min(interaction_count * 0.5, 5.0)

    TimeDecayFactor = 0.5 ^ (age_hours / 6.0)
                      * (1 + freshness_boost if age < 30min)

    PersonalizationMultiplier = type_affinity * topic_affinity * author_affinity
```

| Ranking Signal | Weight | Rationale |
|---|---|---|
| Shares | 5x | Strongest endorsement (puts reputation on line) |
| Saves | 4x | High-intent signal (returning later) |
| Comments | 3x | Active engagement beyond passive consumption |
| Likes | 1x | Low-effort positive signal |
| Clicks | 0.5x | Interest but not necessarily approval |
| Reports | -10x | Strong negative signal |

| Time Decay Model | Formula | Use Case |
|---|---|---|
| Exponential | `score * 0.5^(age/halflife)` | Standard feed (this design) |
| Linear | `score * max(0, 1 - age/max_age)` | Simple, aggressive decay |
| Gravity (HN) | `score / (age + 2)^gravity` | Hacker News-style |
| Log | `score / log(age + 2)` | Gentle decay for long-lived content |

Key patterns:
1. Multi-signal scoring prevents gaming via any single metric
2. Normalize engagement by impressions to avoid rich-get-richer bias
3. Time decay with freshness boost balances recency with quality
4. Diversity constraints prevent monotonous feeds (author/type limits)
5. Personalization multiplier adapts to individual preferences over time
6. Exponential moving average for preference learning forgets stale signals gradually'''
    ),
    (
        "system-design/infinite-scroll-pagination",
        "Design infinite scroll with cursor-based pagination for social feeds, handling real-time insertions, deletions, and consistent pagination under concurrent updates.",
        '''Infinite scroll with cursor-based pagination:

```python
# pagination/cursor.py — Cursor-based pagination for feeds
import base64
import json
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from enum import Enum

import asyncpg


T = TypeVar('T')


class SortOrder(str, Enum):
    NEWEST_FIRST = "newest_first"
    SCORE_DESC = "score_desc"
    OLDEST_FIRST = "oldest_first"


@dataclass
class CursorData:
    """Encoded cursor containing pagination state."""
    sort_value: float       # Primary sort key value (timestamp or score)
    post_id: str            # Tiebreaker for stable sort
    sort_order: SortOrder
    created_at: float       # When this cursor was created

    def encode(self) -> str:
        """Encode cursor as URL-safe base64 string."""
        data = json.dumps({
            "sv": self.sort_value,
            "pid": self.post_id,
            "so": self.sort_order.value,
            "ca": self.created_at,
        })
        return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, cursor_str: str) -> 'CursorData':
        """Decode a cursor string."""
        # Re-add padding
        padding = 4 - len(cursor_str) % 4
        if padding != 4:
            cursor_str += "=" * padding
        data = json.loads(base64.urlsafe_b64decode(cursor_str))
        return cls(
            sort_value=data["sv"],
            post_id=data["pid"],
            sort_order=SortOrder(data["so"]),
            created_at=data["ca"],
        )


@dataclass
class PaginatedResponse(Generic[T]):
    """Standard paginated response with cursor metadata."""
    items: list[T]
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    total_estimate: int | None = None  # Approximate total count


class CursorPaginator:
    """
    Cursor-based pagination that handles concurrent inserts/deletes.

    Why cursors over offset pagination:
    - Offset: page 2 shifts when new item is inserted (user sees duplicates/misses)
    - Cursor: anchored to a specific item, stable under concurrent modifications

    Technique: keyset pagination (WHERE created_at < $cursor_value ORDER BY created_at DESC)
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_page(
        self,
        user_id: str,
        cursor: str | None = None,
        limit: int = 20,
        sort_order: SortOrder = SortOrder.NEWEST_FIRST,
    ) -> PaginatedResponse[dict]:
        """
        Fetch a page of feed items using keyset pagination.

        First request: no cursor, returns newest items
        Subsequent: cursor from previous response's next_cursor
        """
        limit = min(limit, 100)  # Cap page size

        if cursor:
            cursor_data = CursorData.decode(cursor)
        else:
            cursor_data = None

        async with self.pool.acquire() as conn:
            if sort_order == SortOrder.NEWEST_FIRST:
                rows = await self._query_newest(conn, user_id, cursor_data, limit)
            elif sort_order == SortOrder.SCORE_DESC:
                rows = await self._query_by_score(conn, user_id, cursor_data, limit)
            else:
                rows = await self._query_oldest(conn, user_id, cursor_data, limit)

            # Estimate total (cached, approximate)
            total = await conn.fetchval(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = 'feed_items'",
            )

        # Build response
        items = [dict(row) for row in rows[:limit]]
        has_more = len(rows) > limit

        next_cursor = None
        if has_more and items:
            last = items[-1]
            sort_val = last.get("created_at", last.get("score", 0))
            if hasattr(sort_val, "timestamp"):
                sort_val = sort_val.timestamp()
            next_cursor = CursorData(
                sort_value=float(sort_val),
                post_id=last["post_id"],
                sort_order=sort_order,
                created_at=time.time(),
            ).encode()

        prev_cursor = None
        if cursor_data and items:
            first = items[0]
            sort_val = first.get("created_at", first.get("score", 0))
            if hasattr(sort_val, "timestamp"):
                sort_val = sort_val.timestamp()
            prev_cursor = CursorData(
                sort_value=float(sort_val),
                post_id=first["post_id"],
                sort_order=sort_order,
                created_at=time.time(),
            ).encode()

        return PaginatedResponse(
            items=items,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            has_more=has_more,
            total_estimate=total,
        )

    async def _query_newest(
        self, conn: asyncpg.Connection,
        user_id: str,
        cursor: CursorData | None,
        limit: int,
    ) -> list[asyncpg.Record]:
        """Keyset pagination: newest first."""
        if cursor:
            return await conn.fetch("""
                SELECT f.post_id, f.author_id, f.content, f.score,
                       f.created_at, f.media_urls, f.like_count, f.comment_count
                FROM feed_items f
                WHERE f.user_id = $1
                  AND (f.created_at, f.post_id) < ($2::timestamptz, $3)
                ORDER BY f.created_at DESC, f.post_id DESC
                LIMIT $4
            """, user_id, cursor.sort_value, cursor.post_id, limit + 1)
        else:
            return await conn.fetch("""
                SELECT f.post_id, f.author_id, f.content, f.score,
                       f.created_at, f.media_urls, f.like_count, f.comment_count
                FROM feed_items f
                WHERE f.user_id = $1
                ORDER BY f.created_at DESC, f.post_id DESC
                LIMIT $2
            """, user_id, limit + 1)

    async def _query_by_score(
        self, conn: asyncpg.Connection,
        user_id: str,
        cursor: CursorData | None,
        limit: int,
    ) -> list[asyncpg.Record]:
        """Keyset pagination: highest score first."""
        if cursor:
            return await conn.fetch("""
                SELECT f.post_id, f.author_id, f.content, f.score,
                       f.created_at, f.media_urls, f.like_count, f.comment_count
                FROM feed_items f
                WHERE f.user_id = $1
                  AND (f.score, f.post_id) < ($2, $3)
                ORDER BY f.score DESC, f.post_id DESC
                LIMIT $4
            """, user_id, cursor.sort_value, cursor.post_id, limit + 1)
        else:
            return await conn.fetch("""
                SELECT f.post_id, f.author_id, f.content, f.score,
                       f.created_at, f.media_urls, f.like_count, f.comment_count
                FROM feed_items f
                WHERE f.user_id = $1
                ORDER BY f.score DESC, f.post_id DESC
                LIMIT $2
            """, user_id, limit + 1)

    async def _query_oldest(
        self, conn: asyncpg.Connection,
        user_id: str,
        cursor: CursorData | None,
        limit: int,
    ) -> list[asyncpg.Record]:
        if cursor:
            return await conn.fetch("""
                SELECT f.post_id, f.author_id, f.content, f.score,
                       f.created_at, f.media_urls
                FROM feed_items f
                WHERE f.user_id = $1
                  AND (f.created_at, f.post_id) > ($2::timestamptz, $3)
                ORDER BY f.created_at ASC, f.post_id ASC
                LIMIT $4
            """, user_id, cursor.sort_value, cursor.post_id, limit + 1)
        else:
            return await conn.fetch("""
                SELECT f.post_id, f.author_id, f.content, f.score,
                       f.created_at, f.media_urls
                FROM feed_items f
                WHERE f.user_id = $1
                ORDER BY f.created_at ASC, f.post_id ASC
                LIMIT $2
            """, user_id, limit + 1)
```

```sql
-- Schema and indexes for cursor-based feed pagination
CREATE TABLE feed_items (
    user_id     TEXT NOT NULL,           -- Feed owner
    post_id     TEXT NOT NULL,           -- Unique post identifier
    author_id   TEXT NOT NULL,
    content     TEXT,
    score       DOUBLE PRECISION DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    media_urls  JSONB DEFAULT '[]',
    like_count  INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, post_id)
);

-- Composite index for keyset pagination (newest first)
-- Covers the most common query pattern
CREATE INDEX idx_feed_user_created
ON feed_items (user_id, created_at DESC, post_id DESC);

-- Composite index for score-based pagination
CREATE INDEX idx_feed_user_score
ON feed_items (user_id, score DESC, post_id DESC);

-- Partial index for unread items
CREATE INDEX idx_feed_unread
ON feed_items (user_id, created_at DESC)
WHERE created_at > NOW() - INTERVAL '7 days';
```

```typescript
// frontend/useInfiniteScroll.ts — React hook for infinite scroll
import { useState, useEffect, useCallback, useRef } from 'react';

interface FeedPage<T> {
    items: T[];
    next_cursor: string | null;
    has_more: boolean;
}

interface UseInfiniteScrollOptions {
    threshold: number;      // Pixels from bottom to trigger load
    initialPageSize: number;
}

function useInfiniteScroll<T>(
    fetchPage: (cursor: string | null) => Promise<FeedPage<T>>,
    options: UseInfiniteScrollOptions = { threshold: 300, initialPageSize: 20 },
) {
    const [items, setItems] = useState<T[]>([]);
    const [cursor, setCursor] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [error, setError] = useState<Error | null>(null);
    const observerRef = useRef<IntersectionObserver | null>(null);
    const sentinelRef = useRef<HTMLDivElement | null>(null);

    const loadMore = useCallback(async () => {
        if (loading || !hasMore) return;

        setLoading(true);
        setError(null);

        try {
            const page = await fetchPage(cursor);
            setItems(prev => [...prev, ...page.items]);
            setCursor(page.next_cursor);
            setHasMore(page.has_more);
        } catch (err) {
            setError(err instanceof Error ? err : new Error(String(err)));
        } finally {
            setLoading(false);
        }
    }, [cursor, loading, hasMore, fetchPage]);

    // IntersectionObserver for infinite scroll trigger
    useEffect(() => {
        if (observerRef.current) {
            observerRef.current.disconnect();
        }

        observerRef.current = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && hasMore && !loading) {
                    loadMore();
                }
            },
            { rootMargin: `${options.threshold}px` },
        );

        if (sentinelRef.current) {
            observerRef.current.observe(sentinelRef.current);
        }

        return () => observerRef.current?.disconnect();
    }, [loadMore, hasMore, loading, options.threshold]);

    const reset = useCallback(() => {
        setItems([]);
        setCursor(null);
        setHasMore(true);
        setError(null);
    }, []);

    return { items, loading, hasMore, error, sentinelRef, reset, loadMore };
}
```

| Pagination Method | Consistency | Performance | Complexity | Supports Inserts |
|---|---|---|---|---|
| Offset (LIMIT/OFFSET) | Unstable under writes | O(offset) skip | Low | Duplicates/gaps |
| Cursor (keyset) | Stable | O(log N) seek | Medium | Correct |
| Seek (WHERE id > X) | Stable (monotonic) | O(log N) | Low | Only for monotonic keys |
| Time-based cursor | Stable | O(log N) | Medium | Correct with tiebreaker |
| Page tokens (opaque) | Stable | O(log N) | Medium | Server-controlled |

Key patterns:
1. Keyset pagination uses `WHERE (col, id) < ($cursor_val, $cursor_id)` for stable pages
2. Tiebreaker column (post_id) ensures uniqueness when sort values collide
3. Fetch `limit + 1` rows: the extra row indicates `has_more` without a separate COUNT query
4. Encode cursors as opaque base64 strings -- clients should never parse them
5. Composite indexes must match the ORDER BY clause exactly for index-only scans
6. IntersectionObserver is more efficient than scroll event listeners for infinite scroll'''
    ),
    (
        "system-design/content-moderation",
        "Design a content moderation pipeline with automated ML classification, human review queues, appeal workflows, and action enforcement across a social platform.",
        '''Content moderation pipeline with ML, human review, and enforcement:

```python
# moderation/pipeline.py — Multi-stage content moderation pipeline
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)


class ViolationType(str, Enum):
    SPAM = "spam"
    HATE_SPEECH = "hate_speech"
    VIOLENCE = "violence"
    NUDITY = "nudity"
    HARASSMENT = "harassment"
    MISINFORMATION = "misinformation"
    SELF_HARM = "self_harm"
    CHILD_SAFETY = "child_safety"
    COPYRIGHT = "copyright"
    NONE = "none"


class ModerationAction(str, Enum):
    APPROVE = "approve"
    WARN = "warn"                 # Notify user
    LIMIT_REACH = "limit_reach"   # Reduce distribution
    REMOVE = "remove"             # Delete content
    SHADOW_BAN = "shadow_ban"     # Hide from others
    SUSPEND = "suspend"           # Temporary account suspension
    BAN = "ban"                   # Permanent ban
    ESCALATE = "escalate"         # Send to human review


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    APPEALED = "appealed"
    APPEAL_REVIEWED = "appeal_reviewed"


@dataclass
class ModerationResult:
    """Result from a single moderation check."""
    violation_type: ViolationType
    confidence: float             # 0.0 - 1.0
    severity: Severity
    recommended_action: ModerationAction
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentItem:
    content_id: str
    author_id: str
    content_type: str            # "post", "comment", "message", "profile"
    text: str | None = None
    media_urls: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class ModerationCase:
    case_id: str = field(default_factory=lambda: uuid4().hex[:12])
    content: ContentItem | None = None
    ml_results: list[ModerationResult] = field(default_factory=list)
    human_result: ModerationResult | None = None
    final_action: ModerationAction = ModerationAction.APPROVE
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer_id: str | None = None
    appeal: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    audit_log: list[dict] = field(default_factory=list)

    def log_event(self, event: str, data: dict | None = None) -> None:
        self.audit_log.append({
            "event": event,
            "timestamp": time.time(),
            "data": data or {},
        })


class MLClassifier:
    """Automated content classification using ML models."""

    # Thresholds for automatic action
    AUTO_REMOVE_THRESHOLD = 0.95    # Very high confidence = auto-remove
    HUMAN_REVIEW_THRESHOLD = 0.60   # Medium confidence = human review
    AUTO_APPROVE_THRESHOLD = 0.20   # Very low confidence = auto-approve

    # Severity requires immediate action
    CRITICAL_TYPES = {ViolationType.CHILD_SAFETY, ViolationType.SELF_HARM}

    async def classify_text(self, text: str) -> list[ModerationResult]:
        """Classify text content for policy violations."""
        results: list[ModerationResult] = []

        # Simulated ML model scores (would call real model API)
        scores = await self._run_text_model(text)

        for violation_type, confidence in scores.items():
            if confidence < 0.1:
                continue

            severity = self._compute_severity(violation_type, confidence)
            action = self._recommend_action(violation_type, confidence, severity)

            results.append(ModerationResult(
                violation_type=violation_type,
                confidence=confidence,
                severity=severity,
                recommended_action=action,
                evidence={"text_excerpt": text[:200], "model": "text-classifier-v3"},
            ))

        return results

    async def classify_image(self, image_url: str) -> list[ModerationResult]:
        """Classify image content."""
        results: list[ModerationResult] = []
        scores = await self._run_image_model(image_url)

        for violation_type, confidence in scores.items():
            if confidence < 0.1:
                continue
            severity = self._compute_severity(violation_type, confidence)
            action = self._recommend_action(violation_type, confidence, severity)
            results.append(ModerationResult(
                violation_type=violation_type,
                confidence=confidence,
                severity=severity,
                recommended_action=action,
                evidence={"image_url": image_url, "model": "image-safety-v2"},
            ))

        return results

    def _compute_severity(self, vtype: ViolationType, confidence: float) -> Severity:
        if vtype in self.CRITICAL_TYPES:
            return Severity.CRITICAL
        if confidence > 0.9:
            return Severity.HIGH
        if confidence > 0.7:
            return Severity.MEDIUM
        return Severity.LOW

    def _recommend_action(
        self,
        vtype: ViolationType,
        confidence: float,
        severity: Severity,
    ) -> ModerationAction:
        # Critical content: always escalate or remove
        if severity == Severity.CRITICAL:
            if confidence > self.AUTO_REMOVE_THRESHOLD:
                return ModerationAction.REMOVE
            return ModerationAction.ESCALATE

        # High confidence: auto-action
        if confidence > self.AUTO_REMOVE_THRESHOLD:
            return ModerationAction.REMOVE

        # Medium confidence: human review
        if confidence > self.HUMAN_REVIEW_THRESHOLD:
            return ModerationAction.ESCALATE

        # Low confidence: approve
        return ModerationAction.APPROVE

    async def _run_text_model(self, text: str) -> dict[ViolationType, float]:
        """Placeholder for actual ML model call."""
        return {ViolationType.SPAM: 0.1, ViolationType.HATE_SPEECH: 0.05}

    async def _run_image_model(self, url: str) -> dict[ViolationType, float]:
        return {ViolationType.NUDITY: 0.1, ViolationType.VIOLENCE: 0.05}


class ModerationPipeline:
    """
    Multi-stage moderation pipeline.

    Stage 1: Automated ML classification (milliseconds)
    Stage 2: Rule-based policy checks (milliseconds)
    Stage 3: Human review queue (minutes to hours)
    Stage 4: Action enforcement
    Stage 5: Appeal handling
    """

    def __init__(
        self,
        classifier: MLClassifier,
        action_handler: Callable[[str, ModerationAction, str], Awaitable[None]],
    ):
        self.classifier = classifier
        self.action_handler = action_handler
        self.cases: dict[str, ModerationCase] = {}
        self.review_queue: asyncio.Queue[str] = asyncio.Queue()
        self._stats = {
            "total_items": 0, "auto_approved": 0, "auto_removed": 0,
            "human_reviewed": 0, "appeals": 0,
        }

    async def moderate(self, item: ContentItem) -> ModerationCase:
        """Run content through the moderation pipeline."""
        self._stats["total_items"] += 1

        case = ModerationCase(content=item)
        case.log_event("created", {"content_id": item.content_id})

        # Stage 1: ML classification
        ml_results = []
        if item.text:
            ml_results.extend(await self.classifier.classify_text(item.text))
        for url in item.media_urls:
            ml_results.extend(await self.classifier.classify_image(url))

        case.ml_results = ml_results
        case.log_event("ml_classified", {
            "results": [
                {"type": r.violation_type.value, "confidence": r.confidence}
                for r in ml_results
            ],
        })

        # Stage 2: Determine action
        if not ml_results:
            case.final_action = ModerationAction.APPROVE
            case.status = ReviewStatus.COMPLETED
            self._stats["auto_approved"] += 1
        else:
            worst = max(ml_results, key=lambda r: r.confidence)

            if worst.recommended_action == ModerationAction.APPROVE:
                case.final_action = ModerationAction.APPROVE
                case.status = ReviewStatus.COMPLETED
                self._stats["auto_approved"] += 1

            elif worst.recommended_action == ModerationAction.ESCALATE:
                case.status = ReviewStatus.PENDING
                self.review_queue.put_nowait(case.case_id)
                case.log_event("escalated_to_human", {
                    "reason": worst.violation_type.value,
                    "confidence": worst.confidence,
                })

            else:
                # Auto-action (high confidence)
                case.final_action = worst.recommended_action
                case.status = ReviewStatus.COMPLETED
                self._stats["auto_removed"] += 1
                case.log_event("auto_actioned", {
                    "action": case.final_action.value,
                })

        # Stage 4: Enforce action
        if case.status == ReviewStatus.COMPLETED:
            await self.action_handler(
                item.content_id, case.final_action, item.author_id
            )
            case.resolved_at = time.time()

        self.cases[case.case_id] = case
        return case

    async def submit_human_review(
        self,
        case_id: str,
        reviewer_id: str,
        action: ModerationAction,
        violation_type: ViolationType,
        notes: str = "",
    ) -> ModerationCase:
        """Human reviewer submits their decision."""
        case = self.cases[case_id]
        case.reviewer_id = reviewer_id
        case.human_result = ModerationResult(
            violation_type=violation_type,
            confidence=1.0,
            severity=Severity.HIGH if action in (ModerationAction.REMOVE, ModerationAction.BAN) else Severity.MEDIUM,
            recommended_action=action,
            evidence={"reviewer": reviewer_id, "notes": notes},
        )
        case.final_action = action
        case.status = ReviewStatus.COMPLETED
        case.resolved_at = time.time()
        case.log_event("human_reviewed", {
            "reviewer": reviewer_id, "action": action.value,
        })

        self._stats["human_reviewed"] += 1

        # Enforce
        await self.action_handler(
            case.content.content_id, action, case.content.author_id
        )

        return case

    async def submit_appeal(
        self,
        case_id: str,
        user_id: str,
        reason: str,
    ) -> ModerationCase:
        """User appeals a moderation decision."""
        case = self.cases[case_id]
        if case.content.author_id != user_id:
            raise ValueError("Only content author can appeal")

        case.appeal = {
            "reason": reason,
            "submitted_at": time.time(),
            "user_id": user_id,
        }
        case.status = ReviewStatus.APPEALED
        case.log_event("appeal_submitted", {"reason": reason})
        self._stats["appeals"] += 1

        # Re-queue for human review
        self.review_queue.put_nowait(case.case_id)
        return case

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "queue_depth": self.review_queue.qsize(),
            "auto_action_rate": (
                (self._stats["auto_approved"] + self._stats["auto_removed"])
                / max(self._stats["total_items"], 1) * 100
            ),
        }
```

```python
# moderation/enforcement.py — Action enforcement across the platform
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserStrike:
    violation_type: str
    action_taken: str
    content_id: str
    timestamp: float = field(default_factory=time.time)


class EnforcementEngine:
    """Enforce moderation actions with escalating consequences."""

    STRIKE_THRESHOLDS = {
        1: "warn",
        3: "restrict_posting_24h",
        5: "restrict_posting_7d",
        7: "suspend_30d",
        10: "permanent_ban",
    }

    def __init__(self):
        self.user_strikes: dict[str, list[UserStrike]] = {}

    async def enforce(
        self,
        content_id: str,
        action: str,
        author_id: str,
    ) -> dict[str, Any]:
        """Execute a moderation action."""
        result: dict[str, Any] = {
            "content_id": content_id,
            "action": action,
            "author_id": author_id,
        }

        if action == "remove":
            # Remove content from feed, search, recommendations
            result["content_hidden"] = True
            result["removed_from"] = ["feed", "search", "recommendations"]

            # Add strike
            strike = UserStrike(
                violation_type="policy_violation",
                action_taken=action,
                content_id=content_id,
            )
            self.user_strikes.setdefault(author_id, []).append(strike)
            strike_count = len(self.user_strikes[author_id])

            # Check for escalation
            for threshold, escalation in sorted(self.STRIKE_THRESHOLDS.items()):
                if strike_count >= threshold:
                    result["escalation"] = escalation

            result["strike_count"] = strike_count

        elif action == "limit_reach":
            result["distribution_reduced"] = True
            result["reach_multiplier"] = 0.1  # Reduce to 10% visibility

        elif action == "shadow_ban":
            result["visible_to_author"] = True
            result["visible_to_others"] = False

        elif action == "approve":
            result["content_visible"] = True

        return result
```

```text
Moderation Pipeline Flow:

  Content Created
       │
       v
  ┌──────────────┐
  │ ML Classifier │ <1 second
  │ (text + image)│
  └──────┬───────┘
         │
    ┌────┴────┐
    │         │
  <0.20    0.20-0.95   >0.95
    │         │           │
    v         v           v
  Auto      Human      Auto
  Approve   Review     Remove
              │           │
              v           │
        ┌──────────┐     │
        │ Reviewer  │     │
        │  Queue    │     │
        │ (SLA: 4h) │     │
        └─────┬────┘     │
              │           │
              v           v
         ┌─────────────────┐
         │  Enforce Action  │
         │  + Track Strikes │
         └────────┬────────┘
                  │
                  v
            ┌──────────┐
            │  Appeal   │ (if user disagrees)
            │  Re-review│
            └──────────┘

  Strike Escalation:
    1 strike:  Warning notification
    3 strikes: 24-hour posting restriction
    5 strikes: 7-day posting restriction
    7 strikes: 30-day suspension
    10 strikes: Permanent ban
```

| Moderation Approach | Latency | Accuracy | Cost | Scale |
|---|---|---|---|---|
| ML auto-moderation | <100ms | 85-95% | Low | Unlimited |
| Keyword/regex filters | <10ms | 60-70% | Very low | Unlimited |
| Human review | 1-24 hours | 95-99% | High | Limited by staff |
| Community reports | Hours-days | 80-90% | Medium | Scales with users |
| Hybrid (this design) | <100ms (ML) + hours (human) | 95%+ | Medium | Production scale |

Key patterns:
1. ML classifier handles volume (99% of content), humans handle edge cases
2. Two thresholds: auto-approve (<0.20), human review (0.20-0.95), auto-remove (>0.95)
3. Critical content types (child safety, self-harm) bypass confidence thresholds
4. Strike system provides progressive enforcement with clear escalation path
5. Complete audit log on every case enables transparency and appeal review
6. Appeal workflow allows users to contest decisions, re-queued for different reviewer'''
    ),
]
