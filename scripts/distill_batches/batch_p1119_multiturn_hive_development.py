"""
Multi-turn conversation training pairs - Hive blockchain development
Covers: setting up beem -> posting -> custom_json -> streaming -> building a bot
Hive-specific multi-turn development conversations
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: I want to start building on the Hive blockchain with Python. What library should I use?
Assistant: Use beem -- it's the most maintained Python library for Hive. Install with pip install beem. It handles account operations, posting, custom_json, streaming, and all the common Hive operations. It supports both Hive mainnet and testnet.

[Current message]
User: I installed beem. How do I connect to Hive and read basic account information? I want to check an account's balance and recent posts.''',
        "output": r'''Since you have beem installed, here is how to connect and read account data.

```python
from beem import Hive
from beem.account import Account

# Connect to Hive mainnet (uses default public nodes)
hive = Hive()

# You can specify nodes explicitly if default ones are slow
# hive = Hive(node=['https://api.hive.blog', 'https://api.deathwing.me'])

# Read account information
acct = Account('hiveio', blockchain_instance=hive)

# Basic account info
print('Name:', acct['name'])
print('Reputation:', acct.get_reputation())
print('Created:', acct['created'])

# Balances
print('HIVE balance:', acct.get_balance('available', 'HIVE'))
print('HBD balance:', acct.get_balance('available', 'HBD'))
print('HP (vests):', acct.get_balance('available', 'VESTS'))

# Convert VESTS to HP for human-readable display
hp = hive.vests_to_hp(float(acct.get_balance('available', 'VESTS')))
print('Hive Power: %.3f HP' % hp)

# Get recent posts
from beem.comment import Comment

posts = acct.get_blog(limit=5)
for post in posts:
    print('---')
    print('Title:', post['title'])
    print('Author:', post['author'])
    print('Permlink:', post['permlink'])
    print('Votes:', post['net_votes'])
    print('Payout:', post['pending_payout_value'])
```

A few things to know about beem:

1. **No keys needed for reading** -- you can read any public data (account info, posts, blockchain state) without providing private keys. Keys are only needed for writing (posting, voting, transfers).

2. **Node selection matters** -- public nodes have rate limits. If you are building a bot or app that makes frequent calls, consider running your own node or using a paid API service.

3. **Account object is lazy** -- it fetches data on first access, so the initial Account() call is fast. The data loads when you access properties.

4. **Reputation is stored as a large integer** -- `get_reputation()` converts it to the familiar 25-75 scale you see on frontends like PeakD.

Try this script with different account names to get comfortable with the data structures before we move on to writing operations.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I can read Hive account data with beem now. I want to start posting to Hive programmatically. How do I authenticate?
Assistant: You need your Hive posting key (not your master password or active key). Never hardcode keys in source files. Use environment variables or a separate config file that is in .gitignore. When creating the Hive instance, pass the posting key as a parameter.

User: I have my posting key stored in an environment variable called HIVE_POSTING_KEY. My account name is in HIVE_ACCOUNT.
Assistant: Perfect. Create the Hive instance with those credentials and you can start posting.

[Current message]
User: Show me how to create a post on Hive with beem. I want to include tags, set a beneficiary, and choose the reward type (50/50 HBD/HP).''',
        "output": r'''Since you have your posting key in the HIVE_POSTING_KEY environment variable, here is how to create a full post with all the options.

```python
import os
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment, Comment_options

# Connect with posting authority
hive = Hive(
    node=['https://api.hive.blog', 'https://api.deathwing.me'],
    keys=[os.environ['HIVE_POSTING_KEY']],
)

account = os.environ['HIVE_ACCOUNT']

def create_post(title, body, tags, beneficiaries=None, max_accepted_payout='1000000.000 HBD'):
    # The first tag becomes the "category" (community)
    main_tag = tags[0]

    # Create a unique permlink from the title
    import re
    from datetime import datetime
    permlink = re.sub(r'[^a-z0-9-]', '', title.lower().replace(' ', '-'))
    permlink = permlink + '-' + datetime.utcnow().strftime('%Y%m%d%H%M%S')

    # Build the JSON metadata
    json_metadata = {
        'tags': tags,
        'app': 'myapp/1.0',
        'format': 'markdown',
    }

    # Post the content
    import json
    hive.post(
        title=title,
        body=body,
        author=account,
        permlink=permlink,
        tags=tags,
        json_metadata=json_metadata,
        self_vote=False,
        community=main_tag,  # Optional: post to a community
    )

    # Set comment options (beneficiaries, payout type)
    if beneficiaries:
        # Beneficiaries must be sorted alphabetically by account name
        sorted_bens = sorted(beneficiaries, key=lambda x: x['account'])

        comment_options = Comment_options(
            **{
                'author': account,
                'permlink': permlink,
                'max_accepted_payout': max_accepted_payout,
                'percent_hbd': 10000,  # 10000 = 50/50, 0 = 100% HP
                'allow_votes': True,
                'allow_curation_rewards': True,
                'extensions': [[0, {'beneficiaries': sorted_bens}]],
            }
        )

        tx = TransactionBuilder(blockchain_instance=hive)
        tx.appendOps(comment_options)
        tx.appendSigner(account, 'posting')
        tx.sign()
        tx.broadcast()

    print('Post created: https://peakd.com/@%s/%s' % (account, permlink))
    return permlink


# Usage:
permlink = create_post(
    title='My First Programmatic Post',
    body=(
        '# Hello Hive!\n\n'
        'This post was created using beem and Python.\n\n'
        '## Why automate posting?\n\n'
        '- Schedule content ahead of time\n'
        '- Cross-post from other platforms\n'
        '- Build content bots\n\n'
        'Thanks for reading!\n'
    ),
    tags=['python', 'programming', 'development', 'hive'],
    beneficiaries=[
        {'account': 'somecurator', 'weight': 500},   # 5%
        {'account': 'someproject', 'weight': 1000},   # 10%
    ],
)
```

Important notes:

1. **Beneficiary weights** are in basis points: 500 = 5%, 1000 = 10%. Total cannot exceed 10000 (100%).

2. **Beneficiaries must be sorted alphabetically** by account name. If not sorted, the transaction will be rejected by the blockchain.

3. **percent_hbd** controls the reward split: 10000 means 50% HBD / 50% HP (the default "50/50" option). Set to 0 for 100% HP. There is no 100% liquid option on Hive.

4. **Permlinks must be unique** per account. Adding a timestamp ensures uniqueness even if you post similar titles.

5. **Rate limits** -- Hive allows one post every 5 minutes per account. Comments (replies) have a 3-second cooldown.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I can create posts on Hive now. I want to build a bot that automatically votes on posts with specific tags. How do I stream new posts from the blockchain?
Assistant: Beem has a Blockchain class that streams operations in real-time. You can filter for specific operation types like 'comment' (which includes both posts and replies). The stream follows the blockchain head block and yields operations as they happen.

[Current message]
User: Show me how to stream new posts and filter by tags. I want to see posts tagged with 'python' or 'programming' as they appear on the blockchain.''',
        "output": r'''Building on the beem connection we set up earlier, here is how to stream and filter posts in real-time.

```python
import os
import json
from beem import Hive
from beem.blockchain import Blockchain

hive = Hive(node=['https://api.hive.blog', 'https://api.deathwing.me'])
chain = Blockchain(blockchain_instance=hive)

TARGET_TAGS = {'python', 'programming', 'developer', 'coding'}

def stream_tagged_posts():
    print('Streaming new posts... (Ctrl+C to stop)')

    # Stream only 'comment' operations (posts and replies)
    for op in chain.stream(opNames=['comment']):
        # Skip replies -- we only want top-level posts
        if op['parent_author'] != '':
            continue

        # Parse the json_metadata to get tags
        try:
            metadata = json.loads(op.get('json_metadata', '{}'))
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        tags = set(metadata.get('tags', []))

        # Check if any target tags are present
        matching_tags = tags.intersection(TARGET_TAGS)
        if not matching_tags:
            continue

        print('---')
        print('Author: @%s' % op['author'])
        print('Title: %s' % op.get('title', '(no title)'))
        print('Tags: %s' % ', '.join(tags))
        print('Matched: %s' % ', '.join(matching_tags))
        print('Link: https://peakd.com/@%s/%s' % (op['author'], op['permlink']))
        print('Block: %s' % op.get('block_num', 'unknown'))

if __name__ == '__main__':
    try:
        stream_tagged_posts()
    except KeyboardInterrupt:
        print('\nStopped.')
```

To make this more robust for a production bot:

```python
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('hive_stream')

def stream_with_recovery():
    # Track the last processed block to resume after crashes
    last_block_file = 'last_block.txt'

    def get_start_block():
        try:
            with open(last_block_file, 'r') as f:
                return int(f.read().strip())
        except FileNotFoundError:
            return None

    def save_block(block_num):
        with open(last_block_file, 'w') as f:
            f.write(str(block_num))

    while True:
        try:
            start_block = get_start_block()

            if start_block:
                logger.info('Resuming from block %d', start_block)
                stream = chain.stream(
                    opNames=['comment'],
                    start=start_block,
                )
            else:
                logger.info('Starting from head block')
                stream = chain.stream(opNames=['comment'])

            for op in stream:
                # Skip replies
                if op['parent_author'] != '':
                    continue

                try:
                    metadata = json.loads(op.get('json_metadata', '{}'))
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

                tags = set(metadata.get('tags', []))
                matching = tags.intersection(TARGET_TAGS)

                if matching:
                    handle_matching_post(op, matching)

                # Save progress every block
                block_num = op.get('block_num')
                if block_num:
                    save_block(block_num)

        except Exception as e:
            logger.error('Stream error: %s. Reconnecting in 10s...', e)
            time.sleep(10)

def handle_matching_post(op, matching_tags):
    logger.info(
        'Found post by @%s: "%s" [%s]',
        op['author'],
        op.get('title', ''),
        ', '.join(matching_tags),
    )
    # Add your bot logic here -- voting, commenting, etc.
```

The recovery mechanism is critical for production bots. When the connection drops (which happens regularly with public nodes), the bot resumes from the last processed block instead of missing posts. Hive produces a new block every 3 seconds, so the stream yields operations continuously.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a Hive post streaming bot that filters by tags. Now I want it to automatically upvote matching posts. How do I vote with beem?
Assistant: Use the hive.vote() method with your posting key. You specify the author, permlink, and vote weight (1-100%). Be careful with voting power -- each 100% vote uses about 2% of your voting mana, and it regenerates at about 20% per day.

User: I want to be smart about it -- vote 50% on posts from accounts I follow and 25% on posts from others. Also, I should not vote on my own posts.
Assistant: Good plan. You can fetch your following list once at startup and check against it. Let me show you the voting logic.

[Current message]
User: Show me the complete voting bot logic. I also want to make sure I do not run out of voting power -- stop voting if my mana drops below 80%.''',
        "output": r'''Building on the streaming code we set up, here is the complete voting bot with mana management.

```python
import os
import json
import time
import logging
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger('vote_bot')

# Configuration
MY_ACCOUNT = os.environ['HIVE_ACCOUNT']
POSTING_KEY = os.environ['HIVE_POSTING_KEY']
TARGET_TAGS = {'python', 'programming', 'development'}
MIN_VOTING_MANA = 80.0  # Stop voting below this percentage
VOTE_WEIGHT_FOLLOWING = 50.0  # 50% for people I follow
VOTE_WEIGHT_DEFAULT = 25.0    # 25% for others
VOTE_DELAY_SECONDS = 300      # Wait 5 min before voting (curation rewards)

hive = Hive(
    node=['https://api.hive.blog', 'https://api.deathwing.me'],
    keys=[POSTING_KEY],
)

class VoteBot:
    def __init__(self):
        self.account = Account(MY_ACCOUNT, blockchain_instance=hive)
        self.following = set()
        self.voted_today = set()
        self.pending_votes = []

    def load_following(self):
        # Fetch the list of accounts we follow
        following_list = self.account.get_following()
        self.following = set(f['following'] for f in following_list)
        logger.info('Loaded %d following accounts', len(self.following))

    def get_voting_mana(self):
        # Refresh account data
        self.account.refresh()
        mana = self.account.get_voting_power()
        return mana

    def should_vote(self, author, permlink):
        # Do not self-vote
        if author == MY_ACCOUNT:
            return False, 'self-post'

        # Check voting mana
        mana = self.get_voting_mana()
        if mana < MIN_VOTING_MANA:
            return False, 'low mana (%.1f%%)' % mana

        # Do not vote on the same post twice
        post_key = '%s/%s' % (author, permlink)
        if post_key in self.voted_today:
            return False, 'already voted'

        return True, 'ok'

    def get_vote_weight(self, author):
        if author in self.following:
            return VOTE_WEIGHT_FOLLOWING
        return VOTE_WEIGHT_DEFAULT

    def cast_vote(self, author, permlink, weight):
        try:
            hive.vote(weight, '@%s/%s' % (author, permlink), account=MY_ACCOUNT)
            self.voted_today.add('%s/%s' % (author, permlink))
            logger.info(
                'Voted %.0f%% on @%s/%s',
                weight, author, permlink,
            )
            return True
        except Exception as e:
            logger.error('Vote failed on @%s/%s: %s', author, permlink, e)
            return False

    def process_pending_votes(self):
        # Process votes that have waited long enough
        now = time.time()
        remaining = []
        for vote in self.pending_votes:
            if now >= vote['vote_at']:
                ok, reason = self.should_vote(vote['author'], vote['permlink'])
                if ok:
                    weight = self.get_vote_weight(vote['author'])
                    self.cast_vote(vote['author'], vote['permlink'], weight)
                else:
                    logger.info(
                        'Skipping @%s/%s: %s',
                        vote['author'], vote['permlink'], reason,
                    )
            else:
                remaining.append(vote)
        self.pending_votes = remaining

    def run(self):
        self.load_following()
        chain = Blockchain(blockchain_instance=hive)

        logger.info('Bot started. Monitoring for tags: %s', TARGET_TAGS)
        logger.info('Current voting mana: %.1f%%', self.get_voting_mana())

        for op in chain.stream(opNames=['comment']):
            # Process any pending delayed votes
            self.process_pending_votes()

            # Skip replies
            if op['parent_author'] != '':
                continue

            # Check tags
            try:
                metadata = json.loads(op.get('json_metadata', '{}'))
            except (json.JSONDecodeError, TypeError):
                continue

            tags = set(metadata.get('tags', []))
            if not tags.intersection(TARGET_TAGS):
                continue

            author = op['author']
            permlink = op['permlink']
            title = op.get('title', '')

            logger.info('Found: "%s" by @%s', title, author)

            # Queue vote with delay for better curation rewards
            self.pending_votes.append({
                'author': author,
                'permlink': permlink,
                'vote_at': time.time() + VOTE_DELAY_SECONDS,
            })
            logger.info(
                'Queued vote for @%s/%s (in %ds)',
                author, permlink, VOTE_DELAY_SECONDS,
            )

if __name__ == '__main__':
    bot = VoteBot()
    while True:
        try:
            bot.run()
        except Exception as e:
            logger.error('Bot error: %s. Restarting in 30s...', e)
            time.sleep(30)
```

The 5-minute vote delay is important for curation rewards on Hive -- voting too early (under 5 minutes) means you earn less curation. The mana check at 80% ensures you always have voting power available for manual curation too.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My voting bot is working. Now I want to use custom_json operations to store data on the Hive blockchain. I am building a decentralized app (dApp) that tracks user achievements.
Assistant: custom_json is perfect for dApp data on Hive. It lets you broadcast arbitrary JSON data that gets stored on the blockchain. Your dApp reads this data by scanning the blockchain for your specific custom_json ID. The data is immutable once broadcast and costs no fees -- only requires posting or active authority.

[Current message]
User: Show me how to broadcast and read custom_json operations. My dApp ID will be 'myachievements' and I want to store achievement unlock events.''',
        "output": r'''Building on your beem setup with posting key authentication, here is how to broadcast and read custom_json operations for your achievements dApp.

Broadcasting custom_json:

```python
import os
import json
import time
from beem import Hive
from beem.blockchain import Blockchain
from datetime import datetime

hive = Hive(
    node=['https://api.hive.blog', 'https://api.deathwing.me'],
    keys=[os.environ['HIVE_POSTING_KEY']],
)

MY_ACCOUNT = os.environ['HIVE_ACCOUNT']
DAPP_ID = 'myachievements'

def broadcast_achievement(achievement_id, achievement_name, metadata=None):
    # Build the custom_json payload
    payload = {
        'action': 'unlock',
        'achievement_id': achievement_id,
        'achievement_name': achievement_name,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    if metadata:
        payload['metadata'] = metadata

    # Broadcast the custom_json operation
    hive.custom_json(
        id=DAPP_ID,
        json_data=json.dumps(payload),
        required_posting_auths=[MY_ACCOUNT],
    )

    print('Achievement broadcast: %s (%s)' % (achievement_name, achievement_id))
    return payload

# Example: unlock an achievement
broadcast_achievement(
    achievement_id='first_post',
    achievement_name='First Post',
    metadata={'category': 'beginner', 'points': 10},
)

# Another example
broadcast_achievement(
    achievement_id='100_posts',
    achievement_name='Century Blogger',
    metadata={'category': 'milestone', 'points': 100},
)
```

Reading custom_json from the blockchain:

```python
def scan_achievements(account=None, start_block=None, limit=100):
    # Scan the blockchain for achievement custom_json operations
    chain = Blockchain(blockchain_instance=hive)
    achievements = []

    stream_args = {'opNames': ['custom_json']}
    if start_block:
        stream_args['start'] = start_block

    count = 0
    for op in chain.stream(**stream_args):
        # Filter for our dApp ID
        if op.get('id') != DAPP_ID:
            continue

        try:
            data = json.loads(op.get('json', '{}'))
        except json.JSONDecodeError:
            continue

        # Get the account that broadcast this
        auths = op.get('required_posting_auths', [])
        author = auths[0] if auths else 'unknown'

        # Filter by account if specified
        if account and author != account:
            continue

        achievement = {
            'author': author,
            'block_num': op.get('block_num'),
            'trx_id': op.get('trx_id'),
            'data': data,
        }
        achievements.append(achievement)
        count += 1

        if count >= limit:
            break

    return achievements

# Get all achievements for a specific user
user_achievements = scan_achievements(account='someuser', limit=50)
for a in user_achievements:
    print('@%s unlocked: %s (block %s)' % (
        a['author'],
        a['data'].get('achievement_name', 'unknown'),
        a['block_num'],
    ))
```

Building a state from custom_json history:

```python
class AchievementTracker:
    def __init__(self):
        # user -> set of unlocked achievement IDs
        self.user_achievements = {}
        # user -> total points
        self.user_points = {}
        self.last_block = 0

    def process_operation(self, op):
        auths = op.get('required_posting_auths', [])
        if not auths:
            return

        author = auths[0]
        try:
            data = json.loads(op.get('json', '{}'))
        except json.JSONDecodeError:
            return

        action = data.get('action')
        if action == 'unlock':
            aid = data.get('achievement_id')
            if author not in self.user_achievements:
                self.user_achievements[author] = set()
                self.user_points[author] = 0

            if aid not in self.user_achievements[author]:
                self.user_achievements[author].add(aid)
                points = data.get('metadata', {}).get('points', 0)
                self.user_points[author] += points

        self.last_block = op.get('block_num', self.last_block)

    def get_leaderboard(self, top_n=10):
        sorted_users = sorted(
            self.user_points.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_users[:top_n]
```

Custom_json is limited to 8192 bytes per operation and uses posting authority (no active key needed). There are no fees -- you only need enough Resource Credits (RC), which regenerate over time based on your HP. For a typical account with 50+ HP, you can broadcast hundreds of custom_json operations per day.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a Hive dApp using custom_json for achievements. I want to build a web API that serves the achievement data. Users should be able to query their achievements and see a leaderboard.
Assistant: You need a backend service that indexes the blockchain data. The common pattern is: stream custom_json operations, store them in a local database (PostgreSQL or SQLite), and serve the indexed data through a REST API. This is much faster than scanning the blockchain for every user request.

User: I will use Flask and SQLite for simplicity. How do I structure this?
Assistant: You will need two components running: a blockchain indexer (streams and stores data) and a Flask API (serves queries). The indexer runs continuously in the background, and the API reads from the same database.

[Current message]
User: Show me the complete architecture -- the database schema, the indexer, and the Flask API endpoints.''',
        "output": r'''Building on the achievement tracker concept and your custom_json format, here is the complete system.

Database schema:

```python
# database.py
import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', 'achievements.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            achievement_id TEXT NOT NULL,
            achievement_name TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            category TEXT DEFAULT '',
            block_num INTEGER NOT NULL,
            trx_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(author, achievement_id)
        );

        CREATE INDEX IF NOT EXISTS idx_achievements_author
            ON achievements(author);
        CREATE INDEX IF NOT EXISTS idx_achievements_category
            ON achievements(category);

        CREATE TABLE IF NOT EXISTS indexer_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()
```

The blockchain indexer:

```python
# indexer.py
import json
import time
import logging
from beem import Hive
from beem.blockchain import Blockchain
from database import get_db, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('indexer')

DAPP_ID = 'myachievements'

hive = Hive(node=['https://api.hive.blog', 'https://api.deathwing.me'])

def get_last_block():
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM indexer_state WHERE key = 'last_block'"
    ).fetchone()
    conn.close()
    if row:
        return int(row['value'])
    return None

def save_last_block(block_num):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO indexer_state (key, value) VALUES ('last_block', ?)",
        (str(block_num),)
    )
    conn.commit()
    conn.close()

def process_achievement(op):
    auths = op.get('required_posting_auths', [])
    if not auths:
        return

    try:
        data = json.loads(op.get('json', '{}'))
    except json.JSONDecodeError:
        return

    if data.get('action') != 'unlock':
        return

    author = auths[0]
    meta = data.get('metadata', {})

    conn = get_db()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO achievements
            (author, achievement_id, achievement_name, points, category, block_num, trx_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            author,
            data.get('achievement_id', ''),
            data.get('achievement_name', ''),
            meta.get('points', 0),
            meta.get('category', ''),
            op.get('block_num', 0),
            op.get('trx_id', ''),
            data.get('timestamp', ''),
        ))
        conn.commit()
        logger.info('Indexed: @%s unlocked %s', author, data.get('achievement_name'))
    except Exception as e:
        logger.error('DB error: %s', e)
    finally:
        conn.close()

def run_indexer():
    init_db()
    chain = Blockchain(blockchain_instance=hive)

    while True:
        try:
            start_block = get_last_block()
            if start_block:
                logger.info('Resuming from block %d', start_block)

            stream_kwargs = {'opNames': ['custom_json']}
            if start_block:
                stream_kwargs['start'] = start_block

            for op in chain.stream(**stream_kwargs):
                if op.get('id') == DAPP_ID:
                    process_achievement(op)

                block_num = op.get('block_num')
                if block_num and block_num % 100 == 0:
                    save_last_block(block_num)

        except Exception as e:
            logger.error('Stream error: %s. Restarting in 10s...', e)
            time.sleep(10)

if __name__ == '__main__':
    run_indexer()
```

The Flask API:

```python
# api.py
from flask import Flask, jsonify, request
from database import get_db, init_db

app = Flask(__name__)

@app.route('/api/achievements/<username>')
def user_achievements(username):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM achievements WHERE author = ? ORDER BY block_num DESC',
        (username,)
    ).fetchall()
    conn.close()

    total_points = sum(r['points'] for r in rows)

    return jsonify({
        'user': username,
        'total_points': total_points,
        'achievement_count': len(rows),
        'achievements': [
            {
                'id': r['achievement_id'],
                'name': r['achievement_name'],
                'points': r['points'],
                'category': r['category'],
                'unlocked_at': r['timestamp'],
                'block': r['block_num'],
            }
            for r in rows
        ],
    })

@app.route('/api/leaderboard')
def leaderboard():
    limit = request.args.get('limit', 20, type=int)
    conn = get_db()
    rows = conn.execute("""
        SELECT author, SUM(points) as total_points, COUNT(*) as count
        FROM achievements
        GROUP BY author
        ORDER BY total_points DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    return jsonify({
        'leaderboard': [
            {'rank': i + 1, 'user': r['author'],
             'points': r['total_points'], 'achievements': r['count']}
            for i, r in enumerate(rows)
        ],
    })

if __name__ == '__main__':
    init_db()
    app.run(port=5000, debug=True)
```

Run both components: `python indexer.py` in one terminal and `python api.py` in another. The indexer continuously populates the database, and the API serves it. SQLite with WAL mode handles concurrent reads (API) and writes (indexer) safely.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Hive dApp is working with the indexer and API. Now I want to add Hive Keychain authentication so users can log in to my web frontend and prove they own their Hive account.
Assistant: Hive Keychain is a browser extension that manages Hive private keys. For authentication, the standard approach is to have the user sign a message with their posting key via Keychain. Your backend verifies the signature to confirm account ownership. This is similar to how MetaMask works for Ethereum.

[Current message]
User: Show me both the frontend JavaScript for Hive Keychain login and the backend Python verification.''',
        "output": r'''Since you need both the browser-side Keychain interaction and the server-side signature verification, here is the complete auth flow.

Frontend -- Hive Keychain login:

```html
<button id="loginBtn" onclick="loginWithKeychain()">
    Login with Hive Keychain
</button>
<div id="loginStatus"></div>

<script>
function loginWithKeychain() {
    var statusDiv = document.getElementById('loginStatus');

    // Check if Keychain is installed
    if (!window.hive_keychain) {
        statusDiv.textContent = 'Please install Hive Keychain extension';
        return;
    }

    var username = prompt('Enter your Hive username:');
    if (!username) return;

    // Request a challenge from our backend
    fetch('/api/auth/challenge', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: username}),
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var challenge = data.challenge;

        // Ask Keychain to sign the challenge with posting key
        window.hive_keychain.requestSignBuffer(
            username,
            challenge,
            'Posting',
            function(response) {
                if (response.success) {
                    // Send the signature to our backend for verification
                    verifySignature(username, challenge, response.result);
                } else {
                    statusDiv.textContent = 'Keychain error: ' + response.message;
                }
            }
        );
    })
    .catch(function(err) {
        statusDiv.textContent = 'Error: ' + err.message;
    });
}

function verifySignature(username, challenge, signature) {
    var statusDiv = document.getElementById('loginStatus');

    fetch('/api/auth/verify', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            username: username,
            challenge: challenge,
            signature: signature,
        }),
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.authenticated) {
            statusDiv.textContent = 'Logged in as @' + username;
            // Store the session token
            localStorage.setItem('auth_token', data.token);
            localStorage.setItem('hive_user', username);
        } else {
            statusDiv.textContent = 'Authentication failed: ' + data.error;
        }
    });
}
</script>
```

Backend -- Challenge generation and signature verification:

```python
# auth.py
import os
import uuid
import time
import hashlib
import json
from flask import Flask, request, jsonify
from beem.account import Account
from beem import Hive
from beemgraphenebase.ecdsasig import verify_message
from beemgraphenebase.account import PublicKey

hive = Hive(node=['https://api.hive.blog'])

# In-memory challenge store (use Redis in production)
pending_challenges = {}

SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production')

@app.route('/api/auth/challenge', methods=['POST'])
def create_challenge():
    data = request.json
    username = data.get('username', '').strip().lower()

    if not username:
        return jsonify({'error': 'Username required'}), 400

    # Create a unique challenge string
    challenge = 'hive_auth_%s_%s_%d' % (username, uuid.uuid4().hex[:16], int(time.time()))

    # Store with expiry (5 minutes)
    pending_challenges[challenge] = {
        'username': username,
        'expires': time.time() + 300,
    }

    return jsonify({'challenge': challenge})


@app.route('/api/auth/verify', methods=['POST'])
def verify_challenge():
    data = request.json
    username = data.get('username', '').strip().lower()
    challenge = data.get('challenge', '')
    signature = data.get('signature', '')

    # Check the challenge exists and is not expired
    stored = pending_challenges.pop(challenge, None)
    if not stored:
        return jsonify({'authenticated': False, 'error': 'Invalid challenge'}), 401
    if time.time() > stored['expires']:
        return jsonify({'authenticated': False, 'error': 'Challenge expired'}), 401
    if stored['username'] != username:
        return jsonify({'authenticated': False, 'error': 'Username mismatch'}), 401

    # Get the account's public posting keys from the blockchain
    try:
        acct = Account(username, blockchain_instance=hive)
        posting_keys = [str(k) for k in acct['posting']['key_auths']]
    except Exception as e:
        return jsonify({'authenticated': False, 'error': 'Account not found'}), 404

    # Verify the signature matches one of the posting public keys
    verified = False
    for pub_key_str in posting_keys:
        try:
            # The signature verification logic depends on the beem version
            # This checks if the signature was created by the private key
            # corresponding to this public key
            pub_key = PublicKey(pub_key_str[0], prefix='STM')
            message_hash = hashlib.sha256(challenge.encode()).digest()
            verified = verify_message(message_hash, bytes.fromhex(signature), str(pub_key))
            if verified:
                break
        except Exception:
            continue

    if not verified:
        return jsonify({'authenticated': False, 'error': 'Invalid signature'}), 401

    # Generate a session token
    import jwt
    token = jwt.encode(
        {'sub': username, 'iat': int(time.time()), 'exp': int(time.time()) + 86400},
        SECRET_KEY,
        algorithm='HS256',
    )

    return jsonify({
        'authenticated': True,
        'username': username,
        'token': token,
    })
```

The flow is: frontend requests a challenge -> user signs it with Keychain -> backend verifies the signature against the account's on-chain public keys -> issues a JWT session token. No passwords are ever transmitted or stored. The challenge is single-use and expires after 5 minutes to prevent replay attacks.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I want to build a Hive-based tipping bot. When someone comments "!tip 1" on a post, the bot should send 1 HIVE from the bot account to the post author.
Assistant: That requires the active key (not posting key) because HIVE transfers require active authority. Be very careful with the active key -- it can transfer funds. Store it securely and set strict limits on the bot's spending.

User: I understand the security implications. I will keep a small amount of HIVE in the bot account and set a max tip amount. How do I structure this?
Assistant: Stream comments from the blockchain, parse the !tip command, validate the amount, check the bot's balance, and execute the transfer. Add rate limiting to prevent abuse.

[Current message]
User: Show me the complete tipping bot with safety checks, rate limiting, and proper error handling.''',
        "output": r'''Building on the streaming pattern from our earlier bot work, here is a tipping bot with comprehensive safety checks.

```python
import os
import json
import time
import logging
import re
from collections import defaultdict
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
from beem.amount import Amount

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger('tipbot')

# Configuration
BOT_ACCOUNT = os.environ['HIVE_BOT_ACCOUNT']
ACTIVE_KEY = os.environ['HIVE_ACTIVE_KEY']
POSTING_KEY = os.environ['HIVE_POSTING_KEY']

MAX_TIP_AMOUNT = 5.0      # Max tip per command
DAILY_TIP_LIMIT = 50.0    # Max total tips per day per user
MIN_BOT_BALANCE = 10.0    # Stop tipping if bot balance drops below this
COOLDOWN_SECONDS = 60     # Min time between tips from same user

hive = Hive(
    node=['https://api.hive.blog', 'https://api.deathwing.me'],
    keys=[ACTIVE_KEY, POSTING_KEY],
)

TIP_PATTERN = re.compile(r'!tip\s+([0-9]+(?:\.[0-9]{1,3})?)\s*$', re.IGNORECASE)

class TipBot:
    def __init__(self):
        self.daily_totals = defaultdict(float)  # user -> total tipped today
        self.last_tip_time = {}  # user -> timestamp
        self.last_reset = time.time()

    def reset_daily_limits(self):
        # Reset daily totals every 24 hours
        if time.time() - self.last_reset > 86400:
            self.daily_totals.clear()
            self.last_reset = time.time()
            logger.info('Daily tip limits reset')

    def get_bot_balance(self):
        acct = Account(BOT_ACCOUNT, blockchain_instance=hive)
        balance = float(acct.get_balance('available', 'HIVE'))
        return balance

    def validate_tip(self, sender, amount):
        # Check tip amount
        if amount <= 0:
            return False, 'Tip amount must be positive'
        if amount > MAX_TIP_AMOUNT:
            return False, 'Max tip is %.1f HIVE' % MAX_TIP_AMOUNT

        # Check daily limit
        if self.daily_totals[sender] + amount > DAILY_TIP_LIMIT:
            remaining = DAILY_TIP_LIMIT - self.daily_totals[sender]
            return False, 'Daily limit reached (%.1f HIVE remaining)' % remaining

        # Check cooldown
        last = self.last_tip_time.get(sender, 0)
        if time.time() - last < COOLDOWN_SECONDS:
            wait = int(COOLDOWN_SECONDS - (time.time() - last))
            return False, 'Please wait %d seconds between tips' % wait

        # Check bot balance
        balance = self.get_bot_balance()
        if balance < MIN_BOT_BALANCE:
            return False, 'Bot is low on funds. Please try later.'
        if balance < amount:
            return False, 'Insufficient bot balance'

        # Do not allow self-tipping
        if sender == BOT_ACCOUNT:
            return False, 'Cannot tip yourself'

        return True, 'ok'

    def send_tip(self, sender, recipient, amount, memo_permlink):
        memo = 'Tip from @%s via !tip command on %s' % (sender, memo_permlink)

        try:
            hive.transfer(
                recipient,
                amount,
                'HIVE',
                memo=memo,
                account=BOT_ACCOUNT,
            )

            # Update limits
            self.daily_totals[sender] += amount
            self.last_tip_time[sender] = time.time()

            logger.info(
                'Sent %.3f HIVE from @%s to @%s',
                amount, BOT_ACCOUNT, recipient,
            )
            return True
        except Exception as e:
            logger.error('Transfer failed: %s', e)
            return False

    def post_reply(self, parent_author, parent_permlink, body):
        try:
            hive.post(
                title='',
                body=body,
                author=BOT_ACCOUNT,
                reply_identifier='@%s/%s' % (parent_author, parent_permlink),
                tags=[],
            )
        except Exception as e:
            logger.error('Reply failed: %s', e)

    def process_comment(self, op):
        # Only process replies (has a parent_author)
        if op['parent_author'] == '':
            return

        body = op.get('body', '')
        match = TIP_PATTERN.search(body)
        if not match:
            return

        amount = float(match.group(1))
        sender = op['author']
        recipient = op['parent_author']
        permlink = '@%s/%s' % (op['parent_author'], op['parent_permlink'])

        logger.info(
            'Tip command: @%s -> @%s %.3f HIVE',
            sender, recipient, amount,
        )

        # Do not tip yourself
        if sender == recipient:
            return

        valid, reason = self.validate_tip(sender, amount)
        if not valid:
            logger.info('Tip rejected: %s', reason)
            self.post_reply(
                op['author'], op['permlink'],
                'Sorry @%s, tip failed: %s' % (sender, reason),
            )
            return

        success = self.send_tip(sender, recipient, amount, permlink)
        if success:
            self.post_reply(
                op['author'], op['permlink'],
                'Sent %.3f HIVE to @%s. Have a great day!' % (amount, recipient),
            )

    def run(self):
        chain = Blockchain(blockchain_instance=hive)
        balance = self.get_bot_balance()
        logger.info('TipBot started. Balance: %.3f HIVE', balance)

        for op_data in chain.stream(opNames=['comment']):
            self.reset_daily_limits()
            self.process_comment(op_data)

if __name__ == '__main__':
    bot = TipBot()
    while True:
        try:
            bot.run()
        except Exception as e:
            logger.error('Bot error: %s. Restarting in 30s...', e)
            time.sleep(30)
```

Safety features:
- Max tip per command (5 HIVE) prevents large accidental tips
- Daily per-user limit (50 HIVE) prevents drain attacks
- Min bot balance check (10 HIVE) as a safety net
- Cooldown prevents spam
- Self-tip prevention
- The bot replies with success or failure messages so users get feedback

For production, store daily_totals and last_tip_time in Redis or SQLite instead of memory, so limits survive bot restarts.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I want to monitor Hive witness status and get alerts when a witness misses blocks. I run a Hive witness node and want to know immediately if it goes down.
Assistant: You can monitor witness performance by checking the witness object on-chain. It includes the total_missed count and the last_confirmed_block_num. You can poll these values periodically and alert when total_missed increases.

User: Can I also check if my signing key is correct and compare my price feed age?
Assistant: Yes -- the witness object contains the signing_key and the last hbd_exchange_rate update time. You can check if the signing key matches your expected key and alert if the price feed is stale.

[Current message]
User: Show me a complete witness monitoring script with alerts. I want it to check every minute and send alerts to a Discord webhook.''',
        "output": r'''Building on the monitoring approach we discussed, here is a complete witness monitor with Discord alerts.

```python
import os
import time
import json
import logging
from datetime import datetime, timedelta
from beem import Hive
from beem.witness import Witness
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger('witness_monitor')

# Configuration
WITNESS_NAME = os.environ.get('HIVE_WITNESS', 'yourwitness')
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK', '')
EXPECTED_SIGNING_KEY = os.environ.get('EXPECTED_SIGNING_KEY', '')
CHECK_INTERVAL = 60  # seconds
PRICE_FEED_MAX_AGE_HOURS = 24

hive = Hive(node=['https://api.hive.blog', 'https://api.deathwing.me'])

class WitnessMonitor:
    def __init__(self, witness_name):
        self.witness_name = witness_name
        self.last_missed = None
        self.last_alert_time = {}
        self.alert_cooldown = 300  # 5 min between same alert type

    def get_witness_data(self):
        try:
            w = Witness(self.witness_name, blockchain_instance=hive)
            return {
                'name': w['owner'],
                'total_missed': w['total_missed'],
                'last_confirmed_block': w['last_confirmed_block_num'],
                'signing_key': w['signing_key'],
                'running_version': w['running_version'],
                'hbd_exchange_rate': w['hbd_exchange_rate'],
                'last_hbd_exchange_update': w['last_hbd_exchange_update'],
                'votes': w['votes'],
                'is_disabled': w['signing_key'] == 'STM1111111111111111111111111111111114T1Anm',
            }
        except Exception as e:
            logger.error('Failed to fetch witness data: %s', e)
            return None

    def send_discord_alert(self, title, message, color=16711680):
        # color: 16711680 = red, 65280 = green, 16776960 = yellow
        if not DISCORD_WEBHOOK:
            logger.warning('No Discord webhook configured')
            return

        embed = {
            'title': title,
            'description': message,
            'color': color,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'footer': {'text': 'Hive Witness Monitor'},
        }

        try:
            requests.post(DISCORD_WEBHOOK, json={'embeds': [embed]}, timeout=10)
        except Exception as e:
            logger.error('Discord alert failed: %s', e)

    def should_alert(self, alert_type):
        last = self.last_alert_time.get(alert_type, 0)
        if time.time() - last < self.alert_cooldown:
            return False
        self.last_alert_time[alert_type] = time.time()
        return True

    def check_missed_blocks(self, data):
        current_missed = data['total_missed']

        if self.last_missed is not None and current_missed > self.last_missed:
            new_misses = current_missed - self.last_missed
            if self.should_alert('missed_block'):
                self.send_discord_alert(
                    'Missed Blocks Alert',
                    '@%s missed %d block(s)!\n'
                    'Total missed: %d\n'
                    'Last confirmed: %d' % (
                        self.witness_name, new_misses,
                        current_missed, data['last_confirmed_block'],
                    ),
                    color=16711680,  # red
                )
            logger.warning('Missed %d blocks! Total: %d', new_misses, current_missed)

        self.last_missed = current_missed

    def check_signing_key(self, data):
        if data['is_disabled']:
            if self.should_alert('disabled'):
                self.send_discord_alert(
                    'Witness DISABLED',
                    '@%s signing key is set to the disabled key!\n'
                    'The witness is not producing blocks.' % self.witness_name,
                    color=16711680,
                )
            logger.error('Witness is DISABLED')
            return

        if EXPECTED_SIGNING_KEY and data['signing_key'] != EXPECTED_SIGNING_KEY:
            if self.should_alert('wrong_key'):
                self.send_discord_alert(
                    'Signing Key Mismatch',
                    '@%s signing key does not match expected key!\n'
                    'Current: %s...\n'
                    'Expected: %s...' % (
                        self.witness_name,
                        data['signing_key'][:20],
                        EXPECTED_SIGNING_KEY[:20],
                    ),
                    color=16776960,  # yellow
                )

    def check_price_feed(self, data):
        update_time = datetime.strptime(
            str(data['last_hbd_exchange_update']),
            '%Y-%m-%dT%H:%M:%S',
        )
        age = datetime.utcnow() - update_time
        age_hours = age.total_seconds() / 3600

        if age_hours > PRICE_FEED_MAX_AGE_HOURS:
            if self.should_alert('stale_feed'):
                rate = data['hbd_exchange_rate']
                self.send_discord_alert(
                    'Stale Price Feed',
                    '@%s price feed is %.1f hours old!\n'
                    'Last update: %s\n'
                    'Rate: %s' % (
                        self.witness_name, age_hours,
                        str(update_time), str(rate),
                    ),
                    color=16776960,
                )
            logger.warning('Price feed is %.1f hours old', age_hours)

    def run_check(self):
        data = self.get_witness_data()
        if not data:
            if self.should_alert('fetch_error'):
                self.send_discord_alert(
                    'Monitor Error',
                    'Failed to fetch witness data for @%s.\n'
                    'API nodes may be down.' % self.witness_name,
                    color=16776960,
                )
            return

        self.check_missed_blocks(data)
        self.check_signing_key(data)
        self.check_price_feed(data)

        logger.info(
            'Status OK | missed: %d | block: %d | version: %s',
            data['total_missed'],
            data['last_confirmed_block'],
            data['running_version'],
        )

    def run(self):
        logger.info('Monitoring witness: @%s', self.witness_name)
        self.send_discord_alert(
            'Monitor Started',
            'Witness monitor started for @%s' % self.witness_name,
            color=65280,  # green
        )

        while True:
            self.run_check()
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    monitor = WitnessMonitor(WITNESS_NAME)
    monitor.run()
```

The monitor checks three things every minute: missed blocks (immediate red alert), signing key validity (catches unauthorized changes or accidental disable), and price feed freshness (yellow warning if older than 24 hours). The 5-minute cooldown between same-type alerts prevents Discord spam during extended outages.

Set the environment variables and run with `python witness_monitor.py`. For production, run it under systemd or supervisord so it auto-restarts.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I am building a Hive-based content aggregator. I need to fetch posts from specific communities and rank them by engagement. How do communities work on Hive?
Assistant: Hive communities are managed through the hivemind layer. Each community has an account name (like hive-123456) and community-specific metadata. Posts are associated with a community through the parent_permlink field (which matches the community name) or through the community field in json_metadata.

User: I want to fetch the top posts from the "HiveDevs" community (hive-169321) for the past 7 days.
Assistant: You can use the bridge API which is part of hivemind. It has endpoints for fetching community posts with various sorting options. Let me show you how.

[Current message]
User: Show me how to fetch and rank community posts. I want to combine on-chain engagement metrics (votes, comments, payout) into a single ranking score.''',
        "output": r'''Building on the hivemind bridge API approach, here is how to fetch community posts and build a custom ranking system.

```python
import requests
import json
from datetime import datetime, timedelta

HIVE_API = 'https://api.hive.blog'

def call_bridge(method, params):
    # Call the hivemind bridge API
    payload = {
        'jsonrpc': '2.0',
        'method': 'bridge.' + method,
        'params': params,
        'id': 1,
    }
    response = requests.post(HIVE_API, json=payload, timeout=15)
    result = response.json()
    if 'error' in result:
        raise Exception('API error: %s' % result['error'])
    return result['result']

def fetch_community_posts(community, sort='created', limit=100):
    # Fetch posts from a specific community
    # sort options: trending, hot, created, promoted, payout, muted
    all_posts = []
    last_author = ''
    last_permlink = ''

    while len(all_posts) < limit:
        batch_size = min(20, limit - len(all_posts))
        params = {
            'community': community,
            'sort': sort,
            'limit': batch_size,
        }
        if last_author:
            params['start_author'] = last_author
            params['start_permlink'] = last_permlink

        posts = call_bridge('get_ranked_posts', params)

        if not posts:
            break

        # Skip the first post on subsequent pages (it is a duplicate)
        start_idx = 1 if last_author else 0
        for post in posts[start_idx:]:
            all_posts.append(post)

        last_author = posts[-1]['author']
        last_permlink = posts[-1]['permlink']

        if len(posts) < batch_size:
            break

    return all_posts

def calculate_engagement_score(post):
    # Custom engagement ranking formula
    # Weights: votes (moderate), comments (high), payout (moderate)

    votes = post.get('stats', {}).get('total_votes', 0)
    comments = post.get('children', 0)

    # Parse payout value
    payout_str = post.get('payout', '0.000 HBD')
    payout = float(str(payout_str).split(' ')[0])

    # Time decay: newer posts get a boost
    created = datetime.strptime(post['created'], '%Y-%m-%dT%H:%M:%S')
    age_hours = (datetime.utcnow() - created).total_seconds() / 3600
    time_factor = 1.0 / (1.0 + age_hours / 24.0)  # Decays over days

    # Engagement score formula
    score = (
        (votes * 1.0) +
        (comments * 5.0) +   # Comments are high-effort engagement
        (payout * 2.0) +     # Payout reflects curator interest
        (time_factor * 10.0)  # Recency bonus
    )

    return round(score, 2)

def get_top_community_posts(community, days=7, top_n=20):
    # Fetch recent posts
    posts = fetch_community_posts(community, sort='created', limit=200)

    # Filter to the time window
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = []
    for post in posts:
        created = datetime.strptime(post['created'], '%Y-%m-%dT%H:%M:%S')
        if created >= cutoff:
            recent.append(post)

    # Calculate scores and rank
    scored = []
    for post in recent:
        score = calculate_engagement_score(post)
        scored.append({
            'title': post['title'],
            'author': post['author'],
            'permlink': post['permlink'],
            'created': post['created'],
            'votes': post.get('stats', {}).get('total_votes', 0),
            'comments': post.get('children', 0),
            'payout': post.get('payout', '0.000 HBD'),
            'engagement_score': score,
            'url': 'https://peakd.com/@%s/%s' % (post['author'], post['permlink']),
        })

    scored.sort(key=lambda x: x['engagement_score'], reverse=True)
    return scored[:top_n]


# Usage
if __name__ == '__main__':
    print('Top posts in HiveDevs community (past 7 days):')
    print('=' * 60)

    top_posts = get_top_community_posts('hive-169321', days=7, top_n=10)
    for i, post in enumerate(top_posts):
        print('%d. [%.1f] %s' % (i + 1, post['engagement_score'], post['title']))
        print('   @%s | %d votes | %d comments | %s payout' % (
            post['author'], post['votes'], post['comments'], post['payout'],
        ))
        print('   %s' % post['url'])
        print()
```

The bridge API is the preferred way to fetch community content because it uses hivemind's pre-indexed data, which is much faster than scanning raw blockchain operations. The `get_ranked_posts` endpoint supports pagination through start_author/start_permlink.

The engagement score formula weights comments highest (5x) because writing a comment takes more effort than voting. You can tune the weights based on what matters for your aggregator. The time decay factor ensures fresh content with moderate engagement ranks above old content with high engagement.'''
    },
]
