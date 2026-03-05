"""P1 Batch: Modern web frameworks — HTMX, Astro, SvelteKit, React Server Components."""

PAIRS = [
    (
        "HTMX hypermedia-driven web applications",
        "Explain HTMX — what problem does it solve, how does it differ from React/Vue, and when should you use it? Show a complete working example of a dynamic web app using HTMX with a Python backend.",
        """## HTMX: The Anti-Framework Framework

### The Problem HTMX Solves

Modern web development assumes you need a JavaScript framework (React, Vue, Svelte) for any interactivity. This means: a build step, a bundler, a Node.js toolchain, client-side routing, state management, hydration, and megabytes of JavaScript shipped to the browser.

HTMX takes a radically different approach: **the server sends HTML, not JSON**. Any HTML element can make HTTP requests and swap the response into the page. No JavaScript needed (beyond the 14KB HTMX library).

### How It Works

```html
<!-- Traditional approach: fetch JSON, parse it, update DOM with JavaScript -->
<button onclick="fetch('/api/users').then(r => r.json()).then(data => {
    document.getElementById('user-list').innerHTML = data.map(u =>
        `<li>${u.name}</li>`).join('');
})">Load Users</button>

<!-- HTMX approach: server returns HTML, HTMX swaps it in -->
<button hx-get="/users" hx-target="#user-list" hx-swap="innerHTML">
    Load Users
</button>
<div id="user-list"></div>
```

That's it. No JavaScript, no build step, no framework. The `hx-get` attribute tells HTMX to make a GET request, `hx-target` says where to put the response, and `hx-swap` says how to insert it.

### Complete Example: Task Manager with Flask + HTMX

```python
# app.py — A complete dynamic web app with ZERO client-side JavaScript
from flask import Flask, render_template_string, request

app = Flask(__name__)

# In-memory task store (use a database in production)
tasks = [
    {"id": 1, "text": "Learn HTMX", "done": False},
    {"id": 2, "text": "Build something cool", "done": False},
]
next_id = 3

LAYOUT = \"\"\"<!DOCTYPE html>
<html>
<head>
    <title>HTMX Task Manager</title>
    <script src="https://unpkg.com/htmx.org@2.0.0"></script>
    <style>
        body { font-family: system-ui; max-width: 600px; margin: 2rem auto; }
        .done { text-decoration: line-through; opacity: 0.6; }
        .task { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem; }
        .task:hover { background: #f5f5f5; }
        input[type=text] { flex: 1; padding: 0.5rem; font-size: 1rem; }
        button { padding: 0.5rem 1rem; cursor: pointer; }
        .htmx-indicator { display: none; }
        .htmx-request .htmx-indicator { display: inline; }
    </style>
</head>
<body>
    <h1>Task Manager</h1>

    <!-- Add task form: submits via HTMX, appends result to task list -->
    <form hx-post="/tasks" hx-target="#task-list" hx-swap="beforeend"
          hx-on::after-request="this.reset()">
        <input type="text" name="text" placeholder="New task..." required>
        <button type="submit">Add</button>
        <span class="htmx-indicator">Adding...</span>
    </form>

    <!-- Task list: each task is independently updatable -->
    <div id="task-list">
        {% for task in tasks %}
        """ + '{{ task_html(task) }}' + """
        {% endfor %}
    </div>

    <!-- Live search: filters as you type (debounced) -->
    <input type="search" name="q" placeholder="Search tasks..."
           hx-get="/tasks/search" hx-target="#task-list"
           hx-trigger="input changed delay:300ms"
           hx-indicator=".htmx-indicator">
</body>
</html>\"\"\"

TASK_TEMPLATE = \"\"\"
<div class="task {{ 'done' if task.done else '' }}" id="task-{{ task.id }}">
    <input type="checkbox" {{ 'checked' if task.done else '' }}
           hx-patch="/tasks/{{ task.id }}/toggle"
           hx-target="#task-{{ task.id }}"
           hx-swap="outerHTML">
    <span>{{ task.text }}</span>
    <button hx-delete="/tasks/{{ task.id }}"
            hx-target="#task-{{ task.id }}"
            hx-swap="outerHTML"
            hx-confirm="Delete this task?">X</button>
</div>
\"\"\"


def render_task(task):
    return render_template_string(TASK_TEMPLATE, task=task)


@app.route("/")
def index():
    return render_template_string(LAYOUT, tasks=tasks, task_html=render_task)


@app.route("/tasks", methods=["POST"])
def add_task():
    global next_id
    text = request.form.get("text", "").strip()
    if not text:
        return "", 400
    task = {"id": next_id, "text": text, "done": False}
    next_id += 1
    tasks.append(task)
    # Return JUST the new task HTML — HTMX appends it to the list
    return render_task(task)


@app.route("/tasks/<int:task_id>/toggle", methods=["PATCH"])
def toggle_task(task_id):
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return "", 404
    task["done"] = not task["done"]
    # Return the updated task HTML — HTMX swaps it in place
    return render_task(task)


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    global tasks
    tasks = [t for t in tasks if t["id"] != task_id]
    return ""  # Empty response — HTMX removes the element


@app.route("/tasks/search")
def search_tasks():
    q = request.args.get("q", "").lower()
    filtered = [t for t in tasks if q in t["text"].lower()] if q else tasks
    return "".join(render_task(t) for t in filtered)


if __name__ == "__main__":
    app.run(debug=True)
```

### HTMX vs React: When to Use Each

| Aspect | HTMX | React |
|--------|------|-------|
| **Build step** | None | Webpack/Vite/etc. |
| **JS shipped to client** | 14KB | 100KB-2MB+ |
| **State management** | Server (session/DB) | Client (Redux/Zustand) |
| **SEO** | Free (server-rendered) | Requires SSR/SSG |
| **Real-time updates** | SSE/WebSocket + hx-swap | useState/useEffect |
| **Offline support** | None | Service workers |
| **Team skills needed** | Backend dev | Frontend + backend dev |
| **Best for** | CRUD apps, dashboards, internal tools | SPAs, offline-first, complex UI |

The rule of thumb: if your app is primarily a server-side application with some dynamic elements (admin panels, dashboards, content management), HTMX is simpler and faster to build. If your app is primarily a client-side application with complex state (collaborative editors, real-time games, offline-capable), use React/Vue/Svelte.

The common mistake is using React for everything. Most business applications are server-driven CRUD — HTMX handles these with 10× less code and complexity.""",
    ),

    (
        "Astro framework for content-first websites",
        "Explain the Astro web framework — its island architecture, zero-JS-by-default approach, and content collections. When should you choose Astro over Next.js? Show a complete example with interactive islands.",
        """## Astro: Ship Zero JavaScript by Default

### The Problem with SPAs for Content Sites

If you build a documentation site, blog, or marketing page with Next.js, you're shipping React's runtime (~80KB gzipped) to every visitor — even though 95% of the page is static HTML that never changes. This JavaScript must be downloaded, parsed, and executed before the page is interactive. On mobile devices, this adds 2-5 seconds of delay.

Astro's approach: **render everything to static HTML at build time. Only ship JavaScript for the components that need interactivity.** This is the "island architecture" — the page is a sea of static HTML with interactive "islands" where JavaScript is loaded.

### Zero JS by Default

```astro
---
// src/pages/index.astro
// The --- fence is server-side code (runs at BUILD time, not in the browser)
const posts = await fetch('https://api.example.com/posts').then(r => r.json());
const title = "My Blog";
---

<html>
<head><title>{title}</title></head>
<body>
  <h1>{title}</h1>
  <p>This page ships ZERO JavaScript to the browser.</p>

  <!-- Static rendering — no JS needed -->
  <ul>
    {posts.map(post => (
      <li>
        <a href={`/blog/${post.slug}`}>{post.title}</a>
        <time>{new Date(post.date).toLocaleDateString()}</time>
      </li>
    ))}
  </ul>

  <!-- This React component IS an island — JS loads only for this -->
  <SearchWidget client:visible />
  <!-- client:visible = load JS only when scrolled into view -->
</body>
</html>
```

### Island Architecture: Selective Hydration

```astro
---
// src/pages/docs.astro
// Mix ANY framework's components — React, Vue, Svelte, Solid
import ReactSearch from '../components/Search.tsx';
import VueCounter from '../components/Counter.vue';
import SvelteAccordion from '../components/Accordion.svelte';
---

<html>
<body>
  <!-- Static: no JS -->
  <nav>
    <a href="/">Home</a>
    <a href="/docs">Docs</a>
  </nav>

  <!-- Island: React search with client-side JS -->
  <!-- client:load = load JS immediately (above the fold, critical) -->
  <ReactSearch client:load placeholder="Search docs..." />

  <!-- Static: rendered at build time -->
  <article>
    <h1>Getting Started</h1>
    <p>This is static content. No JavaScript needed.</p>
  </article>

  <!-- Island: Vue counter loads when visible (lazy) -->
  <VueCounter client:visible initial={0} />

  <!-- Island: Svelte accordion loads on idle (low priority) -->
  <SvelteAccordion client:idle items={faqItems} />

  <!-- client:media = load only on desktop (responsive islands) -->
  <ReactSearch client:media="(min-width: 768px)" />
</body>
</html>
```

### Content Collections: Type-Safe Content Management

```typescript
// src/content/config.ts — Define your content schema
import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
    type: 'content',
    schema: z.object({
        title: z.string(),
        date: z.date(),
        author: z.string(),
        tags: z.array(z.string()),
        draft: z.boolean().default(false),
        // Astro validates ALL content at build time
        // A typo in any .md frontmatter = build error, not runtime error
    }),
});

const docs = defineCollection({
    type: 'content',
    schema: z.object({
        title: z.string(),
        section: z.enum(['getting-started', 'api', 'guides', 'reference']),
        order: z.number(),
    }),
});

export const collections = { blog, docs };
```

```astro
---
// src/pages/blog/[...slug].astro — Type-safe blog posts
import { getCollection } from 'astro:content';

export async function getStaticPaths() {
    const posts = await getCollection('blog', ({ data }) => !data.draft);
    return posts.map(post => ({
        params: { slug: post.slug },
        props: { post },
    }));
}

const { post } = Astro.props;
const { Content } = await post.render();
---

<html>
<body>
  <article>
    <h1>{post.data.title}</h1>
    <time>{post.data.date.toLocaleDateString()}</time>
    <div class="tags">
      {post.data.tags.map(tag => <span class="tag">{tag}</span>)}
    </div>
    <!-- Renders the Markdown content as HTML -->
    <Content />
  </article>
</body>
</html>
```

### Astro vs Next.js Decision Matrix

| Factor | Astro | Next.js |
|--------|-------|---------|
| **Content sites (blogs, docs)** | Ideal (zero JS) | Overkill (ships React runtime) |
| **Marketing/landing pages** | Ideal | Works but heavier |
| **Web applications** | Possible with islands | Ideal (full React) |
| **Performance (Lighthouse)** | 95-100 typical | 70-90 typical |
| **Framework flexibility** | Use any (React+Vue+Svelte) | React only |
| **Data fetching** | Build-time (SSG) + server (SSR) | SSG + SSR + ISR + RSC |
| **Auth/sessions** | Possible but limited | Full support |
| **Learning curve** | Low (HTML + JS basics) | Medium (React ecosystem) |

Choose Astro when content is king and interactivity is secondary. Choose Next.js when the app IS the interaction.""",
    ),

    (
        "SvelteKit full-stack web applications",
        "Explain SvelteKit — how it differs from React/Next.js, what 'compiler-first' means, and how to build a full-stack app. Show a complete example with routing, server-side data loading, and forms.",
        """## SvelteKit: The Compiler-First Full-Stack Framework

### Why Svelte is Fundamentally Different

React, Vue, and Angular all use a **virtual DOM**: your component renders a virtual tree, the framework diffs it against the previous tree, and applies the minimal DOM changes. This diffing happens on every state change, in the browser, at runtime.

Svelte takes a completely different approach: it's a **compiler**. At build time, Svelte analyzes your component, figures out exactly which DOM nodes depend on which variables, and generates vanilla JavaScript that surgically updates only those nodes. No virtual DOM, no diffing, no runtime framework.

The result: Svelte apps ship 30-50% less JavaScript and run faster because there's no framework overhead on every state change.

```svelte
<!-- Counter.svelte — This compiles to ~2KB of vanilla JS -->
<script>
    let count = 0;

    // No useState, no useEffect, no dependency arrays.
    // The compiler knows 'count' is reactive because it's assigned to.
    function increment() {
        count += 1;  // Svelte detects this assignment and updates the DOM
    }

    // Reactive declarations: recompute when dependencies change
    $: doubled = count * 2;
    $: if (count > 10) {
        console.log('Count exceeded 10');
    }
</script>

<button on:click={increment}>
    Clicks: {count} (doubled: {doubled})
</button>

<style>
    /* Styles are scoped to this component by default */
    button { padding: 1rem 2rem; font-size: 1.2rem; }
</style>
```

### SvelteKit: Full-Stack with File-Based Routing

```
src/routes/
├── +page.svelte          # Home page (/)
├── +page.server.js       # Server-side data loading for /
├── +layout.svelte        # Shared layout (nav, footer)
├── blog/
│   ├── +page.svelte      # Blog listing (/blog)
│   ├── +page.server.js   # Load blog posts server-side
│   └── [slug]/
│       ├── +page.svelte  # Individual post (/blog/my-post)
│       └── +page.server.js
├── api/
│   └── tasks/
│       └── +server.js    # API endpoint (/api/tasks)
```

### Complete Example: Task App with Server-Side Logic

```javascript
// src/routes/+page.server.js — Runs ONLY on the server
// This never ships to the browser — safe for DB queries, API keys, etc.

// Simulate a database
let tasks = [
    { id: 1, text: 'Learn SvelteKit', done: false },
    { id: 2, text: 'Build something', done: false },
];
let nextId = 3;

/** @type {import('./$types').PageServerLoad} */
export async function load() {
    // This runs on the server for every request (or is cached)
    return {
        tasks: tasks.map(t => ({ ...t })),  // Clone to prevent mutation
    };
}

/** @type {import('./$types').Actions} */
export const actions = {
    // Form actions: handle POST requests without writing API endpoints
    add: async ({ request }) => {
        const data = await request.formData();
        const text = data.get('text')?.toString().trim();
        if (!text) return { error: 'Task text is required' };

        tasks.push({ id: nextId++, text, done: false });
        // No redirect needed — SvelteKit automatically re-runs load()
    },

    toggle: async ({ request }) => {
        const data = await request.formData();
        const id = parseInt(data.get('id'));
        const task = tasks.find(t => t.id === id);
        if (task) task.done = !task.done;
    },

    delete: async ({ request }) => {
        const data = await request.formData();
        const id = parseInt(data.get('id'));
        tasks = tasks.filter(t => t.id !== id);
    },
};
```

```svelte
<!-- src/routes/+page.svelte — Client-side component -->
<script>
    /** @type {import('./$types').PageData} */
    export let data;  // Populated by load() function above

    // Progressive enhancement: works without JavaScript!
    // Forms submit normally; with JS, SvelteKit intercepts for SPA behavior.
    import { enhance } from '$app/forms';
</script>

<h1>Tasks ({data.tasks.filter(t => !t.done).length} remaining)</h1>

<!-- Progressive enhancement: use:enhance makes it SPA-like when JS loads -->
<form method="POST" action="?/add" use:enhance>
    <input type="text" name="text" placeholder="New task..." required>
    <button type="submit">Add</button>
</form>

{#each data.tasks as task (task.id)}
    <div class="task" class:done={task.done}>
        <form method="POST" action="?/toggle" use:enhance>
            <input type="hidden" name="id" value={task.id}>
            <button type="submit" class="toggle">
                {task.done ? '✓' : '○'}
            </button>
        </form>

        <span>{task.text}</span>

        <form method="POST" action="?/delete" use:enhance>
            <input type="hidden" name="id" value={task.id}>
            <button type="submit" class="delete">×</button>
        </form>
    </div>
{/each}

<style>
    .task { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem; }
    .done span { text-decoration: line-through; opacity: 0.5; }
    .toggle { background: none; border: none; font-size: 1.2rem; cursor: pointer; }
    .delete { background: none; border: none; color: red; cursor: pointer; }
</style>
```

### SvelteKit vs Next.js

| Feature | SvelteKit | Next.js |
|---------|-----------|---------|
| **Runtime JS** | ~5KB (no framework) | ~80KB (React runtime) |
| **Reactivity model** | Compiler-analyzed assignments | Virtual DOM diffing |
| **Learning curve** | Low (HTML + JS) | Medium (hooks, useEffect, etc.) |
| **Form handling** | Built-in form actions | Need react-hook-form or similar |
| **Progressive enhancement** | Built-in (works without JS) | Requires deliberate effort |
| **Ecosystem** | Growing, smaller | Massive, mature |
| **TypeScript** | First-class | First-class |
| **Deployment** | Adapters for any platform | Vercel-optimized |

SvelteKit's killer feature: **progressive enhancement**. Every form works without JavaScript. When JS loads, SvelteKit upgrades the experience with client-side navigation, optimistic UI updates, and seamless transitions. This means your app is functional on slow connections, old browsers, and for screen readers — by default, not as an afterthought.""",
    ),

    (
        "Solana blockchain development with Anchor framework",
        "Explain Solana blockchain development — its account model, how it differs from Ethereum, and how to build smart contracts using the Anchor framework in Rust. Show a complete token vesting contract example.",
        """## Solana: High-Throughput Blockchain with Account-Based State

### Solana vs Ethereum: Fundamental Differences

Ethereum stores state IN the smart contract (contract has its own storage). Solana separates programs from state — programs are stateless, and all data lives in **accounts** that are passed to programs as arguments. This is why Solana can parallelize: transactions that touch different accounts can execute simultaneously.

| Aspect | Ethereum | Solana |
|--------|----------|--------|
| **State model** | Contract storage (key-value in contract) | Account model (separate data accounts) |
| **Language** | Solidity | Rust (via Anchor framework) |
| **Execution** | Sequential (all txs in order) | Parallel (non-overlapping accounts) |
| **Throughput** | ~15-30 TPS | ~4,000+ TPS |
| **Fees** | $1-100+ (variable, auction-based) | ~$0.00025 (fixed, predictable) |
| **Finality** | ~12 minutes | ~400ms |

### Anchor Framework: Solana's Hardhat

Anchor abstracts Solana's raw account model into something manageable. It handles serialization, account validation, error handling, and testing.

```rust
// programs/vesting/src/lib.rs — Token vesting contract
use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

declare_id!("VEST1111111111111111111111111111111111111111");

#[program]
pub mod vesting {
    use super::*;

    /// Create a new vesting schedule.
    /// Tokens are locked and released linearly over the vesting period.
    ///
    /// Why linear vesting? It's the simplest model that aligns incentives:
    /// the recipient must stay engaged to receive their full allocation.
    /// Cliff vesting (all-or-nothing) creates a perverse incentive to leave
    /// immediately after the cliff. Linear vesting keeps incentives continuous.
    pub fn create_vesting(
        ctx: Context<CreateVesting>,
        amount: u64,
        start_ts: i64,
        cliff_ts: i64,      // No tokens released before this timestamp
        end_ts: i64,         // All tokens released by this timestamp
    ) -> Result<()> {
        require!(amount > 0, VestingError::ZeroAmount);
        require!(start_ts < cliff_ts, VestingError::InvalidSchedule);
        require!(cliff_ts < end_ts, VestingError::InvalidSchedule);

        let vesting = &mut ctx.accounts.vesting_account;
        vesting.beneficiary = ctx.accounts.beneficiary.key();
        vesting.mint = ctx.accounts.token_mint.key();
        vesting.total_amount = amount;
        vesting.released_amount = 0;
        vesting.start_ts = start_ts;
        vesting.cliff_ts = cliff_ts;
        vesting.end_ts = end_ts;
        vesting.bump = ctx.bumps.vesting_account;

        // Transfer tokens from creator to vesting escrow
        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.creator_token.to_account_info(),
                    to: ctx.accounts.escrow_token.to_account_info(),
                    authority: ctx.accounts.creator.to_account_info(),
                },
            ),
            amount,
        )?;

        emit!(VestingCreated {
            beneficiary: vesting.beneficiary,
            amount,
            cliff_ts,
            end_ts,
        });

        Ok(())
    }

    /// Release vested tokens to the beneficiary.
    /// Anyone can call this (permissionless), but tokens always go to the beneficiary.
    pub fn release(ctx: Context<Release>) -> Result<()> {
        let vesting = &mut ctx.accounts.vesting_account;
        let clock = Clock::get()?;
        let now = clock.unix_timestamp;

        // Calculate vested amount
        let vested = calculate_vested(
            vesting.total_amount,
            vesting.start_ts,
            vesting.cliff_ts,
            vesting.end_ts,
            now,
        );

        let releasable = vested.checked_sub(vesting.released_amount)
            .ok_or(VestingError::MathOverflow)?;
        require!(releasable > 0, VestingError::NothingToRelease);

        // Transfer from escrow to beneficiary (PDA-signed)
        let seeds = &[
            b"vesting",
            vesting.beneficiary.as_ref(),
            &[vesting.bump],
        ];
        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.escrow_token.to_account_info(),
                    to: ctx.accounts.beneficiary_token.to_account_info(),
                    authority: ctx.accounts.vesting_account.to_account_info(),
                },
                &[seeds],
            ),
            releasable,
        )?;

        vesting.released_amount += releasable;

        emit!(TokensReleased {
            beneficiary: vesting.beneficiary,
            amount: releasable,
            total_released: vesting.released_amount,
        });

        Ok(())
    }
}

fn calculate_vested(total: u64, start: i64, cliff: i64, end: i64, now: i64) -> u64 {
    if now < cliff {
        0  // Before cliff: nothing vested
    } else if now >= end {
        total  // After end: everything vested
    } else {
        // Linear vesting between cliff and end
        let elapsed = (now - start) as u128;
        let duration = (end - start) as u128;
        ((total as u128 * elapsed) / duration) as u64
    }
}

// Account structures — Anchor handles serialization automatically
#[account]
pub struct VestingAccount {
    pub beneficiary: Pubkey,     // Who receives the tokens
    pub mint: Pubkey,            // Which token
    pub total_amount: u64,       // Total tokens in vesting
    pub released_amount: u64,    // Tokens already released
    pub start_ts: i64,           // Vesting start timestamp
    pub cliff_ts: i64,           // Cliff timestamp
    pub end_ts: i64,             // Full vesting timestamp
    pub bump: u8,                // PDA bump seed
}

// Validation structs — Anchor validates all constraints before the instruction runs
#[derive(Accounts)]
pub struct CreateVesting<'info> {
    #[account(mut)]
    pub creator: Signer<'info>,

    /// CHECK: Beneficiary doesn't need to sign (they receive tokens)
    pub beneficiary: UncheckedAccount<'info>,

    #[account(
        init,
        payer = creator,
        space = 8 + std::mem::size_of::<VestingAccount>(),
        seeds = [b"vesting", beneficiary.key().as_ref()],
        bump,
    )]
    pub vesting_account: Account<'info, VestingAccount>,

    pub token_mint: Account<'info, anchor_spl::token::Mint>,

    #[account(mut, constraint = creator_token.owner == creator.key())]
    pub creator_token: Account<'info, TokenAccount>,

    #[account(mut, constraint = escrow_token.owner == vesting_account.key())]
    pub escrow_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Release<'info> {
    #[account(
        mut,
        seeds = [b"vesting", vesting_account.beneficiary.as_ref()],
        bump = vesting_account.bump,
    )]
    pub vesting_account: Account<'info, VestingAccount>,

    #[account(mut, constraint = escrow_token.owner == vesting_account.key())]
    pub escrow_token: Account<'info, TokenAccount>,

    #[account(mut, constraint = beneficiary_token.owner == vesting_account.beneficiary)]
    pub beneficiary_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

#[error_code]
pub enum VestingError {
    #[msg("Amount must be greater than zero")]
    ZeroAmount,
    #[msg("Invalid vesting schedule: start < cliff < end required")]
    InvalidSchedule,
    #[msg("No tokens available to release")]
    NothingToRelease,
    #[msg("Math overflow")]
    MathOverflow,
}

#[event]
pub struct VestingCreated {
    pub beneficiary: Pubkey,
    pub amount: u64,
    pub cliff_ts: i64,
    pub end_ts: i64,
}

#[event]
pub struct TokensReleased {
    pub beneficiary: Pubkey,
    pub amount: u64,
    pub total_released: u64,
}
```

### Testing with Anchor

```typescript
// tests/vesting.ts — Anchor test framework
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { Vesting } from "../target/types/vesting";
import { assert } from "chai";

describe("vesting", () => {
    const provider = anchor.AnchorProvider.env();
    anchor.setProvider(provider);
    const program = anchor.workspace.Vesting as Program<Vesting>;

    it("creates a vesting schedule", async () => {
        const now = Math.floor(Date.now() / 1000);
        const cliff = now + 86400;  // 1 day
        const end = now + 86400 * 365;  // 1 year

        const tx = await program.methods
            .createVesting(
                new anchor.BN(1_000_000),  // 1M tokens
                new anchor.BN(now),
                new anchor.BN(cliff),
                new anchor.BN(end),
            )
            .accounts({
                creator: provider.wallet.publicKey,
                // ... other accounts
            })
            .rpc();

        console.log("Transaction:", tx);
    });

    it("rejects release before cliff", async () => {
        try {
            await program.methods.release().accounts({/* ... */}).rpc();
            assert.fail("Should have thrown");
        } catch (err) {
            assert.include(err.message, "NothingToRelease");
        }
    });
});
```

Solana development is more complex than Ethereum because of the account model, but the payoff is massive: 400ms finality, $0.00025 fees, and parallel execution. The Anchor framework makes it manageable by handling the boilerplate that would otherwise take hundreds of lines of raw Rust.""",
    ),
]
