"""Hive blockchain training pairs: layer 2 solutions and sidechains."""

PAIRS = [
    (
        "hive/vsc-smart-contracts",
        r'''What is VSC (Virtual Smart Contracts) on Hive, and how do I develop smart contracts for it?''',
        r'''VSC (Virtual Smart Contracts) brings programmable smart contracts to the Hive ecosystem. It is a layer-2 solution that uses Hive as the settlement layer while executing smart contract logic off-chain. Here is an overview and how to develop for it:

```javascript
// VSC Smart Contract Development
// VSC uses JavaScript/TypeScript for smart contracts
// Contracts are executed in a sandboxed VM

// Example: A simple token contract on VSC
const contract = {
    // Contract state
    state: {
        balances: {},
        totalSupply: 0,
        name: "MyVSCToken",
        symbol: "MVSC",
        decimals: 3
    },

    // Initialize the contract
    init(params) {
        this.state.name = params.name || "MyVSCToken";
        this.state.symbol = params.symbol || "MVSC";
        this.state.totalSupply = 0;
    },

    // Mint tokens (only contract owner)
    mint(to, amount) {
        if (this.msg.sender !== this.owner) {
            throw new Error("Only owner can mint");
        }
        const current = this.state.balances[to] || 0;
        this.state.balances[to] = current + amount;
        this.state.totalSupply += amount;

        this.emit("Transfer", {from: null, to, amount});
    },

    // Transfer tokens
    transfer(to, amount) {
        const sender = this.msg.sender;
        const senderBalance = this.state.balances[sender] || 0;

        if (senderBalance < amount) {
            throw new Error("Insufficient balance");
        }
        if (amount <= 0) {
            throw new Error("Amount must be positive");
        }

        this.state.balances[sender] = senderBalance - amount;
        this.state.balances[to] = (this.state.balances[to] || 0) + amount;

        this.emit("Transfer", {from: sender, to, amount});
    },

    // Query balance
    balanceOf(account) {
        return this.state.balances[account] || 0;
    }
};

// Deploying a VSC contract from Hive
// VSC contracts are deployed via custom_json on Hive

const dhive = require("@hiveio/dhive");
const client = new dhive.Client(["https://api.hive.blog"]);

async function deployVSCContract(account, activeKey, contractCode) {
    const key = dhive.PrivateKey.fromString(activeKey);

    // VSC deployment uses a specific custom_json format
    const deployPayload = {
        action: "deploy_contract",
        contract: {
            code: contractCode,
            name: "my-token-contract",
            version: "1.0.0"
        }
    };

    const op = {
        required_auths: [account],
        required_posting_auths: [],
        id: "vsc.network",
        json: JSON.stringify(deployPayload)
    };

    const result = await client.broadcast.json(op, key);
    console.log("Contract deployed:", result.id);
    return result;
}

// Interacting with a VSC contract
async function callContract(account, postingKey, contractId, method, args) {
    const key = dhive.PrivateKey.fromString(postingKey);

    const callPayload = {
        action: "call_contract",
        contract_id: contractId,
        method: method,
        args: args
    };

    const op = {
        required_auths: [],
        required_posting_auths: [account],
        id: "vsc.network",
        json: JSON.stringify(callPayload)
    };

    return await client.broadcast.json(op, key);
}

// Example usage:
// await callContract("alice", key, "contract123", "transfer", ["bob", 100]);
```

VSC is still evolving. Key concepts: contracts are written in JavaScript, state is maintained by VSC nodes, and all contract calls are recorded on Hive via custom_json for verifiability. VSC aims to bring Ethereum-like programmability to Hive without the gas fees.
'''
    ),
    (
        "hive/hive-engine-smart-contracts",
        r'''How do Hive Engine smart contracts work? Can I create custom contracts on the sidechain?''',
        r'''Hive Engine uses a smart contract system where contracts are written in JavaScript and executed by sidechain nodes. While most users interact with built-in contracts (tokens, market, nft), custom contracts can be deployed:

```javascript
// Hive Engine Smart Contract Structure
// Contracts are JavaScript modules with specific lifecycle methods

// Example: A simple lottery contract
const contract = {
    // Called when contract is deployed
    createSSC: async function() {
        // Initialize contract tables (like database tables)
        await api.db.createTable("lotteries", ["id", "creator"]);
        await api.db.createTable("tickets", ["lotteryId", "buyer"]);
    },

    // Custom action: create a new lottery
    createLottery: async function(payload) {
        const {ticketPrice, maxTickets, prizeToken} = payload;
        const creator = api.sender;

        // Validate inputs
        if (!ticketPrice || ticketPrice <= 0) {
            return api.assert(false, "Invalid ticket price");
        }

        const lottery = {
            id: api.transactionId,
            creator: creator,
            ticketPrice: ticketPrice.toString(),
            maxTickets: parseInt(maxTickets),
            prizeToken: prizeToken,
            ticketsSold: 0,
            status: "active",
            createdAt: api.blockNumber
        };

        await api.db.insert("lotteries", lottery);
        api.emit("lotteryCreated", {id: lottery.id, creator});
    },

    // Custom action: buy a ticket
    buyTicket: async function(payload) {
        const {lotteryId} = payload;
        const buyer = api.sender;

        const lottery = await api.db.findOne("lotteries", {id: lotteryId});
        if (!lottery) return api.assert(false, "Lottery not found");
        if (lottery.status !== "active") return api.assert(false, "Lottery closed");
        if (lottery.ticketsSold >= lottery.maxTickets) {
            return api.assert(false, "Sold out");
        }

        // Transfer ticket price from buyer to contract
        const transferred = await api.executeSmartContract(
            "tokens", "transferToContract",
            {symbol: lottery.prizeToken, quantity: lottery.ticketPrice}
        );
        if (!transferred) return;

        // Record the ticket
        const ticket = {
            lotteryId: lotteryId,
            buyer: buyer,
            number: lottery.ticketsSold + 1,
            blockNum: api.blockNumber
        };
        await api.db.insert("tickets", ticket);

        // Update lottery
        lottery.ticketsSold += 1;
        await api.db.update("lotteries", lottery);

        api.emit("ticketBought", {lotteryId, buyer, number: ticket.number});
    },

    // Custom action: draw winner
    drawWinner: async function(payload) {
        const {lotteryId} = payload;
        const lottery = await api.db.findOne("lotteries", {id: lotteryId});

        if (!lottery) return api.assert(false, "Not found");
        if (api.sender !== lottery.creator) {
            return api.assert(false, "Only creator can draw");
        }

        const tickets = await api.db.find("tickets", {lotteryId});
        if (tickets.length === 0) return api.assert(false, "No tickets");

        // Deterministic random using block hash
        const seed = api.blockNumber + api.transactionId;
        const winnerIndex = parseInt(seed, 16) % tickets.length;
        const winner = tickets[winnerIndex];

        // Transfer prize to winner
        const totalPrize = parseFloat(lottery.ticketPrice) * lottery.ticketsSold;
        await api.executeSmartContract(
            "tokens", "transferFromContract",
            {
                to: winner.buyer,
                symbol: lottery.prizeToken,
                quantity: totalPrize.toString()
            }
        );

        lottery.status = "completed";
        lottery.winner = winner.buyer;
        await api.db.update("lotteries", lottery);

        api.emit("winnerDrawn", {lotteryId, winner: winner.buyer, prize: totalPrize});
    }
};

// Deploying a Hive Engine smart contract requires:
// 1. BEE tokens for deployment fee
// 2. Broadcasting via custom_json with id "ssc-mainnet-hive"
// 3. The contract code must follow the HE contract API

// Interaction from Python
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json
import json

def call_he_contract(account, key, contract_name, action, payload):
    hive = Hive(node=["https://api.hive.blog"], keys=[key])
    data = {
        "contractName": contract_name,
        "contractAction": action,
        "contractPayload": payload
    }
    op = Custom_json(**{
        "required_auths": [account],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps(data)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account, "active")
    tx.sign()
    return tx.broadcast()
```

Hive Engine contracts use the `api` object for database operations, token transfers, and event emission. Custom contracts can interact with built-in contracts (tokens, market, nft) through `api.executeSmartContract`. Deployment costs BEE tokens and requires approval from the sidechain governance.
'''
    ),
    (
        "hive/sidechain-bridges",
        r'''How do bridges between Hive and other blockchains work? Show me how wrapped HIVE tokens function.''',
        r'''Blockchain bridges on Hive enable cross-chain asset transfers. The most common pattern uses a custodial bridge with multi-sig security. Here is how they work:

```python
# Bridge Architecture for Hive
#
# Hive <-> Bridge Contract <-> External Chain (ETH, BSC, etc.)
#
# Deposit flow (Hive -> Wrapped):
# 1. User sends HIVE to bridge account on Hive
# 2. Bridge validators confirm the deposit
# 3. Wrapped HIVE is minted on the external chain
#
# Withdrawal flow (Wrapped -> Hive):
# 1. User burns wrapped HIVE on external chain
# 2. Bridge validators confirm the burn
# 3. Real HIVE is sent from bridge account to user

from beem import Hive
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
import json
import hashlib
import time

class HiveBridgeMonitor:
    """Monitor a Hive bridge account for deposits."""

    def __init__(self, bridge_account, nodes=None):
        self.bridge_account = bridge_account
        self.hive = Hive(node=nodes or ["https://api.hive.blog"])
        self.processed_txs = set()

    def parse_bridge_memo(self, memo):
        """Parse bridge memo format.

        Expected format: BRIDGE:<chain>:<address>
        Example: BRIDGE:ETH:0x1234...abcd
        """
        if not memo.startswith("BRIDGE:"):
            return None
        parts = memo.split(":")
        if len(parts) < 3:
            return None
        return {
            "chain": parts[1],
            "address": parts[2],
            "raw": memo
        }

    def stream_deposits(self, callback):
        """Stream deposits to the bridge account."""
        blockchain = Blockchain(hive_instance=self.hive)
        stream = blockchain.stream(
            opNames=["transfer"],
            raw_ops=False,
            threading=False
        )

        for op in stream:
            if op.get("to") != self.bridge_account:
                continue

            tx_id = f"{op.get('block_num')}:{op.get('from')}:{op.get('amount')}"
            if tx_id in self.processed_txs:
                continue

            bridge_info = self.parse_bridge_memo(op.get("memo", ""))
            if not bridge_info:
                continue

            amount_str = op.get("amount", "0 HIVE")
            parts = amount_str.split()
            amount = float(parts[0])
            asset = parts[1] if len(parts) > 1 else "HIVE"

            deposit = {
                "from": op["from"],
                "amount": amount,
                "asset": asset,
                "target_chain": bridge_info["chain"],
                "target_address": bridge_info["address"],
                "block": op.get("block_num"),
                "tx_hash": hashlib.sha256(tx_id.encode()).hexdigest()
            }

            self.processed_txs.add(tx_id)
            callback(deposit)

class HiveBridgeWithdrawer:
    """Process withdrawals from the bridge (send HIVE to users)."""

    def __init__(self, bridge_account, active_key, nodes=None):
        self.account = bridge_account
        self.hive = Hive(
            node=nodes or ["https://api.hive.blog"],
            keys=[active_key]
        )

    def process_withdrawal(self, to_account, amount, asset, external_tx_hash):
        """Send HIVE/HBD for a confirmed external chain burn."""
        memo = f"Bridge withdrawal: {external_tx_hash}"

        op = Transfer(**{
            "from": self.account,
            "to": to_account,
            "amount": f"{amount:.3f} {asset}",
            "memo": memo
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()
        print(f"Withdrawal: {amount:.3f} {asset} -> @{to_account}")
        return result

# Hive Engine bridge (SWAP.HIVE)
def deposit_to_hive_engine(account, active_key, amount):
    """Deposit HIVE to get SWAP.HIVE on Hive Engine."""
    hive = Hive(node=["https://api.hive.blog"], keys=[active_key])
    op = Transfer(**{
        "from": account,
        "to": "honey-swap",  # Official Hive Engine gateway
        "amount": f"{amount:.3f} HIVE",
        "memo": account  # Your HE account (usually same)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account, "active")
    tx.sign()
    return tx.broadcast()

def withdraw_from_hive_engine(account, active_key, amount):
    """Withdraw SWAP.HIVE to get HIVE back."""
    hive = Hive(node=["https://api.hive.blog"], keys=[active_key])
    payload = {
        "contractName": "hivepegged",
        "contractAction": "withdraw",
        "contractPayload": {"quantity": str(amount)}
    }
    from beembase.operations import Custom_json
    op = Custom_json(**{
        "required_auths": [account],
        "required_posting_auths": [],
        "id": "ssc-mainnet-hive",
        "json": json.dumps(payload)
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account, "active")
    tx.sign()
    return tx.broadcast()

# monitor = HiveBridgeMonitor("bridge-account")
# monitor.stream_deposits(lambda d: print(f"Deposit: {d}"))
```

Bridge security considerations: use multi-signature bridge accounts (no single point of failure), require multiple validator confirmations before minting wrapped tokens, implement rate limits and maximum transfer sizes, and maintain transparent reserves that can be audited on-chain. The SWAP.HIVE bridge (honey-swap) is the most used bridge on Hive for connecting to the Hive Engine sidechain.
'''
    ),
    (
        "hive/cross-chain-communication",
        r'''How do I implement cross-chain communication patterns between Hive and other blockchains?''',
        r'''Cross-chain communication between Hive and other chains typically uses an oracle/relay pattern. Here is a practical implementation:

```python
import json
import time
import hashlib
from web3 import Web3
from beem import Hive
from beem.blockchain import Blockchain
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Custom_json

class CrossChainRelay:
    """Relay messages between Hive and an EVM chain."""

    def __init__(self, hive_account, hive_key, eth_rpc, eth_private_key):
        self.hive = Hive(
            node=["https://api.hive.blog"],
            keys=[hive_key]
        )
        self.hive_account = hive_account
        self.w3 = Web3(Web3.HTTPProvider(eth_rpc))
        self.eth_key = eth_private_key

    def hive_to_eth(self, data):
        """Send a message from Hive to an EVM chain.

        Pattern:
        1. Broadcast custom_json on Hive with the message
        2. Oracle detects the custom_json
        3. Oracle submits proof to EVM contract
        """
        payload = {
            "action": "cross_chain_message",
            "target": "eth",
            "data": data,
            "nonce": int(time.time()),
            "hash": hashlib.sha256(json.dumps(data).encode()).hexdigest()
        }

        op = Custom_json(**{
            "required_auths": [self.hive_account],
            "required_posting_auths": [],
            "id": "cross-chain-relay",
            "json": json.dumps(payload)
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.hive_account, "active")
        tx.sign()
        result = tx.broadcast()
        print(f"Hive message sent: {result.get('id', 'unknown')}")
        return result

    def watch_hive_messages(self, callback):
        """Watch for cross-chain messages on Hive."""
        blockchain = Blockchain(hive_instance=self.hive)
        stream = blockchain.stream(
            opNames=["custom_json"],
            raw_ops=False,
            threading=False
        )
        for op in stream:
            if op.get("id") != "cross-chain-relay":
                continue
            try:
                data = json.loads(op["json"])
                if data.get("action") == "cross_chain_message":
                    callback(data, op)
            except (json.JSONDecodeError, KeyError):
                continue

    def eth_to_hive(self, message, target_account):
        """Relay a message from EVM chain to Hive.

        The relay broadcasts a custom_json on Hive containing
        the EVM transaction data as proof.
        """
        payload = {
            "action": "eth_relay",
            "source_chain": "ethereum",
            "target_account": target_account,
            "message": message,
            "relayed_at": int(time.time())
        }

        op = Custom_json(**{
            "required_auths": [self.hive_account],
            "required_posting_auths": [],
            "id": "cross-chain-relay",
            "json": json.dumps(payload)
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.hive_account, "active")
        tx.sign()
        return tx.broadcast()

# Cross-chain message verification
class MessageVerifier:
    """Verify cross-chain messages using merkle proofs."""

    @staticmethod
    def create_message_hash(sender, data, nonce):
        """Create a deterministic hash for message verification."""
        msg = f"{sender}:{json.dumps(data, sort_keys=True)}:{nonce}"
        return hashlib.sha256(msg.encode()).hexdigest()

    @staticmethod
    def verify_hive_message(tx_id, expected_hash, hive_instance):
        """Verify a Hive transaction contains the expected message."""
        try:
            tx = hive_instance.rpc.get_transaction(
                {"id": tx_id}, api="condenser_api"
            )
            for op in tx.get("operations", []):
                if isinstance(op, list) and op[0] == "custom_json":
                    data = json.loads(op[1]["json"])
                    if data.get("hash") == expected_hash:
                        return True
        except Exception:
            pass
        return False

# Usage
# relay = CrossChainRelay("relaybot", "5ActiveKey", "https://eth-rpc.com", "0xEthKey")
# relay.hive_to_eth({"action": "lock_tokens", "amount": 100})
# relay.watch_hive_messages(lambda data, op: print(f"Message: {data}"))
```

Cross-chain patterns on Hive:
- Oracle relay: Trusted relayers submit proofs between chains
- Hash time-locked contracts: Atomic swaps using hash locks
- Multi-sig bridges: Multiple validators must agree on transfers
- Light client verification: Verify Hive block headers on EVM chains

All cross-chain messages on Hive use custom_json, which provides an immutable, timestamped record that can be verified by any party.
'''
    ),
    (
        "hive/wrapped-hive-tokens",
        r'''How do wrapped HIVE tokens work on external chains, and how do I interact with them programmatically?''',
        r'''Wrapped HIVE tokens (like wHIVE on Ethereum or BSC) represent HIVE locked on the Hive blockchain, with equivalent tokens minted on the external chain. Here is how the system works and how to interact with it:

```python
# Wrapped HIVE Architecture
#
# 1. User deposits HIVE to a custodial/multi-sig account on Hive
# 2. Bridge service detects the deposit
# 3. Equivalent wHIVE is minted on the external chain
# 4. User can trade wHIVE on DEXes (Uniswap, PancakeSwap, etc.)
# 5. To unwrap: burn wHIVE on external chain -> receive HIVE on Hive

from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Transfer
import json

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5YourActiveKey"]
)

# Wrapping: Deposit HIVE to get wHIVE
def wrap_hive(account, amount, target_chain, target_address):
    """Deposit HIVE to receive wrapped HIVE on another chain.

    The memo must contain the target chain and address
    so the bridge knows where to mint.
    """
    # Different bridges use different memo formats
    # This is a generic pattern
    memo = f"wrap:{target_chain}:{target_address}"

    op = Transfer(**{
        "from": account,
        "to": "hive-bridge",  # Bridge custody account
        "amount": f"{amount:.3f} HIVE",
        "memo": memo
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Wrap initiated: {amount:.3f} HIVE -> {target_chain}")
    print(f"Target: {target_address}")
    return result

# Using Hive Engine's SWAP.HIVE (most common wrapped HIVE)
def get_swap_hive(account, amount):
    """Convert HIVE to SWAP.HIVE on Hive Engine."""
    op = Transfer(**{
        "from": account,
        "to": "honey-swap",
        "amount": f"{amount:.3f} HIVE",
        "memo": account
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(account, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Deposited {amount:.3f} HIVE for SWAP.HIVE")
    return result

# Check wrapped token reserves (transparency)
def check_bridge_reserves(bridge_account):
    """Verify the bridge has sufficient HIVE reserves."""
    from beem.account import Account
    acct = Account(bridge_account, hive_instance=hive)
    hive_balance = str(acct["balance"])
    hbd_balance = str(acct["hbd_balance"])
    savings_hbd = str(acct["savings_hbd_balance"])

    print(f"Bridge reserves (@{bridge_account}):")
    print(f"  HIVE:         {hive_balance}")
    print(f"  HBD:          {hbd_balance}")
    print(f"  HBD savings:  {savings_hbd}")

    return {
        "hive": hive_balance,
        "hbd": hbd_balance,
        "savings_hbd": savings_hbd
    }

# Verify 1:1 peg (wrapped supply == locked reserves)
def verify_peg(bridge_account, wrapped_supply_url=None):
    """Verify that wrapped token supply matches locked reserves."""
    reserves = check_bridge_reserves(bridge_account)
    locked_hive = float(str(reserves["hive"]).split()[0])

    # In production, query the external chain for circulating supply
    # of the wrapped token
    print(f"\nLocked HIVE:         {locked_hive:,.3f}")
    print("Compare with wrapped token circulating supply")
    print("If locked >= circulating, the peg is sound")

    return locked_hive

# Monitor bridge transactions
def monitor_bridge_activity(bridge_account, limit=20):
    """Monitor recent bridge deposits and withdrawals."""
    from beem.account import Account
    acct = Account(bridge_account, hive_instance=hive)
    history = acct.get_account_history(
        index=-1, limit=limit, only_ops=["transfer"]
    )

    deposits = []
    withdrawals = []

    for entry in history:
        op = entry["op"]
        op_data = op[1] if isinstance(op, list) else op
        if op_data.get("to") == bridge_account:
            deposits.append(op_data)
        elif op_data.get("from") == bridge_account:
            withdrawals.append(op_data)

    print(f"\nRecent bridge activity for @{bridge_account}:")
    print(f"  Deposits (last {limit}):    {len(deposits)}")
    print(f"  Withdrawals (last {limit}): {len(withdrawals)}")

    for d in deposits[:5]:
        print(f"  IN:  @{d['from']} deposited {d['amount']}")
    for w in withdrawals[:5]:
        print(f"  OUT: {w['amount']} -> @{w['to']}")

# check_bridge_reserves("honey-swap")
# verify_peg("honey-swap")
```

Wrapped token security: always verify the bridge reserves match the circulating supply of the wrapped token. Reputable bridges use multi-sig custody, publish regular audits, and maintain transparent on-chain reserves. The honey-swap bridge for SWAP.HIVE is the most trusted and widely used wrapper on Hive.
'''
    ),
]
