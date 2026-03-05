"""
Batch P1 — Blockchain: Cosmos SDK, Move language, ZK rollups, cross-chain bridges.
"""

PAIRS = [
    # --- 1. Cosmos SDK / IBC ---
    (
        "cosmos_sdk_ibc_module",
        "Explain the Cosmos SDK architecture and how to build a custom IBC-enabled blockchain module. "
        "Cover the module structure, keeper pattern, message handling, and IBC packet lifecycle.",
        """\
# Cosmos SDK Architecture & Custom IBC Modules

## Why Cosmos SDK?

Cosmos SDK enables **application-specific blockchains** (appchains) — unlike smart-contract
platforms where all dApps share one chain's throughput, each Cosmos chain is sovereign with
its own validator set and can communicate via IBC (Inter-Blockchain Communication).

Key architectural insight: Cosmos separates **consensus** (CometBFT/Tendermint) from
**application logic** (SDK modules), connected via ABCI (Application BlockChain Interface).

## SDK Module Architecture

Every module follows a consistent pattern:

```
x/mymodule/
├── keeper/          # State access layer (the "database interface")
│   ├── keeper.go    # Core keeper struct
│   ├── msg_server.go # Transaction message handlers
│   └── grpc_query.go # Query handlers
├── types/
│   ├── keys.go      # Store key prefixes
│   ├── msgs.go      # Message type definitions
│   ├── errors.go    # Sentinel errors
│   └── expected_keepers.go  # Interfaces for dependent modules
├── module.go        # AppModule interface implementation
├── genesis.go       # Import/export genesis state
└── client/
    └── cli/         # CLI transaction and query commands
```

## The Keeper Pattern

The keeper is the **only** way to read/write module state — it's an enforced boundary:

```go
package keeper

import (
    "cosmossdk.io/store/prefix"
    storetypes "cosmossdk.io/store/types"
    "github.com/cosmos/cosmos-sdk/codec"
    sdk "github.com/cosmos/cosmos-sdk/types"
)

type Keeper struct {
    cdc      codec.BinaryCodec
    storeKey storetypes.StoreKey
    // Dependencies on other modules' keepers (via interfaces, not concrete types)
    bankKeeper    types.BankKeeper
    channelKeeper types.ChannelKeeper
    portKeeper    types.PortKeeper
    scopedKeeper  types.ScopedKeeper
}

// SetData writes to the module's KV store with a prefixed key
func (k Keeper) SetData(ctx sdk.Context, key string, value types.MyData) {
    store := prefix.NewStore(ctx.KVStore(k.storeKey), types.DataPrefix)
    bz := k.cdc.MustMarshal(&value)
    store.Set([]byte(key), bz)
}

// GetData reads from the module's KV store
func (k Keeper) GetData(ctx sdk.Context, key string) (types.MyData, bool) {
    store := prefix.NewStore(ctx.KVStore(k.storeKey), types.DataPrefix)
    bz := store.Get([]byte(key))
    if bz == nil {
        return types.MyData{}, false
    }
    var data types.MyData
    k.cdc.MustUnmarshal(bz, &data)
    return data, true
}
```

**Why interfaces for dependencies?** This enables testing with mock keepers and prevents
circular imports between modules. Your module declares what it *needs* (e.g., `BankKeeper`
with `SendCoins`), not what concrete type it uses.

## Message Handling

```go
// types/msgs.go — Define the transaction message
type MsgSendCrossChain struct {
    Sender       string
    Receiver     string  // On destination chain
    ChannelId    string  // IBC channel
    Amount       sdk.Coin
    TimeoutHeight uint64
}

func (msg *MsgSendCrossChain) ValidateBasic() error {
    if _, err := sdk.AccAddressFromBech32(msg.Sender); err != nil {
        return sdkerrors.Wrap(sdkerrors.ErrInvalidAddress, "invalid sender")
    }
    if !msg.Amount.IsPositive() {
        return sdkerrors.Wrap(sdkerrors.ErrInvalidCoins, "amount must be positive")
    }
    return nil
}

// keeper/msg_server.go — Handle the message
func (k msgServer) SendCrossChain(
    goCtx context.Context,
    msg *types.MsgSendCrossChain,
) (*types.MsgSendCrossChainResponse, error) {
    ctx := sdk.UnwrapSDKContext(goCtx)

    // 1. Validate sender has funds
    sender, _ := sdk.AccAddressFromBech32(msg.Sender)

    // 2. Escrow tokens (lock them in module account)
    if err := k.bankKeeper.SendCoinsFromAccountToModule(
        ctx, sender, types.ModuleName, sdk.NewCoins(msg.Amount),
    ); err != nil {
        return nil, err
    }

    // 3. Construct IBC packet
    packet := types.CrossChainPacketData{
        Sender:   msg.Sender,
        Receiver: msg.Receiver,
        Amount:   msg.Amount,
    }

    // 4. Send via IBC
    _, err := k.channelKeeper.SendPacket(
        ctx,
        k.scopedKeeper.GetCapability(ctx, host.ChannelCapabilityPath(
            types.PortID, msg.ChannelId,
        )),
        types.PortID,
        msg.ChannelId,
        clienttypes.NewHeight(0, msg.TimeoutHeight),
        0, // timeout timestamp
        packet.GetBytes(),
    )
    if err != nil {
        return nil, err
    }

    return &types.MsgSendCrossChainResponse{}, nil
}
```

## IBC Packet Lifecycle

This is the core of cross-chain communication:

```
Chain A (source)              Relayer              Chain B (destination)
     │                           │                        │
     │ SendPacket()              │                        │
     │──────────────────────────>│                        │
     │                           │ OnRecvPacket()         │
     │                           │───────────────────────>│
     │                           │       ack              │
     │                           │<───────────────────────│
     │ OnAcknowledgementPacket() │                        │
     │<──────────────────────────│                        │
```

If timeout expires before acknowledgement:
- Relayer calls `OnTimeoutPacket()` on source chain
- Source chain must **refund** the escrowed tokens

```go
// IBCModule interface — your module implements these
func (im IBCModule) OnRecvPacket(
    ctx sdk.Context,
    packet channeltypes.Packet,
    relayer sdk.AccAddress,
) exported.Acknowledgement {
    var data types.CrossChainPacketData
    if err := types.ModuleCdc.UnmarshalJSON(packet.GetData(), &data); err != nil {
        return channeltypes.NewErrorAcknowledgement(err)
    }

    // Mint or unlock tokens on destination
    receiver, _ := sdk.AccAddressFromBech32(data.Receiver)
    if err := im.keeper.bankKeeper.MintCoins(
        ctx, types.ModuleName, sdk.NewCoins(data.Amount),
    ); err != nil {
        return channeltypes.NewErrorAcknowledgement(err)
    }
    im.keeper.bankKeeper.SendCoinsFromModuleToAccount(
        ctx, types.ModuleName, receiver, sdk.NewCoins(data.Amount),
    )

    return channeltypes.NewResultAcknowledgement([]byte{1})
}

func (im IBCModule) OnTimeoutPacket(
    ctx sdk.Context,
    packet channeltypes.Packet,
    relayer sdk.AccAddress,
) error {
    // MUST refund — this is a safety invariant
    var data types.CrossChainPacketData
    types.ModuleCdc.UnmarshalJSON(packet.GetData(), &data)

    sender, _ := sdk.AccAddressFromBech32(data.Sender)
    return im.keeper.bankKeeper.SendCoinsFromModuleToAccount(
        ctx, types.ModuleName, sender, sdk.NewCoins(data.Amount),
    )
}
```

## Production Considerations

1. **Light client verification**: IBC doesn't trust relayers — every packet is verified against
   the counterparty chain's light client. Relayers are permissionless message carriers.

2. **Channel ordering**: Use UNORDERED channels for most cases (better liveness). ORDERED
   channels halt if one packet times out.

3. **Packet fee middleware**: IBC v7+ supports paying relayers via the fee middleware module.

4. **Interchain Accounts (ICA)**: Execute transactions on remote chains without deploying
   code there — your chain controls an account on chain B via IBC messages.

5. **Interchain Queries (ICQ)**: Read state from remote chains trustlessly.

The Cosmos SDK + IBC stack enables a network of sovereign, interoperable blockchains — each
optimized for its use case while sharing liquidity and state through standardized protocols.
"""
    ),

    # --- 2. Move Language (Aptos/Sui) ---
    (
        "move_language_resource_model",
        "Explain the Move programming language's resource-oriented model, how it prevents common "
        "smart contract vulnerabilities, and show a complete token implementation on Aptos with "
        "comparison to Solidity's approach.",
        """\
# Move Language: Resource-Oriented Smart Contracts

## Why Move Matters

Move was designed at Facebook/Meta specifically to handle **digital assets safely**. Its key
innovation is the **resource model** — inspired by linear type theory, where resources
(tokens, NFTs, accounts) cannot be copied, implicitly dropped, or double-spent at the
**language level**, not just at the runtime level.

This is fundamentally different from Solidity, where a token balance is just a `uint256` in a
mapping — the EVM doesn't know it represents value.

## Resource Safety: How Move Prevents Vulnerabilities

### Solidity's Reentrancy Problem
```solidity
// VULNERABLE Solidity — the DAO hack pattern
mapping(address => uint256) balances;

function withdraw(uint256 amount) external {
    require(balances[msg.sender] >= amount);
    // BUG: External call BEFORE state update
    (bool ok, ) = msg.sender.call{value: amount}("");
    require(ok);
    balances[msg.sender] -= amount;  // Too late — attacker re-entered
}
```

### Move Makes This Impossible
```move
module token::managed_coin {
    use std::signer;

    // `store` = can be stored in global storage
    // `key` = can be a top-level resource
    // NO `copy` or `drop` — this is the magic
    struct Coin has store, key {
        value: u64,
    }

    struct CoinStore has key {
        coin: Coin,
    }

    // Withdraw returns the Coin resource — it MUST be used somewhere
    // The compiler ensures it cannot be dropped or duplicated
    public fun withdraw(account: &signer, amount: u64): Coin acquires CoinStore {
        let addr = signer::address_of(account);
        let coin_store = borrow_global_mut<CoinStore>(addr);
        assert!(coin_store.coin.value >= amount, 1);
        coin_store.coin.value = coin_store.coin.value - amount;
        // Return a new Coin resource — caller MUST do something with it
        Coin { value: amount }
    }

    // Deposit consumes the Coin resource — it's moved, not copied
    public fun deposit(addr: address, coin: Coin) acquires CoinStore {
        let coin_store = borrow_global_mut<CoinStore>(addr);
        let Coin { value } = coin;  // Destructure = consume the resource
        coin_store.coin.value = coin_store.coin.value + value;
    }

    // Transfer is withdraw + deposit — atomic, no reentrancy possible
    public entry fun transfer(
        from: &signer,
        to: address,
        amount: u64,
    ) acquires CoinStore {
        let coin = withdraw(from, amount);
        deposit(to, coin);
    }
}
```

**Why reentrancy can't happen:**
1. `withdraw` returns a `Coin` resource — it's a **value**, not a balance update
2. The `Coin` has no `copy` ability — it can't be duplicated
3. The `Coin` has no `drop` ability — it MUST be consumed (deposited somewhere)
4. Move's borrow checker prevents holding mutable references across calls
5. No external calls with callbacks — no reentrancy vector

## Complete Aptos Token with Advanced Features

```move
module my_addr::loyalty_token {
    use std::signer;
    use std::string::String;
    use aptos_framework::event;
    use aptos_framework::timestamp;
    use aptos_framework::account;

    /// Errors
    const E_NOT_ADMIN: u64 = 1;
    const E_INSUFFICIENT_BALANCE: u64 = 2;
    const E_EXPIRED: u64 = 3;

    /// The token itself — linear type, no copy/drop
    struct LoyaltyPoint has store {
        value: u64,
        earned_at: u64,  // Timestamp
        expires_at: u64, // Points can expire!
    }

    /// User's point wallet
    struct PointWallet has key {
        points: vector<LoyaltyPoint>,
        total_earned: u64,
        tier: u8,  // 0=bronze, 1=silver, 2=gold
    }

    /// Admin capability — whoever holds this can mint
    /// Using capability pattern instead of address checks
    struct AdminCap has key, store {}

    /// Events
    #[event]
    struct MintEvent has drop, store {
        to: address,
        amount: u64,
        expires_at: u64,
    }

    #[event]
    struct RedeemEvent has drop, store {
        from: address,
        amount: u64,
        reward: String,
    }

    /// Initialize — only called once during module publish
    fun init_module(admin: &signer) {
        move_to(admin, AdminCap {});
    }

    /// Mint loyalty points to a user
    public entry fun mint(
        admin: &signer,
        to: address,
        amount: u64,
        validity_days: u64,
    ) acquires PointWallet {
        // Capability check — must possess AdminCap
        assert!(exists<AdminCap>(signer::address_of(admin)), E_NOT_ADMIN);

        let now = timestamp::now_seconds();
        let expires = now + (validity_days * 86400);

        // Ensure wallet exists
        if (!exists<PointWallet>(to)) {
            let wallet_signer = account::create_signer_with_capability(
                // In production, use resource accounts
                &account::create_test_signer_cap(to)
            );
            move_to(&wallet_signer, PointWallet {
                points: vector::empty(),
                total_earned: 0,
                tier: 0,
            });
        };

        let wallet = borrow_global_mut<PointWallet>(to);
        let point = LoyaltyPoint {
            value: amount,
            earned_at: now,
            expires_at: expires,
        };
        vector::push_back(&mut wallet.points, point);
        wallet.total_earned = wallet.total_earned + amount;

        // Update tier
        wallet.tier = if (wallet.total_earned >= 10000) { 2 }
                      else if (wallet.total_earned >= 5000) { 1 }
                      else { 0 };

        event::emit(MintEvent { to, amount, expires_at: expires });
    }

    /// Get valid (non-expired) balance
    public fun valid_balance(addr: address): u64 acquires PointWallet {
        if (!exists<PointWallet>(addr)) return 0;

        let wallet = borrow_global<PointWallet>(addr);
        let now = timestamp::now_seconds();
        let total = 0u64;
        let i = 0;
        while (i < vector::length(&wallet.points)) {
            let point = vector::borrow(&wallet.points, i);
            if (point.expires_at > now) {
                total = total + point.value;
            };
            i = i + 1;
        };
        total
    }

    /// Redeem points — consumes oldest non-expired points first (FIFO)
    public entry fun redeem(
        user: &signer,
        amount: u64,
        reward: String,
    ) acquires PointWallet {
        let addr = signer::address_of(user);
        let wallet = borrow_global_mut<PointWallet>(addr);
        let now = timestamp::now_seconds();

        let remaining = amount;
        let i = 0;
        while (remaining > 0 && i < vector::length(&wallet.points)) {
            let point = vector::borrow_mut(&mut wallet.points, i);
            if (point.expires_at <= now) {
                // Skip expired — will clean up later
                i = i + 1;
                continue
            };
            if (point.value <= remaining) {
                remaining = remaining - point.value;
                point.value = 0;  // Consumed
            } else {
                point.value = point.value - remaining;
                remaining = 0;
            };
            i = i + 1;
        };
        assert!(remaining == 0, E_INSUFFICIENT_BALANCE);

        // Clean up zero-value points
        let j = 0;
        while (j < vector::length(&wallet.points)) {
            if (vector::borrow(&wallet.points, j).value == 0) {
                let LoyaltyPoint { value: _, earned_at: _, expires_at: _ } =
                    vector::swap_remove(&mut wallet.points, j);
                // Destructured = properly consumed (no drop ability)
            } else {
                j = j + 1;
            };
        };

        event::emit(RedeemEvent { from: addr, amount, reward });
    }
}
```

## Move vs Solidity — Vulnerability Prevention Summary

| Vulnerability          | Solidity Risk | Move Prevention                         |
|------------------------|---------------|------------------------------------------|
| Reentrancy             | HIGH          | No callbacks, linear resources           |
| Integer overflow       | MEDIUM        | Checked arithmetic by default (aborts)   |
| Double-spend           | MEDIUM        | Resources can't be copied (no `copy`)    |
| Lost tokens            | HIGH          | Resources can't be dropped (no `drop`)   |
| Access control bypass  | HIGH          | Capability pattern (AdminCap resource)   |
| Storage collision      | MEDIUM        | Type-safe global storage, no raw slots   |
| Uninitialized storage  | LOW           | All fields must be initialized            |
| Front-running          | EXISTS        | Still possible (not a language issue)     |

## Key Takeaway

Move shifts safety from **runtime checks** (require statements, modifiers) to **compile-time
guarantees** (the type system itself). A well-typed Move program cannot lose assets, duplicate
them, or leave them in limbo — the compiler simply won't allow it. This is why Move is
considered the most significant advance in smart contract language design since Solidity.
"""
    ),

    # --- 3. Zero-Knowledge Rollups ---
    (
        "zk_rollups_architecture",
        "Explain how ZK rollups work for Ethereum scaling, covering the proof generation pipeline, "
        "data availability, and how to write ZK circuits. Compare zkEVM approaches (Polygon zkEVM, "
        "zkSync Era, Scroll) and explain the tradeoffs.",
        """\
# Zero-Knowledge Rollups: Ethereum Scaling via Validity Proofs

## The Scaling Problem

Ethereum L1 processes ~15 TPS with ~$1-50 gas fees during congestion. ZK rollups solve this
by executing transactions off-chain and posting a **succinct validity proof** to L1 that
proves all transactions were executed correctly — without re-executing them.

## How ZK Rollups Work

```
                       ZK Rollup Architecture

Users ──> Sequencer ──> Executor ──> Prover ──> L1 Contract
              │              │           │           │
         Order txs     Execute &    Generate     Verify proof
                       compute      ZK proof     + store state
                       state diff   (SNARK/      root
                                    STARK)

Data flow:
1. Users submit txs to sequencer (centralized or decentralized)
2. Sequencer orders and batches transactions
3. Executor runs transactions, produces state diff
4. Prover generates cryptographic proof of correct execution
5. L1 verifier contract checks proof + accepts new state root
6. Transaction data posted to L1 for data availability
```

## The Proof Generation Pipeline

### Step 1: Arithmetization — Turning Computation into Math

Every computation must be expressed as polynomial constraints:

```python
# Conceptual: A simple transfer in a ZK circuit
# "Prove that sender_balance >= amount AND new_sender_balance = old - amount"

# This becomes polynomial constraints:
# 1. range_check(sender_balance)  — balance is non-negative
# 2. sender_balance - amount >= 0 — sufficient funds
# 3. new_sender_balance = sender_balance - amount
# 4. new_receiver_balance = receiver_balance + amount
# 5. merkle_proof(old_root, sender_leaf) is valid
# 6. merkle_proof(new_root, new_sender_leaf) is valid

# In practice, each "simple" operation expands to thousands of constraints
# A single ECDSA signature verification ≈ 500,000 constraints
```

### Step 2: Writing ZK Circuits (Circom Example)

```circom
// circuits/transfer.circom
pragma circom 2.1.0;

include "circomlib/poseidon.circom";
include "circomlib/comparators.circom";
include "circomlib/mux1.circom";

template Transfer() {
    // Public inputs (known to verifier)
    signal input old_state_root;
    signal input new_state_root;
    signal input amount;

    // Private inputs (only prover knows)
    signal input sender_balance;
    signal input receiver_balance;
    signal input sender_key;
    signal input sender_path[20];  // Merkle proof
    signal input receiver_path[20];

    // Constraint 1: Sender has sufficient balance
    component gte = GreaterEqThan(64);
    gte.in[0] <== sender_balance;
    gte.in[1] <== amount;
    gte.out === 1;

    // Constraint 2: New balances are correct
    signal new_sender_balance;
    new_sender_balance <== sender_balance - amount;

    signal new_receiver_balance;
    new_receiver_balance <== receiver_balance + amount;

    // Constraint 3: Merkle proof validates against old root
    component old_hash = Poseidon(2);
    old_hash.inputs[0] <== sender_key;
    old_hash.inputs[1] <== sender_balance;
    // ... verify Merkle path up to old_state_root

    // Constraint 4: New Merkle root is correct
    component new_hash = Poseidon(2);
    new_hash.inputs[0] <== sender_key;
    new_hash.inputs[1] <== new_sender_balance;
    // ... verify Merkle path produces new_state_root
}

component main {public [old_state_root, new_state_root, amount]} = Transfer();
```

### Step 3: Proof Systems

```
SNARK vs STARK comparison:

┌─────────────────┬──────────────────┬──────────────────┐
│                  │ SNARKs (Groth16) │ STARKs           │
├─────────────────┼──────────────────┼──────────────────┤
│ Proof size      │ ~200 bytes       │ ~50-200 KB       │
│ Verify time     │ ~1ms             │ ~5-50ms          │
│ Prove time      │ Fast             │ Slower           │
│ Trusted setup   │ YES (toxic waste)│ NO               │
│ Quantum safe    │ NO               │ YES              │
│ L1 gas cost     │ ~200K gas        │ ~500K-1M gas     │
│ Used by         │ Polygon zkEVM    │ StarkNet         │
│                 │ zkSync Era       │                   │
│                 │ Scroll           │                   │
└─────────────────┴──────────────────┴──────────────────┘

Modern trend: Use STARKs internally (no trusted setup, fast prover)
then wrap in a SNARK for cheap L1 verification. Best of both worlds.
```

## Data Availability

**Critical design choice**: Where does transaction data live?

```
Option 1: Calldata (current)
  - Post compressed tx data as L1 calldata
  - Cost: ~16 gas/byte (was 68 before EIP-4844)
  - Every L1 node stores it forever

Option 2: EIP-4844 Blobs (post-Dencun)
  - Post data as "blobs" — available for ~18 days
  - Cost: ~1 gas/byte (separate blob gas market)
  - Enough time for anyone to reconstruct state
  - 10-100x cheaper than calldata

Option 3: Validium (off-chain DA)
  - Data stored off-chain (committee, DAC, Celestia)
  - Cheapest but weaker security guarantee
  - If DA layer fails, funds can be frozen (not stolen)

Option 4: Volition (hybrid)
  - Users choose per-transaction: on-chain or off-chain DA
  - zkSync Era and StarkNet support this
```

## zkEVM Approaches Compared

The holy grail: run existing Solidity smart contracts inside a ZK proof.

### Type 1: Ethereum-equivalent (Taiko, Scroll aims for this)
```
- Proves actual Ethereum execution (same opcodes, same state layout)
- Any Ethereum tool works unmodified
- Slowest proving time (~hours per block)
- Most compatible, least performant
```

### Type 2: EVM-equivalent (Scroll, Polygon zkEVM)
```
- Proves EVM execution with minor differences
- 99% of contracts work, some edge cases differ
- Proving time: minutes to hours
- Good compatibility/performance balance
```

### Type 2.5: EVM-equivalent except gas costs (Polygon zkEVM)
```
- Different gas costs for ZK-expensive operations
- Some opcodes cost more (KECCAK256 is expensive in circuits)
- Most contracts work, gas optimization may differ
```

### Type 3: Almost EVM-equivalent (Scroll historical)
```
- Most EVM features but some missing
- Contracts may need minor modifications
- Faster proving
```

### Type 4: High-level language equivalent (zkSync Era)
```
- Compiles Solidity/Vyper to custom VM (zkSync's EraVM)
- Assembly-level differences from EVM
- Fastest proving, most custom
- Some low-level EVM tricks don't work
- Unique advantages: native account abstraction, paymaster
```

## Cost Comparison (approximate, post-EIP-4844)

```
Simple ETH transfer costs:
  L1 Ethereum:      ~21,000 gas × $30/M gas = ~$0.63
  Optimistic rollup: ~$0.01-0.05
  ZK rollup:         ~$0.005-0.02
  Validium:          ~$0.001-0.005

Why ZK < Optimistic for simple txs:
  - Proof cost is amortized across thousands of txs in a batch
  - No 7-day challenge period (finality in ~minutes, not days)
  - Proof verification: fixed ~200K-500K gas regardless of batch size
  - 1000 txs in batch → verification cost per tx is tiny
```

## Key Tradeoff Summary

**Choose ZK rollup when**: Fast finality needed, bridging speed matters, high throughput
**Choose Optimistic rollup when**: EVM compatibility is paramount, simpler tech stack
**Choose Validium when**: Cost is primary concern, can accept DA committee trust assumption

The ZK rollup space is converging: most projects aim for Type 1/2 zkEVM with STARK proving
and SNARK wrapping, using EIP-4844 blobs for DA. The endgame is ZK-proving Ethereum itself.
"""
    ),

    # --- 4. Cross-Chain Bridges and Security ---
    (
        "cross_chain_bridge_security",
        "Explain cross-chain bridge architectures, the major bridge hacks (Ronin, Wormhole, Nomad), "
        "what went wrong in each, and how to design a secure bridge. Include specific code patterns "
        "for the verification layer.",
        """\
# Cross-Chain Bridge Security: Lessons from $2B+ in Hacks

## Why Bridges Are The Hardest Problem

Cross-chain bridges must solve an impossible problem: **verifying the state of Chain A on
Chain B** without either chain natively understanding the other. Every bridge is a
trade-off between trust assumptions, cost, latency, and security.

## Bridge Architecture Patterns

```
1. LOCK-AND-MINT (most common)
   Chain A: Lock tokens in bridge contract
   Bridge:  Verify lock event, signal to Chain B
   Chain B: Mint wrapped tokens

2. LIQUIDITY POOL (Across, Stargate)
   Chain A: Deposit to pool
   Bridge:  Match with liquidity on Chain B
   Chain B: Release from pool (native tokens, not wrapped)
   Advantage: No wrapped tokens, faster

3. ATOMIC SWAP (trustless, limited)
   Uses hash time-locked contracts (HTLCs)
   No intermediary, but limited to simple transfers
```

## Major Bridge Hacks — What Went Wrong

### 1. Ronin Bridge ($624M, March 2022)

**Architecture**: 9-of-9 multisig (later 5-of-9 for "gas optimization")

```
What happened:
- Axie Infinity's Ronin bridge used a validator multisig
- Sky Mavis (the company) controlled 4 of 9 validators
- Axie DAO had delegated signing authority to Sky Mavis "temporarily"
  (this was never revoked — a governance failure)
- Attacker compromised Sky Mavis infrastructure → got 5 keys
- 5-of-9 threshold met → attacker drained bridge

Root cause: CENTRALIZATION + POOR KEY MANAGEMENT
- Too few validators (9 is tiny)
- One organization controlled majority
- No monitoring for large withdrawals
- Hack went undetected for 6 DAYS
```

**Lesson**: A multisig bridge is only as strong as its weakest signer. The validator set
must be large, diverse, and economically aligned.

### 2. Wormhole ($320M, February 2022)

**Architecture**: Guardian network (19 validators) verifying VAAs (Verified Action Approvals)

```solidity
// SIMPLIFIED vulnerable code pattern
function completeTransfer(bytes memory encodedVM) public {
    // Parse the VAA (Verified Action Approval)
    (IWormhole.VM memory vm, bool valid, ) = wormhole.parseAndVerifyVM(encodedVM);

    // BUG: On Solana side, the signature verification used a
    // deprecated/unpatched system program
    // Attacker created a fake SignatureSet account that passed verification
    // without valid guardian signatures

    // The Solana contract called `verify_signatures` with a spoofed
    // sysvar account instead of the real Instructions sysvar
    // This made the contract think signatures were valid when they weren't
}
```

**Root cause**: LOGIC BUG IN SIGNATURE VERIFICATION
- Solana's `verify_signatures` instruction accepted a user-supplied account
  as the "Instructions sysvar" instead of enforcing the real system address
- Attacker passed a fake account containing pre-crafted "valid" signatures
- No additional validation that the sysvar was actually the system sysvar

### 3. Nomad Bridge ($190M, August 2022)

**Architecture**: Optimistic verification with fraud proofs

```solidity
// THE BUG — in the Replica contract
function process(bytes memory _message) public returns (bool _success) {
    bytes32 _messageHash = keccak256(_message);

    // This check was supposed to verify the message was "proven"
    // against a valid Merkle root
    require(acceptableRoot(messages[_messageHash]), "not accepted");

    // PROBLEM: During a routine upgrade, the trusted root was
    // initialized to 0x000...000
    // AND messages[_messageHash] for unprocessed messages returns 0x000...000
    // So: acceptableRoot(0x000...000) returned TRUE

    // Anyone could process ANY message — just copy a valid tx,
    // change the recipient address, and replay
    // This became a "free-for-all" — hundreds of copycats
}
```

**Root cause**: INITIALIZATION BUG
- Upgrade set trusted root to `bytes32(0)` (the zero hash)
- Unprocessed messages default to `bytes32(0)` in the mapping
- `0 == 0` → all messages accepted as valid
- Once one person exploited it, anyone could copy the exploit tx and change the recipient

## Secure Bridge Design Patterns

### Pattern 1: Light Client Verification (strongest)

```solidity
// Verify source chain's consensus directly — no trust assumptions
contract LightClientBridge {
    // Store verified block headers from source chain
    mapping(uint256 => bytes32) public verifiedHeaders;

    // Verify a block header using the source chain's consensus rules
    function submitHeader(
        bytes calldata header,
        bytes calldata validatorSigs,
        bytes calldata validatorSet
    ) external {
        // Verify >= 2/3 validator signatures (for BFT chains)
        require(
            verifyConsensusSignatures(header, validatorSigs, validatorSet),
            "insufficient signatures"
        );

        // Verify validator set matches what we know
        require(
            keccak256(validatorSet) == knownValidatorSetHash,
            "unknown validator set"
        );

        uint256 blockNum = parseBlockNumber(header);
        verifiedHeaders[blockNum] = keccak256(header);
    }

    // Verify a specific transaction/event occurred using Merkle proof
    function verifyEvent(
        uint256 blockNum,
        bytes calldata proof,
        bytes calldata eventData
    ) external view returns (bool) {
        require(verifiedHeaders[blockNum] != bytes32(0), "header not verified");

        // Verify Merkle proof against the receipts root in the verified header
        return MerkleProof.verify(
            proof,
            getReceiptsRoot(verifiedHeaders[blockNum]),
            keccak256(eventData)
        );
    }
}
```

### Pattern 2: Defense-in-Depth for Multisig Bridges

```solidity
contract SecureBridge {
    uint256 public constant WITHDRAWAL_DELAY = 1 hours;
    uint256 public constant LARGE_THRESHOLD = 1_000_000e18;
    uint256 public constant DAILY_LIMIT = 10_000_000e18;

    mapping(bytes32 => uint256) public pendingWithdrawals;
    uint256 public dailyWithdrawn;
    uint256 public lastDayReset;

    // Rate limiting — prevents draining in one tx
    modifier withinDailyLimit(uint256 amount) {
        if (block.timestamp > lastDayReset + 1 days) {
            dailyWithdrawn = 0;
            lastDayReset = block.timestamp;
        }
        require(dailyWithdrawn + amount <= DAILY_LIMIT, "daily limit exceeded");
        dailyWithdrawn += amount;
        _;
    }

    // Time-lock large withdrawals
    function initiateWithdrawal(
        bytes32 messageHash,
        uint256 amount,
        address recipient
    ) external onlyVerified(messageHash) withinDailyLimit(amount) {
        if (amount >= LARGE_THRESHOLD) {
            // Large withdrawals get a time delay — allows monitoring
            pendingWithdrawals[messageHash] = block.timestamp;
            emit LargeWithdrawalQueued(messageHash, amount, recipient);
        } else {
            _executeWithdrawal(messageHash, amount, recipient);
        }
    }

    function finalizeWithdrawal(bytes32 messageHash) external {
        require(pendingWithdrawals[messageHash] != 0, "not pending");
        require(
            block.timestamp >= pendingWithdrawals[messageHash] + WITHDRAWAL_DELAY,
            "delay not met"
        );
        // Guardian can cancel during delay if suspicious
        require(!cancelled[messageHash], "cancelled by guardian");

        delete pendingWithdrawals[messageHash];
        _executeWithdrawal(...);
    }

    // Emergency pause — circuit breaker
    function emergencyPause() external onlyGuardian {
        _pause();
        emit EmergencyPause(msg.sender, block.timestamp);
    }
}
```

### Security Checklist for Bridge Builders

1. **Never trust a single verification method** — layer light clients + multisig + rate limits
2. **Rate limit everything** — daily caps, per-tx limits, time delays for large amounts
3. **Monitor and alert** — Ronin went 6 days undetected. Real-time monitoring is mandatory
4. **Diverse validator sets** — different organizations, geographies, infrastructure
5. **Upgradability with timelocks** — Nomad's instant upgrade enabled the zero-root bug
6. **Formal verification of core logic** — the bridge contract is THE highest-value target
7. **Bug bounty proportional to TVL** — Wormhole's bounty was $10M (appropriate for $1B+ TVL)
8. **Assume compromise, design for containment** — even if validators are compromised, limit damage

The future of bridges is **ZK light clients** — verify source chain consensus with a ZK proof
on the destination chain. No trust assumptions, no multisig, no optimistic delays. Projects
like Succinct and Lagrange are building this now.
"""
    ),

    # --- 5. DeFi Composability & Flash Loans ---
    (
        "defi_composability_flash_loans",
        "Explain DeFi composability and flash loans — how atomic multi-protocol interactions work, "
        "the mechanics of flash loans, common use cases (arbitrage, liquidation, collateral swaps), "
        "and how to build a flash loan bot with proper MEV protection.",
        """\
# DeFi Composability & Flash Loans

## What is Composability?

DeFi's superpower is **composability** — any protocol can call any other protocol in a single
atomic transaction. This is possible because all protocols share the same execution environment
(the EVM) and state (Ethereum's storage). If any step in a composed transaction fails, the
entire transaction reverts — all or nothing.

This creates "money legos" — you can snap protocols together:
- Borrow from Aave → Swap on Uniswap → Provide liquidity on Curve → Stake LP token
- All in one transaction. If the final step fails, everything unwinds.

## Flash Loan Mechanics

A flash loan is an **uncollateralized loan that must be repaid within the same transaction**.
This sounds impossible, but it works because of atomicity:

```
Transaction execution:
1. Borrow 1,000,000 USDC from Aave (no collateral needed)
2. Use the USDC for some operation (arbitrage, liquidation, etc.)
3. Repay 1,000,000 USDC + 0.09% fee to Aave
4. If step 3 fails → entire transaction reverts → loan never happened

The EVM guarantees: either ALL steps succeed, or NONE do.
The lender has ZERO risk — the loan either gets repaid or it never existed.
```

### Implementing a Flash Loan Receiver

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@aave/v3-core/contracts/flashloan/base/FlashLoanSimpleReceiverBase.sol";
import "@aave/v3-core/contracts/interfaces/IPoolAddressesProvider.sol";
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";

contract FlashLoanArbitrage is FlashLoanSimpleReceiverBase {
    ISwapRouter public immutable uniswapRouter;
    ISwapRouter public immutable sushiRouter;
    address public immutable owner;

    constructor(
        IPoolAddressesProvider provider,
        ISwapRouter _uniswap,
        ISwapRouter _sushi
    ) FlashLoanSimpleReceiverBase(provider) {
        uniswapRouter = _uniswap;
        sushiRouter = _sushi;
        owner = msg.sender;
    }

    /// @notice Called by Aave after funds are transferred to this contract
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,  // The flash loan fee
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        // Only Aave pool can call this
        require(msg.sender == address(POOL), "caller must be pool");
        require(initiator == address(this), "initiator must be this contract");

        // Decode strategy parameters
        (address tokenB, uint24 uniPoolFee, uint24 sushiPoolFee) =
            abi.decode(params, (address, uint24, uint24));

        // Step 1: Buy tokenB on Uniswap (where it's cheaper)
        IERC20(asset).approve(address(uniswapRouter), amount);
        uint256 tokenBAmount = uniswapRouter.exactInputSingle(
            ISwapRouter.ExactInputSingleParams({
                tokenIn: asset,
                tokenOut: tokenB,
                fee: uniPoolFee,
                recipient: address(this),
                deadline: block.timestamp,
                amountIn: amount,
                amountOutMinimum: 0,  // In production: use oracle price
                sqrtPriceLimitX96: 0
            })
        );

        // Step 2: Sell tokenB on Sushiswap (where it's more expensive)
        IERC20(tokenB).approve(address(sushiRouter), tokenBAmount);
        uint256 amountReturned = sushiRouter.exactInputSingle(
            ISwapRouter.ExactInputSingleParams({
                tokenIn: tokenB,
                tokenOut: asset,
                fee: sushiPoolFee,
                recipient: address(this),
                deadline: block.timestamp,
                amountIn: tokenBAmount,
                amountOutMinimum: amount + premium,  // Must cover loan + fee
                sqrtPriceLimitX96: 0
            })
        );

        // Step 3: Approve Aave to pull back loan + premium
        uint256 amountOwed = amount + premium;
        IERC20(asset).approve(address(POOL), amountOwed);

        // Profit stays in this contract
        // amountReturned - amountOwed = profit

        return true;  // Tells Aave the operation succeeded
    }

    /// @notice Initiate the flash loan
    function executeArbitrage(
        address asset,
        uint256 amount,
        address tokenB,
        uint24 uniPoolFee,
        uint24 sushiPoolFee
    ) external {
        require(msg.sender == owner, "only owner");

        bytes memory params = abi.encode(tokenB, uniPoolFee, sushiPoolFee);

        POOL.flashLoanSimple(
            address(this),  // receiverAddress
            asset,          // asset to borrow
            amount,         // amount
            params,         // passed to executeOperation
            0               // referralCode
        );
    }

    /// @notice Withdraw profits
    function withdrawProfit(address token) external {
        require(msg.sender == owner, "only owner");
        uint256 balance = IERC20(token).balanceOf(address(this));
        IERC20(token).transfer(owner, balance);
    }
}
```

## Common Flash Loan Use Cases

### 1. Arbitrage (shown above)
Buy cheap on DEX A, sell expensive on DEX B, profit from price difference.

### 2. Liquidation
```
1. Flash borrow USDC
2. Repay undercollateralized position on Aave/Compound
3. Receive collateral (ETH) at discount (usually 5-10%)
4. Sell ETH for USDC on DEX
5. Repay flash loan
6. Keep the liquidation bonus
```

### 3. Collateral Swap (no unwinding needed)
```
1. Flash borrow DAI
2. Repay your Aave DAI debt
3. Withdraw your ETH collateral from Aave
4. Swap ETH → WBTC on Uniswap
5. Deposit WBTC as new collateral on Aave
6. Borrow DAI against WBTC
7. Repay flash loan
Result: Swapped collateral from ETH to WBTC without any liquidation risk
```

### 4. Self-Liquidation
```
1. Flash borrow enough to repay your entire debt
2. Repay debt, withdraw collateral
3. Sell collateral to repay flash loan
Result: Closed leveraged position in one tx, avoided gradual liquidation penalties
```

## MEV Protection

**MEV (Maximal Extractable Value)** means your profitable flash loan tx can be:
- **Front-run**: Someone sees your tx in the mempool, copies it, pays more gas
- **Sandwiched**: Attacker manipulates price before and after your swap

### Protection strategies:

```solidity
// 1. Private transaction submission (Flashbots Protect)
// Submit tx directly to block builders, skipping the public mempool
// Use: flashbots RPC endpoint instead of public RPC

// 2. Slippage protection — ALWAYS set minimum output
amountOutMinimum: expectedOutput * 995 / 1000  // Max 0.5% slippage

// 3. Deadline protection
deadline: block.timestamp  // Tx is only valid in current block
// Prevents tx from being held and executed later at worse price

// 4. Access control — prevent others from calling your bot
modifier onlyOwner() {
    require(msg.sender == owner, "not owner");
    _;
}

// 5. Commit-reveal for larger operations
// Phase 1: Commit hash of your operation parameters
// Phase 2: Reveal and execute (MEV searchers can't front-run what they can't see)
```

### Flashbots Bundle Submission (Python)

```python
from web3 import Web3
from flashbots import flashbot

w3 = Web3(Web3.HTTPProvider("https://rpc.flashbots.net"))
flashbot(w3, signer)  # Your private key for signing bundles

# Build the transaction
arb_tx = contract.functions.executeArbitrage(
    USDC_ADDRESS, amount, WETH_ADDRESS, 3000, 3000
).build_transaction({
    'from': account.address,
    'nonce': w3.eth.get_transaction_count(account.address),
    'maxFeePerGas': Web3.to_wei(50, 'gwei'),
    'maxPriorityFeePerGas': Web3.to_wei(2, 'gwei'),
})

signed_tx = account.sign_transaction(arb_tx)

# Submit as Flashbots bundle — goes directly to builders, not mempool
bundle = [{"signed_transaction": signed_tx.rawTransaction}]
block_number = w3.eth.block_number

# Try for next 3 blocks
for target_block in range(block_number + 1, block_number + 4):
    result = w3.flashbots.send_bundle(bundle, target_block_number=target_block)
    print(f"Bundle submitted for block {target_block}: {result}")
```

## Economics Reality Check

Flash loan arbitrage is extremely competitive:
- Simple two-DEX arbitrage: mostly extracted by MEV bots with faster infrastructure
- Profitable opportunities: multi-hop paths, cross-chain, exotic pairs, new protocol launches
- You compete against teams with custom hardware, direct builder relationships, and colocated nodes
- Most individual flash loan arb bots lose money to gas costs

The real value of understanding flash loans is **defensive** — knowing how your protocol can
be exploited via flash loans helps you build safer DeFi applications.
"""
    ),
]
