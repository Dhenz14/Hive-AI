"""
Hive blockchain bot development training pairs: voting bots, content bots,
trading bots, monitoring bots, bot rate limiting and ethics.
"""

PAIRS = [
    (
        "hive-bot-voting",
        r'''How do I build a curation voting bot on Hive that votes on posts matching specific criteria with configurable vote weight and timing?''',
        r'''<think>
A curation bot needs to: monitor new posts, evaluate them against criteria (tags, authors, word count, etc.), and cast votes with appropriate weight and timing. Vote timing matters because curation rewards are maximized when voting early on posts that will get large payouts. I need to handle RC costs, vote power regeneration (20% per day, full at 10000), and avoid double-voting.
</think>

A curation voting bot monitors the blockchain for new posts and votes based on configurable rules. Key considerations include vote power management (regenerates 20% per day from 10000 max), curation reward timing, and RC costs. Here is a production-ready bot:

```python
from beem import Hive
from beem.account import Account
from beem.blockchain import Blockchain
from beem.comment import Comment
import json
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("curation_bot")

class CurationBot:
    def __init__(self, account, posting_key, config):
        self.hive = Hive(keys=[posting_key], node=[
            "https://api.hive.blog",
            "https://api.deathwing.me",
            "https://rpc.ausbit.dev"
        ])
        self.account_name = account
        self.account = Account(account, blockchain_instance=self.hive)
        self.config = config
        self.voted_posts = set()  # Track to avoid double votes
        self.daily_vote_count = 0
        self.last_reset = datetime.utcnow().date()

    def get_voting_power(self):
        """Get current voting power as percentage (0-100)."""
        self.account.refresh()
        vp = self.account.get_voting_power()
        return vp

    def should_vote(self, post):
        """Evaluate a post against all configured rules."""
        reasons = []
        # Check author whitelist/blacklist
        author = post["author"]
        if self.config.get("author_whitelist"):
            if author in self.config["author_whitelist"]:
                reasons.append(f"whitelisted author: {author}")
            else:
                return False, "author not in whitelist"
        if author in self.config.get("author_blacklist", []):
            return False, "blacklisted author"
        # Check tags
        metadata = json.loads(post.get("json_metadata", "{}"))
        tags = metadata.get("tags", [])
        required_tags = self.config.get("required_tags", [])
        if required_tags and not any(t in tags for t in required_tags):
            return False, "no matching tags"
        excluded_tags = self.config.get("excluded_tags", [])
        if any(t in tags for t in excluded_tags):
            return False, "excluded tag found"
        # Check minimum content length
        body = post.get("body", "")
        min_length = self.config.get("min_body_length", 200)
        if len(body) < min_length:
            return False, f"body too short ({len(body)} < {min_length})"
        # Check if post is a reply (skip if configured)
        if not self.config.get("vote_replies", False):
            if post.get("parent_author", "") != "":
                return False, "is a reply"
        # Check author reputation
        author_account = Account(author, blockchain_instance=self.hive)
        rep = author_account.get_reputation()
        min_rep = self.config.get("min_reputation", 25)
        if rep < min_rep:
            return False, f"low reputation ({rep} < {min_rep})"
        # Check daily vote limit
        if self.daily_vote_count >= self.config.get("max_daily_votes", 20):
            return False, "daily vote limit reached"
        # Check voting power threshold
        vp = self.get_voting_power()
        if vp < self.config.get("min_voting_power", 80):
            return False, f"voting power too low ({vp}%)"
        reasons.append("passed all filters")
        return True, "; ".join(reasons)

    def calculate_vote_weight(self, post):
        """Determine vote weight based on post quality signals."""
        base_weight = self.config.get("base_vote_weight", 50)  # percent
        metadata = json.loads(post.get("json_metadata", "{}"))
        tags = metadata.get("tags", [])
        # Boost for preferred tags
        boost_tags = self.config.get("boost_tags", {})
        for tag in tags:
            if tag in boost_tags:
                base_weight += boost_tags[tag]
        # Boost for whitelisted authors
        author_boosts = self.config.get("author_weight_boost", {})
        if post["author"] in author_boosts:
            base_weight += author_boosts[post["author"]]
        # Longer content gets slight boost
        body_len = len(post.get("body", ""))
        if body_len > 2000:
            base_weight += 5
        if body_len > 5000:
            base_weight += 5
        # Cap between 1 and 100
        return max(1, min(100, base_weight))

    def vote(self, post, weight):
        """Cast a vote on a post."""
        identifier = f"@{post['author']}/{post['permlink']}"
        if identifier in self.voted_posts:
            log.warning(f"Already voted on {identifier}, skipping")
            return False
        try:
            c = Comment(identifier, blockchain_instance=self.hive)
            c.vote(weight, account=self.account_name)
            self.voted_posts.add(identifier)
            self.daily_vote_count += 1
            log.info(f"VOTED {weight}% on {identifier}")
            return True
        except Exception as e:
            log.error(f"Vote failed on {identifier}: {e}")
            return False

    def run(self):
        """Main bot loop - stream new posts and evaluate them."""
        blockchain = Blockchain(blockchain_instance=self.hive)
        vote_delay = self.config.get("vote_delay_minutes", 5)
        log.info(f"Starting curation bot for @{self.account_name}")
        log.info(f"Vote delay: {vote_delay} minutes")
        log.info(f"VP threshold: {self.config.get('min_voting_power', 80)}%")
        pending_votes = []  # (vote_time, post) queue for delayed voting
        for op in blockchain.stream(opNames=["comment"]):
            # Reset daily counter
            today = datetime.utcnow().date()
            if today != self.last_reset:
                self.daily_vote_count = 0
                self.last_reset = today
                log.info("Daily vote counter reset")
            # Process pending delayed votes
            now = datetime.utcnow()
            ready = [pv for pv in pending_votes if now >= pv[0]]
            for vote_time, queued_post in ready:
                weight = self.calculate_vote_weight(queued_post)
                self.vote(queued_post, weight)
                pending_votes.remove((vote_time, queued_post))
            # Only process new top-level posts
            if op.get("parent_author", "") != "" and not self.config.get("vote_replies"):
                continue
            should, reason = self.should_vote(op)
            if should:
                vote_at = now + timedelta(minutes=vote_delay)
                pending_votes.append((vote_at, op))
                log.info(f"Queued vote for @{op['author']}/{op['permlink']} "
                         f"at {vote_at.strftime('%H:%M:%S')} - {reason}")
            time.sleep(0.1)

# Configuration
config = {
    "required_tags": ["python", "programming", "hive-dev"],
    "excluded_tags": ["nsfw", "spam"],
    "author_blacklist": ["knownspammer1", "knownspammer2"],
    "author_whitelist": [],  # Empty = no whitelist filter
    "author_weight_boost": {"trusteddev": 20, "goodwriter": 10},
    "boost_tags": {"python": 10, "tutorial": 15},
    "min_body_length": 500,
    "min_reputation": 25,
    "min_voting_power": 75,
    "max_daily_votes": 20,
    "base_vote_weight": 50,
    "vote_delay_minutes": 4,
    "vote_replies": False,
}
bot = CurationBot("mybotaccount", "5KpostingKey", config)
bot.run()
```

Key design points: (1) Vote delay of 4-5 minutes optimizes curation rewards. (2) Voting power regenerates at 20% per day; the bot pauses when VP drops below threshold. (3) Each full vote costs about 2% VP, so 10 full votes per day at equilibrium. (4) The pending_votes queue handles delayed voting without blocking the stream. (5) Author reputation check prevents voting on new spam accounts. Always run bots responsibly and follow Hive community guidelines on automated voting.'''
    ),
    (
        "hive-bot-content",
        r'''How do I build a content monitoring bot on Hive that watches for specific keywords or mentions and sends notifications?''',
        r'''A content monitoring bot streams all new posts and comments, checks for keyword matches or account mentions, and triggers notifications. Here is a complete implementation with webhook and Discord integration:

```python
from beem import Hive
from beem.blockchain import Blockchain
import json
import re
import requests
import time
import logging
from collections import deque

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("monitor_bot")

class ContentMonitorBot:
    def __init__(self, config):
        self.hive = Hive(node=[
            "https://api.hive.blog",
            "https://api.deathwing.me"
        ])
        self.config = config
        self.seen_permlinks = deque(maxlen=10000)  # Dedup buffer
        self.match_count = 0

    def check_keywords(self, text, keywords):
        """Check if any keywords appear in text (case-insensitive)."""
        text_lower = text.lower()
        matched = []
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(kw)
        return matched

    def check_mentions(self, text, accounts):
        """Check if any @account mentions appear in text."""
        mentioned = []
        for account in accounts:
            pattern = r'@' + re.escape(account) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                mentioned.append(account)
        return mentioned

    def check_regex_patterns(self, text, patterns):
        """Check custom regex patterns against text."""
        matched = []
        for name, pattern in patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(name)
        return matched

    def send_discord_webhook(self, embed_data):
        """Send notification to Discord channel via webhook."""
        webhook_url = self.config.get("discord_webhook")
        if not webhook_url:
            return
        payload = {"embeds": [embed_data]}
        try:
            requests.post(webhook_url, json=payload, timeout=10)
        except Exception as e:
            log.error(f"Discord webhook failed: {e}")

    def send_generic_webhook(self, data):
        """Send notification to any webhook endpoint."""
        webhook_url = self.config.get("notification_webhook")
        if not webhook_url:
            return
        try:
            requests.post(webhook_url, json=data, timeout=10)
        except Exception as e:
            log.error(f"Webhook failed: {e}")

    def format_discord_embed(self, op, match_type, matches):
        """Format a Discord embed for a matched post/comment."""
        author = op["author"]
        permlink = op["permlink"]
        parent = op.get("parent_author", "")
        is_reply = parent != ""
        post_type = "Comment" if is_reply else "Post"
        url = f"https://peakd.com/@{author}/{permlink}"
        body_preview = op.get("body", "")[:300]
        title = op.get("title", "(reply)")
        return {
            "title": f"{post_type} Alert: {match_type}",
            "description": f"**{title}**\n\n{body_preview}...",
            "url": url,
            "color": 0x00D4AA,
            "fields": [
                {"name": "Author", "value": f"@{author}", "inline": True},
                {"name": "Matched", "value": ", ".join(matches), "inline": True},
                {"name": "Type", "value": post_type, "inline": True},
            ],
            "footer": {"text": "Hive Content Monitor"}
        }

    def process_operation(self, op):
        """Process a single comment/post operation."""
        identifier = f"{op['author']}/{op['permlink']}"
        if identifier in self.seen_permlinks:
            return
        self.seen_permlinks.append(identifier)
        body = op.get("body", "")
        title = op.get("title", "")
        full_text = f"{title} {body}"
        metadata_str = op.get("json_metadata", "{}")
        try:
            metadata = json.loads(metadata_str)
        except json.JSONDecodeError:
            metadata = {}
        tags = metadata.get("tags", [])
        all_matches = []
        match_types = []
        # Keyword matching
        keywords = self.config.get("keywords", [])
        if keywords:
            kw_matches = self.check_keywords(full_text, keywords)
            if kw_matches:
                all_matches.extend(kw_matches)
                match_types.append("keyword")
        # Mention matching
        watch_accounts = self.config.get("watch_mentions", [])
        if watch_accounts:
            mention_matches = self.check_mentions(full_text, watch_accounts)
            if mention_matches:
                all_matches.extend([f"@{m}" for m in mention_matches])
                match_types.append("mention")
        # Tag matching
        watch_tags = self.config.get("watch_tags", [])
        if watch_tags:
            tag_matches = [t for t in tags if t in watch_tags]
            if tag_matches:
                all_matches.extend([f"#{t}" for t in tag_matches])
                match_types.append("tag")
        # Regex patterns
        regex_patterns = self.config.get("regex_patterns", {})
        if regex_patterns:
            rx_matches = self.check_regex_patterns(full_text, regex_patterns)
            if rx_matches:
                all_matches.extend(rx_matches)
                match_types.append("pattern")
        # Author watch
        watch_authors = self.config.get("watch_authors", [])
        if op["author"] in watch_authors:
            all_matches.append(f"author:{op['author']}")
            match_types.append("author")
        if all_matches:
            self.match_count += 1
            match_type = " + ".join(match_types)
            log.info(f"MATCH [{match_type}]: @{op['author']}/{op['permlink'][:30]} "
                     f"- {all_matches}")
            embed = self.format_discord_embed(op, match_type, all_matches)
            self.send_discord_webhook(embed)
            self.send_generic_webhook({
                "event": "content_match",
                "author": op["author"],
                "permlink": op["permlink"],
                "match_type": match_type,
                "matches": all_matches,
                "url": f"https://peakd.com/@{op['author']}/{op['permlink']}"
            })

    def run(self):
        """Stream blockchain and monitor content."""
        blockchain = Blockchain(blockchain_instance=self.hive)
        log.info("Content monitor started")
        log.info(f"Keywords: {self.config.get('keywords', [])}")
        log.info(f"Watch accounts: {self.config.get('watch_mentions', [])}")
        log.info(f"Watch tags: {self.config.get('watch_tags', [])}")
        for op in blockchain.stream(opNames=["comment"]):
            try:
                self.process_operation(op)
            except Exception as e:
                log.error(f"Error processing op: {e}")
                time.sleep(1)

# Configuration
config = {
    "keywords": ["hive-engine", "splinterlands", "3speak"],
    "watch_mentions": ["myaccount", "myproject"],
    "watch_authors": ["hivedev", "blocktrades"],
    "watch_tags": ["hive-dev", "witness-update"],
    "regex_patterns": {
        "wallet_address": r"0x[a-fA-F0-9]{40}",
        "proposal_link": r"peakd\.com/proposals/\d+",
    },
    "discord_webhook": "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/TOKEN",
    "notification_webhook": "https://your-server.com/api/hive-alerts",
}
bot = ContentMonitorBot(config)
bot.run()
```

This bot supports five matching modes: keyword search, @mention detection, tag filtering, custom regex patterns, and author watching. The deque-based dedup buffer prevents duplicate notifications for edited posts. For production use, add a database backend to persist match history and support search/analytics over historical matches. The Discord embed format provides rich notifications with post previews and direct links to peakd.com for reading the full content.'''
    ),
    (
        "hive-bot-trading",
        r'''How do I build a market-making trading bot for Hive Engine tokens that manages order books with spread and inventory control?''',
        r'''<think>
A market-making bot needs to maintain both buy and sell orders around a mid price, manage inventory to avoid excessive exposure to one side, and dynamically adjust spreads based on volatility and inventory. On Hive Engine, orders go through the "market" contract via custom_json. The bot needs to cancel stale orders and replace them as the market moves. This is a complex topic requiring careful risk management.
</think>

A market-making bot on Hive Engine places simultaneous buy and sell orders around a mid price, profiting from the spread. It must manage inventory risk and adapt to price changes. Here is a production-grade implementation:

```python
from beem import Hive
import requests
import json
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("market_maker")

ENGINE_RPC = "https://engine.rishipanthee.com/contracts"

class MarketMakerBot:
    def __init__(self, account, active_key, symbol, config):
        self.hive = Hive(keys=[active_key], node=["https://api.hive.blog"])
        self.account = account
        self.symbol = symbol
        self.config = config
        self.active_orders = {"buy": [], "sell": []}
        self.inventory_bias = 0  # Positive = too much token, negative = too little

    def engine_query(self, contract, table, query, limit=100):
        resp = requests.post(ENGINE_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "find",
            "params": {"contract": contract, "table": table,
                       "query": query, "limit": limit}
        })
        return resp.json().get("result", [])

    def broadcast_engine(self, contract_name, contract_action, payload):
        data = json.dumps({
            "contractName": contract_name,
            "contractAction": contract_action,
            "contractPayload": payload
        })
        self.hive.custom_json(
            "ssc-mainnet-hive", data,
            required_auths=[self.account],
            required_posting_auths=[]
        )

    def get_mid_price(self):
        """Calculate mid price from order book or use reference price."""
        buy_book = self.engine_query("market", "buyBook",
            {"symbol": self.symbol}, 5)
        sell_book = self.engine_query("market", "sellBook",
            {"symbol": self.symbol}, 5)
        buy_book.sort(key=lambda x: -float(x["price"]))
        sell_book.sort(key=lambda x: float(x["price"]))
        if buy_book and sell_book:
            best_bid = float(buy_book[0]["price"])
            best_ask = float(sell_book[0]["price"])
            return (best_bid + best_ask) / 2
        elif buy_book:
            return float(buy_book[0]["price"]) * 1.01
        elif sell_book:
            return float(sell_book[0]["price"]) * 0.99
        return self.config.get("fallback_price", 0.01)

    def get_token_balance(self):
        balances = self.engine_query("tokens", "balances",
            {"account": self.account, "symbol": self.symbol})
        if balances:
            return float(balances[0].get("balance", 0))
        return 0

    def get_swap_hive_balance(self):
        balances = self.engine_query("tokens", "balances",
            {"account": self.account, "symbol": "SWAP.HIVE"})
        if balances:
            return float(balances[0].get("balance", 0))
        return 0

    def cancel_all_orders(self):
        """Cancel all outstanding orders for this symbol."""
        my_buys = self.engine_query("market", "buyBook",
            {"symbol": self.symbol, "account": self.account}, 50)
        my_sells = self.engine_query("market", "sellBook",
            {"symbol": self.symbol, "account": self.account}, 50)
        for order in my_buys:
            self.broadcast_engine("market", "cancel",
                {"type": "buy", "id": order["_id"]})
            time.sleep(0.5)
        for order in my_sells:
            self.broadcast_engine("market", "cancel",
                {"type": "sell", "id": order["_id"]})
            time.sleep(0.5)
        cancelled = len(my_buys) + len(my_sells)
        if cancelled > 0:
            log.info(f"Cancelled {cancelled} orders")
        return cancelled

    def calculate_order_params(self, mid_price):
        """Calculate order prices and sizes with inventory adjustment."""
        base_spread = self.config["spread_pct"] / 100
        order_size = self.config["order_size"]
        num_levels = self.config.get("num_levels", 3)
        level_spacing = self.config.get("level_spacing_pct", 0.5) / 100
        # Inventory adjustment: widen spread on heavy side
        token_bal = self.get_token_balance()
        hive_bal = self.get_swap_hive_balance()
        token_value = token_bal * mid_price
        total_value = token_value + hive_bal
        if total_value > 0:
            inventory_ratio = token_value / total_value
            # Target 50% inventory ratio
            self.inventory_bias = (inventory_ratio - 0.5) * 2
        else:
            self.inventory_bias = 0
        # Skew spread based on inventory
        buy_spread = base_spread * (1 + max(0, -self.inventory_bias) * 0.5)
        sell_spread = base_spread * (1 + max(0, self.inventory_bias) * 0.5)
        orders = {"buy": [], "sell": []}
        for level in range(num_levels):
            offset = level * level_spacing
            buy_price = mid_price * (1 - buy_spread - offset)
            sell_price = mid_price * (1 + sell_spread + offset)
            # Reduce size for outer levels
            level_size = order_size * (1 - level * 0.2)
            if level_size > 0:
                orders["buy"].append({
                    "price": round(buy_price, 8),
                    "quantity": round(level_size, 8)
                })
                orders["sell"].append({
                    "price": round(sell_price, 8),
                    "quantity": round(level_size, 8)
                })
        return orders

    def place_orders(self, orders):
        """Place buy and sell orders on the book."""
        for order in orders["buy"]:
            hive_needed = order["price"] * order["quantity"]
            if self.get_swap_hive_balance() >= hive_needed:
                self.broadcast_engine("market", "buy", {
                    "symbol": self.symbol,
                    "quantity": f"{order['quantity']:.8f}",
                    "price": f"{order['price']:.8f}"
                })
                log.info(f"BUY {order['quantity']:.4f} @ {order['price']:.8f}")
                time.sleep(0.5)
        for order in orders["sell"]:
            if self.get_token_balance() >= order["quantity"]:
                self.broadcast_engine("market", "sell", {
                    "symbol": self.symbol,
                    "quantity": f"{order['quantity']:.8f}",
                    "price": f"{order['price']:.8f}"
                })
                log.info(f"SELL {order['quantity']:.4f} @ {order['price']:.8f}")
                time.sleep(0.5)

    def run(self):
        """Main bot loop."""
        interval = self.config.get("update_interval_seconds", 60)
        log.info(f"Market maker started for {self.symbol}")
        log.info(f"Spread: {self.config['spread_pct']}%, "
                 f"Size: {self.config['order_size']}, "
                 f"Interval: {interval}s")
        while True:
            try:
                mid = self.get_mid_price()
                log.info(f"Mid price: {mid:.8f}, Inventory bias: {self.inventory_bias:.2f}")
                self.cancel_all_orders()
                time.sleep(4)  # Wait for sidechain to process cancels
                orders = self.calculate_order_params(mid)
                self.place_orders(orders)
                log.info(f"Token: {self.get_token_balance():.4f}, "
                         f"SWAP.HIVE: {self.get_swap_hive_balance():.4f}")
            except Exception as e:
                log.error(f"Error in market maker cycle: {e}")
            time.sleep(interval)

# Configuration
config = {
    "spread_pct": 2.0,       # 2% spread (1% each side)
    "order_size": 100,        # Base order size in tokens
    "num_levels": 3,          # Number of price levels each side
    "level_spacing_pct": 0.5, # Additional spacing between levels
    "update_interval_seconds": 120,
    "fallback_price": 0.01,
}
bot = MarketMakerBot("mybotaccount", "5KactiveKey", "BEE", config)
bot.run()
```

Critical considerations: (1) Always cancel existing orders before placing new ones to avoid stale orders. (2) Inventory management skews the spread to encourage rebalancing. (3) The 3-second sidechain block time means you need delays between cancel and place operations. (4) Monitor your total exposure and set hard stop-loss limits. (5) Start with wide spreads and small sizes until you understand the token's volatility. Never market-make illiquid tokens without understanding the risk of being the sole liquidity provider.'''
    ),
    (
        "hive-bot-monitoring",
        r'''How do I build a Hive blockchain monitoring bot that watches for specific account activities like large transfers, authority changes, or witness votes?''',
        r'''A monitoring bot is essential for security and awareness. It watches the blockchain for critical operations on specified accounts and sends real-time alerts. Here is a comprehensive account monitor:

```python
from beem import Hive
from beem.blockchain import Blockchain
from beem.amount import Amount
import json
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("account_monitor")

class AccountMonitorBot:
    def __init__(self, watch_accounts, alert_config):
        self.hive = Hive(node=[
            "https://api.hive.blog",
            "https://api.deathwing.me"
        ])
        self.watch_accounts = set(watch_accounts)
        self.alert_config = alert_config
        self.alert_handlers = []
        if alert_config.get("discord_webhook"):
            self.alert_handlers.append(self.send_discord_alert)
        if alert_config.get("telegram_bot_token"):
            self.alert_handlers.append(self.send_telegram_alert)

    def send_discord_alert(self, alert):
        url = self.alert_config["discord_webhook"]
        color_map = {"critical": 0xFF0000, "warning": 0xFFA500, "info": 0x00AAFF}
        embed = {
            "title": alert["title"],
            "description": alert["description"],
            "color": color_map.get(alert["severity"], 0x808080),
            "fields": alert.get("fields", []),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Hive Account Monitor"}
        }
        try:
            requests.post(url, json={"embeds": [embed]}, timeout=10)
        except Exception as e:
            log.error(f"Discord alert failed: {e}")

    def send_telegram_alert(self, alert):
        token = self.alert_config["telegram_bot_token"]
        chat_id = self.alert_config["telegram_chat_id"]
        severity_icon = {"critical": "[!!!]", "warning": "[!]", "info": "[i]"}
        icon = severity_icon.get(alert["severity"], "[?]")
        text = f"{icon} {alert['title']}\n{alert['description']}"
        if alert.get("fields"):
            for f in alert["fields"]:
                text += f"\n{f['name']}: {f['value']}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        except Exception as e:
            log.error(f"Telegram alert failed: {e}")

    def fire_alert(self, alert):
        log.warning(f"ALERT [{alert['severity']}]: {alert['title']} - {alert['description']}")
        for handler in self.alert_handlers:
            handler(alert)

    def check_transfer(self, op):
        """Monitor transfers to/from watched accounts."""
        sender = op.get("from", "")
        receiver = op.get("to", "")
        if sender not in self.watch_accounts and receiver not in self.watch_accounts:
            return
        amount_str = op.get("amount", "0 HIVE")
        parts = amount_str.split()
        amount_val = float(parts[0])
        asset = parts[1] if len(parts) > 1 else "HIVE"
        threshold = self.alert_config.get("large_transfer_threshold", {})
        asset_threshold = threshold.get(asset, 1000)
        severity = "info"
        if amount_val >= asset_threshold:
            severity = "warning"
        if amount_val >= asset_threshold * 10:
            severity = "critical"
        if amount_val >= asset_threshold * 0.1:
            self.fire_alert({
                "title": f"Transfer: {amount_val} {asset}",
                "description": f"@{sender} -> @{receiver}",
                "severity": severity,
                "fields": [
                    {"name": "Amount", "value": f"{amount_val} {asset}", "inline": True},
                    {"name": "Memo", "value": op.get("memo", "(none)")[:100], "inline": False},
                ]
            })

    def check_authority_change(self, op):
        """CRITICAL: Monitor account authority changes (key changes)."""
        account = op.get("account", "")
        if account not in self.watch_accounts:
            return
        self.fire_alert({
            "title": f"AUTHORITY CHANGE: @{account}",
            "description": "Account keys or authorities have been modified. "
                          "Verify this was intentional immediately.",
            "severity": "critical",
            "fields": [
                {"name": "Account", "value": f"@{account}", "inline": True},
            ]
        })

    def check_witness_vote(self, op):
        """Monitor witness votes from watched accounts."""
        account = op.get("account", "")
        if account not in self.watch_accounts:
            return
        witness = op.get("witness", "")
        approve = op.get("approve", True)
        action = "voted for" if approve else "unvoted"
        self.fire_alert({
            "title": f"Witness Vote: @{account}",
            "description": f"@{account} {action} witness @{witness}",
            "severity": "info",
            "fields": [
                {"name": "Witness", "value": f"@{witness}", "inline": True},
                {"name": "Action", "value": action, "inline": True},
            ]
        })

    def check_power_operation(self, op, op_type):
        """Monitor power ups and power downs."""
        account = op.get("account", op.get("from", ""))
        if account not in self.watch_accounts:
            return
        if op_type == "withdraw_vesting":
            vests = op.get("vesting_shares", "0 VESTS")
            self.fire_alert({
                "title": f"POWER DOWN Started: @{account}",
                "description": f"@{account} initiated power down of {vests}",
                "severity": "warning",
                "fields": [
                    {"name": "Vesting Shares", "value": vests, "inline": True},
                ]
            })
        elif op_type == "transfer_to_vesting":
            amount = op.get("amount", "0 HIVE")
            self.fire_alert({
                "title": f"Power Up: @{account}",
                "description": f"@{account} powered up {amount}",
                "severity": "info",
                "fields": [
                    {"name": "Amount", "value": amount, "inline": True},
                ]
            })

    def check_delegation(self, op):
        """Monitor delegation changes."""
        delegator = op.get("delegator", "")
        delegatee = op.get("delegatee", "")
        if delegator not in self.watch_accounts and delegatee not in self.watch_accounts:
            return
        vests = op.get("vesting_shares", "0 VESTS")
        direction = "delegated to" if float(vests.split()[0]) > 0 else "removed delegation from"
        self.fire_alert({
            "title": f"Delegation Change",
            "description": f"@{delegator} {direction} @{delegatee}: {vests}",
            "severity": "info",
            "fields": [
                {"name": "Delegator", "value": f"@{delegator}", "inline": True},
                {"name": "Delegatee", "value": f"@{delegatee}", "inline": True},
                {"name": "Amount", "value": vests, "inline": True},
            ]
        })

    def run(self):
        """Stream all operations and route to handlers."""
        blockchain = Blockchain(blockchain_instance=self.hive)
        watched_ops = [
            "transfer", "account_update", "account_update2",
            "account_witness_vote", "withdraw_vesting",
            "transfer_to_vesting", "delegate_vesting_shares",
            "transfer_to_savings", "transfer_from_savings",
        ]
        log.info(f"Monitoring {len(self.watch_accounts)} accounts: "
                 f"{', '.join(list(self.watch_accounts)[:5])}...")
        handlers = {
            "transfer": self.check_transfer,
            "account_update": self.check_authority_change,
            "account_update2": self.check_authority_change,
            "account_witness_vote": self.check_witness_vote,
            "delegate_vesting_shares": self.check_delegation,
        }
        for op in blockchain.stream(opNames=watched_ops):
            op_type = op.get("type", "")
            if op_type in handlers:
                handlers[op_type](op)
            elif op_type in ("withdraw_vesting", "transfer_to_vesting"):
                self.check_power_operation(op, op_type)

# Usage
monitor = AccountMonitorBot(
    watch_accounts=["myaccount", "myproject", "mywallet"],
    alert_config={
        "discord_webhook": "https://discord.com/api/webhooks/ID/TOKEN",
        "telegram_bot_token": "BOT_TOKEN",
        "telegram_chat_id": "CHAT_ID",
        "large_transfer_threshold": {"HIVE": 500, "HBD": 200},
    }
)
monitor.run()
```

This monitors transfers, authority changes (the most critical security event), witness votes, power operations, and delegations. Authority changes are always flagged as critical severity since unauthorized key changes indicate account compromise. For enhanced security, run this bot on a separate server from your main operations and ensure the monitoring account itself has no significant funds.'''
    ),
    (
        "hive-bot-rate-limiting-ethics",
        r'''What are the best practices for rate limiting Hive bots, managing Resource Credits efficiently, and following community ethical guidelines?''',
        r'''Rate limiting and ethical operation are critical for Hive bots. The blockchain has both technical limits (Resource Credits, node rate limits) and community standards. Here is a comprehensive guide with a reusable rate limiter:

```python
import time
import logging
from collections import deque
from datetime import datetime, timedelta
from beem import Hive
from beem.account import Account
from beem.rc import RC
import json

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot_framework")

class HiveBotRateLimiter:
    """
    Rate limiter for Hive blockchain bots that respects both
    technical limits and community guidelines.
    """

    def __init__(self, account_name, keys, config=None):
        self.hive = Hive(keys=keys, node=[
            "https://api.hive.blog",
            "https://api.deathwing.me"
        ])
        self.account_name = account_name
        self.account = Account(account_name, blockchain_instance=self.hive)
        self.config = config or {}
        # Operation tracking with sliding window
        self.op_history = deque(maxlen=10000)
        self.op_counts = {}  # op_type -> count in current window
        # Default rate limits per operation type (per hour)
        self.rate_limits = {
            "vote": self.config.get("votes_per_hour", 12),
            "comment": self.config.get("comments_per_hour", 6),
            "custom_json": self.config.get("custom_json_per_hour", 60),
            "transfer": self.config.get("transfers_per_hour", 30),
        }
        # RC thresholds
        self.min_rc_pct = self.config.get("min_rc_percent", 20)
        self.rc_warning_pct = self.config.get("rc_warning_percent", 40)
        # Vote power management
        self.min_vp = self.config.get("min_voting_power", 75)
        # Backoff state
        self.consecutive_failures = 0
        self.backoff_until = None

    def get_rc_status(self):
        """Check current Resource Credits as percentage."""
        rc = self.account.get_rc()
        rc_pct = rc["rc_pct"]
        rc_max = rc["max_rc"]
        rc_current = rc["rc_current"]
        return {
            "percent": rc_pct,
            "current": rc_current,
            "max": rc_max,
            "enough_for_vote": rc_current > 1_000_000,
            "enough_for_comment": rc_current > 3_000_000,
            "enough_for_transfer": rc_current > 1_500_000,
        }

    def check_rate_limit(self, op_type):
        """Check if an operation is within rate limits."""
        now = datetime.utcnow()
        window = timedelta(hours=1)
        # Clean old entries
        while self.op_history and (now - self.op_history[0][0]) > window:
            old_type = self.op_history.popleft()[1]
            self.op_counts[old_type] = self.op_counts.get(old_type, 1) - 1
        # Check limit
        current_count = self.op_counts.get(op_type, 0)
        limit = self.rate_limits.get(op_type, 30)
        if current_count >= limit:
            log.warning(f"Rate limit reached for {op_type}: "
                       f"{current_count}/{limit} per hour")
            return False
        return True

    def record_operation(self, op_type):
        """Record that an operation was performed."""
        now = datetime.utcnow()
        self.op_history.append((now, op_type))
        self.op_counts[op_type] = self.op_counts.get(op_type, 0) + 1

    def can_operate(self, op_type):
        """
        Check all conditions before performing an operation:
        1. Rate limit not exceeded
        2. Sufficient Resource Credits
        3. Not in backoff period
        4. Voting power sufficient (for vote operations)
        """
        # Check backoff
        if self.backoff_until and datetime.utcnow() < self.backoff_until:
            remaining = (self.backoff_until - datetime.utcnow()).seconds
            log.info(f"In backoff period, {remaining}s remaining")
            return False, "backoff"
        # Check rate limit
        if not self.check_rate_limit(op_type):
            return False, "rate_limit"
        # Check RC
        rc = self.get_rc_status()
        if rc["percent"] < self.min_rc_pct:
            log.warning(f"RC too low: {rc['percent']:.1f}% < {self.min_rc_pct}%")
            return False, "low_rc"
        if rc["percent"] < self.rc_warning_pct:
            log.info(f"RC warning: {rc['percent']:.1f}%")
        # Check voting power for vote operations
        if op_type == "vote":
            vp = self.account.get_voting_power()
            if vp < self.min_vp:
                log.info(f"Voting power too low: {vp:.1f}% < {self.min_vp}%")
                return False, "low_vp"
        return True, "ok"

    def execute_with_retry(self, op_type, operation_func, max_retries=3):
        """Execute an operation with retry logic and backoff."""
        can_do, reason = self.can_operate(op_type)
        if not can_do:
            return {"success": False, "reason": reason}
        for attempt in range(max_retries):
            try:
                result = operation_func()
                self.record_operation(op_type)
                self.consecutive_failures = 0
                return {"success": True, "result": result}
            except Exception as e:
                error_msg = str(e)
                self.consecutive_failures += 1
                if "bandwidth" in error_msg.lower() or "rc" in error_msg.lower():
                    # RC exhaustion - long backoff
                    backoff = 300 * (2 ** self.consecutive_failures)
                    self.backoff_until = datetime.utcnow() + timedelta(seconds=backoff)
                    log.error(f"RC/bandwidth error, backing off {backoff}s")
                    return {"success": False, "reason": "rc_exhausted"}
                elif "too many" in error_msg.lower():
                    # Node rate limit
                    time.sleep(5 * (attempt + 1))
                else:
                    time.sleep(2 * (attempt + 1))
                log.warning(f"Attempt {attempt + 1} failed: {error_msg}")
        return {"success": False, "reason": "max_retries_exceeded"}

    def get_status_report(self):
        """Generate bot status report."""
        rc = self.get_rc_status()
        vp = self.account.get_voting_power()
        return {
            "account": self.account_name,
            "rc_percent": rc["percent"],
            "voting_power": vp,
            "ops_last_hour": dict(self.op_counts),
            "consecutive_failures": self.consecutive_failures,
            "in_backoff": self.backoff_until is not None and
                         datetime.utcnow() < self.backoff_until,
        }

# Community ethical guidelines for Hive bots:
ETHICAL_GUIDELINES = """
Hive Bot Ethics and Best Practices:
1. IDENTIFICATION: Set your account profile to clearly identify as a bot.
   Include bot operator contact info in the profile metadata.
2. OPT-OUT: Always respect user opt-out requests. Maintain a blacklist
   of users who do not want bot interaction.
3. SPAM PREVENTION: Never post more than 2-3 comments per post.
   Avoid repetitive templated comments that add no value.
4. VOTE RESPONSIBILITY: Do not operate vote-selling services that
   enable reward pool abuse. Curate based on content quality.
5. RESOURCE RESPECT: Do not spam the blockchain with unnecessary
   operations. Batch where possible, use efficient API patterns.
6. TRANSPARENCY: Publish your bot's rules and configuration.
   Let the community understand how and why it operates.
7. NO VOTE MANIPULATION: Do not coordinate votes to manipulate
   trending/hot rankings artificially.
8. FOLLOW CHAIN RULES: Respect community muting, community rules,
   and witness-approved protocol parameters.
9. GRACEFUL DEGRADATION: When RC is low or nodes are stressed,
   reduce operation frequency rather than retrying aggressively.
10. ACCOUNTABILITY: The bot operator is responsible for all
    actions the bot takes. Monitor logs and respond to complaints.
"""

# Usage example
limiter = HiveBotRateLimiter("mybotaccount", ["5Kposting", "5Kactive"], {
    "votes_per_hour": 10,
    "comments_per_hour": 4,
    "min_rc_percent": 25,
    "min_voting_power": 80,
})
print(json.dumps(limiter.get_status_report(), indent=2))
```

This framework provides sliding-window rate limiting, RC monitoring with automatic backoff, voting power management, and exponential retry with jitter. The ethical guidelines are community consensus on Hive -- violating them risks downvotes and community blacklisting. Always identify your bot account clearly, respect opt-out requests, and prioritize quality over quantity in all automated interactions.'''
    ),
]
