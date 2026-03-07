"""
Hive blockchain thinking pairs - community feature reasoning
"""

pairs = [
    {
        "instruction": r'''I want to build a moderation system for a Hive community. How do community roles work on Hive and how should I structure the moderation architecture?''',
        "output": r'''<think>
Hive communities have a built-in role system. Let me think through how it works and what moderation capabilities each role has.

The role hierarchy on Hive communities is:
- Owner: created the community, full control
- Admin: can manage roles, settings, and moderate
- Mod: can mute/unmute posts and users
- Member: can post (if community requires membership)
- Guest: default, can post in open communities

Muting on Hive is important to understand. When a mod "mutes" a post in a community, the post is not deleted from the blockchain (nothing can be deleted from the blockchain). Instead, the community front-end hides it. The mute is recorded as a custom_json operation.

Hmm, wait -- the muting mechanism works through the community layer, which is implemented via the hivemind indexer. Hivemind processes community-related custom_json operations and maintains the community state. So muting is only effective on front-ends that use hivemind.

I initially thought I could build moderation purely with custom_json, but actually community operations use the "community" operation type in hivemind. Let me think about what operations are available:

- setRole: assign roles to accounts
- updateProps: change community settings
- mutePost: hide a post from community feed
- unmutePost: restore a hidden post
- pinPost: pin a post to the top
- unpinPost: unpin a post
- flagPost: report a post for review

The tradeoff is: use the built-in community system (standard, supported by all front-ends like PeakD and Ecency) vs build a custom moderation system with custom_json (more flexible but not recognized by standard front-ends).

For most use cases, the built-in system is sufficient. Custom systems make sense when you need features like automated moderation, appeal processes, or multi-level approval workflows.
</think>

Use Hive's built-in community system for standard moderation and layer custom logic on top for advanced features:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import time

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

COMMUNITY = "hive-123456"  # community name (hive-XXXXXX format)
MOD_ACCOUNT = "communitymod"


# === Built-in Community Operations ===
# These are recognized by hivemind and all standard front-ends

def community_op(account, action, data):
    """Broadcast a community operation via custom_json."""
    payload = [
        "community",      # operation type for hivemind
        {
            "community": COMMUNITY,
            "action": action,
            **data
        }
    ]
    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [account],
        "id": "community",
        "json": json.dumps(payload)
    }))
    tx.appendSigner(account, "posting")
    tx.sign()
    return tx.broadcast()


def set_role(admin_account, target_account, role):
    """Assign a role in the community.

    Roles: owner, admin, mod, member, guest, muted
    Requires: admin or owner role
    """
    return community_op(admin_account, "setRole", {
        "account": target_account,
        "role": role
    })


def mute_post(mod_account, author, permlink, notes=""):
    """Mute (hide) a post from the community feed.

    The post still exists on-chain but is hidden by hivemind.
    Requires: mod, admin, or owner role
    """
    return community_op(mod_account, "mutePost", {
        "account": author,
        "permlink": permlink,
        "notes": notes
    })


def unmute_post(mod_account, author, permlink):
    """Restore a muted post to the community feed."""
    return community_op(mod_account, "unmutePost", {
        "account": author,
        "permlink": permlink
    })


def pin_post(mod_account, author, permlink):
    """Pin a post to the top of the community feed."""
    return community_op(mod_account, "pinPost", {
        "account": author,
        "permlink": permlink
    })


def update_community_props(owner_account, title=None, about=None,
                            description=None, flag_text=None,
                            is_nsfw=None):
    """Update community settings. Requires owner role."""
    props = {}
    if title is not None:
        props["title"] = title
    if about is not None:
        props["about"] = about
    if description is not None:
        props["description"] = description
    if flag_text is not None:
        props["flag_text"] = flag_text
    if is_nsfw is not None:
        props["is_nsfw"] = is_nsfw

    return community_op(owner_account, "updateProps", {
        "props": props
    })


# === Advanced: Automated Moderation Layer ===

class AutoModerator:
    """Automated moderation on top of the built-in community system."""

    def __init__(self, mod_account, community, blockchain_instance):
        self.mod_account = mod_account
        self.community = community
        self.hive = blockchain_instance

        # Configurable rules
        self.banned_words = set()
        self.min_reputation = 15
        self.min_body_length = 100
        self.max_links = 10
        self.require_tag = None  # optional required tag

        # Moderation log
        self.actions_log = []

    def check_post(self, author, permlink, body, json_metadata_str):
        """Evaluate a post against moderation rules."""
        violations = []

        # Rule 1: Banned words
        body_lower = body.lower()
        for word in self.banned_words:
            if word.lower() in body_lower:
                violations.append(f"banned_word:{word}")

        # Rule 2: Minimum length
        if len(body.split()) < self.min_body_length:
            violations.append(f"too_short:{len(body.split())}_words")

        # Rule 3: Excessive links (spam indicator)
        link_count = body.count("http://") + body.count("https://")
        if link_count > self.max_links:
            violations.append(f"too_many_links:{link_count}")

        # Rule 4: Required tag
        if self.require_tag:
            try:
                meta = json.loads(json_metadata_str or "{}")
                tags = meta.get("tags", [])
                if self.require_tag not in tags:
                    violations.append(f"missing_tag:{self.require_tag}")
            except json.JSONDecodeError:
                pass

        return violations

    def moderate(self, author, permlink, body, json_metadata_str):
        """Check and auto-moderate a post."""
        violations = self.check_post(
            author, permlink, body, json_metadata_str
        )

        if not violations:
            return {"action": "approved", "violations": []}

        notes = f"Auto-mod: {', '.join(violations)}"

        # Mute the post
        try:
            mute_post(self.mod_account, author, permlink, notes)
            action = {
                "action": "muted",
                "author": author,
                "permlink": permlink,
                "violations": violations,
                "timestamp": time.time()
            }
            self.actions_log.append(action)
            print(f"Auto-muted @{author}/{permlink}: {notes}")
            return action
        except Exception as e:
            print(f"Auto-mute failed: {e}")
            return {"action": "error", "error": str(e)}


# === Usage ===

# Set up community roles
set_role("communityowner", "trusted-user", "mod")
set_role("communityowner", "new-mod", "mod")

# Moderate a post
mute_post(MOD_ACCOUNT, "spammer123", "buy-cheap-tokens",
          "Spam content - commercial promotion")

# Auto-moderation
automod = AutoModerator(MOD_ACCOUNT, COMMUNITY, hive)
automod.banned_words = {"free bitcoin", "guaranteed returns"}
automod.min_body_length = 50
```

Architecture notes: built-in community operations are processed by hivemind and respected by all standard front-ends (PeakD, Ecency, Hive.blog). Muting hides posts from community feeds but does not delete them from the blockchain. For automated moderation, stream community posts and apply rules, then use the standard mute operation for enforcement.'''
    },
    {
        "instruction": r'''How should I implement role-based access control for a Hive community app that has custom permissions beyond the standard Hive community roles?''',
        "output": r'''<think>
The built-in Hive community roles are limited: owner, admin, mod, member, guest, muted. If the app needs more granular permissions (e.g., "can pin but not mute", "can approve new members but not change settings", "can manage contests but not moderate"), I need a custom RBAC system.

The question is where to store and enforce these custom roles. Options:

1. On-chain via custom_json: store role assignments as custom_json operations. The app's indexer reads them and enforces permissions. Fully transparent and auditable.

2. Off-chain database: store roles in a traditional database. Faster queries but centralized.

3. Hybrid: on-chain role assignments (for transparency), off-chain permission evaluation (for speed).

Hmm, I think option 3 is best. Role changes should be on-chain so they are auditable and trustworthy. But checking permissions on every request should hit a local database for speed.

I initially thought about mapping everything to the existing Hive community roles, but they are too coarse-grained. A custom system gives us fine-grained permissions like "can_pin_posts", "can_approve_members", "can_manage_treasury".

The tradeoff is complexity vs flexibility. A simple role system with 3-4 predefined roles is easy to understand. A full permission-based system where each role has configurable permissions is more flexible but harder to manage.

Actually, I think the best approach is a role-based system where roles are predefined but have specific permission sets. So "content_moderator" has {mute_posts, pin_posts}, "community_manager" has {approve_members, manage_settings}, etc. This is simpler than per-user permission assignment.

For enforcement, the app server checks the user's role before executing actions. But since blockchain operations are permissionless (anyone can broadcast custom_json), the indexer also needs to verify the broadcaster had the right role at the time of the operation.
</think>

Build a custom RBAC system using custom_json for transparent role assignments and an indexer for permission enforcement:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import time
from enum import Flag, auto
from collections import defaultdict

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

APP_ID = "myapp_rbac"
COMMUNITY = "hive-123456"


# === Permission Definitions ===

class Permission(Flag):
    """Fine-grained permissions as bit flags."""
    NONE = 0
    VIEW_CONTENT = auto()
    POST_CONTENT = auto()
    MUTE_POSTS = auto()
    PIN_POSTS = auto()
    APPROVE_MEMBERS = auto()
    MANAGE_CONTESTS = auto()
    MANAGE_SETTINGS = auto()
    MANAGE_ROLES = auto()
    MANAGE_TREASURY = auto()
    ALL = (VIEW_CONTENT | POST_CONTENT | MUTE_POSTS | PIN_POSTS |
           APPROVE_MEMBERS | MANAGE_CONTESTS | MANAGE_SETTINGS |
           MANAGE_ROLES | MANAGE_TREASURY)


# Predefined roles with specific permission sets
ROLE_PERMISSIONS = {
    "owner": Permission.ALL,
    "admin": (Permission.VIEW_CONTENT | Permission.POST_CONTENT |
              Permission.MUTE_POSTS | Permission.PIN_POSTS |
              Permission.APPROVE_MEMBERS | Permission.MANAGE_CONTESTS |
              Permission.MANAGE_SETTINGS | Permission.MANAGE_ROLES),
    "content_mod": (Permission.VIEW_CONTENT | Permission.POST_CONTENT |
                    Permission.MUTE_POSTS | Permission.PIN_POSTS),
    "contest_mgr": (Permission.VIEW_CONTENT | Permission.POST_CONTENT |
                    Permission.MANAGE_CONTESTS),
    "treasurer": (Permission.VIEW_CONTENT | Permission.POST_CONTENT |
                  Permission.MANAGE_TREASURY),
    "member": (Permission.VIEW_CONTENT | Permission.POST_CONTENT),
    "guest": Permission.VIEW_CONTENT,
}


# === On-Chain Role Management ===

def assign_role(assigner, target_account, role):
    """Assign a role via on-chain custom_json.

    Transparent and auditable -- anyone can verify role assignments.
    """
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Invalid role: {role}. "
                        f"Valid: {list(ROLE_PERMISSIONS.keys())}")

    payload = {
        "v": 1,
        "action": "assign_role",
        "community": COMMUNITY,
        "target": target_account,
        "role": role,
        "ts": int(time.time())
    }

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [assigner],
        "id": APP_ID,
        "json": json.dumps(payload, separators=(",", ":"))
    }))
    tx.appendSigner(assigner, "posting")
    tx.sign()
    return tx.broadcast()


def revoke_role(assigner, target_account):
    """Revoke all roles from an account."""
    payload = {
        "v": 1,
        "action": "revoke_role",
        "community": COMMUNITY,
        "target": target_account,
        "ts": int(time.time())
    }

    tx = TransactionBuilder(blockchain_instance=hive)
    tx.appendOps(Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [assigner],
        "id": APP_ID,
        "json": json.dumps(payload, separators=(",", ":"))
    }))
    tx.appendSigner(assigner, "posting")
    tx.sign()
    return tx.broadcast()


# === Permission Enforcement (Indexer Side) ===

class RBACManager:
    """Manage roles and check permissions."""

    def __init__(self, owner_account):
        self.owner = owner_account
        # account -> role name
        self.roles = {owner_account: "owner"}

    def process_role_operation(self, op_data, broadcaster):
        """Process a role assignment from the blockchain.

        Validates that the broadcaster has permission to assign roles.
        """
        data = json.loads(op_data["json"])
        action = data.get("action")

        if action == "assign_role":
            target = data["target"]
            role = data["role"]

            # Check: does the broadcaster have MANAGE_ROLES permission?
            if not self.has_permission(broadcaster, Permission.MANAGE_ROLES):
                print(f"REJECTED: @{broadcaster} cannot assign roles")
                return False

            # Check: cannot assign role higher than your own
            broadcaster_role = self.roles.get(broadcaster, "guest")
            role_hierarchy = list(ROLE_PERMISSIONS.keys())
            if (role_hierarchy.index(role) <
                    role_hierarchy.index(broadcaster_role)):
                print(f"REJECTED: @{broadcaster} cannot assign "
                      f"role '{role}' (higher than own)")
                return False

            self.roles[target] = role
            print(f"Role assigned: @{target} -> {role} "
                  f"(by @{broadcaster})")
            return True

        elif action == "revoke_role":
            target = data["target"]
            if not self.has_permission(broadcaster, Permission.MANAGE_ROLES):
                return False
            if target == self.owner:
                print("REJECTED: Cannot revoke owner role")
                return False
            self.roles.pop(target, None)
            return True

        return False

    def get_role(self, account):
        """Get an account's role."""
        return self.roles.get(account, "guest")

    def get_permissions(self, account):
        """Get an account's permission set."""
        role = self.get_role(account)
        return ROLE_PERMISSIONS.get(role, Permission.NONE)

    def has_permission(self, account, permission):
        """Check if an account has a specific permission."""
        user_perms = self.get_permissions(account)
        return bool(user_perms & permission)

    def require_permission(self, account, permission, action_desc=""):
        """Raise error if account lacks permission."""
        if not self.has_permission(account, permission):
            role = self.get_role(account)
            raise PermissionError(
                f"@{account} (role: {role}) lacks permission "
                f"'{permission.name}' for: {action_desc}"
            )


# === Usage in App Logic ===

rbac = RBACManager(owner_account="communityowner")

# Owner assigns roles
assign_role("communityowner", "alice", "content_mod")
assign_role("communityowner", "bob", "treasurer")

# Indexer processes the operations and updates local state
rbac.roles["alice"] = "content_mod"
rbac.roles["bob"] = "treasurer"

# Permission checks in app endpoints
rbac.require_permission("alice", Permission.MUTE_POSTS,
                        "mute spam post")  # OK

try:
    rbac.require_permission("bob", Permission.MUTE_POSTS,
                            "mute spam post")  # Raises
except PermissionError as e:
    print(e)
    # @bob (role: treasurer) lacks permission 'MUTE_POSTS'
```

Key design points: roles are assigned on-chain for transparency but evaluated locally for speed. Role hierarchy prevents privilege escalation (mods cannot create admins). Bit-flag permissions allow flexible role definitions. The indexer validates each role operation against the current state before applying it.'''
    },
    {
        "instruction": r'''I need to build a content filtering system for a Hive community that detects and handles different types of problematic content. What approach should I take?''',
        "output": r'''<think>
Content filtering on Hive -- this is challenging because blockchain content is permanent and decentralized. You cannot delete content, only filter it from your front-end or community view.

Let me think about the types of problematic content and how to handle each:
1. Spam: repeated posts, link farms, copy-paste content
2. Plagiarism: content stolen from other sources
3. NSFW content in a non-NSFW community
4. Hate speech, harassment
5. Off-topic content

For each type, the detection approach differs. Spam can be detected with heuristics (posting frequency, content similarity, link ratios). Plagiarism requires comparing against external sources (difficult to automate fully). NSFW detection could use image classification APIs. Hate speech detection uses NLP models.

Hmm, but running ML models for every post might be overkill. Let me think about a tiered approach:
- Tier 1: Fast heuristic checks (spam indicators, word filters) -- process every post
- Tier 2: More expensive checks (content similarity, API calls) -- only for posts that pass tier 1
- Tier 3: Manual review queue -- for borderline cases

I initially thought about building everything in-house, but for plagiarism detection, services like Cheetah bot on Hive already do this. For NSFW, there are cloud APIs. The smart approach is to integrate with existing services where possible.

The tradeoff is: aggressive filtering (fewer false negatives but more false positives, frustrated legitimate users) vs conservative filtering (more false negatives but fewer false positives, more spam gets through). The answer is to have different confidence thresholds for auto-mute vs manual review.

Also important: transparency. Users should be able to see why their post was filtered and appeal. A fully opaque filter system will drive users away.
</think>

Use a tiered filtering pipeline with automatic handling for high-confidence detections and a review queue for borderline cases:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json
import re
import time
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

MOD_ACCOUNT = "community-filter"
COMMUNITY = "hive-123456"


class ContentFilter:
    """Multi-tier content filtering for Hive communities."""

    # Confidence thresholds
    AUTO_MUTE_THRESHOLD = 0.9    # auto-mute above this
    REVIEW_THRESHOLD = 0.5       # send to review above this

    def __init__(self):
        self.recent_posts = defaultdict(list)  # author -> [timestamps]
        self.content_hashes = {}  # hash -> (author, permlink)
        self.review_queue = []
        self.action_log = []

    # === Tier 1: Fast Heuristic Checks ===

    def check_spam_signals(self, author, body, json_metadata_str):
        """Quick spam detection heuristics."""
        signals = []
        score = 0.0

        # Posting frequency (more than 10 posts in an hour)
        now = time.time()
        self.recent_posts[author].append(now)
        # Clean old entries
        self.recent_posts[author] = [
            t for t in self.recent_posts[author]
            if now - t < 3600
        ]
        if len(self.recent_posts[author]) > 10:
            score += 0.4
            signals.append("high_frequency")

        # Link density
        words = body.split()
        word_count = len(words)
        link_count = body.count("http://") + body.count("https://")
        if word_count > 0 and link_count / max(word_count, 1) > 0.2:
            score += 0.3
            signals.append("high_link_density")

        # Very short posts
        if word_count < 30:
            score += 0.2
            signals.append("very_short")

        # Duplicate content detection
        content_hash = hashlib.md5(body.strip().lower().encode()).hexdigest()
        if content_hash in self.content_hashes:
            original = self.content_hashes[content_hash]
            score += 0.5
            signals.append(f"duplicate_of_{original[0]}/{original[1]}")
        self.content_hashes[content_hash] = (author, "")

        # Known spam patterns
        spam_patterns = [
            r"earn \$\d+ per day",
            r"click here to claim",
            r"guaranteed (profit|returns|income)",
            r"send \d+ (hive|hbd) to",
        ]
        for pattern in spam_patterns:
            if re.search(pattern, body.lower()):
                score += 0.4
                signals.append(f"pattern:{pattern[:30]}")

        return min(score, 1.0), signals

    # === Tier 2: Content Quality Checks ===

    def check_content_quality(self, body, json_metadata_str):
        """Deeper content analysis for posts that pass tier 1."""
        signals = []
        score = 0.0

        # Check for mostly non-ASCII (potential gibberish)
        ascii_chars = sum(1 for c in body if ord(c) < 128)
        if len(body) > 0:
            ascii_ratio = ascii_chars / len(body)
            if ascii_ratio < 0.5:
                score += 0.2
                signals.append("low_ascii_ratio")

        # Check for excessive formatting abuse
        if body.count("**") > 20 or body.count("##") > 15:
            score += 0.15
            signals.append("formatting_abuse")

        # Check tags
        try:
            meta = json.loads(json_metadata_str or "{}")
            tags = meta.get("tags", [])
            # Too many tags often indicates spam
            if len(tags) > 10:
                score += 0.15
                signals.append("excessive_tags")
        except json.JSONDecodeError:
            score += 0.1
            signals.append("invalid_metadata")

        return min(score, 1.0), signals

    # === Combined Pipeline ===

    def evaluate_post(self, author, permlink, body, json_metadata_str):
        """Run the full filtering pipeline on a post."""
        # Tier 1: Fast checks
        spam_score, spam_signals = self.check_spam_signals(
            author, body, json_metadata_str
        )

        if spam_score >= self.AUTO_MUTE_THRESHOLD:
            return {
                "action": "auto_mute",
                "confidence": spam_score,
                "signals": spam_signals,
                "tier": 1
            }

        # Tier 2: Quality checks (only if tier 1 is inconclusive)
        if spam_score >= 0.2:
            quality_score, quality_signals = self.check_content_quality(
                body, json_metadata_str
            )
            combined_score = (spam_score + quality_score) / 2
            all_signals = spam_signals + quality_signals

            if combined_score >= self.AUTO_MUTE_THRESHOLD:
                return {
                    "action": "auto_mute",
                    "confidence": combined_score,
                    "signals": all_signals,
                    "tier": 2
                }

            if combined_score >= self.REVIEW_THRESHOLD:
                return {
                    "action": "review",
                    "confidence": combined_score,
                    "signals": all_signals,
                    "tier": 2
                }

        return {
            "action": "approved",
            "confidence": spam_score,
            "signals": spam_signals,
            "tier": 1
        }

    def handle_result(self, result, author, permlink):
        """Act on the filtering result."""
        action = result["action"]

        if action == "auto_mute":
            notes = (f"Auto-filtered (confidence: {result['confidence']:.0%})"
                    f" - {', '.join(result['signals'][:3])}")
            try:
                self._mute_post(author, permlink, notes)
                print(f"AUTO-MUTED @{author}/{permlink}: {notes}")
            except Exception as e:
                print(f"Mute failed: {e}")

        elif action == "review":
            self.review_queue.append({
                "author": author,
                "permlink": permlink,
                "result": result,
                "queued_at": time.time()
            })
            print(f"QUEUED for review: @{author}/{permlink} "
                  f"({result['confidence']:.0%})")

        self.action_log.append({
            "author": author,
            "permlink": permlink,
            "action": action,
            "confidence": result["confidence"],
            "signals": result["signals"],
            "timestamp": time.time()
        })

    def _mute_post(self, author, permlink, notes):
        """Mute a post using the community system."""
        payload = ["community", {
            "community": COMMUNITY,
            "action": "mutePost",
            "account": author,
            "permlink": permlink,
            "notes": notes
        }]
        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [MOD_ACCOUNT],
            "id": "community",
            "json": json.dumps(payload)
        }))
        tx.appendSigner(MOD_ACCOUNT, "posting")
        tx.sign()
        return tx.broadcast()


# Usage
content_filter = ContentFilter()

# Process incoming community posts from block stream
chain = Blockchain(blockchain_instance=hive)
for op in chain.stream(opNames=["comment"]):
    if op.get("parent_author") == "":  # root posts only
        result = content_filter.evaluate_post(
            op["author"], op["permlink"],
            op.get("body", ""),
            op.get("json_metadata", "{}")
        )
        content_filter.handle_result(
            result, op["author"], op["permlink"]
        )
```

Design philosophy: fast heuristics catch obvious spam before expensive checks run. Different thresholds for auto-action vs human review prevent false-positive frustration. All actions are logged for transparency. The review queue lets human moderators handle ambiguous cases. Content is never deleted (impossible on Hive), only muted from the community feed.'''
    },
    {
        "instruction": r'''I want to implement a subscription-based community on Hive where only members who pay a monthly fee can post. How would I design this?''',
        "output": r'''<think>
A subscription-based community on Hive -- this is interesting because Hive communities are fundamentally open. There is no built-in paywall mechanism. So I need to build a custom access control layer.

Let me think about the components:
1. Payment: users pay a monthly fee in HIVE or HBD
2. Membership tracking: track who has active subscriptions
3. Content gating: either prevent non-members from posting or mute their posts
4. Renewal/expiration logic

For payment, users could send HIVE/HBD to a community account with a specific memo (like "subscribe"). The system monitors incoming transfers and grants membership.

Hmm, but how do I prevent non-subscribers from posting? On Hive, anyone can post to any community (for open communities). I cannot actually prevent the post from being created on-chain. I can only:
1. Mute non-member posts after they appear
2. Use front-end filtering to hide them
3. Set the community to "restricted" which requires role-based approval

Wait, actually Hive communities have a "restricted" mode where only members (those with the "member" role or above) can post. This is a built-in feature. So the flow could be:
1. Set community to restricted
2. When someone pays, grant them the "member" role
3. When their subscription expires, revoke the "member" role

I initially thought I would need a custom filtering system, but the restricted community mode plus role management handles the access control natively.

The tradeoff is: restricted mode is clean but relies on the standard role system. A custom system could offer more flexibility (like trial access, different tier levels) but requires building more infrastructure.

For payment tracking, I need to monitor transfers to the community account. I should also handle edge cases: what if someone pays twice? What if they send the wrong amount? What about refunds?
</think>

Use Hive's restricted community mode with automated role management based on transfer monitoring:

```python
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json, Transfer
import json
import time
from datetime import datetime, timedelta

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey", "5YourActiveKey"]
)

COMMUNITY = "hive-123456"
COMMUNITY_ACCOUNT = "premium-community"
SUBSCRIPTION_PRICE_HIVE = 5.0    # 5 HIVE per month
SUBSCRIPTION_PRICE_HBD = 2.5     # or 2.5 HBD per month
SUBSCRIBE_MEMO = "subscribe"


class SubscriptionManager:
    """Manage paid subscriptions for a Hive community."""

    def __init__(self, community, account, blockchain_instance):
        self.community = community
        self.account = account
        self.hive = blockchain_instance
        # member -> expiration datetime
        self.subscriptions = {}
        self.processed_tx_ids = set()  # prevent double-processing

    def _community_op(self, action, data):
        """Broadcast a community operation."""
        payload = ["community", {
            "community": self.community,
            "action": action,
            **data
        }]
        tx = TransactionBuilder(blockchain_instance=self.hive)
        tx.appendOps(Custom_json(**{
            "required_auths": [],
            "required_posting_auths": [self.account],
            "id": "community",
            "json": json.dumps(payload)
        }))
        tx.appendSigner(self.account, "posting")
        tx.sign()
        return tx.broadcast()

    def grant_membership(self, account):
        """Grant member role in the community."""
        try:
            self._community_op("setRole", {
                "account": account,
                "role": "member"
            })
            print(f"Granted membership to @{account}")
        except Exception as e:
            print(f"Failed to grant membership to @{account}: {e}")

    def revoke_membership(self, account):
        """Revoke member role (set to guest)."""
        try:
            self._community_op("setRole", {
                "account": account,
                "role": "guest"
            })
            print(f"Revoked membership from @{account}")
        except Exception as e:
            print(f"Failed to revoke membership from @{account}: {e}")

    def process_transfer(self, transfer_op, tx_id, block_num):
        """Process an incoming transfer as potential subscription."""
        # Dedup
        if tx_id in self.processed_tx_ids:
            return

        to = transfer_op.get("to", "")
        if to != self.account:
            return

        from_account = transfer_op.get("from", "")
        memo = transfer_op.get("memo", "").strip().lower()
        amount_str = transfer_op.get("amount", "")

        # Check memo
        if SUBSCRIBE_MEMO not in memo:
            return

        # Parse amount
        parts = amount_str.split()
        if len(parts) != 2:
            return
        amount = float(parts[0])
        currency = parts[1]

        # Validate payment
        valid = False
        months = 0
        if currency == "HIVE":
            months = int(amount / SUBSCRIPTION_PRICE_HIVE)
            valid = months >= 1
        elif currency == "HBD":
            months = int(amount / SUBSCRIPTION_PRICE_HBD)
            valid = months >= 1

        if not valid:
            # Refund if wrong amount
            print(f"Invalid payment from @{from_account}: {amount_str}")
            self._send_refund(from_account, amount_str,
                            "Invalid subscription amount. "
                            f"Price: {SUBSCRIPTION_PRICE_HIVE:.3f} HIVE "
                            f"or {SUBSCRIPTION_PRICE_HBD:.3f} HBD per month.")
            self.processed_tx_ids.add(tx_id)
            return

        # Extend subscription
        now = datetime.utcnow()
        current_expiry = self.subscriptions.get(from_account)
        if current_expiry and current_expiry > now:
            # Extend from current expiry
            new_expiry = current_expiry + timedelta(days=30 * months)
        else:
            # New subscription
            new_expiry = now + timedelta(days=30 * months)

        self.subscriptions[from_account] = new_expiry
        self.grant_membership(from_account)

        print(f"Subscription: @{from_account} -> {months} month(s), "
              f"expires {new_expiry.strftime('%Y-%m-%d')}")
        self.processed_tx_ids.add(tx_id)

        # Confirmation memo
        self._send_confirmation(from_account, months, new_expiry)

    def _send_refund(self, account, amount_str, reason):
        """Refund an invalid payment."""
        try:
            tx = TransactionBuilder(blockchain_instance=self.hive)
            tx.appendOps(Transfer(**{
                "from": self.account,
                "to": account,
                "amount": amount_str,
                "memo": f"Refund: {reason}"
            }))
            tx.appendSigner(self.account, "active")
            tx.sign()
            tx.broadcast()
        except Exception as e:
            print(f"Refund to @{account} failed: {e}")

    def _send_confirmation(self, account, months, expiry):
        """Send a small confirmation transfer with memo."""
        try:
            tx = TransactionBuilder(blockchain_instance=self.hive)
            tx.appendOps(Transfer(**{
                "from": self.account,
                "to": account,
                "amount": "0.001 HIVE",
                "memo": (f"Subscription confirmed: {months} month(s). "
                        f"Expires: {expiry.strftime('%Y-%m-%d')}")
            }))
            tx.appendSigner(self.account, "active")
            tx.sign()
            tx.broadcast()
        except Exception:
            pass

    def check_expirations(self):
        """Revoke expired subscriptions."""
        now = datetime.utcnow()
        expired = [
            account for account, expiry in self.subscriptions.items()
            if expiry < now
        ]
        for account in expired:
            self.revoke_membership(account)
            del self.subscriptions[account]
            print(f"Subscription expired: @{account}")

    def run(self, start_block=None):
        """Main loop: monitor transfers and manage subscriptions."""
        chain = Blockchain(blockchain_instance=self.hive)
        last_expiry_check = time.time()

        print(f"Subscription manager running for {self.community}")
        print(f"Price: {SUBSCRIPTION_PRICE_HIVE} HIVE or "
              f"{SUBSCRIPTION_PRICE_HBD} HBD/month")

        for op in chain.stream(opNames=["transfer"]):
            self.process_transfer(
                op, op.get("trx_id", ""), op.get("block_num", 0)
            )

            # Check expirations every hour
            if time.time() - last_expiry_check > 3600:
                self.check_expirations()
                last_expiry_check = time.time()


# Usage
manager = SubscriptionManager(COMMUNITY, COMMUNITY_ACCOUNT, hive)
manager.run()
```

How it works: the community is set to "restricted" mode (done once via front-end or API). Users send HIVE/HBD with "subscribe" memo to the community account. The bot grants the "member" role, enabling posting. Expired subscriptions are revoked automatically. Invalid payments are refunded with an explanation. Multi-month payments extend the subscription additively.'''
    },
    {
        "instruction": r'''How can I list all posts in a specific Hive community and filter them by various criteria using the API?''',
        "output": r'''<think>
Querying community posts on Hive -- the community data is managed by hivemind, which provides API endpoints for fetching community content. Let me think about the available methods.

The bridge API (via hivemind) has methods for fetching community data:
- bridge.get_ranked_posts: get posts ranked by trending, hot, created, etc.
- bridge.get_community: get community metadata
- bridge.get_community_context: get a user's role in a community
- bridge.list_communities: list communities

For getting posts in a specific community, bridge.get_ranked_posts with the "tag" parameter set to the community name should work. The "sort" parameter controls ranking: trending, hot, created, promoted, payout, muted.

Hmm, but what about pagination? These API calls typically return 20 posts at a time. To get more, I need to paginate using the last post's author and permlink as the start point for the next page.

I initially thought I could just use condenser_api.get_discussions_by_created with a community tag, but the bridge API is the proper way to query community-specific content. The condenser API methods work with tags, and while community names are valid tags, the bridge API has better community-aware filtering.

Wait, there is also the question of filtering. The API provides basic sorting but not complex filtering (e.g., "posts with more than 10 votes" or "posts by members with rep > 50"). For complex filtering, I need to fetch posts and filter client-side, or use a custom indexer.

The tradeoff is: API-level filtering (fast, limited criteria) vs client-side filtering (flexible but must fetch all posts first). For most use cases, fetching by sort order and filtering client-side works fine for reasonable community sizes.
</think>

Use the bridge API (hivemind) for community post queries. Here is a comprehensive client:

```python
import requests
import json
from datetime import datetime

HIVE_API = "https://api.hive.blog"


class CommunityPostQuery:
    """Query and filter posts from a Hive community."""

    def __init__(self, api_url=None):
        self.api = api_url or HIVE_API
        self.session = requests.Session()

    def _rpc_call(self, method, params):
        """Make an RPC call to the Hive API."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        resp = self.session.post(self.api, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            raise Exception(f"RPC error: {result['error']}")
        return result.get("result")

    def get_community_info(self, community):
        """Get community metadata."""
        return self._rpc_call("bridge.get_community", {
            "name": community
        })

    def get_community_posts(self, community, sort="created", limit=100):
        """Fetch posts from a community with pagination.

        sort options: trending, hot, created, promoted, payout, muted
        """
        all_posts = []
        last_author = ""
        last_permlink = ""

        while len(all_posts) < limit:
            batch_size = min(20, limit - len(all_posts))
            params = {
                "sort": sort,
                "tag": community,
                "limit": batch_size
            }

            if last_author and last_permlink:
                params["start_author"] = last_author
                params["start_permlink"] = last_permlink

            posts = self._rpc_call("bridge.get_ranked_posts", params)

            if not posts:
                break

            # Skip the first post on subsequent pages (duplicate)
            start_idx = 1 if last_author else 0
            new_posts = posts[start_idx:]

            if not new_posts:
                break

            all_posts.extend(new_posts)
            last_post = posts[-1]
            last_author = last_post["author"]
            last_permlink = last_post["permlink"]

            if len(posts) < batch_size:
                break  # no more pages

        return all_posts[:limit]

    def get_community_subscribers(self, community, limit=100):
        """Get community subscriber list."""
        return self._rpc_call("bridge.list_subscribers", {
            "community": community,
            "limit": limit
        })

    # === Client-Side Filters ===

    def filter_by_votes(self, posts, min_votes=0, max_votes=None):
        """Filter posts by vote count."""
        filtered = []
        for post in posts:
            votes = post.get("stats", {}).get("total_votes", 0)
            if votes >= min_votes:
                if max_votes is None or votes <= max_votes:
                    filtered.append(post)
        return filtered

    def filter_by_payout(self, posts, min_payout=0.0):
        """Filter posts by pending payout value."""
        filtered = []
        for post in posts:
            payout_str = post.get("payout", "0")
            try:
                payout = float(str(payout_str).replace(" HBD", "").replace(" HIVE", ""))
            except (ValueError, AttributeError):
                payout = 0.0
            if payout >= min_payout:
                filtered.append(post)
        return filtered

    def filter_by_author_rep(self, posts, min_rep=25):
        """Filter posts by author reputation."""
        return [
            p for p in posts
            if p.get("author_reputation", 0) >= min_rep
        ]

    def filter_by_word_count(self, posts, min_words=100):
        """Filter posts by body word count."""
        return [
            p for p in posts
            if len(p.get("body", "").split()) >= min_words
        ]

    def filter_by_date_range(self, posts, start_date=None, end_date=None):
        """Filter posts by creation date."""
        filtered = []
        for post in posts:
            created_str = post.get("created", "")
            try:
                created = datetime.strptime(
                    created_str, "%Y-%m-%dT%H:%M:%S"
                )
                if start_date and created < start_date:
                    continue
                if end_date and created > end_date:
                    continue
                filtered.append(post)
            except ValueError:
                continue
        return filtered

    def filter_by_tags(self, posts, required_tags=None, excluded_tags=None):
        """Filter posts by tags."""
        filtered = []
        for post in posts:
            try:
                meta = json.loads(post.get("json_metadata", "{}"))
                post_tags = set(meta.get("tags", []))
            except json.JSONDecodeError:
                post_tags = set()

            if required_tags and not set(required_tags).issubset(post_tags):
                continue
            if excluded_tags and set(excluded_tags).intersection(post_tags):
                continue
            filtered.append(post)
        return filtered

    def search_posts(self, posts, keyword):
        """Simple keyword search in title and body."""
        keyword_lower = keyword.lower()
        return [
            p for p in posts
            if (keyword_lower in p.get("title", "").lower() or
                keyword_lower in p.get("body", "").lower())
        ]


# === Usage ===

query = CommunityPostQuery()

# Get community info
info = query.get_community_info("hive-169321")  # Hive DevTalk
if info:
    print(f"Community: {info.get('title')}")
    print(f"Subscribers: {info.get('subscribers')}")

# Fetch recent posts
posts = query.get_community_posts("hive-169321", sort="created", limit=50)
print(f"Fetched {len(posts)} posts")

# Apply filters
quality_posts = query.filter_by_votes(posts, min_votes=5)
quality_posts = query.filter_by_word_count(quality_posts, min_words=200)
print(f"Quality posts (5+ votes, 200+ words): {len(quality_posts)}")

# Search
python_posts = query.search_posts(posts, "python")
print(f"Python-related posts: {len(python_posts)}")

for post in quality_posts[:5]:
    print(f"  @{post['author']}: {post.get('title', 'untitled')}")
```

The bridge API handles community-specific queries including role-based visibility (muted posts are excluded by default). For complex filtering requirements beyond what the API provides, fetch posts in bulk using pagination and apply client-side filters. For very large communities, consider building a custom indexer that mirrors community posts into a database with proper indexes.'''
    },
]
