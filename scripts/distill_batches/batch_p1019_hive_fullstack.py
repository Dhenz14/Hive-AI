"""
Hive blockchain full-stack dApp training pairs: Next.js + Hive, React + dhive,
Vue + hiveTX, mobile Hive integration, SSR with Hive data.
"""

PAIRS = [
    (
        "hive-fullstack-nextjs",
        r'''How do I build a full-stack Next.js application that integrates with the Hive blockchain for posting, voting, and displaying content?''',
        r'''<think>
A Next.js + Hive dApp needs several components: server-side data fetching for SEO (using getServerSideProps or App Router server components), client-side signing via Hive Keychain, API routes for backend operations, and proper handling of the dhive library (which has Node.js dependencies that need careful handling in Next.js). I should show a complete structure with both read operations (server) and write operations (client via Keychain).
</think>

Building a Next.js dApp with Hive requires server-side rendering for content (SEO), client-side Keychain integration for signing, and API routes for backend logic. Here is a complete application structure:

```javascript
// === package.json dependencies ===
// "@hiveio/dhive": "^1.3.0"
// "next": "^14.0.0"
// "react": "^18.0.0"

// === lib/hive.js - Shared Hive client ===
import { Client } from "@hiveio/dhive";

// Server-side client (used in API routes and getServerSideProps)
export function getHiveClient() {
    return new Client([
        "https://api.hive.blog",
        "https://api.deathwing.me",
        "https://rpc.ausbit.dev"
    ]);
}

export async function fetchPost(author, permlink) {
    const client = getHiveClient();
    return client.call("bridge", "get_post", { author, permlink });
}

export async function fetchTrending(tag = "", limit = 20) {
    const client = getHiveClient();
    const params = { sort: "trending", limit };
    if (tag) params.tag = tag;
    return client.call("bridge", "get_ranked_posts", params);
}

export async function fetchAccountPosts(account, limit = 20) {
    const client = getHiveClient();
    return client.call("bridge", "get_account_posts", {
        account, sort: "posts", limit
    });
}

export async function fetchProfile(account) {
    const client = getHiveClient();
    return client.call("bridge", "get_profile", { account });
}

// === lib/keychain.js - Client-side Keychain helper ===
export function isKeychainInstalled() {
    return typeof window !== "undefined" && !!window.hive_keychain;
}

export function keychainVote(voter, author, permlink, weight) {
    return new Promise((resolve, reject) => {
        if (!isKeychainInstalled()) {
            reject(new Error("Hive Keychain not installed"));
            return;
        }
        window.hive_keychain.requestVote(
            voter, permlink, author, weight,
            (response) => {
                if (response.success) resolve(response);
                else reject(new Error(response.message));
            }
        );
    });
}

export function keychainPost(author, title, body, parentPermlink, jsonMeta, permlink) {
    return new Promise((resolve, reject) => {
        if (!isKeychainInstalled()) {
            reject(new Error("Hive Keychain not installed"));
            return;
        }
        window.hive_keychain.requestPost(
            author, title, body,
            parentPermlink, "", // parent_author empty for top-level posts
            jsonMeta, permlink, "",
            (response) => {
                if (response.success) resolve(response);
                else reject(new Error(response.message));
            }
        );
    });
}

export function keychainLogin(username) {
    return new Promise((resolve, reject) => {
        const message = `login-${Date.now()}`;
        window.hive_keychain.requestSignBuffer(
            username, message, "Posting",
            (response) => {
                if (response.success) {
                    resolve({ username, publicKey: response.publicKey });
                } else {
                    reject(new Error(response.message));
                }
            }
        );
    });
}

// === app/page.js - Home page (App Router, Server Component) ===
import { fetchTrending } from "@/lib/hive";
import PostCard from "@/components/PostCard";

export const revalidate = 60; // ISR: revalidate every 60 seconds

export default async function HomePage() {
    const posts = await fetchTrending("", 10);
    return (
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-6">Trending on Hive</h1>
            <div className="grid gap-6">
                {posts.map((post) => (
                    <PostCard key={`${post.author}/${post.permlink}`} post={post} />
                ))}
            </div>
        </div>
    );
}

// === components/PostCard.jsx - Post display component ===
import Link from "next/link";

export default function PostCard({ post }) {
    const payout = parseFloat(post.payout || 0).toFixed(2);
    const votes = post.stats?.total_votes || 0;
    const created = new Date(post.created).toLocaleDateString();
    const imageMatch = post.body?.match(/!\[.*?\]\((https?:\/\/[^\)]+)\)/);
    const thumbnail = post.json_metadata?.image?.[0] || imageMatch?.[1] || null;

    return (
        <div className="border rounded-lg p-4 hover:shadow-lg transition">
            <div className="flex gap-4">
                {thumbnail && (
                    <img src={thumbnail} alt="" className="w-32 h-24 object-cover rounded" />
                )}
                <div className="flex-1">
                    <Link href={`/@${post.author}/${post.permlink}`}
                          className="text-xl font-semibold hover:text-blue-600">
                        {post.title}
                    </Link>
                    <p className="text-gray-600 text-sm mt-1">
                        by <Link href={`/@${post.author}`} className="font-medium">
                            @{post.author}
                        </Link> | {created}
                    </p>
                    <p className="text-gray-500 text-sm mt-2">
                        {post.body?.replace(/[#*!\[\]()]/g, "").substring(0, 150)}...
                    </p>
                    <div className="flex gap-4 mt-2 text-sm text-gray-500">
                        <span>${payout}</span>
                        <span>{votes} votes</span>
                        <span>{post.children} comments</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

// === app/@[author]/[permlink]/page.js - Post detail page (SSR) ===
import { fetchPost } from "@/lib/hive";
import VoteButton from "@/components/VoteButton";
import { notFound } from "next/navigation";

export async function generateMetadata({ params }) {
    const post = await fetchPost(params.author, params.permlink);
    if (!post) return { title: "Not Found" };
    return {
        title: post.title,
        description: post.body?.substring(0, 160),
        openGraph: {
            title: post.title,
            description: post.body?.substring(0, 160),
            images: post.json_metadata?.image || [],
        },
    };
}

export default async function PostPage({ params }) {
    const post = await fetchPost(params.author, params.permlink);
    if (!post) notFound();
    return (
        <article className="container mx-auto px-4 py-8 max-w-3xl">
            <h1 className="text-3xl font-bold">{post.title}</h1>
            <p className="text-gray-600 mt-2">
                by @{post.author} | {new Date(post.created).toLocaleString()}
            </p>
            <div className="prose mt-6" dangerouslySetInnerHTML={{ __html: post.body }} />
            <div className="mt-6 flex gap-4 items-center">
                <VoteButton author={post.author} permlink={post.permlink} />
                <span className="text-lg font-medium">${parseFloat(post.payout).toFixed(2)}</span>
            </div>
        </article>
    );
}

// === components/VoteButton.jsx - Client component for voting ===
"use client";
import { useState } from "react";
import { keychainVote, isKeychainInstalled } from "@/lib/keychain";

export default function VoteButton({ author, permlink }) {
    const [voted, setVoted] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleVote = async () => {
        const username = localStorage.getItem("hive_username");
        if (!username) {
            setError("Please login first");
            return;
        }
        if (!isKeychainInstalled()) {
            setError("Install Hive Keychain extension");
            return;
        }
        setLoading(true);
        setError(null);
        try {
            await keychainVote(username, author, permlink, 10000);
            setVoted(true);
        } catch (err) {
            setError(err.message);
        }
        setLoading(false);
    };

    return (
        <div>
            <button onClick={handleVote} disabled={voted || loading}
                    className={`px-4 py-2 rounded ${voted ? "bg-green-500" : "bg-blue-500"} text-white`}>
                {loading ? "Voting..." : voted ? "Voted!" : "Upvote"}
            </button>
            {error && <p className="text-red-500 text-sm mt-1">{error}</p>}
        </div>
    );
}

// === app/api/hive/search/route.js - API route for search ===
import { getHiveClient } from "@/lib/hive";
import { NextResponse } from "next/server";

export async function GET(request) {
    const { searchParams } = new URL(request.url);
    const tag = searchParams.get("tag") || "";
    const sort = searchParams.get("sort") || "trending";
    const limit = Math.min(parseInt(searchParams.get("limit") || "20"), 50);
    try {
        const client = getHiveClient();
        const posts = await client.call("bridge", "get_ranked_posts", {
            sort, tag, limit
        });
        return NextResponse.json({ posts });
    } catch (error) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
```

This architecture uses Next.js App Router with server components for SEO-optimized content rendering, client components for interactive features (voting via Keychain), and API routes for custom backend logic. The `revalidate = 60` setting enables ISR (Incremental Static Regeneration) so trending pages are cached and rebuilt every 60 seconds. Key patterns: server-side data fetching with dhive for read operations, client-side Hive Keychain for all signing operations (never send private keys to the server), and OpenGraph metadata generation from post content for social sharing.'''
    ),
    (
        "hive-fullstack-react-dhive",
        r'''Show me how to build a React application with dhive that handles login, posting, and a user dashboard showing account balances and recent activity.''',
        r'''A React + dhive application needs a Hive Keychain login flow, state management for the authenticated user, and API calls for account data. Here is a complete single-page application:

```javascript
// === src/services/hiveApi.js - Hive API service ===
import { Client } from "@hiveio/dhive";

const client = new Client([
    "https://api.hive.blog",
    "https://api.deathwing.me"
]);

export async function getAccount(username) {
    const accounts = await client.database.getAccounts([username]);
    if (!accounts.length) return null;
    const acct = accounts[0];
    // Calculate HP from VESTS
    const props = await client.database.getDynamicGlobalProperties();
    const totalVests = parseFloat(props.total_vesting_shares);
    const totalHive = parseFloat(props.total_vesting_fund_hive);
    const userVests = parseFloat(acct.vesting_shares);
    const delegatedIn = parseFloat(acct.received_vesting_shares);
    const delegatedOut = parseFloat(acct.delegated_vesting_shares);
    const ownHP = (userVests * totalHive) / totalVests;
    const effectiveHP = ((userVests + delegatedIn - delegatedOut) * totalHive) / totalVests;
    return {
        name: acct.name,
        balance: acct.balance,
        hbd_balance: acct.hbd_balance,
        savings_hbd: acct.savings_hbd_balance,
        vesting_shares: acct.vesting_shares,
        own_hp: ownHP.toFixed(3),
        effective_hp: effectiveHP.toFixed(3),
        reputation: acct.reputation,
        post_count: acct.post_count,
        voting_power: calculateVotingPower(acct),
        profile: parseProfile(acct),
    };
}

function calculateVotingPower(account) {
    const lastVoteTime = new Date(account.last_vote_time + "Z").getTime();
    const now = Date.now();
    const secondsSinceVote = (now - lastVoteTime) / 1000;
    const currentVP = Math.min(
        10000,
        account.voting_power + (secondsSinceVote * 10000 / 432000)
    );
    return (currentVP / 100).toFixed(2);
}

function parseProfile(account) {
    try {
        const meta = JSON.parse(account.posting_json_metadata || "{}");
        return meta.profile || {};
    } catch { return {}; }
}

export async function getRecentPosts(username, limit = 10) {
    return client.call("bridge", "get_account_posts", {
        account: username, sort: "posts", limit
    });
}

export async function getNotifications(username, limit = 20) {
    return client.call("bridge", "account_notifications", {
        account: username, limit
    });
}

export async function getFollowCount(username) {
    return client.database.call("get_follow_count", [username]);
}

// === src/hooks/useHiveAuth.js - Authentication hook ===
import { useState, useEffect, createContext, useContext } from "react";
import { getAccount } from "../services/hiveApi";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const saved = localStorage.getItem("hive_user");
        if (saved) {
            loadUser(saved);
        } else {
            setLoading(false);
        }
    }, []);

    async function loadUser(username) {
        setLoading(true);
        try {
            const account = await getAccount(username);
            if (account) {
                setUser(account);
                localStorage.setItem("hive_user", username);
            }
        } catch (err) {
            console.error("Failed to load user:", err);
        }
        setLoading(false);
    }

    async function login(username) {
        if (!window.hive_keychain) {
            throw new Error("Hive Keychain not found");
        }
        return new Promise((resolve, reject) => {
            const msg = `login:${username}:${Date.now()}`;
            window.hive_keychain.requestSignBuffer(
                username, msg, "Posting",
                async (resp) => {
                    if (resp.success) {
                        await loadUser(username);
                        resolve(true);
                    } else {
                        reject(new Error(resp.message || "Login failed"));
                    }
                }
            );
        });
    }

    function logout() {
        setUser(null);
        localStorage.removeItem("hive_user");
    }

    return (
        <AuthContext.Provider value={{ user, login, logout, loading, refresh: () => loadUser(user?.name) }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useHiveAuth() {
    return useContext(AuthContext);
}

// === src/components/Dashboard.jsx ===
import { useState, useEffect } from "react";
import { useHiveAuth } from "../hooks/useHiveAuth";
import { getRecentPosts, getNotifications, getFollowCount } from "../services/hiveApi";

export default function Dashboard() {
    const { user, refresh } = useHiveAuth();
    const [posts, setPosts] = useState([]);
    const [notifications, setNotifications] = useState([]);
    const [follows, setFollows] = useState(null);

    useEffect(() => {
        if (!user) return;
        Promise.all([
            getRecentPosts(user.name, 5),
            getNotifications(user.name, 10),
            getFollowCount(user.name),
        ]).then(([p, n, f]) => {
            setPosts(p || []);
            setNotifications(n || []);
            setFollows(f);
        });
    }, [user]);

    if (!user) return <p>Please login to view dashboard</p>;

    return (
        <div className="max-w-4xl mx-auto p-6">
            <div className="flex items-center gap-4 mb-8">
                {user.profile.profile_image && (
                    <img src={user.profile.profile_image} alt=""
                         className="w-16 h-16 rounded-full" />
                )}
                <div>
                    <h2 className="text-2xl font-bold">@{user.name}</h2>
                    <p className="text-gray-600">{user.profile.about || ""}</p>
                </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <StatCard label="HIVE" value={user.balance} />
                <StatCard label="HBD" value={user.hbd_balance} />
                <StatCard label="HP (Own)" value={`${user.own_hp} HP`} />
                <StatCard label="HP (Effective)" value={`${user.effective_hp} HP`} />
                <StatCard label="Savings HBD" value={user.savings_hbd} />
                <StatCard label="Vote Power" value={`${user.voting_power}%`} />
                <StatCard label="Followers" value={follows?.follower_count || 0} />
                <StatCard label="Posts" value={user.post_count} />
            </div>
            <div className="grid md:grid-cols-2 gap-8">
                <div>
                    <h3 className="text-xl font-semibold mb-4">Recent Posts</h3>
                    {posts.map(p => (
                        <div key={p.permlink} className="border-b py-3">
                            <a href={`https://peakd.com/@${p.author}/${p.permlink}`}
                               className="font-medium hover:text-blue-600"
                               target="_blank" rel="noreferrer">
                                {p.title}
                            </a>
                            <p className="text-sm text-gray-500">
                                ${parseFloat(p.payout).toFixed(2)} | {p.children} comments
                            </p>
                        </div>
                    ))}
                </div>
                <div>
                    <h3 className="text-xl font-semibold mb-4">Notifications</h3>
                    {notifications.map((n, i) => (
                        <div key={i} className="border-b py-2 text-sm">
                            <span className="font-medium">{n.type}:</span> {n.msg}
                            <span className="text-gray-400 ml-2">{n.date}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function StatCard({ label, value }) {
    return (
        <div className="bg-white border rounded-lg p-4 text-center">
            <p className="text-sm text-gray-500">{label}</p>
            <p className="text-lg font-bold">{value}</p>
        </div>
    );
}

// === src/components/PostEditor.jsx ===
import { useState } from "react";
import { useHiveAuth } from "../hooks/useHiveAuth";

export default function PostEditor() {
    const { user } = useHiveAuth();
    const [title, setTitle] = useState("");
    const [body, setBody] = useState("");
    const [tags, setTags] = useState("");
    const [status, setStatus] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!user || !window.hive_keychain) return;
        const tagList = tags.split(",").map(t => t.trim()).filter(Boolean);
        const permlink = title.toLowerCase().replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "") + "-" + Date.now().toString(36);
        const jsonMeta = JSON.stringify({
            tags: tagList, app: "hivereact/1.0", format: "markdown"
        });
        setStatus("posting...");
        window.hive_keychain.requestPost(
            user.name, title, body,
            tagList[0] || "general", "",
            jsonMeta, permlink, "",
            (resp) => {
                if (resp.success) {
                    setStatus("Posted successfully!");
                    setTitle(""); setBody(""); setTags("");
                } else {
                    setStatus("Error: " + resp.message);
                }
            }
        );
    };

    return (
        <form onSubmit={handleSubmit} className="max-w-2xl mx-auto p-6">
            <h2 className="text-2xl font-bold mb-4">New Post</h2>
            <input value={title} onChange={e => setTitle(e.target.value)}
                   placeholder="Post title" required
                   className="w-full border rounded p-2 mb-4" />
            <textarea value={body} onChange={e => setBody(e.target.value)}
                      placeholder="Write your post in Markdown..."
                      rows={12} required
                      className="w-full border rounded p-2 mb-4" />
            <input value={tags} onChange={e => setTags(e.target.value)}
                   placeholder="Tags (comma separated)"
                   className="w-full border rounded p-2 mb-4" />
            <button type="submit" disabled={!user}
                    className="bg-blue-600 text-white px-6 py-2 rounded">
                Publish to Hive
            </button>
            {status && <p className="mt-2 text-sm">{status}</p>}
        </form>
    );
}
```

This React application provides: authentication via Hive Keychain with persistent sessions, a dashboard showing all account balances (with VESTS-to-HP conversion), recent posts and notifications, and a post editor that publishes directly to Hive. The AuthProvider context makes the current user available throughout the app. Key patterns: never handle private keys in the app (always use Keychain), compute HP from VESTS using the global properties ratio, and use the bridge API for rich content queries. For production, add markdown rendering (react-markdown), image upload to IPFS, and beneficiary support in the post editor.'''
    ),
    (
        "hive-fullstack-vue-hivetx",
        r'''How do I build a Vue.js application that integrates with Hive using the lightweight hive-tx library for transaction signing?''',
        r'''The **hive-tx** library is a lightweight alternative to dhive that focuses on transaction building and signing. It is ideal for frontend apps where bundle size matters. Here is a Vue 3 application with Composition API:

```javascript
// === src/services/hiveTx.js - hive-tx integration ===
import { Transaction, call, config } from "hive-tx";

// Configure hive-tx nodes
config.node = "https://api.hive.blog";
config.chain_id = "beeab0de00000000000000000000000000000000000000000000000000000000";

export async function hiveCall(api, method, params) {
    return call(api, method, params);
}

export async function getAccounts(usernames) {
    const result = await hiveCall("condenser_api", "get_accounts", [usernames]);
    return result;
}

export async function getGlobalProps() {
    return hiveCall("condenser_api", "get_dynamic_global_properties", []);
}

export async function getRankedPosts(sort, tag = "", limit = 20) {
    const params = { sort, limit };
    if (tag) params.tag = tag;
    return hiveCall("bridge", "get_ranked_posts", params);
}

export async function getAccountPosts(account, sort = "posts", limit = 20) {
    return hiveCall("bridge", "get_account_posts", {
        account, sort, limit
    });
}

export function buildVoteTransaction(voter, author, permlink, weight) {
    const tx = new Transaction();
    tx.create([
        ["vote", { voter, author, permlink, weight }]
    ]);
    return tx;
}

export function buildPostTransaction(author, title, body, tags, permlink) {
    const parentPermlink = tags[0] || "general";
    const jsonMetadata = JSON.stringify({
        tags, app: "hivevue/1.0", format: "markdown"
    });
    const tx = new Transaction();
    tx.create([
        ["comment", {
            parent_author: "",
            parent_permlink: parentPermlink,
            author, permlink, title, body,
            json_metadata: jsonMetadata
        }]
    ]);
    return tx;
}

export function buildTransferTransaction(from, to, amount, asset, memo = "") {
    const tx = new Transaction();
    tx.create([
        ["transfer", {
            from, to,
            amount: `${parseFloat(amount).toFixed(3)} ${asset}`,
            memo
        }]
    ]);
    return tx;
}

// === src/composables/useHiveAuth.js - Vue 3 composable ===
import { ref, computed } from "vue";
import { getAccounts, getGlobalProps } from "../services/hiveTx";

const currentUser = ref(null);
const isLoading = ref(false);
const isLoggedIn = computed(() => !!currentUser.value);

export function useHiveAuth() {
    async function login(username) {
        if (!window.hive_keychain) {
            throw new Error("Hive Keychain is required");
        }
        isLoading.value = true;
        return new Promise((resolve, reject) => {
            const message = `hivevue-login:${Date.now()}`;
            window.hive_keychain.requestSignBuffer(
                username, message, "Posting",
                async (response) => {
                    if (response.success) {
                        await loadAccount(username);
                        localStorage.setItem("hive_user", username);
                        resolve(currentUser.value);
                    } else {
                        reject(new Error(response.message));
                    }
                    isLoading.value = false;
                }
            );
        });
    }

    async function loadAccount(username) {
        const accounts = await getAccounts([username]);
        if (!accounts || !accounts.length) return;
        const acct = accounts[0];
        const props = await getGlobalProps();
        const totalVests = parseFloat(props.total_vesting_shares);
        const totalHive = parseFloat(props.total_vesting_fund_hive);
        const userVests = parseFloat(acct.vesting_shares);
        const hp = (userVests * totalHive) / totalVests;
        let profile = {};
        try {
            profile = JSON.parse(acct.posting_json_metadata || "{}").profile || {};
        } catch (e) { /* ignore parse errors */ }
        currentUser.value = {
            name: acct.name,
            balance: acct.balance,
            hbd_balance: acct.hbd_balance,
            hp: hp.toFixed(3),
            reputation: acct.reputation,
            profile,
        };
    }

    function logout() {
        currentUser.value = null;
        localStorage.removeItem("hive_user");
    }

    function restoreSession() {
        const saved = localStorage.getItem("hive_user");
        if (saved) loadAccount(saved);
    }

    return { currentUser, isLoggedIn, isLoading, login, logout, restoreSession };
}

// === src/components/HiveFeed.vue ===
/*
<template>
  <div class="feed">
    <div class="flex gap-2 mb-6">
      <button v-for="s in sorts" :key="s"
              :class="['px-4 py-2 rounded', sort === s ? 'bg-blue-600 text-white' : 'bg-gray-200']"
              @click="sort = s; loadPosts()">
        {{ s }}
      </button>
    </div>
    <div v-if="loading" class="text-center py-8">Loading...</div>
    <div v-else class="space-y-4">
      <article v-for="post in posts" :key="post.author + '/' + post.permlink"
               class="border rounded-lg p-4">
        <h3 class="text-lg font-semibold">
          <a :href="'https://peakd.com/@' + post.author + '/' + post.permlink"
             target="_blank">{{ post.title }}</a>
        </h3>
        <p class="text-sm text-gray-600">
          by @{{ post.author }} | ${{ parseFloat(post.payout).toFixed(2) }}
          | {{ post.children }} comments
        </p>
        <p class="text-gray-700 mt-2">{{ preview(post.body) }}</p>
        <button @click="vote(post)" :disabled="post.voted"
                class="mt-2 px-3 py-1 bg-green-500 text-white rounded text-sm">
          {{ post.voted ? 'Voted' : 'Upvote' }}
        </button>
      </article>
    </div>
  </div>
</template>
*/

// <script setup>
import { ref, onMounted } from "vue";
import { getRankedPosts } from "../services/hiveTx";
import { useHiveAuth } from "../composables/useHiveAuth";

const { currentUser, isLoggedIn } = useHiveAuth();
const posts = ref([]);
const loading = ref(false);
const sort = ref("trending");
const sorts = ["trending", "hot", "created"];

function preview(body) {
    return (body || "").replace(/[#*!\[\]()>]/g, "").substring(0, 200) + "...";
}

async function loadPosts() {
    loading.value = true;
    const result = await getRankedPosts(sort.value, "", 15);
    posts.value = (result || []).map(p => ({ ...p, voted: false }));
    loading.value = false;
}

function vote(post) {
    if (!isLoggedIn.value || !window.hive_keychain) return;
    window.hive_keychain.requestVote(
        currentUser.value.name,
        post.permlink, post.author, 10000,
        (resp) => {
            if (resp.success) post.voted = true;
        }
    );
}

onMounted(loadPosts);
// </script>

// === src/App.vue structure ===
/*
<template>
  <div id="app">
    <nav class="bg-gray-800 text-white p-4 flex justify-between">
      <span class="font-bold text-xl">HiveVue</span>
      <div v-if="isLoggedIn" class="flex items-center gap-4">
        <span>@{{ currentUser.name }}</span>
        <span>{{ currentUser.balance }}</span>
        <button @click="logout" class="text-sm underline">Logout</button>
      </div>
      <div v-else>
        <input v-model="loginUsername" placeholder="Username" class="text-black px-2 py-1 rounded" />
        <button @click="handleLogin" class="ml-2 bg-blue-500 px-3 py-1 rounded">
          Login with Keychain
        </button>
      </div>
    </nav>
    <main class="container mx-auto py-8">
      <HiveFeed />
    </main>
  </div>
</template>
*/

export default {
    // Component registration and setup would go here
    // This demonstrates the pattern for Vue + hive-tx integration
};
```

The hive-tx library is much smaller than dhive (around 50KB vs 300KB+ bundled), making it better for client-side applications where bundle size matters. The key advantage is the `Transaction` class that builds properly formatted Hive transactions. However, for most frontend apps, you will still use Hive Keychain for signing rather than handling keys directly with hive-tx. The `call` function from hive-tx handles JSON-RPC calls to any Hive API. The Vue Composition API pattern with `useHiveAuth` composable keeps authentication state clean and reusable across components.'''
    ),
    (
        "hive-fullstack-mobile",
        r'''How do I integrate Hive blockchain functionality into a mobile application using React Native or a WebView approach?''',
        r'''Mobile Hive integration presents unique challenges since Hive Keychain is a browser extension. Solutions include: HiveAuth (QR-code based auth), deep links to Hive Keychain mobile app, or a WebView bridge. Here is a React Native implementation:

```javascript
// === src/services/hiveAuth.js - HiveAuth integration for mobile ===
import { Client } from "@hiveio/dhive";

const client = new Client(["https://api.hive.blog"]);

// HiveAuth protocol for mobile authentication
// Uses WebSocket connection to HiveAuth server
export class HiveAuthMobile {
    constructor() {
        this.ws = null;
        this.authKey = null;
        this.username = null;
    }

    generateAuthKey() {
        // Generate a random 32-byte key for encryption
        const array = new Uint8Array(32);
        crypto.getRandomValues(array);
        return Array.from(array, b => b.toString(16).padStart(2, "0")).join("");
    }

    async connect() {
        return new Promise((resolve, reject) => {
            this.ws = new WebSocket("wss://hiveauth.com/");
            this.ws.onopen = () => resolve();
            this.ws.onerror = (err) => reject(err);
        });
    }

    async requestAuth(username, appName = "MyHiveApp") {
        this.authKey = this.generateAuthKey();
        this.username = username;
        const authPayload = {
            cmd: "auth_req",
            account: username,
            data: {
                app: {
                    name: appName,
                    description: "Mobile Hive Application",
                    icon: "https://myapp.com/icon.png"
                },
                token: this.authKey,
            }
        };
        return new Promise((resolve, reject) => {
            this.ws.send(JSON.stringify(authPayload));
            this.ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.cmd === "auth_wait") {
                    // Return QR code data for user to scan
                    resolve({
                        qrData: msg.uuid,
                        deepLink: `hiveauth://auth/${msg.uuid}`,
                        expiresIn: msg.expire,
                    });
                } else if (msg.cmd === "auth_ack") {
                    resolve({ authenticated: true, token: msg.token });
                } else if (msg.cmd === "auth_nack") {
                    reject(new Error("Authentication rejected"));
                }
            };
        });
    }

    async requestSignTransaction(operations) {
        const signPayload = {
            cmd: "sign_req",
            account: this.username,
            data: {
                key_type: "posting",
                ops: operations,
                broadcast: true,
            },
            token: this.authKey,
        };
        return new Promise((resolve, reject) => {
            this.ws.send(JSON.stringify(signPayload));
            this.ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.cmd === "sign_ack") {
                    resolve({ success: true, result: msg.data });
                } else if (msg.cmd === "sign_nack") {
                    reject(new Error("Signing rejected"));
                } else if (msg.cmd === "sign_wait") {
                    // User needs to approve on their device
                }
            };
        });
    }

    disconnect() {
        if (this.ws) this.ws.close();
    }
}

// === React Native components ===
// Note: Uses react-native, @react-native-async-storage/async-storage,
//       react-native-qrcode-svg for QR display

/*
// src/screens/LoginScreen.jsx
import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert } from "react-native";
import QRCode from "react-native-qrcode-svg";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { HiveAuthMobile } from "../services/hiveAuth";

export default function LoginScreen({ navigation }) {
    const [username, setUsername] = useState("");
    const [qrData, setQrData] = useState(null);
    const [status, setStatus] = useState("");

    const loginWithHiveAuth = async () => {
        if (!username.trim()) {
            Alert.alert("Error", "Please enter your Hive username");
            return;
        }
        try {
            setStatus("Connecting to HiveAuth...");
            const ha = new HiveAuthMobile();
            await ha.connect();
            setStatus("Waiting for approval...");
            const authResult = await ha.requestAuth(username, "MyHiveApp");
            if (authResult.qrData) {
                setQrData(authResult.qrData);
                setStatus("Scan QR code with Hive Keychain mobile app");
            }
            if (authResult.authenticated) {
                await AsyncStorage.setItem("hive_user", username);
                await AsyncStorage.setItem("hive_auth_token", authResult.token);
                navigation.navigate("Dashboard");
            }
        } catch (err) {
            Alert.alert("Login Failed", err.message);
            setStatus("");
            setQrData(null);
        }
    };

    return (
        <View style={styles.container}>
            <Text style={styles.title}>Login to Hive</Text>
            <TextInput
                style={styles.input}
                value={username}
                onChangeText={setUsername}
                placeholder="Hive username"
                autoCapitalize="none"
            />
            <TouchableOpacity style={styles.button} onPress={loginWithHiveAuth}>
                <Text style={styles.buttonText}>Login with HiveAuth</Text>
            </TouchableOpacity>
            {status ? <Text style={styles.status}>{status}</Text> : null}
            {qrData && (
                <View style={styles.qrContainer}>
                    <QRCode value={qrData} size={200} />
                    <Text style={styles.qrHint}>
                        Scan with Hive Keychain app
                    </Text>
                </View>
            )}
        </View>
    );
}

// src/screens/DashboardScreen.jsx
import React, { useState, useEffect } from "react";
import { View, Text, FlatList, RefreshControl, StyleSheet } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

export default function DashboardScreen() {
    const [account, setAccount] = useState(null);
    const [posts, setPosts] = useState([]);
    const [refreshing, setRefreshing] = useState(false);

    const loadData = async () => {
        const username = await AsyncStorage.getItem("hive_user");
        if (!username) return;

        // Fetch account data
        const resp = await fetch("https://api.hive.blog", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0", id: 1,
                method: "condenser_api.get_accounts",
                params: [[username]]
            })
        });
        const data = await resp.json();
        if (data.result && data.result.length) {
            setAccount(data.result[0]);
        }

        // Fetch recent posts
        const postResp = await fetch("https://api.hive.blog", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0", id: 2,
                method: "bridge.get_account_posts",
                params: { account: username, sort: "posts", limit: 10 }
            })
        });
        const postData = await postResp.json();
        setPosts(postData.result || []);
    };

    useEffect(() => { loadData(); }, []);

    const onRefresh = async () => {
        setRefreshing(true);
        await loadData();
        setRefreshing(false);
    };

    const renderPost = ({ item }) => (
        <View style={styles.postCard}>
            <Text style={styles.postTitle}>{item.title}</Text>
            <Text style={styles.postMeta}>
                ${parseFloat(item.payout).toFixed(2)} | {item.children} comments
            </Text>
        </View>
    );

    return (
        <View style={styles.container}>
            {account && (
                <View style={styles.balanceRow}>
                    <BalanceCard label="HIVE" value={account.balance} />
                    <BalanceCard label="HBD" value={account.hbd_balance} />
                </View>
            )}
            <Text style={styles.sectionTitle}>Recent Posts</Text>
            <FlatList
                data={posts}
                renderItem={renderPost}
                keyExtractor={item => item.permlink}
                refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
                }
            />
        </View>
    );
}

function BalanceCard({ label, value }) {
    return (
        <View style={styles.balanceCard}>
            <Text style={styles.balanceLabel}>{label}</Text>
            <Text style={styles.balanceValue}>{value}</Text>
        </View>
    );
}
*/

const styles = {
    // StyleSheet.create would be used in actual React Native
    container: { flex: 1, padding: 16 },
    title: { fontSize: 24, fontWeight: "bold", textAlign: "center", marginBottom: 20 },
    input: { borderWidth: 1, borderColor: "#ccc", padding: 12, borderRadius: 8, marginBottom: 16 },
    button: { backgroundColor: "#e31337", padding: 14, borderRadius: 8, alignItems: "center" },
    buttonText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
};

export default { HiveAuthMobile };
```

Mobile Hive integration options: (1) **HiveAuth** (shown above) uses QR codes and WebSocket for authentication without browser extensions -- best for native mobile apps. (2) **Deep links** to Hive Keychain mobile app for signing on supported platforms. (3) **WebView bridge** where you embed a web-based signing interface inside a WebView. (4) **Direct key storage** using secure device storage (Keychain on iOS, Keystore on Android) -- only for trusted first-party apps. For most mobile dApps, HiveAuth provides the best balance of security (keys never leave the user's Keychain app) and user experience (scan QR code to authenticate). Use `fetch` directly against Hive API nodes for read operations to avoid library compatibility issues with React Native's JavaScript runtime.'''
    ),
    (
        "hive-fullstack-ssr",
        r'''How do I implement server-side rendering with Hive blockchain data for SEO optimization, including caching strategies and error handling?''',
        r'''Server-side rendering with Hive data is critical for SEO since search engines need to see content in the initial HTML response. Here is a production-ready SSR implementation with caching, error handling, and graceful degradation:

```javascript
// === Express + EJS SSR with Hive data ===
const express = require("express");
const { Client } = require("@hiveio/dhive");

const app = express();
app.set("view engine", "ejs");
app.set("views", "./views");

// === Hive client with failover ===
const NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://rpc.ausbit.dev",
    "https://api.openhive.network"
];
let currentNodeIndex = 0;

function getClient() {
    return new Client(NODES.slice(currentNodeIndex).concat(NODES.slice(0, currentNodeIndex)));
}

function rotateNode() {
    currentNodeIndex = (currentNodeIndex + 1) % NODES.length;
    console.log(`Rotated to node: ${NODES[currentNodeIndex]}`);
}

// === In-memory cache with TTL ===
class SimpleCache {
    constructor() {
        this.store = new Map();
    }

    get(key) {
        const entry = this.store.get(key);
        if (!entry) return null;
        if (Date.now() > entry.expiry) {
            this.store.delete(key);
            return null;
        }
        return entry.value;
    }

    set(key, value, ttlSeconds) {
        this.store.set(key, {
            value,
            expiry: Date.now() + (ttlSeconds * 1000)
        });
    }

    clear() {
        this.store.clear();
    }

    // Periodically clean expired entries
    startCleanup(intervalMs = 60000) {
        setInterval(() => {
            const now = Date.now();
            for (const [key, entry] of this.store) {
                if (now > entry.expiry) this.store.delete(key);
            }
        }, intervalMs);
    }
}

const cache = new SimpleCache();
cache.startCleanup();

// Cache TTL configuration (seconds)
const CACHE_TTL = {
    trending: 120,      // 2 minutes for trending (changes frequently)
    post: 300,           // 5 minutes for individual posts
    profile: 600,        // 10 minutes for profiles
    globalProps: 30,     // 30 seconds for chain properties
};

// === Data fetching with cache and error handling ===
async function fetchWithCache(cacheKey, ttlKey, fetchFn) {
    const cached = cache.get(cacheKey);
    if (cached) return cached;
    let lastError = null;
    for (let attempt = 0; attempt < 3; attempt++) {
        try {
            const result = await fetchFn(getClient());
            cache.set(cacheKey, result, CACHE_TTL[ttlKey] || 120);
            return result;
        } catch (err) {
            lastError = err;
            console.error(`Fetch attempt ${attempt + 1} failed:`, err.message);
            rotateNode();
        }
    }
    throw lastError;
}

// === SEO helpers ===
function generateMetaTags(post) {
    const description = (post.body || "")
        .replace(/[#*!\[\]()>]/g, "")
        .replace(/\n+/g, " ")
        .trim()
        .substring(0, 160);
    const image = post.json_metadata?.image?.[0] || "";
    return {
        title: post.title || "Hive Post",
        description,
        image,
        url: `https://myapp.com/@${post.author}/${post.permlink}`,
        author: post.author,
        published: post.created,
        tags: post.json_metadata?.tags || [],
    };
}

function generateStructuredData(post, meta) {
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": meta.title,
        "description": meta.description,
        "image": meta.image,
        "author": {
            "@type": "Person",
            "name": meta.author,
            "url": `https://myapp.com/@${meta.author}`
        },
        "datePublished": meta.published,
        "publisher": {
            "@type": "Organization",
            "name": "MyHiveApp",
            "url": "https://myapp.com"
        }
    };
}

// === Routes ===

// Trending page with SSR
app.get("/", async (req, res) => {
    try {
        const tag = req.query.tag || "";
        const sort = req.query.sort || "trending";
        const cacheKey = `feed:${sort}:${tag}`;
        const posts = await fetchWithCache(cacheKey, "trending", async (client) => {
            const params = { sort, limit: 20 };
            if (tag) params.tag = tag;
            return client.call("bridge", "get_ranked_posts", params);
        });
        res.render("feed", {
            posts,
            sort,
            tag,
            title: tag ? `${sort} in #${tag}` : `${sort} posts`,
            meta: {
                title: `${sort} Hive Posts` + (tag ? ` - #${tag}` : ""),
                description: `Browse ${sort} content on Hive blockchain`,
            }
        });
    } catch (err) {
        console.error("Feed error:", err);
        res.status(500).render("error", { message: "Unable to load feed" });
    }
});

// Individual post page with full SEO
app.get("/@:author/:permlink", async (req, res) => {
    const { author, permlink } = req.params;
    try {
        const cacheKey = `post:${author}/${permlink}`;
        const post = await fetchWithCache(cacheKey, "post", async (client) => {
            return client.call("bridge", "get_post", { author, permlink });
        });
        if (!post || !post.author) {
            return res.status(404).render("error", { message: "Post not found" });
        }
        const meta = generateMetaTags(post);
        const structuredData = generateStructuredData(post, meta);
        // Fetch replies for the post
        const repliesCacheKey = `replies:${author}/${permlink}`;
        let replies = [];
        try {
            replies = await fetchWithCache(repliesCacheKey, "post", async (client) => {
                const discussion = await client.call("bridge", "get_discussion", { author, permlink });
                // Discussion returns all posts keyed by author/permlink
                const replyList = Object.values(discussion).filter(
                    r => r.author !== author || r.permlink !== permlink
                );
                return replyList;
            });
        } catch (e) {
            // Replies failing should not block post rendering
            console.warn("Failed to load replies:", e.message);
        }
        res.render("post", { post, replies, meta, structuredData });
    } catch (err) {
        console.error("Post error:", err);
        res.status(500).render("error", { message: "Unable to load post" });
    }
});

// Profile page
app.get("/@:author", async (req, res) => {
    const { author } = req.params;
    try {
        const cacheKey = `profile:${author}`;
        const profile = await fetchWithCache(cacheKey, "profile", async (client) => {
            const [accounts, bridgeProfile, posts] = await Promise.all([
                client.database.getAccounts([author]),
                client.call("bridge", "get_profile", { account: author }),
                client.call("bridge", "get_account_posts", {
                    account: author, sort: "posts", limit: 10
                })
            ]);
            return { account: accounts[0], profile: bridgeProfile, posts };
        });
        if (!profile.account) {
            return res.status(404).render("error", { message: "Account not found" });
        }
        res.render("profile", {
            ...profile,
            meta: {
                title: `@${author} on Hive`,
                description: profile.profile?.metadata?.profile?.about || "",
            }
        });
    } catch (err) {
        console.error("Profile error:", err);
        res.status(500).render("error", { message: "Unable to load profile" });
    }
});

// API endpoint for client-side fetching
app.get("/api/posts", async (req, res) => {
    const { sort = "trending", tag = "", limit = "20", start_author, start_permlink } = req.query;
    try {
        const params = { sort, limit: Math.min(parseInt(limit), 50) };
        if (tag) params.tag = tag;
        if (start_author) {
            params.start_author = start_author;
            params.start_permlink = start_permlink;
        }
        const client = getClient();
        const posts = await client.call("bridge", "get_ranked_posts", params);
        res.json({ posts });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Health check
app.get("/health", async (req, res) => {
    try {
        const client = getClient();
        const props = await client.database.getDynamicGlobalProperties();
        res.json({
            status: "ok",
            head_block: props.head_block_number,
            node: NODES[currentNodeIndex],
            cache_size: cache.store.size,
        });
    } catch (err) {
        res.status(503).json({ status: "error", message: err.message });
    }
});

app.listen(3000, () => console.log("SSR server running on port 3000"));
```

This SSR setup provides: (1) Node failover with automatic rotation when a node fails. (2) In-memory caching with configurable TTL per content type -- trending pages cache for 2 minutes, individual posts for 5 minutes. (3) Full SEO with meta tags, Open Graph, and JSON-LD structured data for search engines. (4) Graceful degradation where reply loading failures do not block the main post render. (5) A client-side API endpoint for infinite scrolling after the initial SSR load. For production, replace the in-memory cache with Redis for multi-process environments, add rate limiting on the API endpoint, and implement a CDN layer (Cloudflare, Fastly) in front of the SSR server for additional caching.'''
    ),
]
