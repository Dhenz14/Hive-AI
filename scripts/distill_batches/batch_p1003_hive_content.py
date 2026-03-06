"""Hive blockchain training pairs: content creation and management."""

PAIRS = [
    (
        "hive/posting-with-beneficiaries",
        r'''How do I create a post on Hive with beneficiaries so that part of the rewards go to other accounts?''',
        r'''Beneficiaries let you split post rewards with other accounts (e.g., dApp fees, collaborators, charity). They are set via the comment_options operation that must be broadcast in the same transaction as the comment.

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment, Comment_options
import json
import time

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourPostingKey"]
)

AUTHOR = "myaccount"

def create_post_with_beneficiaries(title, body, tags, beneficiaries,
                                     max_accepted_payout="1000000.000 HBD",
                                     percent_hbd=10000, allow_votes=True):
    """Create a post with reward beneficiaries.

    Args:
        beneficiaries: List of {"account": "name", "weight": N}
            where weight is in basis points (10000 = 100%)
            Total weight of all beneficiaries must not exceed 10000
    """
    permlink = title.lower().replace(" ", "-")[:200]
    permlink = "".join(c for c in permlink if c.isalnum() or c == "-")
    permlink = f"{permlink}-{int(time.time())}"

    # Sort beneficiaries alphabetically (required by consensus)
    sorted_beneficiaries = sorted(beneficiaries, key=lambda x: x["account"])

    # Validate total weight
    total_weight = sum(b["weight"] for b in sorted_beneficiaries)
    if total_weight > 10000:
        raise ValueError(f"Total beneficiary weight {total_weight} exceeds 10000")

    # Create the post (comment operation)
    comment_op = Comment(**{
        "parent_author": "",  # Empty for root post
        "parent_permlink": tags[0] if tags else "hive",
        "author": AUTHOR,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json.dumps({
            "tags": tags,
            "app": "myapp/1.0",
            "format": "markdown"
        })
    })

    # Set comment options with beneficiaries
    options_op = Comment_options(**{
        "author": AUTHOR,
        "permlink": permlink,
        "max_accepted_payout": max_accepted_payout,
        "percent_hbd": percent_hbd,
        "allow_votes": allow_votes,
        "allow_curation_rewards": True,
        "extensions": [
            [0, {"beneficiaries": sorted_beneficiaries}]
        ]
    })

    # Both operations must be in the same transaction
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(comment_op)
    tx.appendOps(options_op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    result = tx.broadcast()

    print(f"Post created: @{AUTHOR}/{permlink}")
    print(f"Beneficiaries:")
    for b in sorted_beneficiaries:
        print(f"  @{b['account']}: {b['weight']/100}%")
    remaining = 100 - total_weight / 100
    print(f"  @{AUTHOR} (author): {remaining}%")

    return result, permlink

# Example: Split rewards with a dApp and a collaborator
create_post_with_beneficiaries(
    title="My Awesome Post",
    body="# Hello Hive\n\nThis is a post with beneficiaries!",
    tags=["hive-dev", "tutorial", "python"],
    beneficiaries=[
        {"account": "myapp", "weight": 500},      # 5% to the dApp
        {"account": "collaborator", "weight": 2500}, # 25% to collaborator
    ]
)
```

Important rules:
- Beneficiaries must be sorted alphabetically by account name
- Total weight cannot exceed 10000 (100%)
- Beneficiaries can only be set once (in the same tx as the post)
- They cannot be changed after the post is created
- The comment_options operation must use the same author/permlink
- Curation rewards (50%) are separate; beneficiaries split the author's 50%
'''
    ),
    (
        "hive/post-metadata-json",
        r'''What is the correct format for json_metadata on Hive posts? How do different front-ends use it?''',
        r'''The json_metadata field on Hive posts is a flexible JSON string that front-ends use to store post formatting, media references, and app-specific data. Here is the standard format and how different apps use it:

```python
import json

# Standard json_metadata format
def create_standard_metadata(tags, app_name="myapp/1.0", format_type="markdown",
                              image_urls=None, links=None, description=None):
    """Create properly formatted json_metadata for a Hive post."""
    metadata = {
        "tags": tags,
        "app": app_name,
        "format": format_type,  # "markdown" or "html"
    }

    if image_urls:
        metadata["image"] = image_urls  # List of image URLs
    if links:
        metadata["links"] = links
    if description:
        metadata["description"] = description

    return json.dumps(metadata)

# PeakD extended metadata format
def create_peakd_metadata(tags, images=None, description=""):
    """Metadata format used by PeakD front-end."""
    metadata = {
        "tags": tags,
        "app": "peakd/2024.1",
        "format": "markdown",
        "description": description[:300],  # PeakD truncates to 300 chars
    }
    if images:
        metadata["image"] = images
    return json.dumps(metadata)

# Ecency metadata format
def create_ecency_metadata(tags, images=None):
    """Metadata format used by Ecency."""
    metadata = {
        "tags": tags,
        "app": "ecency/3.0",
        "format": "markdown+html",  # Ecency supports mixed
    }
    if images:
        metadata["image"] = images
    return json.dumps(metadata)

# 3Speak video post metadata
def create_threespeak_metadata(tags, video_id, duration, thumbnail):
    """Metadata format for 3Speak video posts."""
    metadata = {
        "tags": tags,
        "app": "3speak/0.3",
        "format": "markdown",
        "type": "video",
        "video": {
            "info": {
                "platform": "3speak",
                "title": "",
                "author": "",
                "permlink": "",
                "duration": duration,
                "filesize": 0,
                "file": video_id,
                "lang": "en",
                "firstUpload": True,
                "video_v2": f"https://3speak.tv/watch?v={video_id}"
            },
            "content": {
                "description": "",
                "tags": tags
            }
        },
        "image": [thumbnail]
    }
    return json.dumps(metadata)

# Parse metadata from existing posts
def parse_post_metadata(json_metadata_str):
    """Safely parse and extract common fields from json_metadata."""
    try:
        data = json.loads(json_metadata_str)
    except (json.JSONDecodeError, TypeError):
        return {"tags": [], "app": "unknown", "format": "markdown"}

    return {
        "tags": data.get("tags", []),
        "app": data.get("app", "unknown"),
        "format": data.get("format", "markdown"),
        "images": data.get("image", []),
        "links": data.get("links", []),
        "description": data.get("description", ""),
        "video": data.get("video", None),
        "type": data.get("type", "blog"),
        "canonical_url": data.get("canonical_url", ""),
    }

# Complete post creation with rich metadata
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment

def create_rich_post(author, title, body, tags, images=None):
    hive = Hive(node=["https://api.hive.blog"], keys=["5PostingKey"])

    permlink = f"{title.lower().replace(' ', '-')[:100]}-{int(__import__('time').time())}"
    permlink = "".join(c for c in permlink if c.isalnum() or c == "-")

    metadata = {
        "tags": tags[:10],  # Max 10 tags recommended
        "app": "myapp/1.0",
        "format": "markdown",
        "description": body[:160].replace("\n", " "),
    }
    if images:
        metadata["image"] = images[:10]

    op = Comment(**{
        "parent_author": "",
        "parent_permlink": tags[0],
        "author": author,
        "permlink": permlink,
        "title": title[:256],
        "body": body,
        "json_metadata": json.dumps(metadata)
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(author, "posting")
    tx.sign()
    return tx.broadcast()

# Example metadata output
meta = create_standard_metadata(
    tags=["python", "tutorial", "hive-dev"],
    image_urls=["https://example.com/img.jpg"],
    description="A tutorial on Hive development"
)
print("Standard:", meta)
print("Parsed:", json.dumps(parse_post_metadata(meta), indent=2))
```

Key metadata conventions:
- "tags" array should have 1-10 tags; first tag is the primary category
- "app" identifies which front-end or tool created the post
- "format" tells front-ends how to render (markdown, html, markdown+html)
- "image" array is used for thumbnails and Open Graph previews
- The total json_metadata must not exceed the operation size limit
'''
    ),
    (
        "hive/editing-posts",
        r'''How do I edit an existing post on Hive? Can I change the title, body, tags, and beneficiaries after posting?''',
        r'''Editing a post on Hive is done by broadcasting another comment operation with the same author/permlink. However, there are important limitations on what can be changed:

```python
from beem import Hive
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment as CommentOp
import json

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourPostingKey"]
)

AUTHOR = "myaccount"

def edit_post(permlink, new_title=None, new_body=None, new_tags=None):
    """Edit an existing post.

    What CAN be changed:
    - title
    - body
    - json_metadata (tags, images, etc.)

    What CANNOT be changed:
    - permlink (it is the post's unique identifier)
    - parent_author / parent_permlink (cannot move to different category)
    - beneficiaries (set once, immutable)
    - comment_options (max_accepted_payout, percent_hbd)
    """
    # Fetch current post to preserve unchanged fields
    post = Comment(f"@{AUTHOR}/{permlink}", hive_instance=hive)

    # Use existing values for fields not being changed
    title = new_title if new_title is not None else post["title"]
    body = new_body if new_body is not None else post["body"]

    # Parse existing metadata
    try:
        current_meta = json.loads(post.get("json_metadata", "{}"))
    except (json.JSONDecodeError, TypeError):
        current_meta = {}

    if new_tags is not None:
        current_meta["tags"] = new_tags

    # To edit, broadcast a comment op with the SAME permlink
    op = CommentOp(**{
        "parent_author": post["parent_author"],
        "parent_permlink": post["parent_permlink"],
        "author": AUTHOR,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json.dumps(current_meta)
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Post edited: @{AUTHOR}/{permlink}")
    return result

def append_to_post(permlink, additional_text):
    """Append text to an existing post (common pattern for updates)."""
    post = Comment(f"@{AUTHOR}/{permlink}", hive_instance=hive)
    current_body = post["body"]

    separator = "\n\n---\n\n"
    new_body = current_body + separator + additional_text

    return edit_post(permlink, new_body=new_body)

def add_edit_notice(permlink, edit_reason):
    """Add an edit notice to a post (transparent editing)."""
    post = Comment(f"@{AUTHOR}/{permlink}", hive_instance=hive)
    current_body = post["body"]

    from datetime import datetime
    edit_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    notice = f"\n\n*Edit ({edit_time}): {edit_reason}*"

    new_body = current_body + notice
    return edit_post(permlink, new_body=new_body)

def delete_post(permlink):
    """'Delete' a post by blanking its content.

    Hive does not truly delete content from the blockchain.
    This replaces the body with empty content, which front-ends
    treat as deleted.
    """
    op = CommentOp(**{
        "parent_author": "",  # Must know the parent
        "parent_permlink": "hive",
        "author": AUTHOR,
        "permlink": permlink,
        "title": "deleted",
        "body": "deleted",
        "json_metadata": json.dumps({"tags": ["deleted"]})
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Post blanked (deleted): @{AUTHOR}/{permlink}")
    return result

# Check edit history
def get_edit_count(author, permlink):
    """Check how many times a post has been edited."""
    # The content_api tracks edits
    result = hive.rpc.get_content(
        {"author": author, "permlink": permlink},
        api="condenser_api"
    )
    # Most front-ends show the last_update vs created timestamp
    created = result.get("created", "")
    last_update = result.get("last_update", "")
    was_edited = created != last_update

    print(f"Created:      {created}")
    print(f"Last updated: {last_update}")
    print(f"Was edited:   {was_edited}")
    return was_edited

# Usage
# edit_post("my-original-post", new_body="Updated content here")
# edit_post("my-original-post", new_tags=["updated", "hive-dev"])
# append_to_post("my-original-post", "**Update:** Fixed the code example.")
# delete_post("my-original-post")
```

Important editing rules:
- Edits are free (just RC cost) and can be done anytime
- All edits are stored on the blockchain and visible through block explorers
- Beneficiaries cannot be changed after the initial post
- The cashout window is 7 days; after that, no more rewards but still editable
- "Deleting" just blanks content; the original data persists in the block log
- Front-ends typically show the latest version only
'''
    ),
    (
        "hive/community-posting",
        r'''How do I post to a specific Hive community? How do communities work at the protocol level?''',
        r'''<think>
Hive communities are managed by Hivemind (the social consensus layer). At the protocol level, a community post is just a regular comment operation where:
1. The parent_permlink is the community name (e.g., "hive-12345")
2. The community is identified by the account name that owns it
3. Community names follow the pattern "hive-NNNNNN" (hive- followed by digits)

Hivemind indexes these posts and applies community-specific rules (muting, pinning, roles). The community operations themselves are custom_json operations with id "community".
</think>

Hive communities are managed by Hivemind, the social consensus layer. At the blockchain level, posting to a community means setting the parent_permlink to the community name. Here is how it works:

```python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment, Custom_json
import json
import time
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourPostingKey"]
)

AUTHOR = "myaccount"

def post_to_community(community_name, title, body, tags):
    """Post to a Hive community.

    Community names follow the pattern 'hive-NNNNNN'.
    The community name is used as the parent_permlink.
    """
    permlink = f"{title.lower().replace(' ', '-')[:100]}-{int(time.time())}"
    permlink = "".join(c for c in permlink if c.isalnum() or c == "-")

    # The key is: parent_permlink = community name
    op = Comment(**{
        "parent_author": "",  # Empty for root posts
        "parent_permlink": community_name,  # e.g., "hive-163521"
        "author": AUTHOR,
        "permlink": permlink,
        "title": title,
        "body": body,
        "json_metadata": json.dumps({
            "tags": [community_name] + tags,
            "app": "myapp/1.0",
            "format": "markdown",
            "community": community_name
        })
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Posted to {community_name}: @{AUTHOR}/{permlink}")
    return result, permlink

def list_communities(query="", limit=20):
    """List Hive communities via the bridge API."""
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

    print(f"{'Name':20s} {'Title':30s} {'Subscribers':>12} {'Posts':>8}")
    print("-" * 75)
    for c in communities:
        print(f"{c['name']:20s} {c['title'][:30]:30s} "
              f"{c.get('subscribers', 0):>12,} {c.get('num_pending', 0):>8,}")

    return communities

def get_community_posts(community_name, sort="created", limit=20):
    """Get posts from a specific community."""
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.get_ranked_posts",
        "params": {
            "sort": sort,  # created, trending, hot, promoted, payout
            "tag": community_name,
            "limit": limit,
            "observer": ""
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    posts = resp.json().get("result", [])

    print(f"Posts in {community_name} (sorted by {sort}):")
    for p in posts:
        payout = p.get("payout", 0)
        votes = p.get("stats", {}).get("total_votes", 0)
        print(f"  @{p['author']}/{p['permlink'][:30]} "
              f"${payout:.2f} ({votes} votes)")

    return posts

def subscribe_to_community(community_name):
    """Subscribe to a community via custom_json."""
    payload = ["subscribe", {"community": community_name}]
    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [AUTHOR],
        "id": "community",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    return tx.broadcast()

# Community operations (admin/mod)
def set_community_role(community_name, target_account, role):
    """Set a user's role in a community.

    Roles: guest, member, mod, admin, owner
    Only mods+ can set roles for others.
    """
    payload = ["setRole", {
        "community": community_name,
        "account": target_account,
        "role": role
    }]
    op = Custom_json(**{
        "required_auths": [],
        "required_posting_auths": [AUTHOR],
        "id": "community",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    return tx.broadcast()

# Usage
list_communities(query="dev")
# post_to_community("hive-163521", "My Dev Post", "Content here", ["python"])
# subscribe_to_community("hive-163521")
```

Community protocol details:
- Community names are "hive-" followed by a number (the account ID)
- Posting to a community = setting parent_permlink to the community name
- Community operations (subscribe, setRole, mute, pin) use custom_json with id "community"
- Hivemind processes these operations and builds the community state
- Roles: guest < member < mod < admin < owner
- Muted content is hidden by front-ends but still on-chain
'''
    ),
    (
        "hive/reply-and-comment",
        r'''How do I create replies (comments) on Hive posts and manage comment threads programmatically?''',
        r'''Replies on Hive use the same comment operation as posts, but with a non-empty parent_author and the parent post's permlink. Here is how to manage comment threads:

```python
from beem import Hive
from beem.comment import Comment
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment as CommentOp
import json
import time
import requests

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourPostingKey"]
)

AUTHOR = "myaccount"

def reply_to_post(parent_author, parent_permlink, body):
    """Reply to a post or comment."""
    # Generate a unique permlink for the reply
    permlink = f"re-{parent_author}-{parent_permlink[:50]}-{int(time.time())}"
    permlink = "".join(c for c in permlink if c.isalnum() or c == "-")

    op = CommentOp(**{
        "parent_author": parent_author,
        "parent_permlink": parent_permlink,
        "author": AUTHOR,
        "permlink": permlink,
        "title": "",  # Replies typically have empty titles
        "body": body,
        "json_metadata": json.dumps({
            "tags": [],
            "app": "myapp/1.0",
            "format": "markdown"
        })
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(AUTHOR, "posting")
    tx.sign()
    result = tx.broadcast()
    print(f"Reply posted: @{AUTHOR}/{permlink}")
    return result, permlink

def get_comment_thread(author, permlink, depth=0, max_depth=10):
    """Recursively fetch a complete comment thread."""
    # Use bridge API for efficient thread fetching
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.get_discussion",
        "params": {
            "author": author,
            "permlink": permlink,
            "observer": ""
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    result = resp.json().get("result", {})

    if not result:
        return []

    # The result is a flat dict keyed by "author/permlink"
    root_key = f"{author}/{permlink}"
    root = result.get(root_key, {})

    comments = []
    def collect_replies(post_data, current_depth):
        replies = post_data.get("replies", [])
        for reply_key in replies:
            reply = result.get(reply_key, {})
            if reply:
                indent = "  " * current_depth
                print(f"{indent}@{reply['author']}: "
                      f"{reply['body'][:80]}...")
                comments.append({
                    "author": reply["author"],
                    "permlink": reply["permlink"],
                    "body": reply["body"],
                    "depth": current_depth,
                    "payout": reply.get("payout", 0),
                    "votes": reply.get("stats", {}).get("total_votes", 0)
                })
                if current_depth < max_depth:
                    collect_replies(reply, current_depth + 1)

    print(f"Thread: @{author}/{permlink}")
    print(f"Root: {root.get('title', 'No title')}")
    collect_replies(root, 1)
    print(f"\nTotal comments: {len(comments)}")
    return comments

def get_account_replies(account_name, limit=20):
    """Get recent replies to an account's posts."""
    payload = {
        "jsonrpc": "2.0",
        "method": "bridge.get_account_posts",
        "params": {
            "account": account_name,
            "sort": "replies",
            "limit": limit,
            "observer": ""
        },
        "id": 1
    }
    resp = requests.post("https://api.hive.blog", json=payload, timeout=15)
    replies = resp.json().get("result", [])

    print(f"Recent replies to @{account_name}:")
    for r in replies:
        print(f"  @{r['author']}: {r['body'][:100]}...")
    return replies

def batch_reply(parent_comments, reply_template):
    """Reply to multiple comments with a template.

    Useful for automated thank-you messages, etc.
    Respect rate limits: ~5 comments per block (15 seconds).
    """
    for parent in parent_comments:
        body = reply_template.format(
            author=parent["author"],
            permlink=parent["permlink"]
        )
        reply_to_post(parent["author"], parent["permlink"], body)
        time.sleep(3)  # Wait between replies to avoid RC issues

# Usage
# reply_to_post("someauthor", "some-post", "Great article! Thanks for sharing.")
# get_comment_thread("someauthor", "some-post")
# get_account_replies("myaccount")
```

Comment rules on Hive:
- Comments use the same "comment" operation as root posts
- The parent_author is non-empty for replies (empty for root posts)
- Comments can be nested (replies to replies) up to 255 levels
- Each comment has its own 7-day reward window
- You can vote on comments just like posts
- Rate limiting: avoid spamming comments (wastes RC, may trigger downvotes)
'''
    ),
]
