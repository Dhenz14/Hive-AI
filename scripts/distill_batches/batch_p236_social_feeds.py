"""Social feed system design — fan-out, feed ranking, content moderation, follow/unfollow, pagination, activity streams."""

PAIRS = [
    (
        "social/fan-out-strategies",
        "Implement both fan-out-on-write and fan-out-on-read strategies for a social feed system, with a hybrid approach that uses fan-out-on-write for normal users and fan-out-on-read for celebrity users with millions of followers.",
        '''Hybrid fan-out feed system with write-path for normal users and read-path for celebrities:

```python
# fan_out.py — Hybrid fan-out feed system
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

import redis.asyncio as redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UserTier(str, Enum):
    NORMAL = "normal"           # Fan-out on write (< 10K followers)
    CELEBRITY = "celebrity"     # Fan-out on read (>= 10K followers)


CELEBRITY_THRESHOLD = 10_000    # Follower count threshold


class Post(BaseModel):
    post_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    author_id: str
    content: str
    media_urls: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    visibility: str = "public"  # public, followers, private


class FeedItem(BaseModel):
    post_id: str
    author_id: str
    score: float           # Ranking score (timestamp + engagement boost)
    created_at: float


class FollowGraph:
    """Manages follow/unfollow relationships in Redis sets."""

    def __init__(self, r: redis.Redis):
        self.redis = r

    async def follow(self, follower_id: str, followee_id: str):
        """Bidirectional follow tracking."""
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.sadd(f"following:{follower_id}", followee_id)
            await pipe.sadd(f"followers:{followee_id}", follower_id)
            await pipe.execute()

    async def unfollow(self, follower_id: str, followee_id: str):
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.srem(f"following:{follower_id}", followee_id)
            await pipe.srem(f"followers:{followee_id}", follower_id)
            await pipe.execute()

    async def get_followers(self, user_id: str) -> set[str]:
        return {m.decode() for m in await self.redis.smembers(f"followers:{user_id}")}

    async def get_following(self, user_id: str) -> set[str]:
        return {m.decode() for m in await self.redis.smembers(f"following:{user_id}")}

    async def follower_count(self, user_id: str) -> int:
        return await self.redis.scard(f"followers:{user_id}")

    async def is_following(self, follower_id: str, followee_id: str) -> bool:
        return await self.redis.sismember(f"following:{follower_id}", followee_id)


class PostStore:
    """Stores full post objects in Redis hashes."""

    def __init__(self, r: redis.Redis):
        self.redis = r

    async def save(self, post: Post):
        await self.redis.set(
            f"post:{post.post_id}",
            post.model_dump_json(),
            ex=86400 * 30,  # 30 day TTL
        )

    async def get(self, post_id: str) -> Post | None:
        raw = await self.redis.get(f"post:{post_id}")
        if raw is None:
            return None
        return Post.model_validate_json(raw)

    async def get_batch(self, post_ids: list[str]) -> list[Post]:
        if not post_ids:
            return []
        keys = [f"post:{pid}" for pid in post_ids]
        results = await self.redis.mget(keys)
        posts = []
        for raw in results:
            if raw:
                posts.append(Post.model_validate_json(raw))
        return posts


class FanOutService:
    """Hybrid fan-out: write for normal users, read for celebrities."""

    def __init__(self, r: redis.Redis):
        self.redis = r
        self.graph = FollowGraph(r)
        self.posts = PostStore(r)
        self.FEED_MAX_SIZE = 1000      # Max items in a user's feed
        self.CELEBRITY_FEED_MERGE = 50 # Max celebrity posts to merge per read

    async def get_user_tier(self, user_id: str) -> UserTier:
        count = await self.graph.follower_count(user_id)
        return UserTier.CELEBRITY if count >= CELEBRITY_THRESHOLD else UserTier.NORMAL

    # ============================================================
    # WRITE PATH: Publish a new post
    # ============================================================

    async def publish_post(self, post: Post) -> str:
        """Publish a post and fan out to followers' feeds."""
        # 1. Store the post
        await self.posts.save(post)

        # 2. Add to author's own timeline
        await self._add_to_feed(
            f"timeline:{post.author_id}", post.post_id, post.created_at
        )

        # 3. Determine fan-out strategy based on author's tier
        tier = await self.get_user_tier(post.author_id)

        if tier == UserTier.NORMAL:
            # Fan-out on WRITE: push to every follower's feed
            await self._fan_out_write(post)
        else:
            # Fan-out on READ: only store in author's timeline
            # Followers will merge this on read
            logger.info(
                f"Celebrity post {post.post_id} by {post.author_id}: "
                f"read-path fan-out (skipping write fan-out)"
            )

        return post.post_id

    async def _fan_out_write(self, post: Post):
        """Push post to all follower feeds (batch pipeline for efficiency)."""
        followers = await self.graph.get_followers(post.author_id)
        if not followers:
            return

        # Batch in chunks of 500 to avoid oversized pipelines
        follower_list = list(followers)
        for i in range(0, len(follower_list), 500):
            batch = follower_list[i:i + 500]
            async with self.redis.pipeline(transaction=False) as pipe:
                for follower_id in batch:
                    feed_key = f"feed:{follower_id}"
                    await pipe.zadd(feed_key, {post.post_id: post.created_at})
                    await pipe.zremrangebyrank(feed_key, 0, -(self.FEED_MAX_SIZE + 1))
                await pipe.execute()

        logger.info(
            f"Fan-out write: post {post.post_id} pushed to {len(followers)} feeds"
        )

    async def _add_to_feed(self, feed_key: str, post_id: str, score: float):
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.zadd(feed_key, {post_id: score})
            await pipe.zremrangebyrank(feed_key, 0, -(self.FEED_MAX_SIZE + 1))
            await pipe.execute()

    # ============================================================
    # READ PATH: Get a user's feed
    # ============================================================

    async def get_feed(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Post]:
        """Get feed: merge write-path feed + celebrity timelines on read."""

        # 1. Get the pre-built feed (from fan-out-on-write)
        feed_key = f"feed:{user_id}"
        write_path_ids = await self.redis.zrevrange(
            feed_key, offset, offset + limit + self.CELEBRITY_FEED_MERGE - 1
        )
        write_path_ids = [pid.decode() for pid in write_path_ids]

        # 2. Merge celebrity posts (fan-out-on-read)
        celebrity_ids = await self._get_celebrity_posts(user_id, limit)

        # 3. Combine, deduplicate, and sort by score (timestamp)
        all_post_ids = list(dict.fromkeys(write_path_ids + celebrity_ids))

        # 4. Fetch full post objects
        posts = await self.posts.get_batch(all_post_ids)

        # 5. Sort by created_at descending and apply pagination
        posts.sort(key=lambda p: p.created_at, reverse=True)
        return posts[offset:offset + limit]

    async def _get_celebrity_posts(self, user_id: str, limit: int) -> list[str]:
        """Merge recent posts from celebrities that user follows."""
        following = await self.graph.get_following(user_id)
        celebrity_post_ids = []

        for followee_id in following:
            tier = await self.get_user_tier(followee_id)
            if tier != UserTier.CELEBRITY:
                continue

            # Read from celebrity's timeline directly
            recent = await self.redis.zrevrange(
                f"timeline:{followee_id}", 0, self.CELEBRITY_FEED_MERGE - 1
            )
            celebrity_post_ids.extend(pid.decode() for pid in recent)

        return celebrity_post_ids

    # ============================================================
    # UNFOLLOW: Remove posts from feed
    # ============================================================

    async def handle_unfollow(self, follower_id: str, followee_id: str):
        """Remove unfollowed user's posts from feed and update graph."""
        await self.graph.unfollow(follower_id, followee_id)

        tier = await self.get_user_tier(followee_id)
        if tier == UserTier.NORMAL:
            # Remove their posts from follower's feed
            timeline = await self.redis.zrange(f"timeline:{followee_id}", 0, -1)
            if timeline:
                feed_key = f"feed:{follower_id}"
                await self.redis.zrem(feed_key, *timeline)

    async def handle_follow(self, follower_id: str, followee_id: str):
        """Add followed user's recent posts to feed."""
        await self.graph.follow(follower_id, followee_id)

        tier = await self.get_user_tier(followee_id)
        if tier == UserTier.NORMAL:
            # Backfill recent posts into follower's feed
            recent = await self.redis.zrevrange(
                f"timeline:{followee_id}", 0, 49, withscores=True
            )
            if recent:
                feed_key = f"feed:{follower_id}"
                mapping = {pid: score for pid, score in recent}
                await self.redis.zadd(feed_key, mapping)
```

Hybrid fan-out architecture:

```
Normal user (< 10K followers)     Celebrity user (>= 10K followers)
  publishes post                     publishes post
       |                                  |
  Store post in DB               Store post in DB
       |                                  |
  Fan-out on WRITE:              Store in celebrity timeline only
  Push to each follower's              (no fan-out)
  precomputed feed (Redis ZSET)          |
       |                           On READ, followers
  O(N) writes, N = followers      merge celebrity timelines
       |                           into their feed
  Feed reads are O(1)             O(C) reads, C = celebrities followed
```

| Strategy | Write Cost | Read Cost | Freshness | Best For |
|---|---|---|---|---|
| Fan-out on write | O(followers) | O(1) | Instant | Normal users (< 10K followers) |
| Fan-out on read | O(1) | O(following) | At read time | Celebrities (millions of followers) |
| Hybrid (this) | O(normal_followers) | O(celeb_following) | Near-instant | Production social networks |

Key design decisions:
- Redis sorted sets (ZSET) store feeds with timestamps as scores for efficient range queries
- Feed size is capped at 1000 items with ZREMRANGEBYRANK to bound memory
- Celebrity threshold (10K) prevents write amplification for popular accounts
- Batch pipelines (chunks of 500) prevent Redis command buffer overflow
- Unfollow removes posts from precomputed feed to maintain consistency
- Follow backfills recent posts so the feed is immediately populated
'''
    ),
    (
        "social/feed-ranking",
        "Implement a feed ranking system that scores posts based on engagement, recency, user affinity, content type, and diversity, with an explanation of the ranking formula and tuning parameters.",
        '''Feed ranking system with multi-signal scoring and diversity injection:

```python
# feed_ranking.py — Multi-signal feed ranking with diversity and freshness
import math
import time
import logging
from dataclasses import dataclass, field
from typing import Any
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class PostSignals:
    """Raw signals for a single post used in ranking."""
    post_id: str
    author_id: str
    created_at: float              # Unix timestamp
    content_type: str = "text"     # text, image, video, link, poll
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    save_count: int = 0
    view_count: int = 0
    report_count: int = 0
    click_through_rate: float = 0.0
    avg_dwell_time_ms: float = 0.0  # How long users look at this post
    is_original: bool = True        # vs. reshare
    has_media: bool = False
    language: str = "en"
    topic_tags: list[str] = field(default_factory=list)


@dataclass
class UserAffinitySignals:
    """How much the viewer engages with this author and content type."""
    viewer_id: str
    author_id: str
    interaction_score: float = 0.0   # Normalized 0-1, based on past engagement
    content_type_affinity: float = 0.5  # Viewer preference for this content type
    topic_affinity: float = 0.5      # Viewer interest in post topics
    is_close_friend: bool = False
    is_following: bool = True
    muted: bool = False
    notifications_on: bool = False


@dataclass
class RankingWeights:
    """Tunable parameters for the ranking formula."""
    # Engagement weights
    w_likes: float = 1.0
    w_comments: float = 3.0        # Comments indicate deep engagement
    w_shares: float = 5.0          # Shares are highest-value action
    w_saves: float = 4.0
    w_ctr: float = 2.0
    w_dwell: float = 1.5

    # Recency decay
    half_life_hours: float = 6.0   # Post score halves every 6 hours

    # Affinity weights
    w_user_affinity: float = 10.0
    w_content_affinity: float = 3.0
    w_topic_affinity: float = 2.0
    w_close_friend: float = 5.0    # Bonus for close friends

    # Content type bonuses
    w_video_bonus: float = 1.2     # Videos get a boost (platform goal)
    w_original_bonus: float = 1.1  # Original content over reshares

    # Negative signals
    w_report_penalty: float = -10.0
    w_muted_penalty: float = -100.0

    # Diversity parameters
    diversity_author_decay: float = 0.7   # Each repeat author gets 0.7x
    diversity_type_decay: float = 0.85    # Each repeat content type gets 0.85x
    diversity_window: int = 10            # Look at last N items for diversity


class FeedRanker:
    """Ranks feed items using a multi-signal scoring function."""

    def __init__(self, weights: RankingWeights | None = None):
        self.weights = weights or RankingWeights()

    def score_post(
        self,
        post: PostSignals,
        affinity: UserAffinitySignals,
        now: float | None = None,
    ) -> float:
        """Compute ranking score for a single post.

        Score = (engagement + affinity + bonuses) * time_decay * penalties
        """
        now = now or time.time()
        w = self.weights

        # --- 1. Engagement score (normalized log scale) ---
        engagement = (
            w.w_likes * math.log1p(post.like_count) +
            w.w_comments * math.log1p(post.comment_count) +
            w.w_shares * math.log1p(post.share_count) +
            w.w_saves * math.log1p(post.save_count) +
            w.w_ctr * post.click_through_rate * 10 +
            w.w_dwell * math.log1p(post.avg_dwell_time_ms / 1000)
        )

        # --- 2. Recency decay (exponential half-life) ---
        age_hours = (now - post.created_at) / 3600.0
        time_decay = math.pow(0.5, age_hours / w.half_life_hours)

        # --- 3. User affinity ---
        affinity_score = (
            w.w_user_affinity * affinity.interaction_score +
            w.w_content_affinity * affinity.content_type_affinity +
            w.w_topic_affinity * affinity.topic_affinity +
            (w.w_close_friend if affinity.is_close_friend else 0)
        )

        # --- 4. Content type bonuses ---
        content_bonus = 1.0
        if post.content_type == "video":
            content_bonus *= w.w_video_bonus
        if post.is_original:
            content_bonus *= w.w_original_bonus

        # --- 5. Penalties ---
        penalty = 1.0
        if affinity.muted:
            return w.w_muted_penalty  # Hard filter
        if post.report_count > 0:
            penalty *= max(0.1, 1.0 + w.w_report_penalty * (post.report_count / max(post.view_count, 1)))

        # --- Final score ---
        score = (engagement + affinity_score) * time_decay * content_bonus * penalty
        return score

    def rank_feed(
        self,
        posts: list[PostSignals],
        affinities: dict[str, UserAffinitySignals],
        now: float | None = None,
    ) -> list[tuple[str, float]]:
        """Score and rank a list of candidate posts."""
        now = now or time.time()

        scored = []
        for post in posts:
            aff = affinities.get(post.author_id)
            if aff is None:
                aff = UserAffinitySignals(
                    viewer_id="", author_id=post.author_id
                )
            score = self.score_post(post, aff, now)
            scored.append((post.post_id, post.author_id, post.content_type, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[3], reverse=True)

        # Apply diversity re-ranking
        return self._apply_diversity(scored)

    def _apply_diversity(
        self, scored: list[tuple[str, str, str, float]]
    ) -> list[tuple[str, float]]:
        """Re-rank to ensure diversity of authors and content types.

        Uses a greedy insertion approach: penalize items that repeat
        authors or content types recently seen in the output feed.
        """
        w = self.weights
        result: list[tuple[str, float]] = []
        recent_authors: list[str] = []
        recent_types: list[str] = []

        for post_id, author_id, content_type, base_score in scored:
            # Count recent repeats
            author_repeats = recent_authors[-w.diversity_window:].count(author_id)
            type_repeats = recent_types[-w.diversity_window:].count(content_type)

            # Apply decay for repeats
            diversity_factor = (
                (w.diversity_author_decay ** author_repeats) *
                (w.diversity_type_decay ** type_repeats)
            )
            adjusted_score = base_score * diversity_factor

            result.append((post_id, adjusted_score))
            recent_authors.append(author_id)
            recent_types.append(content_type)

        # Re-sort after diversity adjustment
        result.sort(key=lambda x: x[1], reverse=True)
        return result


# ============================================================
# Affinity computation (runs as a batch job)
# ============================================================

@dataclass
class InteractionEvent:
    user_id: str
    author_id: str
    action: str         # like, comment, share, view, click, dwell
    content_type: str
    topic_tags: list[str]
    timestamp: float
    value: float = 1.0  # dwell time in seconds for dwell events


class AffinityComputer:
    """Computes user-author and user-content affinities from interaction history."""

    # Action weights for affinity calculation
    ACTION_WEIGHTS = {
        "like": 1.0,
        "comment": 3.0,
        "share": 5.0,
        "save": 4.0,
        "click": 0.5,
        "view": 0.1,
        "dwell": 0.02,  # per second of dwell time
    }

    def compute_user_affinity(
        self,
        interactions: list[InteractionEvent],
        decay_days: float = 30.0,
    ) -> dict[str, UserAffinitySignals]:
        """Compute affinity scores from interaction history."""
        now = time.time()
        author_scores: dict[str, float] = Counter()
        content_scores: dict[str, float] = Counter()
        topic_scores: dict[str, float] = Counter()
        total_weight = 0.0

        for event in interactions:
            # Time decay: recent interactions matter more
            age_days = (now - event.timestamp) / 86400
            time_weight = math.exp(-age_days / decay_days)

            action_weight = self.ACTION_WEIGHTS.get(event.action, 0.1)
            if event.action == "dwell":
                action_weight *= event.value  # Scale by dwell seconds

            weight = action_weight * time_weight

            author_scores[event.author_id] += weight
            content_scores[event.content_type] += weight
            for tag in event.topic_tags:
                topic_scores[tag] += weight
            total_weight += weight

        # Normalize to 0-1 range
        max_author = max(author_scores.values(), default=1.0)
        max_content = max(content_scores.values(), default=1.0)
        max_topic = max(topic_scores.values(), default=1.0)

        results = {}
        for author_id, raw_score in author_scores.items():
            results[author_id] = UserAffinitySignals(
                viewer_id="",
                author_id=author_id,
                interaction_score=raw_score / max_author,
                content_type_affinity=0.5,  # Filled per-post at ranking time
                topic_affinity=0.5,
            )

        return results
```

Ranking formula breakdown:

```
score = (engagement + affinity) * time_decay * content_bonus * penalty

engagement = 1.0 * log(1+likes)
           + 3.0 * log(1+comments)
           + 5.0 * log(1+shares)
           + 4.0 * log(1+saves)
           + 2.0 * CTR * 10
           + 1.5 * log(1+dwell_seconds)

time_decay = 0.5 ^ (age_hours / 6.0)

affinity = 10.0 * user_interaction_score
         + 3.0 * content_type_affinity
         + 2.0 * topic_affinity
         + 5.0 * is_close_friend

diversity = 0.7 ^ author_repeats_in_window
          * 0.85 ^ type_repeats_in_window
```

| Signal | Weight | Rationale |
|---|---|---|
| Shares | 5.0x | Strongest intent signal (public endorsement) |
| Saves | 4.0x | High-value private intent signal |
| Comments | 3.0x | Deep engagement indicator |
| Likes | 1.0x | Baseline positive signal |
| Reports | -10.0x | Strong negative signal per report |
| Close friend | +5.0 | Social priority for inner circle |
| Video bonus | 1.2x | Platform strategy to promote video |

Key ranking patterns:
- Log scale for engagement counts prevents viral posts from dominating
- Exponential half-life decay balances freshness with engagement quality
- Diversity re-ranking prevents author or content type monopoly in feed
- Affinity is pre-computed as a batch job, not per-request
- Muted users are hard-filtered (score = -100) before diversity
- CTR and dwell time are the best signals for actual interest vs. rage-clicks
'''
    ),
    (
        "social/content-moderation",
        "Build a content moderation pipeline with automated classification, human review queues, appeal workflows, and escalation, including both pre-publish and post-publish moderation.",
        '''Content moderation pipeline with ML classification, review queues, appeals, and escalation:

```python
# moderation.py — Content moderation pipeline with ML + human review
import asyncio
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, Field
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class ContentCategory(str, Enum):
    SAFE = "safe"
    SPAM = "spam"
    HATE_SPEECH = "hate_speech"
    HARASSMENT = "harassment"
    VIOLENCE = "violence"
    SEXUAL = "sexual"
    SELF_HARM = "self_harm"
    MISINFORMATION = "misinformation"
    ILLEGAL = "illegal"
    COPYRIGHT = "copyright"


class ModerationAction(str, Enum):
    APPROVE = "approve"
    REMOVE = "remove"
    RESTRICT = "restrict"       # Reduce distribution, no notification
    WARN = "warn"               # Approve but warn the author
    ESCALATE = "escalate"       # Send to senior moderator
    APPEAL_APPROVED = "appeal_approved"
    APPEAL_DENIED = "appeal_denied"


class ModerationStatus(str, Enum):
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"
    AUTO_REMOVED = "auto_removed"
    IN_REVIEW = "in_review"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REMOVED = "human_removed"
    APPEALED = "appealed"
    APPEAL_REVIEWED = "appeal_reviewed"


class Priority(str, Enum):
    LOW = "low"           # Borderline spam
    MEDIUM = "medium"     # Potential harassment
    HIGH = "high"         # Hate speech, violence
    CRITICAL = "critical" # Self-harm, CSAM, terrorism


class ClassificationResult(BaseModel):
    """Output from ML content classifier."""
    categories: dict[ContentCategory, float]  # Category -> confidence (0-1)
    overall_toxicity: float                    # Aggregate toxicity score
    language: str = "en"
    contains_pii: bool = False
    spam_score: float = 0.0


class ModerationDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    content_id: str
    content_type: str = "post"       # post, comment, message, profile
    author_id: str
    status: ModerationStatus
    action: ModerationAction
    category: ContentCategory | None = None
    confidence: float = 0.0
    reviewer_id: str | None = None
    reason: str = ""
    created_at: float = Field(default_factory=time.time)
    reviewed_at: float | None = None


class ModerationConfig(BaseModel):
    """Thresholds and policies for auto-moderation."""
    auto_approve_threshold: float = 0.15   # Below this toxicity -> auto approve
    auto_remove_threshold: float = 0.95    # Above this -> auto remove
    review_queue_threshold: float = 0.15   # Between approve and remove -> human review

    # Per-category thresholds (override global)
    category_thresholds: dict[ContentCategory, float] = Field(default_factory=lambda: {
        ContentCategory.SELF_HARM: 0.7,     # Lower threshold (more cautious)
        ContentCategory.ILLEGAL: 0.6,
        ContentCategory.VIOLENCE: 0.8,
        ContentCategory.HATE_SPEECH: 0.75,
    })

    # Priority assignment
    category_priority: dict[ContentCategory, Priority] = Field(default_factory=lambda: {
        ContentCategory.SELF_HARM: Priority.CRITICAL,
        ContentCategory.ILLEGAL: Priority.CRITICAL,
        ContentCategory.VIOLENCE: Priority.HIGH,
        ContentCategory.HATE_SPEECH: Priority.HIGH,
        ContentCategory.HARASSMENT: Priority.MEDIUM,
        ContentCategory.SEXUAL: Priority.MEDIUM,
        ContentCategory.SPAM: Priority.LOW,
        ContentCategory.MISINFORMATION: Priority.MEDIUM,
    })

    # Strike system
    max_strikes_warn: int = 2
    max_strikes_restrict: int = 5
    max_strikes_ban: int = 10


class ContentClassifier:
    """ML-based content classification (wraps external API or local model)."""

    async def classify(self, content: str, media_urls: list[str] | None = None) -> ClassificationResult:
        """Classify content for policy violations.

        In production, this calls an ML model service (e.g., OpenAI Moderation,
        Perspective API, or a custom fine-tuned model).
        """
        # Simplified mock — replace with actual ML inference
        toxicity = 0.05  # Placeholder
        return ClassificationResult(
            categories={cat: 0.01 for cat in ContentCategory},
            overall_toxicity=toxicity,
            language="en",
        )


class ModerationPipeline:
    """Full moderation pipeline: classify -> auto-decide -> queue -> review -> appeal."""

    def __init__(
        self,
        r: redis.Redis,
        classifier: ContentClassifier,
        config: ModerationConfig | None = None,
    ):
        self.redis = r
        self.classifier = classifier
        self.config = config or ModerationConfig()

    async def moderate_content(
        self,
        content_id: str,
        content_type: str,
        author_id: str,
        text: str,
        media_urls: list[str] | None = None,
    ) -> ModerationDecision:
        """Pre-publish moderation: classify and decide before content goes live."""

        # Step 1: ML classification
        result = await self.classifier.classify(text, media_urls)

        # Step 2: Find the highest-confidence violation
        top_category = None
        top_confidence = 0.0
        for category, confidence in result.categories.items():
            if category == ContentCategory.SAFE:
                continue
            if confidence > top_confidence:
                top_category = category
                top_confidence = confidence

        # Step 3: Auto-decision based on thresholds
        decision = await self._auto_decide(
            content_id, content_type, author_id,
            result, top_category, top_confidence,
        )

        # Step 4: Store decision
        await self.redis.set(
            f"moderation:{content_id}",
            decision.model_dump_json(),
            ex=86400 * 90,
        )

        # Step 5: Update author's strike count if removed
        if decision.action == ModerationAction.REMOVE:
            await self._add_strike(author_id, decision)

        return decision

    async def _auto_decide(
        self,
        content_id: str,
        content_type: str,
        author_id: str,
        result: ClassificationResult,
        top_category: ContentCategory | None,
        top_confidence: float,
    ) -> ModerationDecision:
        """Apply auto-moderation rules."""
        cfg = self.config

        # Check per-category thresholds
        if top_category and top_category in cfg.category_thresholds:
            threshold = cfg.category_thresholds[top_category]
            if top_confidence >= threshold:
                # Auto-remove for critical categories
                return ModerationDecision(
                    content_id=content_id,
                    content_type=content_type,
                    author_id=author_id,
                    status=ModerationStatus.AUTO_REMOVED,
                    action=ModerationAction.REMOVE,
                    category=top_category,
                    confidence=top_confidence,
                    reason=f"Auto-removed: {top_category.value} ({top_confidence:.2f})",
                )

        # Global thresholds
        if result.overall_toxicity < cfg.auto_approve_threshold:
            return ModerationDecision(
                content_id=content_id,
                content_type=content_type,
                author_id=author_id,
                status=ModerationStatus.AUTO_APPROVED,
                action=ModerationAction.APPROVE,
                confidence=1.0 - result.overall_toxicity,
                reason="Auto-approved: below toxicity threshold",
            )

        if result.overall_toxicity >= cfg.auto_remove_threshold:
            return ModerationDecision(
                content_id=content_id,
                content_type=content_type,
                author_id=author_id,
                status=ModerationStatus.AUTO_REMOVED,
                action=ModerationAction.REMOVE,
                category=top_category,
                confidence=top_confidence,
                reason="Auto-removed: above toxicity threshold",
            )

        # In between: queue for human review
        priority = cfg.category_priority.get(top_category, Priority.LOW)
        await self._enqueue_review(
            content_id, content_type, author_id,
            top_category, top_confidence, priority,
        )

        return ModerationDecision(
            content_id=content_id,
            content_type=content_type,
            author_id=author_id,
            status=ModerationStatus.IN_REVIEW,
            action=ModerationAction.RESTRICT,  # Reduce distribution while in review
            category=top_category,
            confidence=top_confidence,
            reason=f"Queued for human review (priority={priority.value})",
        )

    async def _enqueue_review(
        self, content_id: str, content_type: str, author_id: str,
        category: ContentCategory | None, confidence: float, priority: Priority,
    ):
        """Add to priority-based review queue."""
        # Priority queues: CRITICAL > HIGH > MEDIUM > LOW
        queue_key = f"review_queue:{priority.value}"
        item = {
            "content_id": content_id,
            "content_type": content_type,
            "author_id": author_id,
            "category": category.value if category else "unknown",
            "confidence": confidence,
            "queued_at": time.time(),
        }
        # Score by inverse confidence (higher confidence = review first)
        await self.redis.zadd(queue_key, {
            f"{content_id}": confidence * 1000 + time.time()
        })
        await self.redis.set(f"review_item:{content_id}", json.dumps(item), ex=86400 * 7)

    async def human_review(
        self,
        content_id: str,
        reviewer_id: str,
        action: ModerationAction,
        reason: str = "",
    ) -> ModerationDecision:
        """Human moderator makes a decision."""
        raw = await self.redis.get(f"moderation:{content_id}")
        decision = ModerationDecision.model_validate_json(raw)

        decision.status = (
            ModerationStatus.HUMAN_APPROVED
            if action == ModerationAction.APPROVE
            else ModerationStatus.HUMAN_REMOVED
        )
        decision.action = action
        decision.reviewer_id = reviewer_id
        decision.reason = reason
        decision.reviewed_at = time.time()

        await self.redis.set(f"moderation:{content_id}", decision.model_dump_json())

        if action == ModerationAction.REMOVE:
            await self._add_strike(decision.author_id, decision)

        return decision

    async def submit_appeal(self, content_id: str, appeal_reason: str) -> str:
        """Author appeals a moderation decision."""
        raw = await self.redis.get(f"moderation:{content_id}")
        decision = ModerationDecision.model_validate_json(raw)
        decision.status = ModerationStatus.APPEALED

        await self.redis.set(f"moderation:{content_id}", decision.model_dump_json())
        # Queue for senior reviewer
        await self._enqueue_review(
            content_id, decision.content_type, decision.author_id,
            decision.category, decision.confidence, Priority.HIGH,
        )
        return decision.decision_id

    async def _add_strike(self, author_id: str, decision: ModerationDecision):
        strikes = await self.redis.incr(f"strikes:{author_id}")
        logger.info(f"User {author_id} strike #{strikes}: {decision.category}")

        if strikes >= self.config.max_strikes_ban:
            logger.warning(f"User {author_id} BANNED ({strikes} strikes)")
        elif strikes >= self.config.max_strikes_restrict:
            logger.warning(f"User {author_id} RESTRICTED ({strikes} strikes)")


import json  # Required for json.dumps in _enqueue_review
```

Moderation pipeline flow:

```
Content submitted
       |
  ML Classification
  (toxicity, categories)
       |
  +---------+-----------+
  |         |           |
 < 0.15   0.15-0.95   > 0.95
  |         |           |
 AUTO      HUMAN       AUTO
 APPROVE   REVIEW      REMOVE
  |         |           |
  |    Priority queue   |  Strike++
  |    (CRITICAL first) |
  |         |           |
  |    Moderator        |
  |    decides          |
  |    /      \\         |
  | Approve  Remove     |
  |             |       |
  |          Strike++   |
  |                     |
  |    APPEAL?          |
  |    /      \\         |
  | Approve  Deny       |
```

| Moderation Layer | Latency | Accuracy | Cost |
|---|---|---|---|
| Pre-publish ML filter | < 100ms | 85-95% | Low (compute) |
| Post-publish user reports | Minutes-hours | 95%+ with volume | Free (crowd) |
| Human review queue | Hours-days | 99%+ | High (labor) |
| Appeal review | 1-3 days | 99%+ | Highest |

Key moderation patterns:
- Pre-publish ML filter catches obvious violations with zero user impact
- "Restrict" action reduces distribution while content is under review (shadow moderation)
- Priority queues ensure critical content (self-harm, CSAM) is reviewed first
- Strike system with escalating consequences (warn -> restrict -> ban)
- Appeal workflow routes to senior reviewers for a fresh look
- Per-category thresholds allow lower tolerance for dangerous categories
'''
    ),
    (
        "social/infinite-scroll-pagination",
        "Implement cursor-based infinite scroll pagination for a social feed, with stable cursors that handle new posts being inserted, deleted posts, and feed re-ranking, including both API and frontend implementation.",
        '''Cursor-based infinite scroll with stable pagination and real-time updates:

```python
# pagination.py — Cursor-based pagination for social feeds
import base64
import json
import time
import logging
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis
from pydantic import BaseModel, Field
from fastapi import FastAPI, Query, HTTPException

logger = logging.getLogger(__name__)

app = FastAPI()


class FeedCursor(BaseModel):
    """Opaque cursor encoding the pagination position.

    Uses (score, post_id) as a stable anchor that survives inserts/deletes.
    Score is the ranking score (not timestamp) for ranked feeds.
    """
    last_score: float      # Score of the last item returned
    last_post_id: str      # Post ID for tie-breaking (scores may collide)
    feed_version: int      # Detects feed rebuilds/re-ranks
    created_at: float      # Cursor creation time (for staleness checks)

    def encode(self) -> str:
        """Encode cursor as URL-safe base64 string (opaque to client)."""
        payload = self.model_dump_json()
        return base64.urlsafe_b64encode(payload.encode()).decode()

    @classmethod
    def decode(cls, encoded: str) -> "FeedCursor":
        payload = base64.urlsafe_b64decode(encoded.encode()).decode()
        return cls.model_validate_json(payload)


class FeedPage(BaseModel):
    """A single page of feed results."""
    items: list[dict[str, Any]]
    next_cursor: str | None = None    # None means no more pages
    has_more: bool = False
    new_items_count: int = 0          # Items added since cursor was created


class PaginatedFeedService:
    """Cursor-based feed pagination over Redis sorted sets."""

    def __init__(self, r: redis.Redis):
        self.redis = r
        self.PAGE_SIZE = 20
        self.MAX_CURSOR_AGE = 3600 * 24  # 24 hours max cursor lifetime

    async def get_feed_page(
        self,
        user_id: str,
        cursor: str | None = None,
        page_size: int = 20,
    ) -> FeedPage:
        """Fetch a page of feed items using cursor-based pagination.

        Cursor strategy:
        - First page: No cursor, return top N items
        - Next pages: Use ZREVRANGEBYSCORE with (last_score, last_id) anchor
        - This is stable across inserts (new high-score items don't shift pages)
        """
        feed_key = f"feed:{user_id}"
        page_size = min(page_size, 50)  # Cap page size

        if cursor is None:
            return await self._first_page(feed_key, user_id, page_size)

        # Decode and validate cursor
        try:
            feed_cursor = FeedCursor.decode(cursor)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

        # Check cursor staleness
        if time.time() - feed_cursor.created_at > self.MAX_CURSOR_AGE:
            raise HTTPException(status_code=410, detail="Cursor expired, refresh feed")

        return await self._next_page(feed_key, user_id, feed_cursor, page_size)

    async def _first_page(
        self, feed_key: str, user_id: str, page_size: int
    ) -> FeedPage:
        """Return the first page (newest/highest-scored items)."""
        # Fetch page_size + 1 to check if there are more
        results = await self.redis.zrevrange(
            feed_key, 0, page_size, withscores=True
        )

        if not results:
            return FeedPage(items=[], has_more=False)

        items = []
        for post_id_bytes, score in results[:page_size]:
            post_id = post_id_bytes.decode()
            items.append({"post_id": post_id, "score": score})

        has_more = len(results) > page_size

        # Build cursor from the last item
        next_cursor = None
        if has_more and items:
            last = items[-1]
            cursor = FeedCursor(
                last_score=last["score"],
                last_post_id=last["post_id"],
                feed_version=1,
                created_at=time.time(),
            )
            next_cursor = cursor.encode()

        # Hydrate posts (fetch full post data)
        items = await self._hydrate_posts(items)

        return FeedPage(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def _next_page(
        self, feed_key: str, user_id: str,
        cursor: FeedCursor, page_size: int,
    ) -> FeedPage:
        """Return the next page starting after the cursor position.

        Uses ZREVRANGEBYSCORE to find items with score < cursor.last_score,
        with the cursor post_id as a tie-breaker for equal scores.
        """
        # Get items with score <= last_score
        # We use the score as the primary anchor and post_id for tie-breaking
        results = await self.redis.zrevrangebyscore(
            feed_key,
            max=cursor.last_score,
            min="-inf",
            start=0,
            num=page_size + 50,  # Over-fetch to handle tie-breaking
            withscores=True,
        )

        # Filter: skip items at or before the cursor position
        items = []
        past_cursor = False
        for post_id_bytes, score in results:
            post_id = post_id_bytes.decode()

            if not past_cursor:
                if score < cursor.last_score:
                    past_cursor = True
                elif score == cursor.last_score and post_id <= cursor.last_post_id:
                    if post_id == cursor.last_post_id:
                        past_cursor = True  # Found the cursor item, skip it
                    continue
                else:
                    continue

            items.append({"post_id": post_id, "score": score})
            if len(items) >= page_size + 1:
                break

        has_more = len(items) > page_size
        items = items[:page_size]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = FeedCursor(
                last_score=last["score"],
                last_post_id=last["post_id"],
                feed_version=cursor.feed_version,
                created_at=time.time(),
            ).encode()

        # Count new items since cursor was created
        new_count = await self.redis.zcount(
            feed_key, cursor.last_score + 0.001, "+inf"
        )

        items = await self._hydrate_posts(items)

        return FeedPage(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            new_items_count=new_count,
        )

    async def _hydrate_posts(self, items: list[dict]) -> list[dict]:
        """Fetch full post data for a list of feed items."""
        if not items:
            return []
        keys = [f"post:{item['post_id']}" for item in items]
        results = await self.redis.mget(keys)

        hydrated = []
        for item, raw in zip(items, results):
            if raw:
                post_data = json.loads(raw)
                hydrated.append({**item, **post_data})
            # Skip items that no longer exist (deleted posts)
        return hydrated


# ============================================================
# API Endpoint
# ============================================================

feed_service: PaginatedFeedService | None = None

@app.get("/api/feed")
async def get_feed(
    user_id: str,
    cursor: str | None = Query(None, description="Pagination cursor"),
    page_size: int = Query(20, ge=1, le=50),
):
    return await feed_service.get_feed_page(user_id, cursor, page_size)
```

```typescript
// feed-client.ts — Frontend infinite scroll with cursor pagination
import { useCallback, useEffect, useRef, useState } from 'react';

interface FeedItem {
    post_id: string;
    score: number;
    content: string;
    author_id: string;
    created_at: number;
}

interface FeedPage {
    items: FeedItem[];
    next_cursor: string | null;
    has_more: boolean;
    new_items_count: number;
}

function useFeed(userId: string) {
    const [items, setItems] = useState<FeedItem[]>([]);
    const [cursor, setCursor] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [newCount, setNewCount] = useState(0);
    const observerRef = useRef<IntersectionObserver | null>(null);
    const sentinelRef = useRef<HTMLDivElement | null>(null);

    const fetchPage = useCallback(async (nextCursor: string | null) => {
        if (loading) return;
        setLoading(true);

        try {
            const params = new URLSearchParams({ user_id: userId, page_size: '20' });
            if (nextCursor) params.set('cursor', nextCursor);

            const resp = await fetch(`/api/feed?${params}`);
            if (resp.status === 410) {
                // Cursor expired — refresh from top
                setCursor(null);
                setItems([]);
                setHasMore(true);
                return;
            }

            const page: FeedPage = await resp.json();

            setItems(prev => nextCursor ? [...prev, ...page.items] : page.items);
            setCursor(page.next_cursor);
            setHasMore(page.has_more);
            setNewCount(page.new_items_count);
        } catch (err) {
            console.error('Feed fetch failed:', err);
        } finally {
            setLoading(false);
        }
    }, [userId, loading]);

    // Intersection Observer for infinite scroll
    useEffect(() => {
        if (observerRef.current) observerRef.current.disconnect();

        observerRef.current = new IntersectionObserver(
            entries => {
                if (entries[0].isIntersecting && hasMore && !loading) {
                    fetchPage(cursor);
                }
            },
            { rootMargin: '500px' }  // Pre-fetch 500px before sentinel is visible
        );

        if (sentinelRef.current) {
            observerRef.current.observe(sentinelRef.current);
        }

        return () => observerRef.current?.disconnect();
    }, [cursor, hasMore, loading, fetchPage]);

    // Initial load
    useEffect(() => {
        fetchPage(null);
    }, [userId]);

    const refreshFeed = () => {
        setCursor(null);
        setItems([]);
        setHasMore(true);
        fetchPage(null);
    };

    return { items, loading, hasMore, newCount, sentinelRef, refreshFeed };
}
```

| Pagination Strategy | Handles Inserts | Handles Deletes | Handles Re-ranking |
|---|---|---|---|
| Offset-based (LIMIT/OFFSET) | Duplicates/skips | Skips | Breaks completely |
| Cursor by timestamp | Stable | Stable | Breaks (order changes) |
| Cursor by (score, id) (this) | Stable | Stable (hydration filters) | Mostly stable |
| Keyset pagination | Stable | Stable | Depends on sort key |

Key pagination patterns:
- Cursor encodes (score, post_id) for stable position across inserts
- Opaque base64 cursor prevents clients from guessing or manipulating
- Over-fetch with tie-breaking handles equal scores correctly
- Deleted posts are silently filtered during hydration (no gaps)
- `new_items_count` enables "N new posts" banner without refreshing
- Intersection Observer with 500px rootMargin pre-fetches before user reaches bottom
- Cursor expiry (24h) forces refresh to prevent infinite stale browsing
'''
    ),
    (
        "social/activity-streams",
        "Implement an Activity Streams (W3C) compatible notification and activity feed system with different feed types (personal, notification, home), fan-out, and aggregation of similar activities.",
        '''Activity Streams-compatible notification system with aggregation and multiple feed types:

```python
# activity_streams.py — W3C Activity Streams with aggregation and multi-feed fan-out
import asyncio
import json
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

import redis.asyncio as redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ActivityVerb(str, Enum):
    """W3C Activity Streams 2.0 activity types."""
    CREATE = "Create"
    LIKE = "Like"
    FOLLOW = "Follow"
    SHARE = "Announce"   # AS2 uses "Announce" for shares
    COMMENT = "Create"   # Create with inReplyTo
    MENTION = "Mention"
    UPDATE = "Update"
    DELETE = "Delete"
    ACCEPT = "Accept"    # Accept follow request
    REJECT = "Reject"


class Activity(BaseModel):
    """W3C Activity Streams 2.0 compatible activity object."""
    id: str = Field(default_factory=lambda: f"urn:activity:{uuid4().hex[:12]}")
    type: str                          # ActivityVerb value
    actor: dict[str, str]              # {"type": "Person", "id": "user:123", "name": "Alice"}
    object: dict[str, Any]             # The target object (post, comment, user)
    target: dict[str, Any] | None = None  # Where the activity is directed
    published: str = ""                # ISO 8601 timestamp
    summary: str = ""                  # Human-readable summary
    context: dict[str, Any] = Field(default_factory=dict)

    # Non-standard extensions for internal use
    _score: float = 0.0
    _aggregation_key: str = ""

    def model_post_init(self, _context: Any) -> None:
        if not self.published:
            from datetime import datetime, timezone
            self.published = datetime.now(timezone.utc).isoformat()
        # Build aggregation key: same verb + same object = aggregatable
        self._aggregation_key = f"{self.type}:{self.object.get('id', '')}"


class AggregatedActivity(BaseModel):
    """Multiple similar activities grouped together.

    Example: "Alice, Bob, and 3 others liked your post"
    """
    aggregation_key: str
    verb: str
    actors: list[dict[str, str]]       # All actors who performed this activity
    object: dict[str, Any]             # The common target
    count: int = 1
    latest_at: float = 0.0
    summary: str = ""                  # "Alice, Bob, and 3 others liked your post"
    is_read: bool = False

    def build_summary(self) -> str:
        names = [a.get("name", "Someone") for a in self.actors[:2]]
        remaining = self.count - len(names)

        if remaining > 0:
            names_str = ", ".join(names)
            return f"{names_str} and {remaining} others {self._verb_past()} your {self.object.get('type', 'post')}"
        elif len(names) == 2:
            return f"{names[0]} and {names[1]} {self._verb_past()} your {self.object.get('type', 'post')}"
        else:
            return f"{names[0]} {self._verb_past()} your {self.object.get('type', 'post')}"

    def _verb_past(self) -> str:
        return {
            "Like": "liked",
            "Create": "commented on",
            "Announce": "shared",
            "Follow": "followed",
            "Mention": "mentioned you in",
        }.get(self.verb, "interacted with")


class FeedType(str, Enum):
    HOME = "home"                    # Posts from people you follow
    NOTIFICATIONS = "notifications"  # Actions on your content
    PERSONAL = "personal"            # Your own activity log
    MENTIONS = "mentions"            # Posts that @mention you


class ActivityFeedService:
    """Manages multiple feed types with activity fan-out and aggregation."""

    def __init__(self, r: redis.Redis):
        self.redis = r
        self.FEED_MAX_SIZE = 500
        self.AGGREGATION_WINDOW = 3600 * 24  # 24h window for aggregation

    async def publish_activity(self, activity: Activity, audiences: dict[FeedType, list[str]]):
        """Publish an activity to specified feed types and audiences.

        audiences = {
            FeedType.NOTIFICATIONS: ["user:456"],  # Notify post owner
            FeedType.HOME: ["user:789", "user:101"],  # Show in followers' home feeds
            FeedType.PERSONAL: ["user:123"],  # Log in actor's personal feed
        }
        """
        activity_json = activity.model_dump_json()
        activity_key = f"activity:{activity.id}"
        score = time.time()

        # Store activity object
        await self.redis.set(activity_key, activity_json, ex=86400 * 30)

        # Fan out to each feed type
        for feed_type, user_ids in audiences.items():
            async with self.redis.pipeline(transaction=False) as pipe:
                for user_id in user_ids:
                    feed_key = f"feed:{feed_type.value}:{user_id}"
                    await pipe.zadd(feed_key, {activity.id: score})
                    await pipe.zremrangebyrank(feed_key, 0, -(self.FEED_MAX_SIZE + 1))
                await pipe.execute()

        logger.info(
            f"Published activity {activity.id} ({activity.type}) "
            f"to {sum(len(v) for v in audiences.values())} feeds"
        )

    async def get_feed(
        self,
        user_id: str,
        feed_type: FeedType,
        offset: int = 0,
        limit: int = 20,
        aggregate: bool = True,
    ) -> list[AggregatedActivity | Activity]:
        """Retrieve feed with optional activity aggregation."""
        feed_key = f"feed:{feed_type.value}:{user_id}"

        # Over-fetch for aggregation
        fetch_limit = limit * 3 if aggregate else limit
        activity_ids = await self.redis.zrevrange(
            feed_key, offset, offset + fetch_limit - 1, withscores=True
        )

        if not activity_ids:
            return []

        # Fetch activity objects
        keys = [f"activity:{aid.decode()}" for aid, _ in activity_ids]
        raw_activities = await self.redis.mget(keys)

        activities = []
        for raw, (_, score) in zip(raw_activities, activity_ids):
            if raw:
                act = Activity.model_validate_json(raw)
                act._score = score
                activities.append(act)

        if not aggregate:
            return activities[:limit]

        # Aggregate similar activities
        return self._aggregate_activities(activities, limit)

    def _aggregate_activities(
        self, activities: list[Activity], limit: int
    ) -> list[AggregatedActivity]:
        """Group activities by (verb, object) within aggregation window."""
        groups: dict[str, AggregatedActivity] = {}
        now = time.time()

        for activity in activities:
            key = activity._aggregation_key

            if key in groups:
                group = groups[key]
                # Only aggregate within time window
                if now - group.latest_at < self.AGGREGATION_WINDOW:
                    group.actors.append(activity.actor)
                    group.count += 1
                    group.latest_at = max(group.latest_at, activity._score)
                    continue

            groups[key] = AggregatedActivity(
                aggregation_key=key,
                verb=activity.type,
                actors=[activity.actor],
                object=activity.object,
                count=1,
                latest_at=activity._score,
            )

        # Build summaries and sort by recency
        result = list(groups.values())
        for agg in result:
            agg.summary = agg.build_summary()
        result.sort(key=lambda a: a.latest_at, reverse=True)

        return result[:limit]

    async def mark_read(self, user_id: str, feed_type: FeedType, up_to_time: float | None = None):
        """Mark all notifications up to a timestamp as read."""
        read_key = f"feed_read:{feed_type.value}:{user_id}"
        timestamp = up_to_time or time.time()
        await self.redis.set(read_key, str(timestamp))

    async def get_unread_count(self, user_id: str, feed_type: FeedType) -> int:
        """Count unread items since last read timestamp."""
        read_key = f"feed_read:{feed_type.value}:{user_id}"
        feed_key = f"feed:{feed_type.value}:{user_id}"

        last_read = await self.redis.get(read_key)
        if last_read is None:
            return await self.redis.zcard(feed_key)

        return await self.redis.zcount(feed_key, float(last_read), "+inf")


# ============================================================
# Helper: Create activities from common social actions
# ============================================================

class ActivityFactory:
    """Convenience methods for creating common activity types."""

    @staticmethod
    def like(actor_id: str, actor_name: str, post_id: str, post_owner_id: str) -> tuple[Activity, dict]:
        activity = Activity(
            type=ActivityVerb.LIKE.value,
            actor={"type": "Person", "id": actor_id, "name": actor_name},
            object={"type": "Note", "id": post_id},
            summary=f"{actor_name} liked a post",
        )
        audiences = {
            FeedType.NOTIFICATIONS: [post_owner_id],
            FeedType.PERSONAL: [actor_id],
        }
        return activity, audiences

    @staticmethod
    def comment(
        actor_id: str, actor_name: str,
        comment_id: str, post_id: str, post_owner_id: str,
    ) -> tuple[Activity, dict]:
        activity = Activity(
            type=ActivityVerb.COMMENT.value,
            actor={"type": "Person", "id": actor_id, "name": actor_name},
            object={"type": "Note", "id": comment_id, "inReplyTo": post_id},
            summary=f"{actor_name} commented on a post",
        )
        audiences = {
            FeedType.NOTIFICATIONS: [post_owner_id],
            FeedType.PERSONAL: [actor_id],
        }
        return activity, audiences

    @staticmethod
    def follow(actor_id: str, actor_name: str, target_id: str) -> tuple[Activity, dict]:
        activity = Activity(
            type=ActivityVerb.FOLLOW.value,
            actor={"type": "Person", "id": actor_id, "name": actor_name},
            object={"type": "Person", "id": target_id},
            summary=f"{actor_name} followed you",
        )
        audiences = {
            FeedType.NOTIFICATIONS: [target_id],
            FeedType.PERSONAL: [actor_id],
        }
        return activity, audiences
```

| Feed Type | Content | Fan-out | Aggregation |
|---|---|---|---|
| Home | Posts from following | On-write (normal) / on-read (celebrity) | None |
| Notifications | Actions on your content | On-write (always small audience) | Yes (likes, follows) |
| Personal | Your own actions log | On-write (single user) | Optional |
| Mentions | Posts @mentioning you | On-write (single user) | None |

Aggregation example:
```
Raw:  Alice liked post, Bob liked post, Charlie liked post, Dave liked post
      |
  Aggregated: "Alice, Bob, and 2 others liked your post"
      (aggregation_key = "Like:post:123", count = 4)
```

Key Activity Streams patterns:
- W3C Activity Streams 2.0 vocabulary (Create, Like, Announce, Follow)
- Aggregation groups by (verb, object_id) within a 24h window
- Separate feeds per type avoids mixing notifications with content
- Unread count uses a watermark timestamp (not per-item read flags)
- Activity objects are stored separately and referenced by ID (space efficient)
- Over-fetch during aggregation ensures enough items after grouping
'''
    ),
]
