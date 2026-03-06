"""dhive.js Core Operations — posting, voting, transfers, custom_json, account creation.

Covers the essential blockchain write operations using the @hiveio/dhive JavaScript
library (v1.x). Every Hive dApp needs these primitives.
"""

PAIRS = [
    (
        "hive/development",
        r'''How do I post content to the Hive blockchain using dhive.js, including setting beneficiaries and other advanced options like community posting?''',
        r'''## Posting Content on Hive with dhive.js

Posting content to Hive uses the `comment` operation. Despite the name, both top-level posts and replies use the same operation — a top-level post simply has an empty `parent_author` and `parent_permlink` set to the main tag.

### Key Concepts

- **Posting key** is required for comment operations (not active key)
- **Permlinks** must be unique per author — convention is to slugify the title with a timestamp
- **Beneficiaries** are set via `comment_options` and must be sorted alphabetically by account
- **Community posting** uses the community name (e.g., `hive-174301`) as the `parent_permlink`

### Basic Post

```javascript
const dhive = require('@hiveio/dhive');

const client = new dhive.Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
  'https://anyx.io',
]);

const postingKey = dhive.PrivateKey.fromString('5Kexample_YOUR_POSTING_KEY_HERE');

async function createPost() {
  const author = 'youraccount';
  const title = 'My First Hive Post';
  const body = '# Hello Hive!\n\nThis is my first post from dhive.';
  const timestamp = new Date().toISOString().replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
  const permlink = `my-first-hive-post-${timestamp}`;
  const mainTag = 'hive-dev';

  const jsonMetadata = JSON.stringify({
    tags: ['hive-dev', 'programming', 'javascript'],
    app: 'myapp/1.0.0',
    format: 'markdown',
    image: [],
  });

  const op = [
    'comment',
    {
      parent_author: '',           // empty = top-level post
      parent_permlink: mainTag,    // first tag or community name
      author: author,
      permlink: permlink,
      title: title,
      body: body,
      json_metadata: jsonMetadata,
    },
  ];

  try {
    const result = await client.broadcast.sendOperations([op], postingKey);
    console.log('Post created:', result);
    console.log(`View at: https://hive.blog/@${author}/${permlink}`);
    return result;
  } catch (err) {
    if (err.message.includes('HIVE_MIN_ROOT_COMMENT_INTERVAL')) {
      console.error('Must wait 5 minutes between top-level posts');
    } else if (err.message.includes('rc_plugin_exception')) {
      console.error('Insufficient Resource Credits — power up or get RC delegation');
    } else {
      console.error('Broadcast failed:', err.message);
    }
    throw err;
  }
}
```

### Production Post with Beneficiaries, Max Accepted Payout, and Community

```javascript
async function createProductionPost({
  author,
  title,
  body,
  tags = [],
  community = null,      // e.g., 'hive-174301' for a specific community
  beneficiaries = [],    // [{account: 'app-fee', weight: 500}] = 5%
  maxAcceptedPayout = '1000000.000 HBD',
  percentHBD = 10000,    // 10000 = 100% HBD of the 50% liquid portion
  allowVotes = true,
  allowCurationRewards = true,
}) {
  const timestamp = Date.now().toString(36);
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  const permlink = `${slug}-${timestamp}`;

  // Community posts use the community ID as parent_permlink
  const parentPermlink = community || tags[0] || 'general';

  // Build json_metadata — communities require specific metadata
  const metadata = {
    tags: tags.length > 0 ? tags : ['general'],
    app: 'myapp/1.0.0',
    format: 'markdown',
    image: extractImages(body),
  };
  if (community) {
    metadata.community = community;
  }

  const operations = [];

  // 1. The comment operation
  operations.push([
    'comment',
    {
      parent_author: '',
      parent_permlink: parentPermlink,
      author,
      permlink,
      title,
      body,
      json_metadata: JSON.stringify(metadata),
    },
  ]);

  // 2. Comment options (beneficiaries, payout settings)
  // Beneficiaries MUST be sorted alphabetically by account name
  const sortedBeneficiaries = [...beneficiaries].sort((a, b) =>
    a.account.localeCompare(b.account)
  );

  // Validate beneficiary weights (total must be <= 10000 = 100%)
  const totalWeight = sortedBeneficiaries.reduce((sum, b) => sum + b.weight, 0);
  if (totalWeight > 10000) {
    throw new Error(`Beneficiary weights total ${totalWeight}, max is 10000`);
  }

  const commentOptions = {
    author,
    permlink,
    max_accepted_payout: maxAcceptedPayout,
    percent_hbd: percentHBD,
    allow_votes: allowVotes,
    allow_curation_rewards: allowCurationRewards,
    extensions: [],
  };

  if (sortedBeneficiaries.length > 0) {
    commentOptions.extensions.push([
      0,   // beneficiary extension ID
      { beneficiaries: sortedBeneficiaries },
    ]);
  }

  operations.push(['comment_options', commentOptions]);

  try {
    const result = await client.broadcast.sendOperations(operations, postingKey);
    console.log('Post published successfully');
    console.log(`Transaction ID: ${result.id}`);
    console.log(`Block: ${result.block_num}`);
    return { permlink, result };
  } catch (err) {
    handleBroadcastError(err);
    throw err;
  }
}

function extractImages(markdown) {
  const regex = /!\[.*?\]\((https?:\/\/[^\s)]+)\)/g;
  const images = [];
  let match;
  while ((match = regex.exec(markdown)) !== null) {
    images.push(match[1]);
  }
  return images;
}

function handleBroadcastError(err) {
  const msg = err.message || '';
  if (msg.includes('HIVE_MIN_ROOT_COMMENT_INTERVAL')) {
    console.error('Rate limited: wait 5 minutes between top-level posts');
  } else if (msg.includes('HIVE_MIN_REPLY_INTERVAL')) {
    console.error('Rate limited: wait 3 seconds between comments');
  } else if (msg.includes('missing required posting authority')) {
    console.error('Wrong key — posting key required for comments');
  } else if (msg.includes('rc_plugin_exception')) {
    console.error('Insufficient Resource Credits');
  } else if (msg.includes('bandwidth')) {
    console.error('Bandwidth exceeded — need more HP or wait');
  } else {
    console.error('Broadcast error:', msg);
  }
}

// Usage:
createProductionPost({
  author: 'youraccount',
  title: 'Building on Hive with dhive',
  body: '# Guide\n\nHere is how to build on Hive...',
  tags: ['hive-dev', 'tutorial', 'javascript'],
  community: 'hive-169321',
  beneficiaries: [
    { account: 'hive-fund', weight: 100 },   // 1% to DHF
    { account: 'myapp', weight: 500 },        // 5% app fee
  ],
  maxAcceptedPayout: '1000000.000 HBD',
  percentHBD: 10000,
});
```

### Important Notes

1. **Beneficiary weight units**: 100 = 1%, 10000 = 100%. A weight of 500 means 5% of post rewards go to that account.
2. **comment_options must be broadcast in the same transaction** as the comment, or broadcast before any votes arrive.
3. **Community posts** still appear on the author's blog but are tagged to the community for moderation and discovery.
4. **Permlink uniqueness**: If you reuse a permlink, it becomes an edit of the existing post, not a new one. Always include a timestamp or random suffix.
5. **json_metadata format**: While the chain stores it as a string, frontends like PeakD and Ecency parse the `tags`, `image`, `app`, and `format` fields for display.
'''
    ),
    (
        "hive/development",
        r'''How do I implement voting on the Hive blockchain using dhive.js? I need to understand vote weight calculation and how curation rewards work.''',
        r'''## Voting on Hive with dhive.js — Weight Calculation and Curation

Voting on Hive involves the `vote` operation. Understanding vote weight, voting power, and curation windows is essential for building any Hive application that interacts with content.

### Core Concepts

- **Vote weight**: Ranges from -10000 (full downvote) to 10000 (full upvote). A weight of 5000 = 50% vote.
- **Voting power (VP)**: Each account has voting mana that regenerates at ~20% per day. A full vote at 100% VP uses 2% of your mana.
- **Curation rewards**: Voters earn curation rewards. Since HF25, there is no curation window penalty — rewards are distributed proportionally regardless of vote timing.
- **Posting key** is used for vote operations.

### Basic Vote

```javascript
const dhive = require('@hiveio/dhive');

const client = new dhive.Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
  'https://anyx.io',
]);

const postingKey = dhive.PrivateKey.fromString('5Kexample_YOUR_POSTING_KEY_HERE');

async function vote(voter, author, permlink, weightPercent) {
  // weightPercent: 0-100 for upvote, negative for downvote
  // Convert percentage to protocol weight (-10000 to 10000)
  const weight = Math.round(weightPercent * 100);

  if (weight < -10000 || weight > 10000) {
    throw new Error('Weight must be between -10000 and 10000');
  }

  const op = [
    'vote',
    {
      voter: voter,
      author: author,
      permlink: permlink,
      weight: weight,
    },
  ];

  try {
    const result = await client.broadcast.sendOperations([op], postingKey);
    console.log(`Voted ${weightPercent}% on @${author}/${permlink}`);
    console.log(`Transaction: ${result.id}, Block: ${result.block_num}`);
    return result;
  } catch (err) {
    if (err.message.includes('HIVE_MIN_VOTE_INTERVAL_SEC')) {
      console.error('Must wait 3 seconds between votes');
    } else if (err.message.includes('already voted')) {
      console.error('Already voted on this post — change weight to update vote');
    } else if (err.message.includes('rc_plugin_exception')) {
      console.error('Insufficient Resource Credits to vote');
    } else {
      console.error('Vote failed:', err.message);
    }
    throw err;
  }
}

// Usage
vote('myaccount', 'hivedev', 'my-tutorial-post', 100);  // 100% upvote
```

### Production Vote Bot with Mana Tracking

```javascript
class HiveVoter {
  constructor(account, postingKey, options = {}) {
    this.account = account;
    this.postingKey = dhive.PrivateKey.fromString(postingKey);
    this.client = new dhive.Client(
      options.nodes || [
        'https://api.hive.blog',
        'https://api.deathwing.me',
        'https://anyx.io',
      ]
    );
    this.minVotingPower = options.minVotingPower || 80; // Don't vote below 80%
    this.voteCooldownMs = 3100; // 3.1 seconds between votes (protocol minimum is 3s)
    this.lastVoteTime = 0;
  }

  async getCurrentVotingPower() {
    const [account] = await this.client.database.getAccounts([this.account]);
    if (!account) throw new Error(`Account ${this.account} not found`);

    // Voting mana calculation
    const totalVests = parseFloat(account.vesting_shares) +
      parseFloat(account.received_vesting_shares) -
      parseFloat(account.delegated_vesting_shares);

    // Current mana with regeneration
    const lastVoteTime = new Date(account.voting_manabar.last_update_time * 1000);
    const now = new Date();
    const elapsedSeconds = (now - lastVoteTime) / 1000;

    const maxMana = totalVests * 1e6;
    let currentMana = Number(account.voting_manabar.current_mana);

    // Mana regenerates linearly over 5 days (432000 seconds)
    currentMana += (elapsedSeconds * maxMana) / 432000;
    currentMana = Math.min(currentMana, maxMana);

    const votingPower = (currentMana / maxMana) * 100;
    return {
      votingPower: Math.round(votingPower * 100) / 100,
      currentMana,
      maxMana,
      totalVests,
    };
  }

  calculateVoteValue(votingPower, vests, weightPercent) {
    // Estimate the rshares a vote will produce
    const weight = weightPercent / 100;
    const usedPower = Math.round(votingPower * weight * 100);
    const rshares = Math.round(vests * 1e6 * usedPower / 10000);
    return rshares;
  }

  async voteWithChecks(author, permlink, weightPercent) {
    // 1. Check voting power
    const vpInfo = await this.getCurrentVotingPower();
    console.log(`Current voting power: ${vpInfo.votingPower}%`);

    if (vpInfo.votingPower < this.minVotingPower) {
      const regenHours = ((this.minVotingPower - vpInfo.votingPower) / 20) * 24;
      console.log(`VP too low. Will regenerate to ${this.minVotingPower}% in ~${regenHours.toFixed(1)} hours`);
      return null;
    }

    // 2. Enforce cooldown
    const timeSinceLastVote = Date.now() - this.lastVoteTime;
    if (timeSinceLastVote < this.voteCooldownMs) {
      const waitMs = this.voteCooldownMs - timeSinceLastVote;
      console.log(`Waiting ${waitMs}ms for vote cooldown...`);
      await new Promise(resolve => setTimeout(resolve, waitMs));
    }

    // 3. Check post exists and is within voting window (7 days)
    const content = await this.client.database.call('get_content', [author, permlink]);
    if (!content || content.id === 0) {
      throw new Error(`Post @${author}/${permlink} not found`);
    }

    const created = new Date(content.created + 'Z');
    const age = (Date.now() - created.getTime()) / 1000;
    const sevenDays = 7 * 24 * 3600;
    if (age > sevenDays) {
      throw new Error('Post is past its 7-day payout window — cannot vote');
    }

    // 4. Cast the vote
    const weight = Math.round(weightPercent * 100);
    const op = ['vote', {
      voter: this.account,
      author,
      permlink,
      weight,
    }];

    const result = await this.client.broadcast.sendOperations([op], this.postingKey);
    this.lastVoteTime = Date.now();

    console.log(`Voted ${weightPercent}% on @${author}/${permlink}`);
    console.log(`VP after vote: ~${(vpInfo.votingPower - (weightPercent / 100) * 2).toFixed(2)}%`);
    return result;
  }
}

// Usage
const voter = new HiveVoter('myaccount', '5Kexample_YOUR_POSTING_KEY_HERE', {
  minVotingPower: 85,
});

(async () => {
  const vp = await voter.getCurrentVotingPower();
  console.log(`Voting Power: ${vp.votingPower}%`);

  await voter.voteWithChecks('hivedev', 'building-on-hive', 50); // 50% vote
})();
```

### Important Notes on Voting Mechanics

1. **Mana regeneration**: 20% per day, full recharge in 5 days (432,000 seconds). Each 100% vote costs 2% of max mana.
2. **Downvote mana**: Separate pool equal to 25% of upvote mana. Free downvotes up to that limit; beyond it draws from upvote mana.
3. **Vote editing**: Voting on something you already voted on changes the vote. Weight of 0 removes the vote.
4. **Dust threshold**: Very small votes (low HP accounts at low weight) may be below the dust threshold and have no effect on rewards.
5. **HF25 changes**: Linear curation curve, no early-vote penalty. Curation rewards are 50% of post rewards distributed proportionally by rshares.
'''
    ),
    (
        "hive/development",
        r'''How do I transfer HIVE and HBD tokens using dhive.js? I need encrypted memo support and error handling for insufficient balance.''',
        r'''## Transferring HIVE and HBD with dhive.js — Including Encrypted Memos

Transfers on Hive use the `transfer` operation and require the **active key** (not posting key). Memos can optionally be encrypted so only the sender and recipient can read them.

### Core Concepts

- **Active key** required for all transfer operations
- **Asset format**: Must be exactly `"1.000 HIVE"` or `"1.000 HBD"` — three decimal places, correct symbol
- **Encrypted memos**: Prefix with `#` to encrypt. Uses the memo keys of sender and recipient
- **Transfer to savings**: Separate operation with a 3-day withdrawal delay for security

### Basic Transfer

```javascript
const dhive = require('@hiveio/dhive');

const client = new dhive.Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
  'https://anyx.io',
]);

const activeKey = dhive.PrivateKey.fromString('5Kexample_YOUR_ACTIVE_KEY_HERE');

async function transfer(from, to, amount, currency, memo = '') {
  // Validate currency
  if (!['HIVE', 'HBD'].includes(currency)) {
    throw new Error('Currency must be HIVE or HBD');
  }

  // Format amount to exactly 3 decimal places
  const formattedAmount = `${parseFloat(amount).toFixed(3)} ${currency}`;

  const op = [
    'transfer',
    {
      from: from,
      to: to,
      amount: formattedAmount,
      memo: memo,
    },
  ];

  try {
    const result = await client.broadcast.sendOperations([op], activeKey);
    console.log(`Transferred ${formattedAmount} from @${from} to @${to}`);
    console.log(`Transaction: ${result.id}`);
    return result;
  } catch (err) {
    handleTransferError(err, from, to, formattedAmount);
    throw err;
  }
}

function handleTransferError(err, from, to, amount) {
  const msg = err.message || '';
  if (msg.includes('insufficient') || msg.includes('Account does not have sufficient')) {
    console.error(`Insufficient balance: @${from} cannot send ${amount}`);
  } else if (msg.includes('missing required active authority')) {
    console.error('Wrong key type — active key is required for transfers');
  } else if (msg.includes('does not exist')) {
    console.error(`Account does not exist`);
  } else if (msg.includes('Cannot transfer to self')) {
    console.error('Cannot transfer to yourself');
  } else if (msg.includes('amount.amount > 0')) {
    console.error('Amount must be greater than zero');
  } else {
    console.error('Transfer failed:', msg);
  }
}

// Usage
transfer('alice', 'bob', '10.5', 'HIVE', 'Payment for development work');
```

### Production Transfer with Encrypted Memos and Balance Checking

```javascript
class HiveTransferManager {
  constructor(options) {
    this.client = new dhive.Client(
      options.nodes || ['https://api.hive.blog', 'https://api.deathwing.me']
    );
    this.account = options.account;
    this.activeKey = dhive.PrivateKey.fromString(options.activeWif);
    // Memo key needed for encryption
    this.memoKey = options.memoWif
      ? dhive.PrivateKey.fromString(options.memoWif)
      : null;
  }

  async getBalance(account) {
    const [acc] = await this.client.database.getAccounts([account || this.account]);
    if (!acc) throw new Error(`Account @${account} not found`);

    return {
      hive: parseFloat(acc.balance),
      hbd: parseFloat(acc.hbd_balance),
      hiveSavings: parseFloat(acc.savings_balance),
      hbdSavings: parseFloat(acc.savings_hbd_balance),
      vestingShares: parseFloat(acc.vesting_shares),
      memoKey: acc.memo_key,  // public memo key for encryption
    };
  }

  async encryptMemo(recipientAccount, message) {
    if (!this.memoKey) {
      throw new Error('Memo private key required for encryption');
    }

    // Get recipient's public memo key
    const [recipient] = await this.client.database.getAccounts([recipientAccount]);
    if (!recipient) throw new Error(`Recipient @${recipientAccount} not found`);

    const recipientMemoPublic = recipient.memo_key;

    // Encrypt the memo using dhive's memo module
    const encoded = dhive.Memo.encode(
      this.memoKey,
      recipientMemoPublic,
      `#${message}`
    );
    return encoded;
  }

  async transfer(to, amount, currency, memo = '', options = {}) {
    const { encrypt = false, checkBalance = true } = options;

    // 1. Validate recipient exists
    const [recipient] = await this.client.database.getAccounts([to]);
    if (!recipient) {
      throw new Error(`Recipient account @${to} does not exist`);
    }

    // 2. Optionally check sender balance
    if (checkBalance) {
      const balance = await this.getBalance(this.account);
      const needed = parseFloat(amount);
      const available = currency === 'HIVE' ? balance.hive : balance.hbd;

      if (available < needed) {
        throw new Error(
          `Insufficient ${currency}: have ${available.toFixed(3)}, need ${needed.toFixed(3)}`
        );
      }
    }

    // 3. Handle memo encryption
    let finalMemo = memo;
    if (encrypt && memo) {
      finalMemo = await this.encryptMemo(to, memo);
    }

    // 4. Build and broadcast
    const formattedAmount = `${parseFloat(amount).toFixed(3)} ${currency}`;
    const op = [
      'transfer',
      {
        from: this.account,
        to: to,
        amount: formattedAmount,
        memo: finalMemo,
      },
    ];

    const result = await this.client.broadcast.sendOperations([op], this.activeKey);
    console.log(`Sent ${formattedAmount} to @${to} | tx: ${result.id}`);
    return result;
  }

  async transferToSavings(to, amount, currency, memo = '') {
    const formattedAmount = `${parseFloat(amount).toFixed(3)} ${currency}`;
    const op = [
      'transfer_to_savings',
      {
        from: this.account,
        to: to,
        amount: formattedAmount,
        memo: memo,
      },
    ];

    const result = await this.client.broadcast.sendOperations([op], this.activeKey);
    console.log(`Transferred ${formattedAmount} to savings for @${to}`);
    return result;
  }

  async withdrawFromSavings(amount, currency, requestId = Date.now()) {
    // Withdrawal takes 3 days to complete
    const formattedAmount = `${parseFloat(amount).toFixed(3)} ${currency}`;
    const op = [
      'transfer_from_savings',
      {
        from: this.account,
        to: this.account,
        amount: formattedAmount,
        request_id: requestId,
        memo: '',
      },
    ];

    const result = await this.client.broadcast.sendOperations([op], this.activeKey);
    console.log(`Initiated withdrawal of ${formattedAmount} from savings (3-day delay)`);
    return result;
  }

  async batchTransfer(transfers) {
    // transfers: [{to, amount, currency, memo}]
    // All transfers in one transaction (atomic — all succeed or all fail)
    const ops = transfers.map(({ to, amount, currency, memo = '' }) => [
      'transfer',
      {
        from: this.account,
        to,
        amount: `${parseFloat(amount).toFixed(3)} ${currency}`,
        memo,
      },
    ]);

    const result = await this.client.broadcast.sendOperations(ops, this.activeKey);
    console.log(`Batch transfer: ${transfers.length} transfers in tx ${result.id}`);
    return result;
  }
}

// Usage
const manager = new HiveTransferManager({
  account: 'myaccount',
  activeWif: '5Kexample_YOUR_ACTIVE_KEY_HERE',
  memoWif: '5Kexample_YOUR_MEMO_KEY_HERE',
});

(async () => {
  // Check balance first
  const balance = await manager.getBalance('myaccount');
  console.log(`HIVE: ${balance.hive}, HBD: ${balance.hbd}`);

  // Plain transfer
  await manager.transfer('bob', '5.000', 'HIVE', 'Thanks for the help');

  // Encrypted memo transfer
  await manager.transfer('bob', '10.000', 'HBD', 'Invoice #1234 payment', {
    encrypt: true,
  });

  // Batch payouts
  await manager.batchTransfer([
    { to: 'dev1', amount: '50', currency: 'HBD', memo: 'Sprint payment' },
    { to: 'dev2', amount: '75', currency: 'HBD', memo: 'Sprint payment' },
    { to: 'designer', amount: '30', currency: 'HBD', memo: 'Logo work' },
  ]);
})();
```

### Critical Notes

1. **Asset precision**: Always use `.toFixed(3)`. Sending `"10 HIVE"` instead of `"10.000 HIVE"` will cause a broadcast error.
2. **Memo encryption**: The `#` prefix signals encryption. Both sender's memo private key and recipient's memo public key are needed. Either party can decrypt with their memo private key.
3. **Irreversible transfers**: Unlike traditional banking, blockchain transfers cannot be reversed. Always validate the recipient account exists before sending.
4. **Savings**: HBD in savings earns interest (currently ~15% APR, set by witnesses). The 3-day withdrawal delay provides security against compromised active keys.
5. **Batch atomicity**: Multiple operations in one transaction are atomic. If any fails, none execute.
'''
    ),
    (
        "hive/development",
        r'''How do I broadcast custom_json operations on Hive using dhive.js? I need to understand how apps like Splinterlands and Hive Engine use custom_json for app-specific data.''',
        r'''## custom_json Operations on Hive with dhive.js

`custom_json` is the most versatile operation on Hive. It allows any application to write arbitrary JSON data to the blockchain without affecting the core token system. This is how Layer 2 tokens (Hive Engine), games (Splinterlands), and social features (follows, reblogs, communities) all work.

### Core Concepts

- **id field**: A string identifier for your app (e.g., `"ssc-mainnet-hive"` for Hive Engine, `"sm_market_sale"` for Splinterlands, `"follow"` for follows/mutes)
- **required_auths**: Accounts whose active key signed the transaction (for operations involving tokens/value)
- **required_posting_auths**: Accounts whose posting key signed the transaction (for social/non-financial operations)
- **json field**: Stringified JSON payload — your application defines the schema
- Uses **posting key** when using `required_posting_auths`, **active key** when using `required_auths`

### Basic custom_json — Follow Operation

```javascript
const dhive = require('@hiveio/dhive');

const client = new dhive.Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
  'https://anyx.io',
]);

const postingKey = dhive.PrivateKey.fromString('5Kexample_YOUR_POSTING_KEY_HERE');

async function followAccount(follower, following) {
  // This is the actual format used by the Hive follow plugin
  const json = JSON.stringify([
    'follow',
    {
      follower: follower,
      following: following,
      what: ['blog'],  // ['blog'] = follow, [] = unfollow, ['ignore'] = mute
    },
  ]);

  const op = [
    'custom_json',
    {
      required_auths: [],
      required_posting_auths: [follower],
      id: 'follow',
      json: json,
    },
  ];

  try {
    const result = await client.broadcast.sendOperations([op], postingKey);
    console.log(`@${follower} now follows @${following}`);
    return result;
  } catch (err) {
    console.error('Follow failed:', err.message);
    throw err;
  }
}

async function reblogPost(account, author, permlink) {
  const json = JSON.stringify([
    'reblog',
    {
      account: account,
      author: author,
      permlink: permlink,
    },
  ]);

  const op = [
    'custom_json',
    {
      required_auths: [],
      required_posting_auths: [account],
      id: 'follow',  // reblogs also use the 'follow' id
      json: json,
    },
  ];

  const result = await client.broadcast.sendOperations([op], postingKey);
  console.log(`Reblogged @${author}/${permlink}`);
  return result;
}
```

### Production App-Specific custom_json System

```javascript
class HiveAppBroadcaster {
  constructor(config) {
    this.client = new dhive.Client(
      config.nodes || ['https://api.hive.blog', 'https://api.deathwing.me']
    );
    this.account = config.account;
    this.postingKey = dhive.PrivateKey.fromString(config.postingWif);
    this.activeKey = config.activeWif
      ? dhive.PrivateKey.fromString(config.activeWif)
      : null;
    this.appId = config.appId;  // Your app's unique custom_json ID
    this.maxJsonSize = 8192;    // Hive protocol limit for custom_json
  }

  async broadcastPosting(action, payload) {
    // For social/non-financial operations (posting key)
    return this._broadcast(action, payload, 'posting');
  }

  async broadcastActive(action, payload) {
    // For financial operations (active key)
    if (!this.activeKey) {
      throw new Error('Active key not configured');
    }
    return this._broadcast(action, payload, 'active');
  }

  async _broadcast(action, payload, authType) {
    const jsonPayload = JSON.stringify({
      action: action,
      payload: payload,
      timestamp: new Date().toISOString(),
      version: '1.0',
    });

    // Validate size
    if (Buffer.byteLength(jsonPayload, 'utf8') > this.maxJsonSize) {
      throw new Error(
        `JSON payload too large: ${Buffer.byteLength(jsonPayload, 'utf8')} bytes (max ${this.maxJsonSize})`
      );
    }

    const op = [
      'custom_json',
      {
        required_auths: authType === 'active' ? [this.account] : [],
        required_posting_auths: authType === 'posting' ? [this.account] : [],
        id: this.appId,
        json: jsonPayload,
      },
    ];

    const key = authType === 'active' ? this.activeKey : this.postingKey;

    try {
      const result = await this.client.broadcast.sendOperations([op], key);
      console.log(`[${this.appId}] ${action} broadcast in block ${result.block_num}`);
      return {
        success: true,
        txId: result.id,
        blockNum: result.block_num,
        action,
      };
    } catch (err) {
      this._handleError(err, action);
      throw err;
    }
  }

  _handleError(err, action) {
    const msg = err.message || '';
    if (msg.includes('rc_plugin_exception')) {
      console.error(`RC insufficient for custom_json: ${action}`);
    } else if (msg.includes('custom_json_size')) {
      console.error('JSON payload exceeds 8192 byte limit');
    } else if (msg.includes('missing required')) {
      console.error('Authorization mismatch — check key type');
    } else {
      console.error(`custom_json failed (${action}):`, msg);
    }
  }
}

// ---- Example: Game Actions ----
const gameApp = new HiveAppBroadcaster({
  account: 'player1',
  postingWif: '5Kexample_YOUR_POSTING_KEY_HERE',
  activeWif: '5Kexample_YOUR_ACTIVE_KEY_HERE',
  appId: 'mygame',
});

// Social action (posting key) — record a game move
await gameApp.broadcastPosting('play_card', {
  gameId: 'game-abc123',
  card: 'fire_dragon',
  position: 3,
});

// Financial action (active key) — enter a tournament with a fee
await gameApp.broadcastActive('enter_tournament', {
  tournamentId: 'weekly-001',
  entryFee: '10.000 HIVE',
});

// ---- Example: Hive Engine Token Transfer ----
async function hiveEngineTransfer(from, to, symbol, quantity, memo = '') {
  const activeKey = dhive.PrivateKey.fromString('5Kexample_YOUR_ACTIVE_KEY_HERE');

  const json = JSON.stringify({
    contractName: 'tokens',
    contractAction: 'transfer',
    contractPayload: {
      symbol: symbol,
      to: to,
      quantity: quantity.toString(),
      memo: memo,
    },
  });

  const op = [
    'custom_json',
    {
      required_auths: [from],
      required_posting_auths: [],
      id: 'ssc-mainnet-hive',
      json: json,
    },
  ];

  const result = await client.broadcast.sendOperations([op], activeKey);
  console.log(`Sent ${quantity} ${symbol} to @${to} via Hive Engine`);
  return result;
}

// Transfer 100 LEO tokens
await hiveEngineTransfer('alice', 'bob', 'LEO', '100', 'Payment for article');
```

### Listening for custom_json Operations

```javascript
async function streamCustomJson(appId, callback) {
  const stream = client.blockchain.getOperationsStream();

  stream.on('data', (operation) => {
    if (operation.op[0] === 'custom_json') {
      const data = operation.op[1];
      if (data.id === appId) {
        try {
          const parsed = JSON.parse(data.json);
          callback({
            sender: data.required_posting_auths[0] || data.required_auths[0],
            authType: data.required_auths.length > 0 ? 'active' : 'posting',
            data: parsed,
            block: operation.block,
            txId: operation.trx_id,
          });
        } catch (parseErr) {
          console.error('Invalid JSON in custom_json:', parseErr.message);
        }
      }
    }
  });

  stream.on('error', (err) => {
    console.error('Stream error:', err.message);
    // Reconnect after delay
    setTimeout(() => streamCustomJson(appId, callback), 5000);
  });
}

// Listen for all "mygame" operations
streamCustomJson('mygame', (event) => {
  console.log(`[Block ${event.block}] ${event.sender}: ${JSON.stringify(event.data)}`);
});
```

### Important Notes

1. **Size limit**: `custom_json` payload is capped at 8,192 bytes. For larger data, use `custom_json` as a pointer and store data off-chain (IPFS, etc.).
2. **RC cost**: `custom_json` is cheap in RC but not free. High-frequency apps should monitor RC and implement backoff.
3. **Consensus**: The Hive blockchain stores `custom_json` but does NOT validate its contents. Validation is your app's responsibility. Layer 2 nodes (like Hive Engine) maintain their own state machines.
4. **Well-known IDs**: `follow` (follows/mutes/reblogs), `community` (community ops), `ssc-mainnet-hive` (Hive Engine), `sm_` prefix (Splinterlands), `notify` (notifications).
5. **Auth choice**: Use `required_posting_auths` for low-risk social actions. Use `required_auths` for anything involving value transfer on your Layer 2.
'''
    ),
    (
        "hive/development",
        r'''How do I create a new Hive account programmatically using dhive.js? I need to understand the different account creation methods: claimed accounts, paid creation, and RC delegation.''',
        r'''## Programmatic Account Creation on Hive with dhive.js

Hive offers multiple account creation methods, each suited for different use cases. Understanding the differences is essential for building onboarding flows.

### Account Creation Methods

1. **`account_create`**: Costs a fee (currently ~3 HIVE, set by witnesses). Simple but expensive at scale.
2. **`create_claimed_account`**: Free creation using a previously claimed account token. Two-step process: claim a token (costs RC), then use it to create.
3. **`account_create_with_delegation`** (deprecated since HF20): Previously allowed delegating HP instead of paying a fee. No longer available.
4. **RC delegation**: Separate from account creation — you can delegate Resource Credits to new accounts so they can transact immediately.

### Method 1: Paid Account Creation

```javascript
const dhive = require('@hiveio/dhive');

const client = new dhive.Client([
  'https://api.hive.blog',
  'https://api.deathwing.me',
]);

const activeKey = dhive.PrivateKey.fromString('5Kexample_CREATOR_ACTIVE_KEY');

async function createAccountPaid(creator, newAccountName, password) {
  // Validate account name (3-16 chars, lowercase, dots/dashes allowed but not at start/end)
  if (!/^[a-z][a-z0-9\-\.]{2,15}$/.test(newAccountName)) {
    throw new Error('Invalid account name. Must be 3-16 chars, lowercase alphanumeric, may contain hyphens/dots');
  }

  // Generate keys deterministically from password (standard Hive convention)
  const ownerKey = dhive.PrivateKey.fromLogin(newAccountName, password, 'owner');
  const activeKeyNew = dhive.PrivateKey.fromLogin(newAccountName, password, 'active');
  const postingKeyNew = dhive.PrivateKey.fromLogin(newAccountName, password, 'posting');
  const memoKeyNew = dhive.PrivateKey.fromLogin(newAccountName, password, 'memo');

  const ownerAuth = {
    weight_threshold: 1,
    account_auths: [],
    key_auths: [[ownerKey.createPublic().toString(), 1]],
  };

  const activeAuth = {
    weight_threshold: 1,
    account_auths: [],
    key_auths: [[activeKeyNew.createPublic().toString(), 1]],
  };

  const postingAuth = {
    weight_threshold: 1,
    account_auths: [],
    key_auths: [[postingKeyNew.createPublic().toString(), 1]],
  };

  const op = [
    'account_create',
    {
      fee: '3.000 HIVE',  // Check current fee via witness parameters
      creator: creator,
      new_account_name: newAccountName,
      owner: ownerAuth,
      active: activeAuth,
      posting: postingAuth,
      memo_key: memoKeyNew.createPublic().toString(),
      json_metadata: JSON.stringify({ created_by: creator }),
    },
  ];

  try {
    const result = await client.broadcast.sendOperations([op], activeKey);
    console.log(`Account @${newAccountName} created!`);
    console.log(`Transaction: ${result.id}`);
    return {
      account: newAccountName,
      password: password,  // User must save this!
      txId: result.id,
      keys: {
        owner: ownerKey.toString(),
        active: activeKeyNew.toString(),
        posting: postingKeyNew.toString(),
        memo: memoKeyNew.toString(),
      },
    };
  } catch (err) {
    handleCreationError(err, newAccountName);
    throw err;
  }
}

function handleCreationError(err, name) {
  const msg = err.message || '';
  if (msg.includes('Account name already in use')) {
    console.error(`Account @${name} already exists`);
  } else if (msg.includes('insufficient')) {
    console.error('Creator has insufficient HIVE balance for account creation fee');
  } else if (msg.includes('name is too')) {
    console.error('Account name length invalid');
  } else {
    console.error('Account creation failed:', msg);
  }
}
```

### Method 2: Claimed Account (Free Creation with Account Tokens)

```javascript
class HiveAccountManager {
  constructor(config) {
    this.client = new dhive.Client(
      config.nodes || ['https://api.hive.blog', 'https://api.deathwing.me']
    );
    this.creator = config.creator;
    this.activeKey = dhive.PrivateKey.fromString(config.activeWif);
  }

  async claimAccountToken() {
    // Step 1: Claim a free account token (costs RC, not HIVE)
    // Requires significant RC — typically accounts with 5000+ HP
    const op = [
      'claim_account',
      {
        creator: this.creator,
        fee: '0.000 HIVE',  // 0 = use RC instead of HIVE
        extensions: [],
      },
    ];

    try {
      const result = await this.client.broadcast.sendOperations([op], this.activeKey);
      console.log('Account creation token claimed via RC');
      return result;
    } catch (err) {
      if (err.message.includes('rc_plugin_exception')) {
        console.error('Insufficient RC to claim account token. Need ~5000+ HP equivalent.');
      }
      throw err;
    }
  }

  async getPendingClaimedAccounts() {
    const [account] = await this.client.database.getAccounts([this.creator]);
    return account.pending_claimed_accounts;
  }

  async createClaimedAccount(newAccountName, keys) {
    // Step 2: Use a claimed token to create the account for free
    const pending = await this.getPendingClaimedAccounts();
    if (pending < 1) {
      throw new Error(`No claimed account tokens available. Current: ${pending}`);
    }

    const op = [
      'create_claimed_account',
      {
        creator: this.creator,
        new_account_name: newAccountName,
        owner: {
          weight_threshold: 1,
          account_auths: [],
          key_auths: [[keys.ownerPublic, 1]],
        },
        active: {
          weight_threshold: 1,
          account_auths: [],
          key_auths: [[keys.activePublic, 1]],
        },
        posting: {
          weight_threshold: 1,
          account_auths: [],
          key_auths: [[keys.postingPublic, 1]],
        },
        memo_key: keys.memoPublic,
        json_metadata: JSON.stringify({
          created_by: this.creator,
          created_at: new Date().toISOString(),
        }),
        extensions: [],
      },
    ];

    const result = await this.client.broadcast.sendOperations([op], this.activeKey);
    console.log(`Account @${newAccountName} created using claimed token`);
    console.log(`Remaining tokens: ${pending - 1}`);
    return result;
  }

  async delegateRC(to, maxRC) {
    // Delegate Resource Credits so the new account can transact
    // This is separate from HP delegation
    const op = [
      'custom_json',
      {
        required_auths: [this.creator],
        required_posting_auths: [],
        id: 'rc',
        json: JSON.stringify([
          'delegate_rc',
          {
            from: this.creator,
            delegatees: [to],
            max_rc: maxRC,  // e.g., 5000000000 for basic operations
          },
        ]),
      },
    ];

    const result = await this.client.broadcast.sendOperations([op], this.activeKey);
    console.log(`Delegated ${maxRC} RC to @${to}`);
    return result;
  }

  async fullOnboarding(newAccountName, password) {
    // Complete onboarding: create account + delegate RC + initial HP delegation
    console.log(`Starting onboarding for @${newAccountName}...`);

    // Generate keys from master password
    const keys = {
      ownerPublic: dhive.PrivateKey.fromLogin(newAccountName, password, 'owner')
        .createPublic().toString(),
      activePublic: dhive.PrivateKey.fromLogin(newAccountName, password, 'active')
        .createPublic().toString(),
      postingPublic: dhive.PrivateKey.fromLogin(newAccountName, password, 'posting')
        .createPublic().toString(),
      memoPublic: dhive.PrivateKey.fromLogin(newAccountName, password, 'memo')
        .createPublic().toString(),
    };

    // 1. Create account using claimed token
    await this.createClaimedAccount(newAccountName, keys);

    // 2. Delegate RC so they can interact immediately
    await this.delegateRC(newAccountName, 5000000000);

    // 3. Optionally delegate HP for visibility and voting
    const delegateOp = [
      'delegate_vesting_shares',
      {
        delegator: this.creator,
        delegatee: newAccountName,
        vesting_shares: '10.000000 VESTS',
      },
    ];
    await this.client.broadcast.sendOperations([delegateOp], this.activeKey);
    console.log('Delegated initial VESTS to new account');

    console.log(`Onboarding complete for @${newAccountName}`);
    return { account: newAccountName, keys };
  }
}

// Usage
const manager = new HiveAccountManager({
  creator: 'myapp',
  activeWif: '5Kexample_CREATOR_ACTIVE_KEY',
});

(async () => {
  // Check available tokens
  const tokens = await manager.getPendingClaimedAccounts();
  console.log(`Available account tokens: ${tokens}`);

  // Claim more tokens if needed
  if (tokens < 5) {
    await manager.claimAccountToken();
  }

  // Create and onboard a new user
  const password = 'P5' + dhive.cryptoUtils.generateTrxId().slice(0, 45);
  await manager.fullOnboarding('newuser123', password);
  console.log('SAVE THIS PASSWORD:', password);
})();
```

### Important Notes

1. **Account name rules**: 3-16 characters, starts with a letter, lowercase only, may contain digits/hyphens/dots but not consecutively and not at the end.
2. **Key hierarchy**: Owner > Active > Posting > Memo. Owner can change all other keys. Active handles financial ops. Posting handles social ops. Memo is for encryption only.
3. **Claimed tokens**: Large stakeholders (5000+ HP) can claim ~1 token every 6 hours using RC. Tokens do not expire. This is the standard method for dApp onboarding.
4. **RC delegation**: Introduced in HF26. Unlike HP delegation, RC delegation does not give voting power — only the ability to transact. Perfect for onboarding: delegate enough RC for ~10 transactions per day.
5. **Security**: Never store or transmit the master password or owner key in your application. Generate keys client-side, show the user once, and only store the public keys on your server.
'''
    ),
]
