"""Collaborative editing — Yjs, CRDTs, and Automerge."""

PAIRS = [
    (
        "frontend/crdt-fundamentals",
        "Explain CRDT fundamentals including G-Counter, PN-Counter, LWW-Register, G-Set, OR-Set, and LWW-Element-Set with TypeScript implementations.",
        '''CRDTs (Conflict-free Replicated Data Types) are data structures that can be replicated across multiple nodes and merged deterministically without coordination, guaranteeing eventual consistency.

```typescript
// --- G-Counter (Grow-only Counter) ---

// Each node maintains its own count. The global value is the sum.
// Merge: take the max of each node's count.

interface GCounter {
  counts: Record<string, number>;  // nodeId -> count
}

function createGCounter(nodeId: string): GCounter {
  return { counts: { [nodeId]: 0 } };
}

function incrementGCounter(counter: GCounter, nodeId: string, amount: number = 1): GCounter {
  return {
    counts: {
      ...counter.counts,
      [nodeId]: (counter.counts[nodeId] ?? 0) + amount,
    },
  };
}

function valueGCounter(counter: GCounter): number {
  return Object.values(counter.counts).reduce((sum, v) => sum + v, 0);
}

function mergeGCounters(a: GCounter, b: GCounter): GCounter {
  const allKeys = new Set([...Object.keys(a.counts), ...Object.keys(b.counts)]);
  const merged: Record<string, number> = {};

  for (const key of allKeys) {
    merged[key] = Math.max(a.counts[key] ?? 0, b.counts[key] ?? 0);
  }

  return { counts: merged };
}


// --- PN-Counter (Positive-Negative Counter) ---

// Two G-Counters: one for increments, one for decrements.
// Value = sum(positive) - sum(negative)

interface PNCounter {
  positive: GCounter;
  negative: GCounter;
}

function createPNCounter(nodeId: string): PNCounter {
  return {
    positive: createGCounter(nodeId),
    negative: createGCounter(nodeId),
  };
}

function incrementPNCounter(counter: PNCounter, nodeId: string): PNCounter {
  return { ...counter, positive: incrementGCounter(counter.positive, nodeId) };
}

function decrementPNCounter(counter: PNCounter, nodeId: string): PNCounter {
  return { ...counter, negative: incrementGCounter(counter.negative, nodeId) };
}

function valuePNCounter(counter: PNCounter): number {
  return valueGCounter(counter.positive) - valueGCounter(counter.negative);
}

function mergePNCounters(a: PNCounter, b: PNCounter): PNCounter {
  return {
    positive: mergeGCounters(a.positive, b.positive),
    negative: mergeGCounters(a.negative, b.negative),
  };
}
```

```typescript
// --- LWW-Register (Last-Writer-Wins Register) ---

// Associates a timestamp with each value. On merge, the
// value with the highest timestamp wins.

interface LWWRegister<T> {
  value: T;
  timestamp: number;
  nodeId: string;      // tie-break when timestamps are equal
}

function createLWWRegister<T>(value: T, nodeId: string): LWWRegister<T> {
  return { value, timestamp: Date.now(), nodeId };
}

function setLWWRegister<T>(
  register: LWWRegister<T>,
  value: T,
  nodeId: string,
): LWWRegister<T> {
  return { value, timestamp: Date.now(), nodeId };
}

function mergeLWWRegisters<T>(a: LWWRegister<T>, b: LWWRegister<T>): LWWRegister<T> {
  if (a.timestamp > b.timestamp) return a;
  if (b.timestamp > a.timestamp) return b;
  // Tie-break: lexicographic node ID comparison
  return a.nodeId > b.nodeId ? a : b;
}


// --- G-Set (Grow-only Set) ---

// Elements can be added but never removed.

type GSet<T> = Set<T>;

function createGSet<T>(): GSet<T> {
  return new Set<T>();
}

function addGSet<T>(set: GSet<T>, element: T): GSet<T> {
  const next = new Set(set);
  next.add(element);
  return next;
}

function mergeGSets<T>(a: GSet<T>, b: GSet<T>): GSet<T> {
  return new Set([...a, ...b]);  // union
}
```

```typescript
// --- OR-Set (Observed-Remove Set) ---

// Each add generates a unique tag. Remove removes all known tags
// for an element. Concurrent add + remove: add wins.

interface ORSet<T> {
  elements: Map<T, Set<string>>;  // element -> set of unique tags
}

function createORSet<T>(): ORSet<T> {
  return { elements: new Map() };
}

function addORSet<T>(set: ORSet<T>, element: T): ORSet<T> {
  const next: ORSet<T> = { elements: new Map(set.elements) };
  const tags = new Set(next.elements.get(element) ?? []);
  tags.add(crypto.randomUUID());  // unique tag per add
  next.elements.set(element, tags);
  return next;
}

function removeORSet<T>(set: ORSet<T>, element: T): ORSet<T> {
  const next: ORSet<T> = { elements: new Map(set.elements) };
  next.elements.delete(element);  // remove all tags for this element
  return next;
}

function lookupORSet<T>(set: ORSet<T>, element: T): boolean {
  const tags = set.elements.get(element);
  return tags !== undefined && tags.size > 0;
}

function elementsORSet<T>(set: ORSet<T>): T[] {
  const result: T[] = [];
  for (const [element, tags] of set.elements) {
    if (tags.size > 0) result.push(element);
  }
  return result;
}

function mergeORSets<T>(a: ORSet<T>, b: ORSet<T>): ORSet<T> {
  const merged: ORSet<T> = { elements: new Map() };
  const allKeys = new Set([...a.elements.keys(), ...b.elements.keys()]);

  for (const key of allKeys) {
    const tagsA = a.elements.get(key) ?? new Set();
    const tagsB = b.elements.get(key) ?? new Set();
    const union = new Set([...tagsA, ...tagsB]);
    if (union.size > 0) {
      merged.elements.set(key, union);
    }
  }

  return merged;
}


// --- LWW-Element-Set ---

// Each element has an add-timestamp and remove-timestamp.
// Element is in set if add-ts > remove-ts.

interface LWWElementSet<T> {
  addSet: Map<T, number>;     // element -> add timestamp
  removeSet: Map<T, number>;  // element -> remove timestamp
}

function createLWWElementSet<T>(): LWWElementSet<T> {
  return { addSet: new Map(), removeSet: new Map() };
}

function addLWWElement<T>(set: LWWElementSet<T>, element: T): LWWElementSet<T> {
  const next = {
    addSet: new Map(set.addSet),
    removeSet: new Map(set.removeSet),
  };
  next.addSet.set(element, Date.now());
  return next;
}

function removeLWWElement<T>(set: LWWElementSet<T>, element: T): LWWElementSet<T> {
  const next = {
    addSet: new Map(set.addSet),
    removeSet: new Map(set.removeSet),
  };
  next.removeSet.set(element, Date.now());
  return next;
}

function lookupLWWElement<T>(set: LWWElementSet<T>, element: T): boolean {
  const addTs = set.addSet.get(element);
  const removeTs = set.removeSet.get(element);
  if (addTs === undefined) return false;
  if (removeTs === undefined) return true;
  return addTs > removeTs;  // bias: add wins on tie
}

function mergeLWWElementSets<T>(a: LWWElementSet<T>, b: LWWElementSet<T>): LWWElementSet<T> {
  const merged: LWWElementSet<T> = { addSet: new Map(), removeSet: new Map() };

  const allAddKeys = new Set([...a.addSet.keys(), ...b.addSet.keys()]);
  for (const key of allAddKeys) {
    merged.addSet.set(key, Math.max(a.addSet.get(key) ?? 0, b.addSet.get(key) ?? 0));
  }

  const allRemoveKeys = new Set([...a.removeSet.keys(), ...b.removeSet.keys()]);
  for (const key of allRemoveKeys) {
    merged.removeSet.set(key, Math.max(a.removeSet.get(key) ?? 0, b.removeSet.get(key) ?? 0));
  }

  return merged;
}
```

| CRDT Type | Operations | Merge Strategy | Limitations |
|---|---|---|---|
| G-Counter | Increment only | Max per node | Cannot decrement |
| PN-Counter | Increment, decrement | Max per node (both) | Monotonically growing metadata |
| LWW-Register | Set value | Latest timestamp wins | Requires synchronized clocks |
| G-Set | Add only | Set union | Cannot remove elements |
| OR-Set | Add, remove | Union of tags | Growing metadata (tombstones) |
| LWW-Element-Set | Add, remove | Latest timestamp per element | Clock synchronization needed |

| Property | State-based (CvRDT) | Operation-based (CmRDT) |
|---|---|---|
| Transmitted data | Full state | Individual operations |
| Network requirement | At-least-once delivery | Exactly-once, causal order |
| Merge function | `merge(stateA, stateB)` | `apply(op)` |
| Bandwidth | Higher (full state) | Lower (ops only) |
| Complexity | Simpler | Requires causal ordering |

Key patterns:
1. CRDTs guarantee eventual consistency without coordination or consensus
2. G-Counter: each node increments its own slot; merge takes max per slot
3. LWW-Register needs roughly synchronized clocks; use Hybrid Logical Clocks in practice
4. OR-Set tracks unique tags per add, so concurrent add+remove is resolved (add wins)
5. State-based CRDTs (CvRDT) send full state; operation-based (CmRDT) send only operations
6. All CRDTs must be commutative, associative, and idempotent in their merge operation
7. In production, use libraries (Yjs, Automerge) instead of hand-rolling CRDTs'''
    ),
    (
        "frontend/yjs-shared-types",
        "Demonstrate Yjs shared types and awareness protocol for building collaborative editing features with rich text, presence, and real-time sync.",
        '''Yjs is a high-performance CRDT implementation for building collaborative applications. It provides shared types (Text, Array, Map, XML) that sync automatically across peers.

```typescript
// --- Yjs core: documents and shared types ---

import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { IndexeddbPersistence } from 'y-indexeddb';

// Create a Yjs document — the root of all shared state
const ydoc = new Y.Doc();

// Shared types are accessed by name from the document
const ytext = ydoc.getText('document');          // Y.Text
const ytodos = ydoc.getArray<Y.Map<unknown>>('todos'); // Y.Array
const ymeta = ydoc.getMap('metadata');           // Y.Map

// --- Y.Text: collaborative rich text ---
ytext.insert(0, 'Hello, ');
ytext.insert(7, 'world!');
ytext.delete(5, 2);  // delete 2 chars at position 5

// Rich text with formatting attributes
ytext.insert(0, 'Bold text', { bold: true });
ytext.format(0, 4, { italic: true });  // make first 4 chars italic

// Observe changes
ytext.observe((event: Y.YTextEvent) => {
  console.log('Text delta:', event.delta);
  // [{ retain: 5 }, { insert: 'new', attributes: { bold: true } }]

  event.delta.forEach(op => {
    if (op.insert) console.log('Inserted:', op.insert);
    if (op.delete) console.log('Deleted chars:', op.delete);
    if (op.retain) console.log('Retained:', op.retain);
  });
});


// --- Y.Array: collaborative list ---
const todo1 = new Y.Map<unknown>();
todo1.set('id', crypto.randomUUID());
todo1.set('text', 'Buy groceries');
todo1.set('done', false);

ytodos.push([todo1]);

// Observe array changes
ytodos.observe((event: Y.YArrayEvent<Y.Map<unknown>>) => {
  let index = 0;
  event.changes.delta.forEach(op => {
    if (op.retain) index += op.retain;
    if (op.insert) {
      console.log(`Inserted ${op.insert.length} items at index ${index}`);
    }
    if (op.delete) {
      console.log(`Deleted ${op.delete} items at index ${index}`);
    }
  });
});


// --- Y.Map: collaborative key-value ---
ymeta.set('title', 'My Document');
ymeta.set('createdAt', Date.now());
ymeta.set('tags', ['draft', 'shared']);

ymeta.observe((event: Y.YMapEvent<unknown>) => {
  event.keysChanged.forEach(key => {
    const change = event.changes.keys.get(key);
    if (change) {
      console.log(`Key "${key}": ${change.action}`);
      // action: 'add' | 'update' | 'delete'
    }
  });
});
```

```typescript
// --- Networking: WebSocket provider + offline persistence ---

// WebSocket provider — syncs with a y-websocket server
const wsProvider = new WebsocketProvider(
  'wss://your-server.com',  // WebSocket URL
  'room-name',               // shared room
  ydoc,
  {
    connect: true,
    params: { token: 'auth-token' },
    WebSocketPolyfill: WebSocket,
    resyncInterval: 10000,  // periodic full sync (ms)
  }
);

wsProvider.on('status', ({ status }: { status: string }) => {
  console.log('Connection status:', status);
  // 'connecting' | 'connected' | 'disconnected'
});

wsProvider.on('sync', (isSynced: boolean) => {
  console.log('Synced with server:', isSynced);
});


// IndexedDB persistence — offline support
const indexeddbProvider = new IndexeddbPersistence('doc-id', ydoc);

indexeddbProvider.on('synced', () => {
  console.log('Loaded from IndexedDB');
});

// Now the document works offline and syncs when online


// --- Awareness protocol (presence, cursors) ---

interface AwarenessState {
  user: {
    name: string;
    color: string;
    avatar: string;
  };
  cursor: {
    anchor: number;   // cursor position
    head: number;      // selection end
  } | null;
  isTyping: boolean;
}

const awareness = wsProvider.awareness;

// Set local user state
awareness.setLocalState({
  user: {
    name: 'Alice',
    color: '#3b82f6',
    avatar: '/avatars/alice.png',
  },
  cursor: null,
  isTyping: false,
} satisfies AwarenessState);

// Update cursor position
function updateCursor(anchor: number, head: number): void {
  awareness.setLocalStateField('cursor', { anchor, head });
}

// Listen for other users' awareness changes
awareness.on('change', ({
  added,
  updated,
  removed,
}: {
  added: number[];
  updated: number[];
  removed: number[];
}) => {
  const states = awareness.getStates() as Map<number, AwarenessState>;

  // Render remote cursors
  for (const [clientId, state] of states) {
    if (clientId === ydoc.clientID) continue;  // skip local
    console.log(`User ${state.user.name} cursor:`, state.cursor);
  }
});

// Get online user count
function getOnlineUsers(): AwarenessState[] {
  const states = awareness.getStates() as Map<number, AwarenessState>;
  return Array.from(states.values());
}
```

```typescript
// --- Integration with editors (Tiptap/ProseMirror) ---

import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Collaboration from '@tiptap/extension-collaboration';
import CollaborationCursor from '@tiptap/extension-collaboration-cursor';

function createCollaborativeEditor(
  element: HTMLElement,
  ydoc: Y.Doc,
  awareness: awarenessProtocol.Awareness,
  user: { name: string; color: string },
): Editor {
  const editor = new Editor({
    element,
    extensions: [
      StarterKit.configure({
        history: false,  // Yjs handles undo/redo
      }),
      Collaboration.configure({
        document: ydoc,
        field: 'content',  // Y.XmlFragment name
      }),
      CollaborationCursor.configure({
        provider: wsProvider,
        user: { name: user.name, color: user.color },
      }),
    ],
    content: '',  // Content comes from Yjs
  });

  return editor;
}


// --- Transactions (atomic operations) ---

// Group multiple operations into one transaction
ydoc.transact(() => {
  const todo = new Y.Map<unknown>();
  todo.set('id', crypto.randomUUID());
  todo.set('text', 'New task');
  todo.set('done', false);
  todo.set('createdAt', Date.now());
  ytodos.push([todo]);
  ymeta.set('lastModified', Date.now());
});
// All observers fire once with all changes batched


// --- Undo/Redo ---

const undoManager = new Y.UndoManager(ytext, {
  trackedOrigins: new Set([null]),  // track all local changes
  captureTimeout: 500,  // group changes within 500ms
});

// Track array too
const todoUndo = new Y.UndoManager(ytodos);

undoManager.on('stack-item-added', (event: { type: string }) => {
  console.log('Undo stack updated:', event.type);  // 'undo' or 'redo'
});

// Undo/redo
undoManager.undo();
undoManager.redo();
console.log(undoManager.canUndo());  // boolean
console.log(undoManager.canRedo());  // boolean


// --- Subdocuments (lazy loading) ---

const rootDoc = new Y.Doc();
const pages = rootDoc.getMap('pages');

function createPage(pageId: string): Y.Doc {
  const pageDoc = new Y.Doc({ guid: pageId });
  pages.set(pageId, pageDoc);
  return pageDoc;
}

// Pages are loaded on demand — not synced until accessed
const pageDoc = pages.get('page-1') as Y.Doc;
pageDoc.load();  // starts syncing this subdocument
```

| Yjs Shared Type | Equivalent JS Type | Best For |
|---|---|---|
| `Y.Text` | String (with formatting) | Rich text editors, code editors |
| `Y.Array` | Array | Lists, kanban boards, ordered items |
| `Y.Map` | Object / Map | Key-value state, settings, metadata |
| `Y.XmlFragment` | DOM tree | ProseMirror, Tiptap integration |
| `Y.XmlElement` | DOM element | Structured document nodes |

| Provider | Transport | Persistence | Use Case |
|---|---|---|---|
| y-websocket | WebSocket | Server-side | Real-time with server |
| y-webrtc | WebRTC (P2P) | None | Serverless, peer-to-peer |
| y-indexeddb | N/A | IndexedDB | Offline persistence |
| y-dat | Hypercore | Dat network | P2P file sharing |
| Hocuspocus | WebSocket | Any backend | Production server |

Key patterns:
1. `Y.Doc` is the root; access shared types via `doc.getText()`, `doc.getArray()`, `doc.getMap()`
2. Awareness protocol tracks user presence, cursors, and ephemeral state
3. `ydoc.transact()` batches multiple operations into a single atomic update
4. `Y.UndoManager` provides undo/redo that respects collaborative changes (only undoes local edits)
5. Use IndexedDB persistence for offline-first; sync via WebSocket when online
6. Subdocuments (`Y.Doc` inside `Y.Map`) enable lazy loading of large document sets
7. Tiptap/ProseMirror integration via `Collaboration` + `CollaborationCursor` extensions'''
    ),
    (
        "frontend/automerge-sync",
        "Demonstrate Automerge for document synchronization including creating documents, making changes, syncing peers, and handling conflicts.",
        '''Automerge is a JSON-like CRDT library that allows multiple users to make concurrent changes to a document and merge them automatically without conflicts.

```typescript
// --- Automerge basics ---

import * as Automerge from '@automerge/automerge';
import { Repo, DocHandle } from '@automerge/automerge-repo';
import { BrowserWebSocketClientAdapter } from '@automerge/automerge-repo-network-websocket';
import { IndexedDBStorageAdapter } from '@automerge/automerge-repo-storage-indexeddb';

// Define document schema
interface TodoDoc {
  title: string;
  todos: Array<{
    id: string;
    text: string;
    done: boolean;
    createdAt: number;
  }>;
  settings: {
    theme: 'light' | 'dark';
    sortBy: 'date' | 'priority';
  };
}

// Create a new document
let doc = Automerge.init<TodoDoc>();

// Make changes (immutable — returns new document)
doc = Automerge.change(doc, 'Initialize document', (d) => {
  d.title = 'My Todo List';
  d.todos = [];
  d.settings = { theme: 'light', sortBy: 'date' };
});

// Add a todo
doc = Automerge.change(doc, 'Add grocery task', (d) => {
  d.todos.push({
    id: crypto.randomUUID(),
    text: 'Buy groceries',
    done: false,
    createdAt: Date.now(),
  });
});

// Toggle a todo
doc = Automerge.change(doc, 'Complete grocery task', (d) => {
  const todo = d.todos.find(t => t.text === 'Buy groceries');
  if (todo) todo.done = true;
});

// Read values (plain JavaScript objects)
console.log(doc.title);             // 'My Todo List'
console.log(doc.todos.length);      // 1
console.log(doc.todos[0].done);     // true


// --- View change history ---
const history = Automerge.getHistory(doc);
for (const entry of history) {
  console.log(`Change: ${entry.change.message}`);
  console.log(`  Time: ${new Date(entry.change.time)}`);
  console.log(`  Actor: ${entry.change.actor}`);
}
```

```typescript
// --- Syncing between peers ---

// Automerge sync protocol: efficient binary sync

// Peer A makes changes
let docA = Automerge.init<TodoDoc>();
docA = Automerge.change(docA, (d) => {
  d.title = 'Shared List';
  d.todos = [];
  d.settings = { theme: 'light', sortBy: 'date' };
});

// Peer B clones and diverges
let docB = Automerge.clone(docA);

// Concurrent changes
docA = Automerge.change(docA, (d) => {
  d.todos.push({ id: '1', text: 'Task from A', done: false, createdAt: Date.now() });
});

docB = Automerge.change(docB, (d) => {
  d.todos.push({ id: '2', text: 'Task from B', done: false, createdAt: Date.now() });
  d.settings.theme = 'dark';
});

// Merge: both changes are preserved
let merged = Automerge.merge(docA, docB);
console.log(merged.todos.length);     // 2 (both tasks present)
console.log(merged.settings.theme);   // 'dark' (B's change)


// --- Efficient sync protocol ---

// Sync state tracks what each peer has seen
let syncStateA = Automerge.initSyncState();
let syncStateB = Automerge.initSyncState();

// Generate sync message from A
let [nextSyncStateA, msgFromA] = Automerge.generateSyncMessage(docA, syncStateA);
syncStateA = nextSyncStateA;

// B receives and applies the message
if (msgFromA) {
  let [nextDocB, nextSyncStateB] = Automerge.receiveSyncMessage(docB, syncStateB, msgFromA);
  docB = nextDocB;
  syncStateB = nextSyncStateB;
}

// B generates response
let [nextSyncStateB2, msgFromB] = Automerge.generateSyncMessage(docB, syncStateB);
syncStateB = nextSyncStateB2;

// A receives B's response
if (msgFromB) {
  let [nextDocA, nextSyncStateA2] = Automerge.receiveSyncMessage(docA, syncStateA, msgFromB);
  docA = nextDocA;
  syncStateA = nextSyncStateA2;
}

// Continue until no more messages (both synced)


// --- Binary document format ---

// Save to binary (efficient storage)
const binary: Uint8Array = Automerge.save(doc);
console.log(`Document size: ${binary.byteLength} bytes`);

// Load from binary
const loaded = Automerge.load<TodoDoc>(binary);

// Incremental save (only new changes)
const changes: Uint8Array[] = Automerge.getLastLocalChange(doc)
  ? [Automerge.getLastLocalChange(doc)!]
  : [];
```

```typescript
// --- Automerge Repo (production-ready networking) ---

// Repo manages documents, networking, and storage
const repo = new Repo({
  network: [
    new BrowserWebSocketClientAdapter('wss://sync.example.com'),
  ],
  storage: new IndexedDBStorageAdapter('my-app'),
});

// Create a new document
const handle: DocHandle<TodoDoc> = repo.create<TodoDoc>();
handle.change((d) => {
  d.title = 'Collaborative List';
  d.todos = [];
  d.settings = { theme: 'light', sortBy: 'date' };
});

// Get the document URL (shareable)
const docUrl = handle.url;
console.log('Share this URL:', docUrl);
// e.g., "automerge:2oFEfMDwj7VQEz18YprVq3anYW5t"

// Open an existing document by URL
const existingHandle = repo.find<TodoDoc>(docUrl);

// Listen for changes (from any peer)
existingHandle.on('change', ({ doc, patches, patchInfo }) => {
  console.log('Document changed:', doc.title);

  // Patches describe what changed
  for (const patch of patches) {
    console.log(`  Path: ${patch.path.join('/')}`);
    console.log(`  Action: ${patch.action}`);
    // action: 'put' | 'del' | 'splice' | 'inc'
  }
});

// Make local changes
existingHandle.change((d) => {
  d.todos.push({
    id: crypto.randomUUID(),
    text: 'New collaborative task',
    done: false,
    createdAt: Date.now(),
  });
});

// Read current doc
const currentDoc = await existingHandle.doc();
console.log(currentDoc?.todos);


// --- React integration ---

import { useDocument, useHandle } from '@automerge/automerge-repo-react-hooks';
import { RepoContext } from '@automerge/automerge-repo-react-hooks';

// Provider
function App() {
  return (
    <RepoContext.Provider value={repo}>
      <TodoApp docUrl={docUrl} />
    </RepoContext.Provider>
  );
}

function TodoApp({ docUrl }: { docUrl: string }) {
  const [doc, changeDoc] = useDocument<TodoDoc>(docUrl);

  if (!doc) return <p>Loading...</p>;

  function addTodo(text: string) {
    changeDoc((d) => {
      d.todos.push({
        id: crypto.randomUUID(),
        text,
        done: false,
        createdAt: Date.now(),
      });
    });
  }

  function toggleTodo(index: number) {
    changeDoc((d) => {
      d.todos[index].done = !d.todos[index].done;
    });
  }

  return (
    <div>
      <h1>{doc.title}</h1>
      <ul>
        {doc.todos.map((todo, i) => (
          <li key={todo.id}>
            <input
              type="checkbox"
              checked={todo.done}
              onChange={() => toggleTodo(i)}
            />
            {todo.text}
          </li>
        ))}
      </ul>
      <button onClick={() => addTodo('New task')}>Add Todo</button>
    </div>
  );
}
```

| Feature | Automerge | Yjs |
|---|---|---|
| Data model | JSON-like document | Shared types (Text, Array, Map) |
| API style | Immutable (returns new doc) | Mutable (modify in place) |
| Encoding | Columnar binary (compact) | Custom binary |
| History | Full change history built-in | Opt-in (snapshots) |
| Sync protocol | Binary sync messages | Binary update encoding |
| Rich text | Via `@automerge/prosemirror` | `Y.Text` with attributes |
| React hooks | `useDocument`, `useHandle` | Custom or `@tiptap` |
| Storage | Binary `save()`/`load()` | Providers (IndexedDB, etc.) |
| Bundle size | ~250 KB (WASM) | ~15 KB |
| Performance | Good (WASM) | Excellent |

Key patterns:
1. `Automerge.change(doc, fn)` returns a new immutable document with changes applied
2. `Automerge.merge(docA, docB)` deterministically merges concurrent changes
3. Sync protocol: `generateSyncMessage` / `receiveSyncMessage` in a loop until done
4. Automerge Repo handles networking, storage, and document lifecycle for production
5. Document URLs (`automerge:...`) are shareable identifiers for collaborative documents
6. Patches describe exactly what changed — useful for targeted UI updates
7. Full change history with `getHistory` includes actor, timestamp, and change message'''
    ),
    (
        "frontend/ot-vs-crdt-comparison",
        "Compare Operational Transform (OT) and CRDTs for collaborative editing including their algorithms, trade-offs, and when to use each approach.",
        '''Operational Transform (OT) and CRDTs are two fundamental approaches to collaborative editing. OT transforms operations against each other; CRDTs use data structures that merge without conflicts.

```typescript
// --- Operational Transform (OT) basics ---

// OT works by transforming operations so they can be applied
// in any order and produce the same result.

type OTOperation =
  | { type: 'insert'; position: number; char: string }
  | { type: 'delete'; position: number };

// Transform function: given two concurrent operations,
// adjust them so they can be applied in either order.
function transform(
  op1: OTOperation,
  op2: OTOperation,
): [OTOperation, OTOperation] {
  // Both operations were created against the same document state.
  // Return [op1', op2'] where:
  //   apply(apply(doc, op1), op2') === apply(apply(doc, op2), op1')

  if (op1.type === 'insert' && op2.type === 'insert') {
    if (op1.position < op2.position) {
      // op1 inserts before op2 — shift op2 right
      return [op1, { ...op2, position: op2.position + 1 }];
    } else if (op1.position > op2.position) {
      return [{ ...op1, position: op1.position + 1 }, op2];
    } else {
      // Same position — tie-break by some rule (e.g., user ID)
      return [op1, { ...op2, position: op2.position + 1 }];
    }
  }

  if (op1.type === 'insert' && op2.type === 'delete') {
    if (op1.position <= op2.position) {
      return [op1, { ...op2, position: op2.position + 1 }];
    } else {
      return [{ ...op1, position: op1.position - 1 }, op2];
    }
  }

  if (op1.type === 'delete' && op2.type === 'insert') {
    if (op1.position < op2.position) {
      return [op1, { ...op2, position: op2.position - 1 }];
    } else {
      return [{ ...op1, position: op1.position + 1 }, op2];
    }
  }

  if (op1.type === 'delete' && op2.type === 'delete') {
    if (op1.position < op2.position) {
      return [op1, { ...op2, position: op2.position - 1 }];
    } else if (op1.position > op2.position) {
      return [{ ...op1, position: op1.position - 1 }, op2];
    } else {
      // Both delete same character — one becomes a no-op
      return [
        { type: 'insert', position: 0, char: '' },  // no-op placeholder
        { type: 'insert', position: 0, char: '' },
      ];
    }
  }

  return [op1, op2];
}


// --- OT Server (centralized) ---

class OTServer {
  private document: string = '';
  private revision: number = 0;
  private history: OTOperation[][] = [];

  applyFromClient(
    clientOps: OTOperation[],
    clientRevision: number,
  ): { ops: OTOperation[]; revision: number } {
    // Transform client ops against all ops that happened
    // since the client's revision
    let transformed = [...clientOps];

    for (let i = clientRevision; i < this.revision; i++) {
      const serverOps = this.history[i];
      transformed = this.transformBatch(transformed, serverOps);
    }

    // Apply transformed ops to the server document
    for (const op of transformed) {
      this.document = this.applyOp(this.document, op);
    }

    this.history.push(transformed);
    this.revision++;

    return { ops: transformed, revision: this.revision };
  }

  private transformBatch(
    clientOps: OTOperation[],
    serverOps: OTOperation[],
  ): OTOperation[] {
    let result = [...clientOps];
    for (const serverOp of serverOps) {
      result = result.map(clientOp => transform(clientOp, serverOp)[0]);
    }
    return result;
  }

  private applyOp(doc: string, op: OTOperation): string {
    if (op.type === 'insert') {
      return doc.slice(0, op.position) + op.char + doc.slice(op.position);
    }
    if (op.type === 'delete') {
      return doc.slice(0, op.position) + doc.slice(op.position + 1);
    }
    return doc;
  }
}
```

```typescript
// --- CRDT approach (simplified RGA for text) ---

// RGA (Replicated Growable Array) — a sequence CRDT

interface RGANode {
  id: { site: string; clock: number };
  value: string | null;  // null = tombstone (deleted)
  parent: { site: string; clock: number } | null;
}

class RGADocument {
  private nodes: RGANode[] = [];
  private clock: number = 0;
  private siteId: string;

  constructor(siteId: string) {
    this.siteId = siteId;
  }

  insert(position: number, char: string): RGANode {
    this.clock++;
    const parentId = position > 0 ? this.visibleNodes()[position - 1].id : null;

    const node: RGANode = {
      id: { site: this.siteId, clock: this.clock },
      value: char,
      parent: parentId,
    };

    // Find insertion point
    const parentIndex = parentId
      ? this.nodes.findIndex(n => n.id.site === parentId.site && n.id.clock === parentId.clock)
      : -1;

    // Insert after parent, respecting ordering of concurrent inserts
    let insertAt = parentIndex + 1;
    while (insertAt < this.nodes.length) {
      const existing = this.nodes[insertAt];
      if (existing.parent?.site === parentId?.site && existing.parent?.clock === parentId?.clock) {
        // Same parent — compare IDs for deterministic ordering
        if (this.compareIds(node.id, existing.id) > 0) break;
        insertAt++;
      } else {
        break;
      }
    }

    this.nodes.splice(insertAt, 0, node);
    return node;
  }

  delete(position: number): void {
    const visible = this.visibleNodes();
    if (position >= 0 && position < visible.length) {
      visible[position].value = null;  // tombstone
    }
  }

  // Apply a remote operation
  applyRemote(node: RGANode): void {
    this.clock = Math.max(this.clock, node.id.clock);

    const parentIndex = node.parent
      ? this.nodes.findIndex(n => n.id.site === node.parent!.site && n.id.clock === node.parent!.clock)
      : -1;

    let insertAt = parentIndex + 1;
    while (insertAt < this.nodes.length) {
      const existing = this.nodes[insertAt];
      if (existing.parent?.site === node.parent?.site && existing.parent?.clock === node.parent?.clock) {
        if (this.compareIds(node.id, existing.id) > 0) break;
        insertAt++;
      } else {
        break;
      }
    }

    this.nodes.splice(insertAt, 0, node);
  }

  getText(): string {
    return this.visibleNodes().map(n => n.value).join('');
  }

  private visibleNodes(): RGANode[] {
    return this.nodes.filter(n => n.value !== null);
  }

  private compareIds(
    a: { site: string; clock: number },
    b: { site: string; clock: number },
  ): number {
    if (a.clock !== b.clock) return b.clock - a.clock;  // higher clock wins
    return b.site.localeCompare(a.site);  // tie-break by site ID
  }
}
```

```typescript
// --- When to use what: decision framework ---

interface CollabArchitecture {
  approach: 'OT' | 'CRDT';
  library: string;
  server: 'required' | 'optional' | 'none';
  complexity: 'low' | 'medium' | 'high';
  bestFor: string;
}

const architectures: CollabArchitecture[] = [
  {
    approach: 'OT',
    library: 'ShareDB',
    server: 'required',
    complexity: 'medium',
    bestFor: 'Text editors with a central server (Google Docs model)',
  },
  {
    approach: 'OT',
    library: 'Firepad / Firebase',
    server: 'required',
    complexity: 'low',
    bestFor: 'Quick collaborative text with Firebase backend',
  },
  {
    approach: 'CRDT',
    library: 'Yjs',
    server: 'optional',
    complexity: 'low',
    bestFor: 'Rich text, P2P, offline-first, best performance',
  },
  {
    approach: 'CRDT',
    library: 'Automerge',
    server: 'optional',
    complexity: 'low',
    bestFor: 'JSON documents, full history, local-first',
  },
  {
    approach: 'CRDT',
    library: 'Diamond Types',
    server: 'optional',
    complexity: 'medium',
    bestFor: 'Plain text with minimal memory usage',
  },
];


// --- Hybrid approach: OT-like server with CRDT clients ---

// Some production systems use a hybrid:
// - Clients use CRDTs for local state
// - Server acts as a single source of truth (like OT server)
// - Server resolves ordering, broadcasts to all clients

class HybridSyncServer {
  private documents: Map<string, {
    content: Uint8Array;  // Yjs/Automerge encoded state
    version: number;
    clients: Set<WebSocket>;
  }> = new Map();

  handleUpdate(
    docId: string,
    update: Uint8Array,
    source: WebSocket,
  ): void {
    const doc = this.documents.get(docId);
    if (!doc) return;

    // Apply update to server's copy
    doc.content = this.mergeUpdate(doc.content, update);
    doc.version++;

    // Broadcast to all other clients
    for (const client of doc.clients) {
      if (client !== source && client.readyState === WebSocket.OPEN) {
        client.send(update);
      }
    }
  }

  private mergeUpdate(current: Uint8Array, update: Uint8Array): Uint8Array {
    // In practice, use Y.mergeUpdates or Automerge.merge
    // This is a simplified placeholder
    return update;
  }
}
```

| Aspect | Operational Transform | CRDTs |
|---|---|---|
| Architecture | Centralized server required | P2P or server, flexible |
| Consistency | Server determines order | Automatic convergence |
| Offline support | Limited (need server) | Full (merge on reconnect) |
| Complexity | Transform function correctness | Data structure design |
| Metadata overhead | Low (operations only) | Higher (vector clocks, tombstones) |
| History/undo | Server-managed | Built into data structure |
| Proven at scale | Google Docs, Etherpad | Figma (custom), Apple Notes |
| Latency | Server round-trip needed | Instant local application |
| Conflict resolution | Transform at server | Deterministic merge rules |

| Library | Approach | Size | Rich Text | Performance |
|---|---|---|---|---|
| Yjs | CRDT (YATA) | ~15 KB | Y.Text | Fastest |
| Automerge | CRDT (RGA) | ~250 KB | Via ProseMirror | Good |
| ShareDB | OT | ~30 KB | Via Quill/Slate | Good |
| Diamond Types | CRDT | ~50 KB (WASM) | Plain text only | Excellent |
| Loro | CRDT (Fugue) | ~100 KB (WASM) | Rich text | Very good |

Key patterns:
1. OT requires a central server to order operations; CRDTs can work peer-to-peer
2. CRDTs guarantee convergence mathematically; OT correctness depends on transform functions
3. For offline-first and P2P, CRDTs are the clear choice (Yjs or Automerge)
4. OT is simpler when you already have a central server and don\'t need offline support
5. Yjs is the most battle-tested CRDT library with the best editor integrations
6. Automerge is best when you need JSON document sync with full change history
7. In practice, both approaches can achieve sub-50ms sync latency in production'''
    ),

    # --- 5. Real-Time WebSocket Sync with Room Management ---
    (
        "frontend/websocket-collab-rooms",
        "Build a production WebSocket server for collaborative editing with room management, "
        "JWT authentication, connection rate limiting, reconnection with state recovery, and "
        "Redis pub/sub for horizontal scaling across multiple server instances.",
        """\
# Production WebSocket Sync Server with Room Management

## Architecture Overview

```
                 Load Balancer (sticky sessions by room)
                          |
             +------------+------------+
             |            |            |
        WS Server 1  WS Server 2  WS Server 3
             |            |            |
             +-----+------+------+----+
                   |             |
             Redis Pub/Sub   PostgreSQL
           (cross-server     (durable
            sync)             persistence)

Key design decisions:
- Sticky sessions route room clients to same server when possible
- Redis pub/sub handles rooms spanning multiple servers
- Y.Doc state cached in Redis (fast), persisted to PostgreSQL (durable)
- JWT tokens carry room permissions; no DB lookup needed on connect
```

## Server: Horizontally Scalable Sync Hub

```typescript
// server/sync-hub.ts
import { WebSocketServer, WebSocket } from "ws";
import Redis from "ioredis";
import * as Y from "yjs";
import { createServer } from "http";
import { verify } from "jsonwebtoken";

const JWT_SECRET = process.env.JWT_SECRET!;
const REDIS_URL = process.env.REDIS_URL!;
const MAX_CLIENTS = 50;
const MAX_OPS_SEC = 100;
const PERSIST_MS = 5_000;
const SERVER_ID = process.env.SERVER_ID ?? crypto.randomUUID();

const redisPub = new Redis(REDIS_URL);
const redisSub = new Redis(REDIS_URL);
const redisStore = new Redis(REDIS_URL);

interface AuthPayload {
  userId: string;
  userName: string;
  permissions: Record<string, "read" | "write" | "admin">;
}

interface RoomClient {
  ws: WebSocket;
  userId: string;
  permission: "read" | "write" | "admin";
  limiter: TokenBucket;
}

interface Room {
  doc: Y.Doc;
  clients: Map<string, RoomClient>;
  dirty: boolean;
}

class TokenBucket {
  private tokens: number;
  private lastRefill: number;
  constructor(private max = MAX_OPS_SEC, private rate = MAX_OPS_SEC) {
    this.tokens = max;
    this.lastRefill = Date.now();
  }
  consume(): boolean {
    const now = Date.now();
    this.tokens = Math.min(
      this.max,
      this.tokens + ((now - this.lastRefill) / 1000) * this.rate
    );
    this.lastRefill = now;
    if (this.tokens >= 1) { this.tokens--; return true; }
    return false;
  }
}

const rooms = new Map<string, Room>();

async function getOrCreateRoom(name: string): Promise<Room> {
  if (rooms.has(name)) return rooms.get(name)!;

  const doc = new Y.Doc();
  const cached = await redisStore.getBuffer(`doc:${name}`);
  if (cached) Y.applyUpdate(doc, new Uint8Array(cached));

  const room: Room = { doc, clients: new Map(), dirty: false };

  doc.on("update", (update: Uint8Array, origin: string) => {
    room.dirty = true;
    for (const [connId, client] of room.clients) {
      if (connId !== origin && client.ws.readyState === WebSocket.OPEN) {
        client.ws.send(
          JSON.stringify({ type: "update", data: Array.from(update) })
        );
      }
    }
    if (origin !== "redis") {
      redisPub.publish(`room:${name}`, JSON.stringify({
        type: "update", data: Array.from(update), serverId: SERVER_ID,
      }));
    }
  });

  rooms.set(name, room);
  return room;
}

// Cross-server sync via Redis
redisSub.on("message", (ch: string, msg: string) => {
  const roomName = ch.replace("room:", "");
  const room = rooms.get(roomName);
  if (!room) return;
  const parsed = JSON.parse(msg);
  if (parsed.serverId === SERVER_ID) return;
  if (parsed.type === "update")
    Y.applyUpdate(room.doc, new Uint8Array(parsed.data), "redis");
});

// Periodic persistence
setInterval(async () => {
  for (const [name, room] of rooms) {
    if (!room.dirty) continue;
    const buf = Buffer.from(Y.encodeStateAsUpdate(room.doc));
    await redisStore.set(`doc:${name}`, buf, "EX", 86_400);
    room.dirty = false;
  }
}, PERSIST_MS);

// Room cleanup
setInterval(() => {
  for (const [name, room] of rooms) {
    if (room.clients.size === 0) {
      room.doc.destroy();
      rooms.delete(name);
      redisSub.unsubscribe(`room:${name}`);
    }
  }
}, 60_000);

const httpServer = createServer();
const wss = new WebSocketServer({ server: httpServer });

wss.on("connection", async (ws, req) => {
  const url = new URL(req.url!, `http://${req.headers.host}`);
  const token = url.searchParams.get("token");
  const roomName = url.pathname.slice(1);

  let auth: AuthPayload;
  try { auth = verify(token!, JWT_SECRET) as AuthPayload; }
  catch { ws.close(4001, "Unauthorized"); return; }

  const perm = auth.permissions[roomName];
  if (!perm) { ws.close(4003, "Forbidden"); return; }

  const room = await getOrCreateRoom(roomName);
  if (room.clients.size >= MAX_CLIENTS) {
    ws.close(4029, "Room full");
    return;
  }

  if (room.clients.size === 0)
    await redisSub.subscribe(`room:${roomName}`);

  const connId = `${auth.userId}-${Date.now()}`;
  room.clients.set(connId, {
    ws, userId: auth.userId, permission: perm,
    limiter: new TokenBucket(),
  });

  ws.send(JSON.stringify({
    type: "sync-init",
    stateVector: Array.from(Y.encodeStateVector(room.doc)),
    clients: room.clients.size,
    permission: perm,
  }));

  ws.on("message", (raw) => {
    const msg = JSON.parse(raw.toString());
    const client = room.clients.get(connId)!;
    switch (msg.type) {
      case "sync-request": {
        const diff = Y.encodeStateAsUpdate(
          room.doc, new Uint8Array(msg.stateVector)
        );
        ws.send(JSON.stringify({
          type: "sync-response", data: Array.from(diff),
        }));
        break;
      }
      case "update": {
        if (perm === "read") {
          ws.send(JSON.stringify({ type: "error", msg: "Read-only" }));
          return;
        }
        if (!client.limiter.consume()) {
          ws.send(JSON.stringify({ type: "error", msg: "Rate limited" }));
          return;
        }
        const update = new Uint8Array(msg.data);
        if (update.byteLength > 1_000_000) {
          ws.send(JSON.stringify({ type: "error", msg: "Too large" }));
          return;
        }
        Y.applyUpdate(room.doc, update, connId);
        break;
      }
      case "awareness": {
        for (const [cid, c] of room.clients) {
          if (cid !== connId && c.ws.readyState === WebSocket.OPEN) {
            c.ws.send(JSON.stringify({
              type: "awareness", clientId: connId, state: msg.state,
            }));
          }
        }
        break;
      }
    }
  });

  ws.on("close", () => {
    room.clients.delete(connId);
    for (const [, c] of room.clients) {
      if (c.ws.readyState === WebSocket.OPEN) {
        c.ws.send(JSON.stringify({
          type: "awareness", clientId: connId, state: null,
        }));
      }
    }
  });
});

httpServer.listen(4444, () => console.log(`Sync hub ${SERVER_ID} on :4444`));
```

## React Hook: useCollaborativeDocument

```tsx
// hooks/useCollaborativeDocument.ts
"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import * as Y from "yjs";

interface CollabState {
  status: "connecting" | "syncing" | "connected" | "disconnected" | "error";
  error: string | null;
  clientCount: number;
  permission: "read" | "write" | "admin" | null;
}

export function useCollaborativeDocument(opts: {
  roomId: string; serverUrl: string; token: string;
}) {
  const { roomId, serverUrl, token } = opts;
  const docRef = useRef(new Y.Doc());
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout>>();
  const attempts = useRef(0);
  const [state, setState] = useState<CollabState>({
    status: "connecting", error: null, clientCount: 0, permission: null,
  });

  const connect = useCallback(() => {
    const doc = docRef.current;
    const ws = new WebSocket(
      `${serverUrl}/${roomId}?token=${encodeURIComponent(token)}`
    );
    wsRef.current = ws;

    ws.onopen = () => {
      setState((s) => ({ ...s, status: "syncing" }));
      attempts.current = 0;
      ws.send(JSON.stringify({
        type: "sync-request",
        stateVector: Array.from(Y.encodeStateVector(doc)),
      }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case "sync-init":
          setState((s) => ({
            ...s, clientCount: msg.clients, permission: msg.permission,
          }));
          break;
        case "sync-response":
          Y.applyUpdate(doc, new Uint8Array(msg.data));
          setState((s) => ({ ...s, status: "connected" }));
          break;
        case "update":
          Y.applyUpdate(doc, new Uint8Array(msg.data), "remote");
          break;
        case "error":
          setState((s) => ({ ...s, error: msg.msg }));
          break;
      }
    };

    const onUpdate = (update: Uint8Array, origin: any) => {
      if (origin === "remote") return;
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "update", data: Array.from(update),
        }));
      }
    };
    doc.on("update", onUpdate);

    ws.onclose = (event) => {
      doc.off("update", onUpdate);
      setState((s) => ({ ...s, status: "disconnected" }));
      if (event.code < 4000) {
        const delay = Math.min(1000 * Math.pow(2, attempts.current), 30_000);
        attempts.current++;
        retryRef.current = setTimeout(connect, delay);
      } else {
        setState((s) => ({
          ...s, status: "error",
          error: event.reason || `Code: ${event.code}`,
        }));
      }
    };
  }, [roomId, serverUrl, token]);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
      docRef.current.destroy();
      docRef.current = new Y.Doc();
    };
  }, [connect]);

  return {
    doc: docRef.current, ...state,
    getText: (name = "default") => docRef.current.getText(name),
    getMap: <T = any>(name = "default") => docRef.current.getMap<T>(name),
    getArray: <T = any>(name = "default") => docRef.current.getArray<T>(name),
  };
}
```

| Scaling Approach | Latency | Max Clients | Offline | Complexity |
|---|---|---|---|---|
| Single WS server | ~5 ms | ~10 K | Yes (CRDT) | Low |
| WS + Redis pub/sub | ~10 ms | 100 K+ | Yes (CRDT) | Medium |
| WS + Kafka log | ~50 ms | 1 M+ | Yes | High |
| P2P via WebRTC | ~20 ms | No server | Yes (CRDT) | High |
| HTTP long-poll | ~1000 ms | Standard | Yes | Low |

Key patterns:
1. Redis pub/sub synchronizes Y.Doc updates across multiple WS server instances
2. Sticky sessions by room reduce cross-server chatter; Redis covers the rest
3. JWT on connect carries room permissions so WS server avoids DB lookups
4. Token bucket rate limiter prevents write abuse (100 ops/sec per client)
5. Dual persistence: Redis cache for fast room loads + PostgreSQL for durability
6. Exponential backoff reconnection; 4xxx close codes signal permanent errors
7. Room cleanup: destroy Y.Doc and unsubscribe Redis channel after 60 s empty"""
    ),
]
