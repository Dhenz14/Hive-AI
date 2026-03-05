"""Smart contract patterns — Solidity ERC standards, reentrancy guards, upgradeable proxies, gas optimization, Foundry testing."""

PAIRS = [
    (
        "smart-contracts/erc20-token",
        "Implement a production ERC-20 token in Solidity with minting caps, pausability, permit (EIP-2612) for gasless approvals, flash minting, and snapshot-based voting power, using OpenZeppelin v5 patterns.",
        '''Production ERC-20 token with permits, flash minting, snapshots, and governance integration:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {ERC20Pausable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import {ERC20Votes} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import {ERC20FlashMint} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20FlashMint.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Nonces} from "@openzeppelin/contracts/utils/Nonces.sol";

/**
 * @title HiveToken
 * @notice ERC-20 with permits (gasless approval), voting power, flash loans,
 *         role-based minting, pausability, and hard supply cap.
 *
 * Roles:
 *   DEFAULT_ADMIN_ROLE — can grant/revoke roles
 *   MINTER_ROLE        — can mint up to maxSupply
 *   PAUSER_ROLE        — can pause/unpause transfers
 */
contract HiveToken is
    ERC20,
    ERC20Burnable,
    ERC20Pausable,
    ERC20Permit,
    ERC20Votes,
    ERC20FlashMint,
    AccessControl
{
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    uint256 public immutable maxSupply;
    uint256 public flashFeeRate; // basis points (1 = 0.01%)

    /// @notice Treasury address that receives flash mint fees
    address public flashFeeTreasury;

    error ExceedsMaxSupply(uint256 requested, uint256 available);
    error ZeroAddress();

    event FlashFeeRateUpdated(uint256 oldRate, uint256 newRate);
    event FlashFeeTreasuryUpdated(address oldTreasury, address newTreasury);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 maxSupply_,
        uint256 initialMint_,
        address admin_,
        address treasury_
    ) ERC20(name_, symbol_) ERC20Permit(name_) {
        if (admin_ == address(0) || treasury_ == address(0)) revert ZeroAddress();
        if (initialMint_ > maxSupply_) {
            revert ExceedsMaxSupply(initialMint_, maxSupply_);
        }

        maxSupply = maxSupply_;
        flashFeeRate = 10; // 0.1% default flash loan fee
        flashFeeTreasury = treasury_;

        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(MINTER_ROLE, admin_);
        _grantRole(PAUSER_ROLE, admin_);

        if (initialMint_ > 0) {
            _mint(admin_, initialMint_);
        }
    }

    // --- Minting with supply cap ---

    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        if (totalSupply() + amount > maxSupply) {
            revert ExceedsMaxSupply(amount, maxSupply - totalSupply());
        }
        _mint(to, amount);
    }

    // --- Pausability ---

    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(PAUSER_ROLE) {
        _unpause();
    }

    // --- Flash Mint configuration ---

    function setFlashFeeRate(uint256 newRate) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit FlashFeeRateUpdated(flashFeeRate, newRate);
        flashFeeRate = newRate;
    }

    function setFlashFeeTreasury(address newTreasury) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (newTreasury == address(0)) revert ZeroAddress();
        emit FlashFeeTreasuryUpdated(flashFeeTreasury, newTreasury);
        flashFeeTreasury = newTreasury;
    }

    /// @dev Override flash fee: percentage of loan amount
    function flashFee(
        address token,
        uint256 amount
    ) public view override returns (uint256) {
        if (token != address(this)) revert ERC3156UnsupportedToken(token);
        return (amount * flashFeeRate) / 10_000;
    }

    /// @dev Flash fee goes to treasury, not burned
    function flashFeeReceiver() public view override returns (address) {
        return flashFeeTreasury;
    }

    // --- Override resolution for multiple inheritance ---

    function _update(
        address from,
        address to,
        uint256 value
    ) internal override(ERC20, ERC20Pausable, ERC20Votes) {
        super._update(from, to, value);
    }

    function nonces(
        address owner
    ) public view override(ERC20Permit, Nonces) returns (uint256) {
        return super.nonces(owner);
    }
}
```

```solidity
// test/HiveToken.t.sol — Foundry tests for the token
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {HiveToken} from "../src/HiveToken.sol";
import {IERC3156FlashBorrower} from "@openzeppelin/contracts/interfaces/IERC3156FlashBorrower.sol";

contract MockBorrower is IERC3156FlashBorrower {
    bytes32 private constant CALLBACK_SUCCESS = keccak256("ERC3156FlashBorrower.onFlashLoan");

    function onFlashLoan(
        address,
        address token,
        uint256 amount,
        uint256 fee,
        bytes calldata
    ) external override returns (bytes32) {
        HiveToken(token).approve(msg.sender, amount + fee);
        return CALLBACK_SUCCESS;
    }
}

contract HiveTokenTest is Test {
    HiveToken public token;
    MockBorrower public borrower;

    address admin = makeAddr("admin");
    address treasury = makeAddr("treasury");
    address user1 = makeAddr("user1");
    address user2 = makeAddr("user2");

    uint256 constant MAX_SUPPLY = 1_000_000_000 ether;
    uint256 constant INITIAL_MINT = 100_000_000 ether;

    function setUp() public {
        token = new HiveToken(
            "Hive Token", "HIVE", MAX_SUPPLY, INITIAL_MINT, admin, treasury
        );
        borrower = new MockBorrower();
    }

    function test_InitialState() public view {
        assertEq(token.name(), "Hive Token");
        assertEq(token.symbol(), "HIVE");
        assertEq(token.maxSupply(), MAX_SUPPLY);
        assertEq(token.totalSupply(), INITIAL_MINT);
        assertEq(token.balanceOf(admin), INITIAL_MINT);
    }

    function test_MintUpToMaxSupply() public {
        uint256 remaining = MAX_SUPPLY - INITIAL_MINT;
        vm.prank(admin);
        token.mint(user1, remaining);
        assertEq(token.totalSupply(), MAX_SUPPLY);
    }

    function test_RevertMintExceedsMax() public {
        uint256 remaining = MAX_SUPPLY - INITIAL_MINT;
        vm.prank(admin);
        vm.expectRevert();
        token.mint(user1, remaining + 1);
    }

    function test_PauseBlocksTransfers() public {
        vm.prank(admin);
        token.transfer(user1, 1000 ether);

        vm.prank(admin);
        token.pause();

        vm.prank(user1);
        vm.expectRevert();
        token.transfer(user2, 500 ether);

        vm.prank(admin);
        token.unpause();

        vm.prank(user1);
        token.transfer(user2, 500 ether);
        assertEq(token.balanceOf(user2), 500 ether);
    }

    function test_PermitGaslessApproval() public {
        uint256 ownerPk = 0xA11CE;
        address owner = vm.addr(ownerPk);

        vm.prank(admin);
        token.transfer(owner, 1000 ether);

        uint256 deadline = block.timestamp + 1 hours;
        uint256 nonce = token.nonces(owner);

        bytes32 structHash = keccak256(abi.encode(
            keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"),
            owner, user1, 500 ether, nonce, deadline
        ));
        bytes32 digest = keccak256(abi.encodePacked(
            "\\x19\\x01",
            token.DOMAIN_SEPARATOR(),
            structHash
        ));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerPk, digest);

        vm.prank(user1);
        token.permit(owner, user1, 500 ether, deadline, v, r, s);
        assertEq(token.allowance(owner, user1), 500 ether);
    }

    function test_FlashMint() public {
        uint256 loanAmount = 10_000 ether;
        uint256 fee = token.flashFee(address(token), loanAmount);

        vm.prank(admin);
        token.transfer(address(borrower), fee);

        uint256 treasuryBefore = token.balanceOf(treasury);

        vm.prank(address(borrower));
        token.flashLoan(borrower, address(token), loanAmount, "");

        assertEq(token.balanceOf(treasury), treasuryBefore + fee);
        assertEq(token.balanceOf(address(borrower)), 0);
    }

    function test_VotingPowerDelegation() public {
        vm.prank(admin);
        token.transfer(user1, 1000 ether);

        vm.prank(user1);
        token.delegate(user1);
        assertEq(token.getVotes(user1), 1000 ether);

        vm.prank(user1);
        token.delegate(user2);
        assertEq(token.getVotes(user1), 0);
        assertEq(token.getVotes(user2), 1000 ether);
    }

    function testFuzz_MintNeverExceedsMax(uint256 amount) public {
        amount = bound(amount, 1, type(uint256).max);
        uint256 remaining = MAX_SUPPLY - token.totalSupply();

        vm.prank(admin);
        if (amount <= remaining) {
            token.mint(user1, amount);
            assertLe(token.totalSupply(), MAX_SUPPLY);
        } else {
            vm.expectRevert();
            token.mint(user1, amount);
        }
    }
}
```

| Feature | Pattern | Gas Impact |
|---|---|---|
| EIP-2612 Permit | Gasless approval via EIP-712 signature | User pays 0, relayer pays ~50k |
| ERC-3156 Flash Mint | Uncollateralized flash loans of native token | ~80k gas per flash loan |
| ERC20Votes | Checkpoint-based voting power delegation | Extra ~30k per transfer |
| Supply cap | Immutable maxSupply enforced in mint() | Minimal (one SLOAD) |
| Pausable | Emergency circuit breaker for transfers | ~2.5k per transfer check |

Key Solidity patterns:
- Use `immutable` for values set once in constructor (cheaper than storage reads)
- Custom errors (`error ExceedsMaxSupply(...)`) save gas vs `require` strings
- Multiple inheritance requires explicit `_update` override resolution
- Foundry fuzz tests (`testFuzz_`) automatically explore edge cases
- EIP-2612 permits enable meta-transactions without separate approve() call
'''
    ),
    (
        "smart-contracts/erc721-nft",
        "Build an ERC-721 NFT contract with lazy minting (off-chain signatures), royalties (EIP-2981), metadata reveal, merkle proof allowlists, and on-chain SVG generation.",
        '''ERC-721 NFT with lazy minting, royalties, reveal mechanism, and allowlists:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721Enumerable} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import {ERC721Royalty} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721Royalty.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";

/**
 * @title HiveNFT
 * @notice ERC-721 with lazy minting via EIP-712 vouchers, merkle allowlist,
 *         delayed metadata reveal, EIP-2981 royalties, and on-chain SVG.
 */
contract HiveNFT is ERC721Enumerable, ERC721Royalty, EIP712, Ownable {
    using Strings for uint256;
    using Strings for address;

    struct MintVoucher {
        uint256 tokenId;
        uint256 price;
        address minter;       // 0x0 = anyone can redeem
        uint256 expiry;
    }

    uint256 public constant MAX_SUPPLY = 10_000;
    uint256 public constant ALLOWLIST_PRICE = 0.05 ether;
    uint256 public constant PUBLIC_PRICE = 0.08 ether;
    uint256 public constant MAX_PER_WALLET = 5;

    bytes32 public merkleRoot;
    bool public revealed;
    bool public allowlistActive;
    bool public publicSaleActive;
    string private _baseTokenURI;
    string private _unrevealedURI;

    address public voucherSigner;
    uint256 private _nextTokenId = 1;

    mapping(address => uint256) public mintCount;
    mapping(uint256 => bool) public voucherRedeemed;

    bytes32 private constant VOUCHER_TYPEHASH = keccak256(
        "MintVoucher(uint256 tokenId,uint256 price,address minter,uint256 expiry)"
    );

    error MaxSupplyReached();
    error MaxPerWalletExceeded();
    error InsufficientPayment();
    error SaleNotActive();
    error InvalidProof();
    error VoucherExpired();
    error VoucherAlreadyRedeemed();
    error InvalidVoucherSignature();
    error AlreadyRevealed();

    event Revealed(string baseURI);
    event AllowlistUpdated(bytes32 newRoot);
    event LazyMint(uint256 indexed tokenId, address indexed minter, uint256 price);

    constructor(
        string memory unrevealedURI_,
        address signer_,
        address royaltyReceiver_,
        uint96 royaltyBps_
    )
        ERC721("HiveNFT", "HNFT")
        EIP712("HiveNFT", "1")
        Ownable(msg.sender)
    {
        _unrevealedURI = unrevealedURI_;
        voucherSigner = signer_;
        _setDefaultRoyalty(royaltyReceiver_, royaltyBps_);
    }

    // --- Allowlist Mint (Merkle Proof) ---

    function mintAllowlist(
        uint256 quantity,
        bytes32[] calldata proof
    ) external payable {
        if (!allowlistActive) revert SaleNotActive();
        if (totalSupply() + quantity > MAX_SUPPLY) revert MaxSupplyReached();
        if (mintCount[msg.sender] + quantity > MAX_PER_WALLET) revert MaxPerWalletExceeded();
        if (msg.value < ALLOWLIST_PRICE * quantity) revert InsufficientPayment();

        bytes32 leaf = keccak256(abi.encodePacked(msg.sender));
        if (!MerkleProof.verifyCalldata(proof, merkleRoot, leaf)) {
            revert InvalidProof();
        }

        mintCount[msg.sender] += quantity;
        for (uint256 i = 0; i < quantity; i++) {
            _safeMint(msg.sender, _nextTokenId++);
        }
    }

    // --- Public Mint ---

    function mintPublic(uint256 quantity) external payable {
        if (!publicSaleActive) revert SaleNotActive();
        if (totalSupply() + quantity > MAX_SUPPLY) revert MaxSupplyReached();
        if (mintCount[msg.sender] + quantity > MAX_PER_WALLET) revert MaxPerWalletExceeded();
        if (msg.value < PUBLIC_PRICE * quantity) revert InsufficientPayment();

        mintCount[msg.sender] += quantity;
        for (uint256 i = 0; i < quantity; i++) {
            _safeMint(msg.sender, _nextTokenId++);
        }
    }

    // --- Lazy Mint (EIP-712 Voucher) ---

    function redeemVoucher(
        MintVoucher calldata voucher,
        bytes calldata signature
    ) external payable {
        if (voucher.expiry < block.timestamp) revert VoucherExpired();
        if (voucherRedeemed[voucher.tokenId]) revert VoucherAlreadyRedeemed();
        if (msg.value < voucher.price) revert InsufficientPayment();
        if (voucher.minter != address(0) && voucher.minter != msg.sender) {
            revert InvalidVoucherSignature();
        }

        bytes32 structHash = keccak256(abi.encode(
            VOUCHER_TYPEHASH,
            voucher.tokenId,
            voucher.price,
            voucher.minter,
            voucher.expiry
        ));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = ECDSA.recover(digest, signature);
        if (signer != voucherSigner) revert InvalidVoucherSignature();

        voucherRedeemed[voucher.tokenId] = true;
        _safeMint(msg.sender, voucher.tokenId);
        emit LazyMint(voucher.tokenId, msg.sender, voucher.price);
    }

    // --- On-chain SVG Metadata ---

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId);

        if (!revealed) return _unrevealedURI;

        if (bytes(_baseTokenURI).length > 0) {
            return string.concat(_baseTokenURI, tokenId.toString(), ".json");
        }

        return _generateOnChainMetadata(tokenId);
    }

    function _generateOnChainMetadata(uint256 tokenId) internal pure returns (string memory) {
        uint256 hue = (tokenId * 137) % 360;
        uint256 size = 50 + (tokenId % 100);

        string memory svg = string.concat(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">',
            '<rect width="400" height="400" fill="hsl(', hue.toString(), ',70%,10%)"/>',
            '<circle cx="200" cy="200" r="', size.toString(),
            '" fill="hsl(', hue.toString(), ',80%,60%)" opacity="0.8"/>',
            '<text x="200" y="210" text-anchor="middle" fill="white" ',
            'font-size="24" font-family="monospace">#', tokenId.toString(), '</text>',
            '</svg>'
        );

        string memory jsonStr = string.concat(
            '{"name":"Hive #', tokenId.toString(),
            '","description":"On-chain generative NFT",',
            '"image":"data:image/svg+xml;base64,', Base64.encode(bytes(svg)),
            '","attributes":[{"trait_type":"Hue","value":', hue.toString(),
            '},{"trait_type":"Size","value":', size.toString(), '}]}'
        );

        return string.concat("data:application/json;base64,", Base64.encode(bytes(jsonStr)));
    }

    // --- Admin ---

    function reveal(string calldata baseURI_) external onlyOwner {
        if (revealed) revert AlreadyRevealed();
        revealed = true;
        _baseTokenURI = baseURI_;
        emit Revealed(baseURI_);
    }

    function setMerkleRoot(bytes32 root_) external onlyOwner {
        merkleRoot = root_;
        emit AllowlistUpdated(root_);
    }

    function setAllowlistActive(bool active_) external onlyOwner { allowlistActive = active_; }
    function setPublicSaleActive(bool active_) external onlyOwner { publicSaleActive = active_; }

    function withdraw() external onlyOwner {
        (bool ok, ) = payable(owner()).call{value: address(this).balance}("");
        require(ok);
    }

    // --- Required overrides ---

    function _update(address to, uint256 tokenId, address auth)
        internal override(ERC721, ERC721Enumerable) returns (address)
    { return super._update(to, tokenId, auth); }

    function _increaseBalance(address account, uint128 value)
        internal override(ERC721, ERC721Enumerable)
    { super._increaseBalance(account, value); }

    function supportsInterface(bytes4 interfaceId)
        public view override(ERC721Enumerable, ERC721Royalty) returns (bool)
    { return super.supportsInterface(interfaceId); }
}
```

| Minting Strategy | Gas Cost | UX | Best For |
|---|---|---|---|
| Allowlist (Merkle) | ~120k gas | Wallet must be on list | Pre-sale / early supporters |
| Public mint | ~100k gas | Anyone can mint | General sale |
| Lazy mint (voucher) | ~130k gas | Creator signs off-chain | Marketplace listings, airdrops |
| On-chain SVG | ~150k gas (view=free) | Fully decentralized art | Generative/permanent art |

Key NFT patterns:
- Merkle proofs compress a 10,000-address allowlist into a single 32-byte root
- EIP-712 vouchers enable lazy minting: creator signs off-chain, buyer pays mint gas
- EIP-2981 royalties are enforced by marketplaces that query `royaltyInfo()`
- Delayed reveal prevents sniping by hiding metadata until post-mint
- On-chain SVG metadata makes the NFT fully self-contained (no IPFS dependency)
- `_safeMint` prevents sending NFTs to contracts that cannot handle them
'''
    ),
    (
        "smart-contracts/reentrancy-guard",
        "Show reentrancy attack patterns in Solidity and all modern defenses: checks-effects-interactions, ReentrancyGuard, pull payments, and how to audit for cross-function and cross-contract reentrancy.",
        '''Reentrancy attack patterns and comprehensive defense strategies:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

// ============================================================
// 1. VULNERABLE CONTRACT — Classic reentrancy via withdraw
// ============================================================

/// @notice DO NOT USE — intentionally vulnerable for educational purposes
contract VulnerableVault {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    /// @dev BUG: Sends ETH before updating state
    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "No balance");

        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "Transfer failed");

        balances[msg.sender] = 0; // Too late — attacker already re-entered
    }
}

/// @notice Attacker exploiting the reentrancy
contract Attacker {
    VulnerableVault public vault;
    uint256 public attackCount;

    constructor(address vault_) { vault = VulnerableVault(vault_); }

    function attack() external payable {
        vault.deposit{value: msg.value}();
        vault.withdraw();
    }

    receive() external payable {
        if (address(vault).balance >= 1 ether) {
            attackCount++;
            vault.withdraw(); // Re-enter while balances[attacker] > 0
        }
    }
}

// ============================================================
// 2. DEFENSE: Checks-Effects-Interactions (CEI)
// ============================================================

contract CEIVault {
    mapping(address => uint256) public balances;

    function deposit() external payable { balances[msg.sender] += msg.value; }

    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "No balance");
        balances[msg.sender] = 0;          // EFFECTS before INTERACTIONS
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "Transfer failed");
    }
}

// ============================================================
// 3. DEFENSE: ReentrancyGuard mutex
// ============================================================

contract GuardedVault is ReentrancyGuard {
    mapping(address => uint256) public balances;

    function deposit() external payable { balances[msg.sender] += msg.value; }

    function withdraw() external nonReentrant {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "No balance");
        balances[msg.sender] = 0;
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "Transfer failed");
    }

    function withdrawTo(address to) external nonReentrant {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "No balance");
        balances[msg.sender] = 0;
        (bool ok, ) = to.call{value: amount}("");
        require(ok, "Transfer failed");
    }
}

// ============================================================
// 4. DEFENSE: Pull Payment (escrow)
// ============================================================

contract PullPaymentVault {
    mapping(address => uint256) public balances;
    mapping(address => uint256) public pendingWithdrawals;

    function deposit() external payable { balances[msg.sender] += msg.value; }

    function requestWithdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "No balance");
        balances[msg.sender] = 0;
        pendingWithdrawals[msg.sender] += amount;
    }

    function claimWithdrawal() external {
        uint256 amount = pendingWithdrawals[msg.sender];
        require(amount > 0, "Nothing to claim");
        pendingWithdrawals[msg.sender] = 0;
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "Transfer failed");
    }
}

// ============================================================
// 5. DEFENSE: Read-only reentrancy guard (view function protection)
// ============================================================

contract ReadOnlyReentrancyGuard {
    uint256 private constant NOT_ENTERED = 1;
    uint256 private constant ENTERED = 2;
    uint256 private _status = NOT_ENTERED;

    modifier nonReentrant() {
        require(_status != ENTERED, "ReentrancyGuard: reentrant call");
        _status = ENTERED;
        _;
        _status = NOT_ENTERED;
    }

    modifier nonReadReentrant() {
        require(_status != ENTERED, "ReentrancyGuard: read-only reentrant call");
        _;
    }

    mapping(address => uint256) public shares;
    uint256 public totalShares;
    uint256 public totalAssets;

    /// @dev Could return stale data if called during reentrancy
    function pricePerShare() external view nonReadReentrant returns (uint256) {
        if (totalShares == 0) return 1e18;
        return (totalAssets * 1e18) / totalShares;
    }

    function withdraw(uint256 shareAmount) external nonReentrant {
        uint256 assets = (shareAmount * totalAssets) / totalShares;
        shares[msg.sender] -= shareAmount;
        totalShares -= shareAmount;
        (bool ok, ) = msg.sender.call{value: assets}("");
        require(ok);
        totalAssets -= assets;
    }
}

// ============================================================
// 6. Transient storage lock (EIP-1153, Solidity 0.8.24+)
// ============================================================

contract TransientLockVault {
    mapping(address => uint256) public balances;

    /// @dev Uses TSTORE/TLOAD — auto-cleared at end of transaction
    modifier transientLock() {
        assembly {
            if tload(0) { revert(0, 0) }
            tstore(0, 1)
        }
        _;
        assembly { tstore(0, 0) }
    }

    function deposit() external payable { balances[msg.sender] += msg.value; }

    function withdraw() external transientLock {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "No balance");
        balances[msg.sender] = 0;
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "Transfer failed");
    }
    // Transient storage costs only 100 gas (vs 5000 for warm SSTORE)
}
```

```solidity
// test/Reentrancy.t.sol — Foundry test demonstrating attack and defense
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {VulnerableVault, Attacker, GuardedVault} from "../src/ReentrancyExamples.sol";

contract ReentrancyTest is Test {
    function test_AttackSucceeds() public {
        VulnerableVault vault = new VulnerableVault();
        Attacker attacker = new Attacker(address(vault));

        address victim = makeAddr("victim");
        vm.deal(victim, 10 ether);
        vm.prank(victim);
        vault.deposit{value: 10 ether}();

        vm.deal(address(attacker), 1 ether);
        attacker.attack{value: 1 ether}();

        assertEq(address(vault).balance, 0);
        assertGt(address(attacker).balance, 10 ether);
    }

    function test_GuardedVaultSafe() public {
        GuardedVault vault = new GuardedVault();
        address user = makeAddr("user");
        vm.deal(user, 5 ether);
        vm.prank(user);
        vault.deposit{value: 5 ether}();

        vm.prank(user);
        vault.withdraw();
        assertEq(vault.balances(user), 0);
    }
}
```

| Reentrancy Type | Vector | Defense |
|---|---|---|
| Single-function | withdraw() calls attacker, who re-enters withdraw() | CEI + nonReentrant |
| Cross-function | withdraw() callback calls withdrawTo() | nonReentrant on ALL mutating functions |
| Cross-contract | Contract A calls B, B calls back into A | Global reentrancy lock |
| Read-only | Callback reads stale view function mid-execution | nonReadReentrant on views |
| ERC-777 hooks | tokensReceived() callback on ERC-20-like transfers | nonReentrant on token handlers |

Audit checklist for reentrancy:
- Every external call (`.call`, `.transfer`, token transfers) is a potential re-entry
- Map all state changes that occur AFTER external calls
- Check view functions that could return stale intermediate state
- Apply `nonReentrant` to ALL public state-changing functions
- Consider ERC-777 token hooks: `tokensReceived()` enables reentrancy on ERC-20 transfers
- Use Slither: `slither . --detect reentrancy-eth,reentrancy-no-eth`
- EIP-1153 transient storage locks are 50x cheaper than SSTORE-based guards
'''
    ),
    (
        "smart-contracts/upgradeable-proxy",
        "Implement the UUPS (Universal Upgradeable Proxy Standard) pattern with an upgradeable ERC-20 token, storage layout safety, initialization instead of constructors, and a Foundry upgrade test.",
        '''UUPS upgradeable proxy pattern with storage-safe ERC-20 and Foundry tests:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20Upgradeable} from "@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import {OwnableUpgradeable} from "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import {UUPSUpgradeable} from "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

/**
 * @title HiveTokenV1
 * @notice Upgradeable ERC-20 using UUPS proxy pattern.
 *
 * Storage layout rules (CRITICAL):
 *   1. NEVER use constructors — use initializer functions
 *   2. NEVER remove or reorder existing storage variables
 *   3. ALWAYS add new variables AFTER existing ones
 *   4. ALWAYS include a __gap array for future-proofing
 */
contract HiveTokenV1 is
    Initializable,
    ERC20Upgradeable,
    OwnableUpgradeable,
    UUPSUpgradeable
{
    uint256 public maxSupply;
    uint256[49] private __gap; // Reserve slots for future V1 additions

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() { _disableInitializers(); }

    function initialize(
        string memory name_,
        string memory symbol_,
        uint256 maxSupply_,
        uint256 initialMint_,
        address owner_
    ) public initializer {
        __ERC20_init(name_, symbol_);
        __Ownable_init(owner_);
        __UUPSUpgradeable_init();
        maxSupply = maxSupply_;
        if (initialMint_ > 0) _mint(owner_, initialMint_);
    }

    function mint(address to, uint256 amount) external onlyOwner {
        require(totalSupply() + amount <= maxSupply, "Exceeds max supply");
        _mint(to, amount);
    }

    function version() public pure virtual returns (string memory) { return "1.0.0"; }

    function _authorizeUpgrade(address) internal override onlyOwner {}
}

/**
 * @title HiveTokenV2
 * @notice Adds transfer fee mechanism. Storage-safe: appends to V1 layout.
 *
 * New storage: transferFeeBps (slot from __gap), feeRecipient (slot from __gap)
 * __gap reduced from 49 to 47.
 */
contract HiveTokenV2 is HiveTokenV1 {
    uint256 public transferFeeBps;
    address public feeRecipient;
    uint256[47] private __gapV2;

    event TransferFeeUpdated(uint256 oldBps, uint256 newBps);

    function initializeV2(address feeRecipient_, uint256 feeBps_) public reinitializer(2) {
        feeRecipient = feeRecipient_;
        transferFeeBps = feeBps_;
    }

    function version() public pure override returns (string memory) { return "2.0.0"; }

    function setTransferFee(uint256 bps) external onlyOwner {
        require(bps <= 1000, "Fee too high");
        emit TransferFeeUpdated(transferFeeBps, bps);
        transferFeeBps = bps;
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0) && transferFeeBps > 0 && to != feeRecipient) {
            uint256 fee = (value * transferFeeBps) / 10_000;
            super._update(from, feeRecipient, fee);
            super._update(from, to, value - fee);
        } else {
            super._update(from, to, value);
        }
    }
}
```

```solidity
// test/Upgrade.t.sol — Foundry proxy deployment and upgrade tests
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {HiveTokenV1, HiveTokenV2} from "../src/HiveTokenUpgradeable.sol";

contract UpgradeTest is Test {
    HiveTokenV1 public v1Impl;
    HiveTokenV2 public v2Impl;
    ERC1967Proxy public proxy;
    HiveTokenV1 public token;

    address owner = makeAddr("owner");
    address user1 = makeAddr("user1");
    address treasury = makeAddr("treasury");

    function setUp() public {
        v1Impl = new HiveTokenV1();
        bytes memory initData = abi.encodeCall(
            HiveTokenV1.initialize,
            ("Hive Token", "HIVE", 1_000_000 ether, 100_000 ether, owner)
        );
        proxy = new ERC1967Proxy(address(v1Impl), initData);
        token = HiveTokenV1(address(proxy));
    }

    function test_V1Works() public view {
        assertEq(token.name(), "Hive Token");
        assertEq(token.totalSupply(), 100_000 ether);
        assertEq(token.balanceOf(owner), 100_000 ether);
        assertEq(token.version(), "1.0.0");
    }

    function test_UpgradeToV2() public {
        v2Impl = new HiveTokenV2();

        vm.prank(owner);
        token.upgradeToAndCall(
            address(v2Impl),
            abi.encodeCall(HiveTokenV2.initializeV2, (treasury, 100))
        );

        HiveTokenV2 tokenV2 = HiveTokenV2(address(proxy));

        // V1 state preserved
        assertEq(tokenV2.name(), "Hive Token");
        assertEq(tokenV2.totalSupply(), 100_000 ether);
        assertEq(tokenV2.maxSupply(), 1_000_000 ether);

        // V2 features work
        assertEq(tokenV2.version(), "2.0.0");
        assertEq(tokenV2.transferFeeBps(), 100);

        // Test fee deduction
        vm.prank(owner);
        tokenV2.transfer(user1, 1000 ether);
        assertEq(tokenV2.balanceOf(user1), 990 ether);   // 1% fee
        assertEq(tokenV2.balanceOf(treasury), 10 ether);
    }

    function test_NonOwnerCannotUpgrade() public {
        v2Impl = new HiveTokenV2();
        vm.prank(user1);
        vm.expectRevert();
        token.upgradeToAndCall(address(v2Impl), "");
    }

    function test_CannotReinitialize() public {
        vm.expectRevert();
        token.initialize("Hack", "HACK", 999, 999, user1);
    }

    function test_StoragePreservedAfterUpgrade() public {
        vm.prank(owner);
        token.mint(user1, 5000 ether);

        v2Impl = new HiveTokenV2();
        vm.prank(owner);
        token.upgradeToAndCall(
            address(v2Impl),
            abi.encodeCall(HiveTokenV2.initializeV2, (treasury, 0))
        );

        HiveTokenV2 tokenV2 = HiveTokenV2(address(proxy));
        assertEq(tokenV2.balanceOf(user1), 5000 ether);
        assertEq(tokenV2.balanceOf(owner), 95_000 ether);
    }
}
```

| Proxy Pattern | Upgrade Logic Location | Gas Overhead | Best For |
|---|---|---|---|
| UUPS (ERC-1822) | Implementation contract | ~200 gas/call | Single upgradeable contracts |
| Transparent Proxy | Proxy admin contract | ~2100 gas/call | Admin-managed protocols |
| Beacon Proxy | Shared beacon contract | ~2600 gas/call | Many identical proxy instances |
| Diamond (ERC-2535) | Per-facet modular | ~2200 gas/call | Complex protocols with modules |

Storage safety checklist:
- Run `forge inspect ContractV1 storage-layout` and compare with V2
- Never change variable types or ordering
- New variables consume __gap slots (reduce gap size accordingly)
- Use `reinitializer(N)` for V2+ init functions (not `initializer`)
- `_disableInitializers()` in constructor prevents implementation initialization
'''
    ),
    (
        "smart-contracts/gas-optimization",
        "Show advanced Solidity gas optimization techniques: storage packing, calldata vs memory, immutable/constant, custom errors, unchecked math, assembly for common operations, and benchmarking with Foundry.",
        '''Advanced Solidity gas optimization with measurements and Foundry benchmarks:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// ============================================================
// 1. STORAGE PACKING — fit multiple variables into one 32-byte slot
// ============================================================

/// @notice UNOPTIMIZED: 4 storage slots
contract UnpackedStorage {
    uint256 public amount;      // Slot 0 (32 bytes)
    address public owner;       // Slot 1 (20 bytes, wastes 12)
    bool public active;         // Slot 2 (1 byte, wastes 31)
    uint256 public timestamp;   // Slot 3
    // Total: 4 slots x 20,000 gas first write = 80,000 gas
}

/// @notice OPTIMIZED: 2 storage slots
contract PackedStorage {
    uint128 public amount;      // Slot 0, first 16 bytes
    uint64 public timestamp;    // Slot 0, next 8 bytes
    bool public active;         // Slot 0, next 1 byte
    address public owner;       // Slot 1, 20 bytes
    // Total: 2 slots = 40,000 gas (50% savings)
}

// ============================================================
// 2. CALLDATA vs MEMORY
// ============================================================

contract CalldataVsMemory {
    /// @dev EXPENSIVE: Copies entire array to memory
    function sumMemory(uint256[] memory arr) external pure returns (uint256 total) {
        for (uint256 i = 0; i < arr.length; i++) total += arr[i];
    }

    /// @dev CHEAP: Reads directly from calldata (no copy)
    function sumCalldata(uint256[] calldata arr) external pure returns (uint256 total) {
        for (uint256 i = 0; i < arr.length; i++) total += arr[i];
    }
}

// ============================================================
// 3. CUSTOM ERRORS vs REQUIRE STRINGS
// ============================================================

contract ErrorPatterns {
    error InsufficientBalance(uint256 available, uint256 required);

    mapping(address => uint256) public balances;

    /// @dev EXPENSIVE: String stored in bytecode
    function withdrawExpensive(uint256 amount) external {
        require(balances[msg.sender] >= amount, "Insufficient balance for withdrawal");
    }

    /// @dev CHEAP: 4-byte selector, no string storage
    function withdrawCheap(uint256 amount) external {
        if (balances[msg.sender] < amount) {
            revert InsufficientBalance(balances[msg.sender], amount);
        }
    }
}

// ============================================================
// 4. UNCHECKED MATH — skip overflow checks when safe
// ============================================================

contract UncheckedMath {
    function sumChecked(uint256[] calldata arr) external pure returns (uint256 total) {
        for (uint256 i = 0; i < arr.length; i++) total += arr[i];
    }

    function sumUnchecked(uint256[] calldata arr) external pure returns (uint256 total) {
        uint256 len = arr.length;
        for (uint256 i = 0; i < len; ) {
            total += arr[i];
            unchecked { ++i; } // i cannot overflow for realistic lengths
        }
    }
}

// ============================================================
// 5. IMMUTABLE/CONSTANT — embed in bytecode
// ============================================================

contract Constants {
    uint256 public constant MAX_SUPPLY = 1_000_000 ether; // 0 gas (inlined)
    uint256 public immutable deployTimestamp;               // 3 gas (PUSH)
    address public immutable deployer;                      // 3 gas (PUSH)
    uint256 public storedValue;                             // 2100 gas (SLOAD)

    constructor() {
        deployTimestamp = block.timestamp;
        deployer = msg.sender;
        storedValue = block.timestamp;
    }
}

// ============================================================
// 6. ASSEMBLY for gas-critical operations
// ============================================================

contract AssemblyOptimizations {
    function isContractSolidity(address addr) external view returns (bool) {
        return addr.code.length > 0;
    }

    function isContractAssembly(address addr) external view returns (bool result) {
        assembly { result := gt(extcodesize(addr), 0) }
    }

    function transferETH(address to, uint256 amount) external {
        assembly {
            let success := call(gas(), to, amount, 0, 0, 0, 0)
            if iszero(success) { revert(0, 0) }
        }
    }

    // Pack two uint128 values into one storage slot with assembly
    uint256 private _packedSlot;

    function setPackedValues(uint128 a, uint128 b) external {
        assembly {
            let packed := or(shl(128, a), b)
            sstore(_packedSlot.slot, packed)
        }
    }

    function getPackedValues() external view returns (uint128 a, uint128 b) {
        assembly {
            let packed := sload(_packedSlot.slot)
            a := shr(128, packed)
            b := and(packed, 0xffffffffffffffffffffffffffffffff)
        }
    }
}

// ============================================================
// 7. BATCH OPERATIONS — amortize 21k base cost
// ============================================================

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract BatchTransfer {
    function batchTransfer(
        IERC20 token,
        address[] calldata recipients,
        uint256[] calldata amounts
    ) external {
        uint256 len = recipients.length;
        require(len == amounts.length, "Length mismatch");
        for (uint256 i = 0; i < len; ) {
            token.transferFrom(msg.sender, recipients[i], amounts[i]);
            unchecked { ++i; }
        }
    }
}

// ============================================================
// 8. TRANSIENT STORAGE (EIP-1153) for within-tx caching
// ============================================================

contract TransientCaching {
    /// @dev Cache a value within a transaction for 100 gas instead of 5000
    function computeExpensiveValue() external returns (uint256 result) {
        assembly {
            result := tload(0)
            if iszero(result) {
                // Expensive computation (simulated)
                result := add(timestamp(), caller())
                tstore(0, result) // 100 gas (vs SSTORE: 5000-20000)
            }
        }
    }
}
```

```solidity
// test/GasBenchmark.t.sol — Foundry gas benchmarks
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {CalldataVsMemory, UncheckedMath, AssemblyOptimizations} from "../src/GasOptimized.sol";

contract GasBenchmarkTest is Test {
    CalldataVsMemory public cdvm;
    UncheckedMath public um;
    AssemblyOptimizations public asmOpt;
    uint256[] testArray;

    function setUp() public {
        cdvm = new CalldataVsMemory();
        um = new UncheckedMath();
        asmOpt = new AssemblyOptimizations();
        for (uint256 i = 1; i <= 100; i++) testArray.push(i);
    }

    function test_CalldataVsMemory() public view {
        uint256 g1 = gasleft();
        cdvm.sumMemory(testArray);
        uint256 memoryCost = g1 - gasleft();

        g1 = gasleft();
        cdvm.sumCalldata(testArray);
        uint256 calldataCost = g1 - gasleft();

        console2.log("memory:", memoryCost, "calldata:", calldataCost);
        assertLt(calldataCost, memoryCost);
    }

    function test_UncheckedMath() public view {
        uint256 g1 = gasleft();
        um.sumChecked(testArray);
        uint256 checkedCost = g1 - gasleft();

        g1 = gasleft();
        um.sumUnchecked(testArray);
        uint256 uncheckedCost = g1 - gasleft();

        console2.log("checked:", checkedCost, "unchecked:", uncheckedCost);
        assertLt(uncheckedCost, checkedCost);
    }

    function test_IsContractGas() public view {
        uint256 g1 = gasleft();
        asmOpt.isContractSolidity(address(this));
        uint256 solidityCost = g1 - gasleft();

        g1 = gasleft();
        asmOpt.isContractAssembly(address(this));
        uint256 assemblyCost = g1 - gasleft();

        console2.log("solidity:", solidityCost, "assembly:", assemblyCost);
        assertLt(assemblyCost, solidityCost);
    }
}
```

Run: `forge test --match-path test/GasBenchmark.t.sol -vv --gas-report`

| Optimization | Gas Saved | Risk | When to Use |
|---|---|---|---|
| Storage packing | 20,000 per slot saved | Low | Always |
| calldata vs memory | 60+ per element | Low | Read-only array/struct params |
| Custom errors | ~200 per revert | Low | Always (replaces require strings) |
| Unchecked math | 70-120 per loop iteration | Medium | Counters, array indices |
| immutable/constant | 2,097 per read | Low | Deploy-time or compile-time values |
| Inline assembly | 100-5000 varies | High | Hot paths only, after profiling |
| Batch operations | 21,000 per saved tx | Low | Multi-recipient transfers |
| Transient storage | 4,900-19,900 per slot | Low | Within-tx caches, reentrancy locks |

Key principles:
- Profile first with `forge test --gas-report` before optimizing
- SLOAD costs 2,100 gas; cache storage reads in local variables
- SSTORE costs 20,000 (cold) or 5,000 (warm); minimize writes
- Assembly bypasses Solidity safety checks: use only after profiling
- EIP-1153 transient storage is the biggest 2024-2026 gas optimization for per-tx state
'''
    ),
]
