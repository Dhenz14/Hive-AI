"""Hive blockchain training pairs: account creation and onboarding."""

PAIRS = [
    (
        "hive/account-creation-fee",
        r'''How do I create a new account on the Hive blockchain using the account creation fee? Show the process with beem.''',
        r'''Creating an account on Hive requires paying an account creation fee (set by witness consensus, typically 3 HIVE). The fee is converted to HP and delegated to the new account. Here is the complete process:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Account_create
from beemgraphenebase.account import PasswordKey
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

CREATOR = "existingaccount"

def create_account_with_fee(new_account_name, master_password,
                             creator=CREATOR, fee="3.000 HIVE"):
    """Create a new Hive account by paying the creation fee.

    The fee is burned and converted to VESTS (HP) for the new account.
    """
    # Derive all four key types from master password
    keys = {}
    for role in ["owner", "active", "posting", "memo"]:
        pk = PasswordKey(new_account_name, master_password, role=role)
        keys[role] = {
            "private": str(pk.get_private_key()),
            "public": str(pk.get_public_key())
        }

    # Build the account_create operation
    op = Account_create(**{
        "fee": fee,
        "creator": creator,
        "new_account_name": new_account_name,
        "owner": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[keys["owner"]["public"], 1]]
        },
        "active": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[keys["active"]["public"], 1]]
        },
        "posting": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[keys["posting"]["public"], 1]]
        },
        "memo_key": keys["memo"]["public"],
        "json_metadata": json.dumps({
            "profile": {
                "name": "",
                "about": "",
                "location": "",
                "website": ""
            }
        })
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(creator, "active")
    tx.sign()
    result = tx.broadcast()

    print(f"Account @{new_account_name} created!")
    print(f"Transaction: {result['id']}")
    print(f"\nKEYS (save these securely):")
    print(f"Master password: {master_password}")
    for role, key_pair in keys.items():
        print(f"  {role} (private): {key_pair['private']}")
        print(f"  {role} (public):  {key_pair['public']}")

    return result, keys

def check_account_name_available(name):
    """Check if an account name is available."""
    try:
        acct = Account(name, hive_instance=hive)
        print(f"@{name} is already taken")
        return False
    except Exception:
        # Validate name rules
        if len(name) < 3:
            print("Name must be at least 3 characters")
            return False
        if len(name) > 16:
            print("Name must be 16 characters or less")
            return False
        if not name[0].isalpha():
            print("Name must start with a letter")
            return False
        import re
        if not re.match(r'^[a-z][a-z0-9\-\.]*[a-z0-9]$', name):
            print("Name can only contain lowercase letters, digits, hyphens, dots")
            return False
        if ".." in name or "--" in name:
            print("Name cannot contain consecutive dots or hyphens")
            return False
        print(f"@{name} is available!")
        return True

# Usage
# check_account_name_available("newuser123")
# create_account_with_fee("newuser123", "P5SomeSecureMasterPassword123!")
```

Account name rules: 3-16 characters, starts with a letter, only lowercase a-z, digits 0-9, hyphens, and dots. No consecutive special characters. The creation fee (median of witness votes) is burned and converted to VESTS for the new account's initial HP.
'''
    ),
    (
        "hive/claimed-account-creation",
        r'''How do I use claimed account tokens to create free accounts on Hive? Explain the claim_account and create_claimed_account process.''',
        r'''<think>
The user is asking about claimed account creation on Hive. I could be thinking of the old Steem account creation system... but wait, Hive forked from Steem and changed some mechanics. Let me think through how this actually works on Hive specifically.

So there are two ways to create accounts: paying the fee directly, or using claimed tokens. The claimed token path is a two-step process -- claim_account first, then create_claimed_account. I initially considered whether claim_account costs HIVE, but actually no, the whole point is that it costs RC instead. The fee field is set to "0.000 HIVE" to signal "pay with RC." That is the key distinction.

Hmm, do claimed tokens expire? I was going to say they have a time limit, but actually they do not expire at all. They sit on the creator account indefinitely. That is why onboarding services like Hiveonboard can stockpile them during periods of low RC demand and spend them later when new users show up.

The RC cost of claiming varies based on the pending claims pool -- because the chain uses a resource credit pricing model where demand drives cost up. Therefore, when many accounts are claiming simultaneously, the RC cost spikes. Since large stakeholders regenerate RC proportional to their HP, they are the ones best positioned to claim tokens efficiently.

Wait, one more thing -- the create_claimed_account operation itself is essentially free (no HIVE fee, minimal RC). So the entire economic cost is front-loaded into the claim step. This makes the system flexible because you decouple the cost (claiming) from the action (creating).
</think>

The claimed account system lets you spend RC to pre-claim account creation tokens, then use them later to create accounts for free. This is the primary mechanism for onboarding new users:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Claim_account, Create_claimed_account
from beemgraphenebase.account import PasswordKey
import json

hive = Hive(
    node=["https://api.hive.blog", "https://api.deathwing.me"],
    keys=["5YourActiveKey"]
)

ACCOUNT = "myaccount"

# Step 1: Claim an account token (costs RC, not HIVE)
def claim_account_token():
    """Claim an account creation token using RC.

    The RC cost varies based on the current claim pool.
    Check your RC before claiming -- it can be expensive.
    """
    op = Claim_account(**{
        "creator": ACCOUNT,
        "fee": "0.000 HIVE",  # 0 HIVE = pay with RC
        "extensions": []
    })
    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()
    print(f"Account token claimed: {result['id']}")
    return result

def check_pending_claimed_accounts():
    """Check how many claimed account tokens you have."""
    acct = Account(ACCOUNT, hive_instance=hive)
    pending = acct.get("pending_claimed_accounts", 0)
    print(f"@{ACCOUNT} has {pending} pending claimed account tokens")
    return pending

# Step 2: Create account using a claimed token
def create_claimed_account(new_account_name, master_password):
    """Create a new account using a previously claimed token."""
    # Derive keys from master password
    keys = {}
    for role in ["owner", "active", "posting", "memo"]:
        pk = PasswordKey(new_account_name, master_password, role=role)
        keys[role] = str(pk.get_public_key())
        keys[f"{role}_private"] = str(pk.get_private_key())

    op = Create_claimed_account(**{
        "creator": ACCOUNT,
        "new_account_name": new_account_name,
        "owner": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[keys["owner"], 1]]
        },
        "active": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[keys["active"], 1]]
        },
        "posting": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[keys["posting"], 1]]
        },
        "memo_key": keys["memo"],
        "json_metadata": json.dumps({"profile": {}}),
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=hive)
    tx.appendOps(op)
    tx.appendSigner(ACCOUNT, "active")
    tx.sign()
    result = tx.broadcast()

    print(f"Account @{new_account_name} created from claimed token!")
    print(f"Transaction: {result['id']}")
    return result, keys

# Automated claiming: claim tokens when RC is high
def auto_claim_tokens(min_rc_pct=80, max_tokens=10):
    """Automatically claim tokens when RC is above threshold."""
    pending = check_pending_claimed_accounts()
    if pending >= max_tokens:
        print(f"Already have {pending} tokens, skipping")
        return

    # Check RC level
    rc_info = hive.rpc.find_rc_accounts(
        {"accounts": [ACCOUNT]}, api="rc_api"
    )
    rc_data = rc_info["rc_accounts"][0]
    max_rc = int(rc_data["max_rc"])
    current = int(rc_data["rc_manabar"]["current_mana"])
    pct = (current / max_rc * 100) if max_rc > 0 else 0

    if pct >= min_rc_pct:
        print(f"RC at {pct:.1f}%, claiming token...")
        claim_account_token()
    else:
        print(f"RC at {pct:.1f}%, below {min_rc_pct}% threshold")

# Usage
check_pending_claimed_accounts()
# claim_account_token()
# create_claimed_account("brandnewuser", "P5SecureMasterPassword!")
```

The claimed account system is how most Hive onboarding services work. Services like Hiveonboard, PeakD, and Ecency claim tokens in bulk when their RC is high, then spend them to create accounts for new users. The creator account becomes the default recovery account for accounts they create.
'''
    ),
    (
        "hive/onboarding-flow",
        r'''How do I build a complete user onboarding flow for a Hive dApp? Include account creation, initial delegation, and first-post setup.''',
        r'''Here is a complete onboarding flow that creates an account, delegates enough HP for them to transact, and sets up their profile:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Create_claimed_account, Delegate_vesting_shares,
    Account_update2, Custom_json, Transfer
)
from beemgraphenebase.account import PasswordKey
from beem.amount import Amount
import json
import secrets
import string
import time

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5ActiveKey", "5PostingKey"]
)
ONBOARDING_ACCOUNT = "myapp"

class HiveOnboarder:
    def __init__(self, hive_instance, onboarding_account):
        self.hive = hive_instance
        self.account = onboarding_account

    def generate_master_password(self, length=52):
        """Generate a secure master password."""
        chars = string.ascii_letters + string.digits
        password = "P5" + "".join(secrets.choice(chars) for _ in range(length))
        return password

    def create_account(self, username):
        """Full account creation with claimed token."""
        password = self.generate_master_password()

        keys = {}
        public_keys = {}
        for role in ["owner", "active", "posting", "memo"]:
            pk = PasswordKey(username, password, role=role)
            keys[role] = str(pk.get_private_key())
            public_keys[role] = str(pk.get_public_key())

        op = Create_claimed_account(**{
            "creator": self.account,
            "new_account_name": username,
            "owner": {
                "weight_threshold": 1,
                "account_auths": [],
                "key_auths": [[public_keys["owner"], 1]]
            },
            "active": {
                "weight_threshold": 1,
                "account_auths": [],
                "key_auths": [[public_keys["active"], 1]]
            },
            "posting": {
                "weight_threshold": 1,
                "account_auths": [],
                "key_auths": [[public_keys["posting"], 1]]
            },
            "memo_key": public_keys["memo"],
            "json_metadata": json.dumps({"app": "myapp/1.0"}),
            "extensions": []
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()

        return {
            "username": username,
            "password": password,
            "keys": keys,
            "public_keys": public_keys,
            "tx_id": result.get("id", "")
        }

    def delegate_initial_hp(self, new_account, hp_amount=15.0):
        """Delegate HP so the new user can transact."""
        # Convert HP to VESTS
        props = self.hive.rpc.get_dynamic_global_properties()
        total_vesting = float(str(props["total_vesting_fund_hive"]).split()[0])
        total_shares = float(str(props["total_vesting_shares"]).split()[0])
        vests_per_hp = total_shares / total_vesting
        vests = hp_amount * vests_per_hp

        op = Delegate_vesting_shares(**{
            "delegator": self.account,
            "delegatee": new_account,
            "vesting_shares": f"{vests:.6f} VESTS"
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        return tx.broadcast()

    def send_welcome_hive(self, new_account, amount=0.1):
        """Send a small amount of HIVE for initial operations."""
        op = Transfer(**{
            "from": self.account,
            "to": new_account,
            "amount": f"{amount:.3f} HIVE",
            "memo": "Welcome to Hive! This is starter HIVE from myapp."
        })
        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        return tx.broadcast()

    def full_onboarding(self, username):
        """Complete onboarding: create, delegate, welcome."""
        print(f"Creating account @{username}...")
        account_info = self.create_account(username)
        print(f"Account created: {account_info['tx_id']}")

        time.sleep(6)  # Wait for block confirmation

        print(f"Delegating 15 HP...")
        self.delegate_initial_hp(username, hp_amount=15.0)

        print(f"Sending welcome HIVE...")
        self.send_welcome_hive(username, amount=0.1)

        print(f"\nOnboarding complete for @{username}!")
        print(f"Master password: {account_info['password']}")
        print("(Share this securely with the user)")

        return account_info

# Usage
onboarder = HiveOnboarder(hive, ONBOARDING_ACCOUNT)
# result = onboarder.full_onboarding("newuser2025")
```

This onboarding flow handles: claimed account creation (free), initial HP delegation (15 HP is enough for basic operations), and a welcome HIVE transfer. The delegation can be removed after the user builds their own HP through posting rewards or power-ups.
'''
    ),
    (
        "hive/account-recovery-setup",
        r'''How should I set up account recovery for accounts my dApp creates? What are the responsibilities of a recovery account?''',
        r'''When your dApp creates accounts, it automatically becomes the recovery account. This is an important responsibility. Here is how to manage it properly:

```python
from beem import Hive
from beem.account import Account
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import (
    Request_account_recovery, Recover_account,
    Change_recovery_account
)
from beemgraphenebase.account import PasswordKey, PrivateKey
import json
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recovery_service")

hive = Hive(
    node=["https://api.hive.blog"],
    keys=["5RecoveryAccountActiveKey"]
)

RECOVERY_ACCOUNT = "myapp"

class RecoveryService:
    """Manage account recovery for accounts created by your dApp."""

    def __init__(self, recovery_account, hive_instance):
        self.account = recovery_account
        self.hive = hive_instance

    def list_recoverable_accounts(self, limit=1000):
        """Find accounts where we are the recovery partner."""
        # This requires scanning -- no direct API for this
        # In practice, track created accounts in your database
        pass

    def verify_identity(self, account_name, proof):
        """Verify the user's identity before initiating recovery.

        This is YOUR responsibility as the recovery account.
        You must verify the user is who they claim to be.
        Methods: email verification, ID check, security questions, etc.
        """
        # Implement your verification logic here
        # This is the most critical step -- wrong recovery = stolen account
        logger.info(f"Identity verification for @{account_name}")
        return True  # Replace with actual verification

    def initiate_recovery(self, account_to_recover, new_owner_public_key):
        """Start the recovery process (recovery account side).

        The new_owner_public_key is a key the legitimate owner
        controls. They must generate it and share the public key
        with you out-of-band.
        """
        new_owner_authority = {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_owner_public_key, 1]]
        }

        op = Request_account_recovery(**{
            "recovery_account": self.account,
            "account_to_recover": account_to_recover,
            "new_owner_authority": new_owner_authority,
            "extensions": []
        })

        tx = TransactionBuilder(hive_instance=self.hive)
        tx.appendOps(op)
        tx.appendSigner(self.account, "active")
        tx.sign()
        result = tx.broadcast()

        logger.info(f"Recovery initiated for @{account_to_recover}: "
                     f"{result['id']}")
        logger.info("User has 24 hours to complete recovery")
        return result

    def check_recovery_requests(self):
        """Check for pending recovery requests."""
        # Use condenser_api to find pending requests
        result = self.hive.rpc.find_change_recovery_account_requests(
            {"accounts": [self.account]},
            api="database_api"
        )
        requests = result.get("requests", [])
        for r in requests:
            logger.info(f"Pending recovery change: "
                        f"@{r['account_to_recover']} -> "
                        f"@{r['recovery_account']}")
        return requests

def user_complete_recovery(account_name, recent_owner_key, new_owner_key):
    """The user's side: complete the recovery.

    Must be done within 24 hours of the recovery request.
    Requires both the old owner key (from last 30 days)
    and the new owner key (matching the recovery request).
    """
    user_hive = Hive(
        node=["https://api.hive.blog"],
        keys=[recent_owner_key, new_owner_key]
    )

    new_pk = PrivateKey(new_owner_key)
    new_public = str(new_pk.pubkey)

    recent_pk = PrivateKey(recent_owner_key)
    recent_public = str(recent_pk.pubkey)

    op = Recover_account(**{
        "account_to_recover": account_name,
        "new_owner_authority": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[new_public, 1]]
        },
        "recent_owner_authority": {
            "weight_threshold": 1,
            "account_auths": [],
            "key_auths": [[recent_public, 1]]
        },
        "extensions": []
    })

    tx = TransactionBuilder(hive_instance=user_hive)
    tx.appendOps(op)
    tx.sign()
    result = tx.broadcast()
    logger.info(f"Recovery completed for @{account_name}: {result['id']}")
    return result

# Usage
service = RecoveryService(RECOVERY_ACCOUNT, hive)
# service.initiate_recovery("compromised_user", "STM7newPublicKey...")
```

Recovery account responsibilities:
- Verify identity thoroughly before initiating recovery (you are the gatekeeper)
- Respond to recovery requests promptly (24-hour window)
- Keep your own keys secure (if your account is compromised, you cannot help)
- Communicate the process clearly to your users during onboarding
- The recovery account change has a 30-day delay for security
'''
    ),
    (
        "hive/account-creation-dhive",
        r'''Show me how to create a Hive account using the dhive JavaScript library, including key generation.''',
        r'''Here is the complete account creation process using dhive in JavaScript:

```javascript
const dhive = require("@hiveio/dhive");
const crypto = require("crypto");

const client = new dhive.Client([
    "https://api.hive.blog",
    "https://api.deathwing.me"
]);

// Generate keys from a master password
function generateKeys(accountName, masterPassword) {
    const roles = ["owner", "active", "posting", "memo"];
    const keys = {};

    for (const role of roles) {
        const privateKey = dhive.PrivateKey.fromLogin(accountName, masterPassword, role);
        keys[role] = {
            private: privateKey.toString(),
            public: privateKey.createPublic().toString()
        };
    }
    return keys;
}

// Generate a secure random master password
function generateMasterPassword() {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    let password = "P5";
    for (let i = 0; i < 50; i++) {
        password += chars.charAt(crypto.randomInt(chars.length));
    }
    return password;
}

// Create account with fee
async function createAccountWithFee(creator, creatorActiveKey, newAccountName) {
    const masterPassword = generateMasterPassword();
    const keys = generateKeys(newAccountName, masterPassword);

    const privateKey = dhive.PrivateKey.fromString(creatorActiveKey);

    const createOp = [
        "account_create",
        {
            fee: "3.000 HIVE",
            creator: creator,
            new_account_name: newAccountName,
            owner: {
                weight_threshold: 1,
                account_auths: [],
                key_auths: [[keys.owner.public, 1]]
            },
            active: {
                weight_threshold: 1,
                account_auths: [],
                key_auths: [[keys.active.public, 1]]
            },
            posting: {
                weight_threshold: 1,
                account_auths: [],
                key_auths: [[keys.posting.public, 1]]
            },
            memo_key: keys.memo.public,
            json_metadata: JSON.stringify({profile: {}})
        }
    ];

    try {
        const result = await client.broadcast.sendOperations(
            [createOp], privateKey
        );
        console.log("Account created:", result.id);
        console.log("Master password:", masterPassword);
        console.log("Keys:", JSON.stringify(keys, null, 2));
        return {masterPassword, keys, txId: result.id};
    } catch (err) {
        console.error("Creation failed:", err.message);
        throw err;
    }
}

// Create account with claimed token (free)
async function createClaimedAccount(creator, creatorActiveKey, newAccountName) {
    const masterPassword = generateMasterPassword();
    const keys = generateKeys(newAccountName, masterPassword);

    const privateKey = dhive.PrivateKey.fromString(creatorActiveKey);

    const createOp = [
        "create_claimed_account",
        {
            creator: creator,
            new_account_name: newAccountName,
            owner: {
                weight_threshold: 1,
                account_auths: [],
                key_auths: [[keys.owner.public, 1]]
            },
            active: {
                weight_threshold: 1,
                account_auths: [],
                key_auths: [[keys.active.public, 1]]
            },
            posting: {
                weight_threshold: 1,
                account_auths: [],
                key_auths: [[keys.posting.public, 1]]
            },
            memo_key: keys.memo.public,
            json_metadata: JSON.stringify({profile: {}}),
            extensions: []
        }
    ];

    const result = await client.broadcast.sendOperations(
        [createOp], privateKey
    );
    return {masterPassword, keys, txId: result.id};
}

// Check if account name is available
async function isNameAvailable(name) {
    try {
        const accounts = await client.database.getAccounts([name]);
        return accounts.length === 0;
    } catch (err) {
        return false;
    }
}

// Validate account name
function validateAccountName(name) {
    if (name.length < 3 || name.length > 16) return "Length must be 3-16";
    if (!/^[a-z]/.test(name)) return "Must start with a letter";
    if (!/^[a-z][a-z0-9\-.]*[a-z0-9]$/.test(name)) return "Invalid characters";
    if (/\.\./.test(name) || /--/.test(name)) return "No consecutive dots/hyphens";
    return null;
}

// Full flow
async function onboardUser(creator, activeKey, username) {
    const error = validateAccountName(username);
    if (error) throw new Error(`Invalid name: ${error}`);

    const available = await isNameAvailable(username);
    if (!available) throw new Error(`@${username} already taken`);

    const result = await createClaimedAccount(creator, activeKey, username);
    console.log(`Created @${username} successfully!`);
    return result;
}

// onboardUser("myapp", "5ActiveKey", "newuser2025");
```

This covers key generation from a master password (using dhive's built-in PasswordKey derivation), both paid and claimed account creation, name validation, and availability checking. The generated master password should be communicated securely to the new user.
'''
    ),
]
