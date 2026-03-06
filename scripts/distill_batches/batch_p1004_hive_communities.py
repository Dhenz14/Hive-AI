"""Hive blockchain training pairs: communities and Hivemind."""

PAIRS = [
    (
        "hive/community-creation",
        r'''How do I create and configure a Hive community? What are the steps and costs involved?''',
        r'''Creating a Hive community requires creating a special account (with the "hive-" prefix) and then broadcasting community setup operations via custom_json. Here is the process:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json, Account_create
from beemgraphenebase.account import PasswordKey
import json
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey", "5YourPostingKey"]
)

CREATOR = "myaccount"

def create_community(community_title, description, is_nsfw=False):
    """Create a Hive community.

    Community accounts use the pattern hive-NNNNNN where NNNNNN
    is derived from the account creation order. In practice,
    most communities are created through front-ends like PeakD
    which handle the account naming.
    """
    # Step 1: The community account must be created first
    # The naming convention is hive-NNNNNN (6 digits)
    # Front-ends typically handle this, but programmatically:

    # After the community account exists, configure it:
    # Step 2: Set community properties
    update_payload = ["updateProps", {
        "community": "hive-123456",  # Your community account
        "props": {
            "title": community_title,
            "about": description[:120],
            "description": description,
            "lang": "en",
            "is_nsfw": is_nsfw,
            "flag_text": "This content violates community rules",
        }
    }]

    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [CREATOR],
        "id": "community",
        "json": json.dumps(update_payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(CREATOR, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Community properties updated: {result['id']}")
    return result

def get_community_info(community_name):
    """Get detailed community information."""
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.get_community",
        "params": {
            "name": community_name,
            "observer": ""
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    community = resp.json().get("result", {})

    if community:
        print(f"Community: {community.get('title', 'N/A')}")
        print(f"  Name:        {community.get('name', 'N/A')}")
        print(f"  About:       {community.get('about', 'N/A')}")
        print(f"  Subscribers: {community.get('subscribers', 0)}")
        print(f"  Posts:       {community.get('num_pending', 0)}")
        print(f"  Authors:     {community.get('num_authors', 0)}")
        print(f"  Created:     {community.get('created_at', 'N/A')}")
        print(f"  NSFW:        {community.get('is_nsfw', False)}")
        print(f"  Type:        {community.get('type_id', 0)}")
        # type_id: 1=topic, 2=journal, 3=council

        team = community.get("team", [])
        if team:
            print(f"  Team:")
            for member in team:
                print(f"    @{member[0]}: {member[1]} - {member[2]}")

    return community

def search_communities(query, limit=10):
    """Search for communities by keyword."""
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.list_communities",
        "params": {
            "last": "",
            "limit": limit,
            "query": query,
            "sort": "rank",
            "observer": ""
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    communities = resp.json().get("result", [])

    for c in communities:
        subs = c.get("subscribers", 0)
        print(f"  {c['name']:20s} {c.get('title', ''):30s} ({subs} subs)")

    return communities

# Usage
get_community_info("hive-163521")
search_communities("programming")
```

Community types on Hive:
- Topic (1): Open community where anyone can post
- Journal (2): Only the owner can post (like a personal blog community)
- Council (3): Only admins and mods can post

Communities are indexed by Hivemind, not by the base layer consensus. This means community rules (muting, pinning) are enforced at the API/front-end level, not at the blockchain consensus level.
'''
    ),
    (
        "hive/community-role-management",
        r'''How do I manage roles in a Hive community? Show me how to set mods, admins, mute users, and pin posts.''',
        r'''Community management on Hive is done through custom_json operations with the "community" id. Here are all the management operations:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourPostingKey"]
)

ADMIN_ACCOUNT = "myaccount"
COMMUNITY = "hive-163521"

def community_action(action, data):
    """Generic community action broadcaster."""
    payload = [action, data]
    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [ADMIN_ACCOUNT],
        "id": "community",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ADMIN_ACCOUNT, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Community action '{action}': {result['id']}")
    return result

# Role management
def set_role(account, role):
    """Set a user's role in the community.

    Roles (hierarchical):
    - muted: Cannot post in the community
    - guest: Default role, can post and comment
    - member: Recognized member (no extra permissions yet)
    - mod: Can mute users, pin posts, set member roles
    - admin: Can set mod roles, update community properties
    - owner: Full control, can set admin roles
    """
    return community_action("setRole", {
        "community": COMMUNITY,
        "account": account,
        "role": role
    })

def set_user_title(account, title):
    """Set a custom title for a user in the community."""
    return community_action("setUserTitle", {
        "community": COMMUNITY,
        "account": account,
        "title": title  # e.g., "Top Contributor", "Core Developer"
    })

# Content moderation
def mute_post(author, permlink, notes=""):
    """Mute (hide) a post in the community."""
    return community_action("mutePost", {
        "community": COMMUNITY,
        "account": author,
        "permlink": permlink,
        "notes": notes
    })

def unmute_post(author, permlink, notes=""):
    """Unmute a previously muted post."""
    return community_action("unmutePost", {
        "community": COMMUNITY,
        "account": author,
        "permlink": permlink,
        "notes": notes
    })

def pin_post(author, permlink):
    """Pin a post to the top of the community feed."""
    return community_action("pinPost", {
        "community": COMMUNITY,
        "account": author,
        "permlink": permlink
    })

def unpin_post(author, permlink):
    """Unpin a previously pinned post."""
    return community_action("unpinPost", {
        "community": COMMUNITY,
        "account": author,
        "permlink": permlink
    })

# Subscription management
def subscribe(community_name):
    """Subscribe to a community."""
    return community_action("subscribe", {
        "community": community_name
    })

def unsubscribe(community_name):
    """Unsubscribe from a community."""
    return community_action("unsubscribe", {
        "community": community_name
    })

# Query community members and roles
def get_community_subscribers(community_name, limit=100):
    """Get community subscribers."""
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.list_subscribers",
        "params": {
            "community": community_name,
            "last": "",
            "limit": limit
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    subs = resp.json().get("result", [])

    print(f"Subscribers of {community_name} ({len(subs)}):")
    for s in subs[:20]:
        # Each entry: [account, role, title, created]
        print(f"  @{s[0]:20s} role={s[1]:8s} title='{s[2]}' since {s[3]}")

    return subs

# Usage
# set_role("newmod", "mod")
# set_role("spammer", "muted")
# set_user_title("contributor1", "Core Developer")
# pin_post("goodauthor", "great-post")
# mute_post("spammer", "spam-post", notes="Spam content")
get_community_subscribers(COMMUNITY)
```

Role permissions hierarchy:
- owner: Can do everything, including setting admins
- admin: Can set mods, update properties, all mod powers
- mod: Can mute/unmute posts, mute users, pin/unpin posts, set member roles
- member: No extra permissions (cosmetic role)
- guest: Default role, can post and comment
- muted: Cannot post in the community (posts hidden by front-ends)
'''
    ),
    (
        "hive/community-muting-moderation",
        r'''How does content moderation work in Hive communities? How do I build an automated moderation bot?''',
        r'''Community moderation on Hive is handled at the Hivemind layer through custom_json operations. Here is how to build an automated moderation bot:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import re
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("modbot")

class CommunityModBot:
    def __init__(self, mod_account, posting_key, community, nodes=None):
        self.account = mod_account
        self.community = community
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog"],
            keys=[posting_key]
        )
        self.spam_patterns = []
        self.banned_domains = set()
        self.min_reputation = -1
        self.min_body_length = 50
        self.max_tags = 10

    def add_spam_pattern(self, pattern):
        """Add a regex pattern to detect spam."""
        self.spam_patterns.append(re.compile(pattern, re.IGNORECASE))

    def add_banned_domain(self, domain):
        """Ban links from a specific domain."""
        self.banned_domains.add(domain.lower())

    def _mute_post(self, author, permlink, reason):
        """Mute a post in the community."""
        payload = ["mutePost", {
            "community": self.community,
            "account": author,
            "permlink": permlink,
            "notes": f"Auto-mod: {reason}"
        }]
        op = Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [self.account],
            "id": "community",
            "json": json.dumps(payload)
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "posting")
        tx.sign()
        result = tx.broadcast()
        logger.warning(f"MUTED @{author}/{permlink}: {reason}")
        return result

    def check_post(self, op_data):
        """Check a post against moderation rules.

        Returns (should_mute, reason) tuple.
        """
        author = op_data.get("author", "")
        body = op_data.get("body", "")
        title = op_data.get("title", "")
        parent_permlink = op_data.get("parent_permlink", "")

        # Only moderate posts in our community
        if parent_permlink != self.community:
            return False, ""

        # Check body length
        if len(body.strip()) < self.min_body_length:
            return True, f"Post too short ({len(body)} chars, min {self.min_body_length})"

        # Check spam patterns
        full_text = f"{title} {body}"
        for pattern in self.spam_patterns:
            if pattern.search(full_text):
                return True, f"Spam pattern detected: {pattern.pattern}"

        # Check banned domains
        url_pattern = re.compile(r'https?://([^\s/]+)')
        domains = url_pattern.findall(body)
        for domain in domains:
            domain_lower = domain.lower()
            for banned in self.banned_domains:
                if banned in domain_lower:
                    return True, f"Banned domain: {domain}"

        # Check tag count
        try:
            metadata = json.loads(op_data.get("json_metadata", "{}"))
            tags = metadata.get("tags", [])
            if len(tags) > self.max_tags:
                return True, f"Too many tags ({len(tags)}, max {self.max_tags})"
        except (json.JSONDecodeError, TypeError):
            pass

        return False, ""

    def run(self):
        """Run the moderation bot."""
        blockchain = Blockchain(hive_instance=self.hive)
        logger.info(f"Mod bot started for {self.community} as @{self.account}")

        stream = blockchain.stream(
            opNames=["comment"],
            raw_ops=False,
            threading=False
        )

        for op in stream:
            # Only check root posts (not comments)
            if op.get("parent_author", ""):
                continue

            should_mute, reason = self.check_post(op)
            if should_mute:
                author = op.get("author", "")
                permlink = op.get("permlink", "")
                try:
                    self._mute_post(author, permlink, reason)
                except Exception as e:
                    logger.error(f"Failed to mute: {e}")
            else:
                author = op.get("author", "")
                if op.get("parent_permlink") == self.community:
                    logger.info(f"Post OK: @{author}/{op.get('permlink', '')[:30]}")

# Configure and run
bot = CommunityModBot(
    mod_account="communitymod",
    posting_key="5ModPostingKey",
    community="hive-163521"
)

# Add moderation rules
bot.add_spam_pattern(r"free\s+bitcoin|earn\s+\$\d+\s+daily")
bot.add_spam_pattern(r"click\s+here\s+to\s+win")
bot.add_banned_domain("scam-site.com")
bot.min_body_length = 100
bot.max_tags = 8

# bot.run()
```

Moderation on Hive is advisory, not censoring. Muted posts are hidden by front-ends that respect Hivemind, but the content remains on the blockchain. Users can always view muted content through block explorers or non-Hivemind API endpoints. The mod bot account must have at least the "mod" role in the community.
'''
    ),
    (
        "hive/community-settings",
        r'''How do I update community settings and properties on Hive? What settings are available?''',
        r'''Community properties on Hive are updated through the "updateProps" custom_json operation. Here are all available settings and how to manage them:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5AdminPostingKey"]
)

ADMIN = "communityadmin"
COMMUNITY = "hive-163521"

def update_community_props(props):
    """Update community properties.

    Available properties:
    - title: Display name (max 20 chars)
    - about: Short description (max 120 chars)
    - description: Full description (max 5000 chars)
    - lang: Language code (e.g., "en", "es", "ko")
    - is_nsfw: Boolean, mark as NSFW
    - flag_text: Custom text shown when reporting content
    """
    payload = ["updateProps", {
        "community": COMMUNITY,
        "props": props
    }]

    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [ADMIN],
        "id": "community",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ADMIN, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Community properties updated: {result['id']}")
    return result

def set_community_title(title):
    """Update the community display title."""
    return update_community_props({"title": title[:20]})

def set_community_description(about, description):
    """Update community descriptions."""
    return update_community_props({
        "about": about[:120],
        "description": description[:5000]
    })

def set_community_language(lang_code):
    """Set community language."""
    return update_community_props({"lang": lang_code})

def toggle_nsfw(is_nsfw):
    """Toggle NSFW flag on community."""
    return update_community_props({"is_nsfw": is_nsfw})

def set_flag_text(text):
    """Set custom flag/report text."""
    return update_community_props({"flag_text": text})

def get_all_community_settings(community_name):
    """Retrieve all current community settings."""
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.get_community",
        "params": {
            "name": community_name,
            "observer": ""
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    community = resp.json().get("result", {})

    if not community:
        print(f"Community {community_name} not found")
        return None

    print(f"=== Settings for {community_name} ===")
    settings = {
        "title": community.get("title", ""),
        "about": community.get("about", ""),
        "description": community.get("description", ""),
        "lang": community.get("lang", "en"),
        "is_nsfw": community.get("is_nsfw", False),
        "flag_text": community.get("flag_text", ""),
        "type_id": community.get("type_id", 1),
        "subscribers": community.get("subscribers", 0),
        "num_pending": community.get("num_pending", 0),
        "num_authors": community.get("num_authors", 0),
        "created_at": community.get("created_at", ""),
        "avatar_url": community.get("avatar_url", ""),
    }

    for key, value in settings.items():
        print(f"  {key:20s}: {value}")

    # Show team/roles
    team = community.get("team", [])
    if team:
        print(f"\n  Team ({len(team)} members):")
        for member in team:
            acct, role, title = member[0], member[1], member[2]
            print(f"    @{acct:20s} {role:8s} '{title}'")

    return settings

def bulk_setup_community(title, about, description, lang="en",
                          mods=None, rules_text=""):
    """Complete community setup in one go."""
    # Update properties
    props = {
        "title": title[:20],
        "about": about[:120],
        "description": description[:5000],
        "lang": lang,
        "is_nsfw": False,
        "flag_text": rules_text or "Content violates community guidelines"
    }
    update_community_props(props)

    # Set moderators
    if mods:
        for mod_account in mods:
            payload = ["setRole", {
                "community": COMMUNITY,
                "account": mod_account,
                "role": "mod"
            }]
            op = Custom_json(**{
                "required_auths": [],
                "required_posting_auths": [ADMIN],
                "id": "community",
                "json": json.dumps(payload)
            })
            tx = TransactionBuilder(hive_instance=hive)
            tx.appendOps(op)
            tx.appendSigner(ADMIN, "posting")
            tx.sign()
            tx.broadcast()
            print(f"Set @{mod_account} as mod")

# Usage
get_all_community_settings("hive-163521")

# bulk_setup_community(
#     title="Hive Developers",
#     about="Community for Hive blockchain developers",
#     description="A community dedicated to...",
#     mods=["moduser1", "moduser2"],
#     rules_text="Be respectful, stay on topic"
# )
```

Important notes:
- Only admins and owners can update community properties
- Changes are processed by Hivemind and reflected on front-ends
- The community type (topic/journal/council) is set at creation and cannot be changed
- Avatar and banner images are set through the community account's profile metadata
- All community operations use the posting key, not the active key
'''
    ),
    (
        "hive/community-scoped-queries",
        r'''How do I query posts, members, and activity within a specific Hive community using the bridge API?''',
        r'''The bridge API (Hivemind) provides community-scoped queries for posts, members, and notifications. Here is a comprehensive guide:

```python
import requests
import json
from datetime import datetime

API_NODE = "https://api.hive.blog"

def bridge_call(method, params):
    """Make a bridge API call."""
    payload = {
        "jsonrpc": "2.0",
        "method": f"bridge.{method}",
        "params": params,
        "id": 1
    }
    resp = requests.post(API_NODE, json=payload, timeout=15)
    return resp.json().get("result", None)

# 1. Get community posts with different sort orders
def get_community_posts(community, sort="created", limit=20, observer=""):
    """Get posts from a community.

    Sort options: created, trending, hot, promoted, payout, muted
    """
    result = bridge_call("get_ranked_posts", {
        "sort": sort,
        "tag": community,
        "limit": limit,
        "observer": observer
    })

    if result:
        print(f"\n{community} posts (sorted by {sort}):")
        for post in result:
            author = post["author"]
            title = post.get("title", "")[:50]
            payout = post.get("payout", 0)
            votes = post.get("stats", {}).get("total_votes", 0)
            created = post.get("created", "")[:10]
            print(f"  [{created}] @{author}: {title} "
                  f"(${payout:.2f}, {votes} votes)")
    return result

# 2. Get community subscribers with roles
def get_subscribers(community, limit=100):
    """Get community subscribers."""
    result = bridge_call("list_subscribers", {
        "community": community,
        "last": "",
        "limit": limit
    })

    if result:
        roles = {}
        for entry in result:
            # [account, role, title, created_at]
            role = entry[1]
            roles[role] = roles.get(role, 0) + 1

        print(f"\nSubscribers of {community}: {len(result)}")
        print(f"Role distribution: {json.dumps(roles)}")
    return result

# 3. Get community notifications
def get_community_notifications(account, community=None, limit=50):
    """Get notifications for community activity."""
    params = {
        "account": account,
        "limit": limit
    }
    result = bridge_call("account_notifications", params)

    if result:
        community_notifs = []
        for n in result:
            if community and n.get("community", "") != community:
                continue
            community_notifs.append(n)
            ntype = n.get("type", "")
            msg = n.get("msg", "")
            ts = n.get("date", "")
            print(f"  [{ts}] {ntype}: {msg}")

        return community_notifs
    return []

# 4. Search within a community
def search_community_posts(community, query, limit=20):
    """Search for posts within a community by content."""
    # Note: bridge does not have a direct search API.
    # Fetch recent posts and filter client-side.
    all_posts = []
    for sort in ["created", "trending"]:
        posts = bridge_call("get_ranked_posts", {
            "sort": sort,
            "tag": community,
            "limit": 50,
            "observer": ""
        }) or []
        all_posts.extend(posts)

    # Deduplicate
    seen = set()
    unique = []
    for p in all_posts:
        key = f"{p['author']}/{p['permlink']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Filter by query
    query_lower = query.lower()
    matches = [
        p for p in unique
        if query_lower in p.get("title", "").lower()
        or query_lower in p.get("body", "").lower()
    ]

    print(f"\nSearch '{query}' in {community}: {len(matches)} results")
    for p in matches[:limit]:
        print(f"  @{p['author']}: {p.get('title', '')[:60]}")

    return matches

# 5. Get community stats over time
def community_activity_summary(community):
    """Summarize recent community activity."""
    # Get recent posts
    recent = bridge_call("get_ranked_posts", {
        "sort": "created",
        "tag": community,
        "limit": 50,
        "observer": ""
    }) or []

    # Get community info
    info = bridge_call("get_community", {
        "name": community,
        "observer": ""
    })

    if info:
        print(f"\n=== {info.get('title', community)} Activity ===")
        print(f"Subscribers: {info.get('subscribers', 0)}")
        print(f"Active authors: {info.get('num_authors', 0)}")
        print(f"Pending posts: {info.get('num_pending', 0)}")

    # Analyze recent posts
    if recent:
        total_payout = sum(p.get("payout", 0) for p in recent)
        total_votes = sum(
            p.get("stats", {}).get("total_votes", 0) for p in recent
        )
        unique_authors = len(set(p["author"] for p in recent))
        avg_payout = total_payout / len(recent) if recent else 0

        print(f"\nLast {len(recent)} posts:")
        print(f"  Unique authors: {unique_authors}")
        print(f"  Total payout:   ${total_payout:.2f}")
        print(f"  Avg payout:     ${avg_payout:.2f}")
        print(f"  Total votes:    {total_votes}")

# Usage
get_community_posts("hive-163521", sort="trending")
get_subscribers("hive-163521", limit=50)
community_activity_summary("hive-163521")
```

The bridge API is the primary way to query community-scoped data on Hive. It is served by Hivemind nodes and provides social-layer queries that the base blockchain API does not support (like community filtering, trending algorithms, and notification feeds).
'''
    ),
]
