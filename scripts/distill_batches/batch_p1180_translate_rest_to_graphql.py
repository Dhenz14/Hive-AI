"""Code translation pairs: REST API patterns to GraphQL schemas and resolvers."""

PAIRS = [
    (
        "code-translation/rest-to-graphql",
        r'''Convert these REST endpoints to a GraphQL schema and resolvers:

GET /api/users              -> list all users
GET /api/users/:id          -> get user by ID
GET /api/users/:id/posts    -> get posts by user
POST /api/users             -> create user (body: {name, email})
PUT /api/users/:id          -> update user
DELETE /api/users/:id       -> delete user

GET /api/posts              -> list posts (query: ?author=X&limit=N)
GET /api/posts/:id          -> get single post
POST /api/posts             -> create post (body: {title, content, authorId})''',
        r'''<think>
REST to GraphQL translation. The key mental shift is:

1. REST: multiple endpoints, each returns a fixed shape. Client gets whatever the server sends.
2. GraphQL: single endpoint, client specifies exactly what fields it needs. Types are explicit in a schema.

For the schema, I need to:
- Define User and Post types with their relationships
- Map GET endpoints to Query type fields
- Map POST/PUT/DELETE to Mutation type fields
- Handle the nested relationship (users/:id/posts) as a field on the User type instead of a separate endpoint

The /api/users/:id/posts endpoint is a great example -- in REST it's a separate route, but in GraphQL it's just a `posts` field on the `User` type that the client can request or not.

Query params like ?author=X&limit=N become arguments on the query field.

For resolvers, I'll show JavaScript/Node.js since that's the most common GraphQL server ecosystem.
</think>

```graphql
# Schema definition

type User {
  id: ID!
  name: String!
  email: String!
  posts: [Post!]!    # replaces GET /users/:id/posts
}

type Post {
  id: ID!
  title: String!
  content: String!
  author: User!      # back-reference to author
}

type Query {
  users: [User!]!                          # GET /users
  user(id: ID!): User                     # GET /users/:id
  posts(authorId: ID, limit: Int): [Post!]! # GET /posts?author=X&limit=N
  post(id: ID!): Post                     # GET /posts/:id
}

input CreateUserInput {
  name: String!
  email: String!
}

input UpdateUserInput {
  name: String
  email: String
}

input CreatePostInput {
  title: String!
  content: String!
  authorId: ID!
}

type Mutation {
  createUser(input: CreateUserInput!): User!    # POST /users
  updateUser(id: ID!, input: UpdateUserInput!): User  # PUT /users/:id
  deleteUser(id: ID!): Boolean!                 # DELETE /users/:id
  createPost(input: CreatePostInput!): Post!    # POST /posts
}
```

```javascript
// Resolvers (Node.js)
const resolvers = {
  Query: {
    users: (_, __, { db }) => db.users.findAll(),
    user: (_, { id }, { db }) => db.users.findById(id),
    posts: (_, { authorId, limit }, { db }) => {
      let query = {};
      if (authorId) query.authorId = authorId;
      return db.posts.findAll({ where: query, limit });
    },
    post: (_, { id }, { db }) => db.posts.findById(id),
  },
  Mutation: {
    createUser: (_, { input }, { db }) => db.users.create(input),
    updateUser: (_, { id, input }, { db }) => db.users.update(id, input),
    deleteUser: (_, { id }, { db }) => db.users.destroy(id),
    createPost: (_, { input }, { db }) => db.posts.create(input),
  },
  // Relationship resolvers
  User: {
    posts: (user, _, { db }) => db.posts.findAll({ where: { authorId: user.id } }),
  },
  Post: {
    author: (post, _, { db }) => db.users.findById(post.authorId),
  },
};
```

Key REST-to-GraphQL translations:

- Multiple GET endpoints -> fields on the `Query` type
- POST/PUT/DELETE -> fields on the `Mutation` type with Input types
- Nested routes (`/users/:id/posts`) -> relationship fields on the parent type
- Query string params (`?author=X`) -> field arguments
- Clients choose which fields to fetch -- no over-fetching''',
    ),
    (
        "code-translation/rest-to-graphql",
        r'''I have this REST API that requires multiple round trips. Convert to a single GraphQL query:

// Client code making 3 REST calls:
const user = await fetch("/api/users/42").then(r => r.json());
const posts = await fetch(`/api/users/${user.id}/posts?limit=5`).then(r => r.json());
const enriched = await Promise.all(
  posts.map(async post => {
    const comments = await fetch(`/api/posts/${post.id}/comments`).then(r => r.json());
    return { ...post, comments, commentCount: comments.length };
  })
);
// Total: 1 + 1 + N requests (N+2 round trips for N posts)''',
        r'''```graphql
# Single GraphQL query replacing all N+2 REST calls:

query UserWithPostsAndComments {
  user(id: "42") {
    id
    name
    email
    posts(limit: 5) {
      id
      title
      content
      comments {
        id
        text
        author {
          name
        }
      }
      commentCount
    }
  }
}
```

```graphql
# Schema additions needed:

type Post {
  id: ID!
  title: String!
  content: String!
  author: User!
  comments: [Comment!]!
  commentCount: Int!        # computed field
}

type Comment {
  id: ID!
  text: String!
  author: User!
}
```

```javascript
// Resolver for the computed field and nested data:
const resolvers = {
  Post: {
    comments: (post, _, { db }) =>
      db.comments.findAll({ where: { postId: post.id } }),
    commentCount: (post, _, { db }) =>
      db.comments.count({ where: { postId: post.id } }),
  },
};
// Note: use DataLoader to avoid N+1 queries on the server side:
// const commentLoader = new DataLoader(postIds =>
//   db.comments.findAll({ where: { postId: postIds } })
//     .then(groupByPostId)
// );
```

What changed:

- N+2 HTTP round trips -> 1 single request. The client describes the shape of data it needs in one query
- Server resolves nested relationships automatically via resolver chain
- `commentCount` becomes a computed field on the Post type instead of client-side `.length`
- The N+1 problem (fetching comments for each post) still exists server-side -- use DataLoader to batch database queries
- Client gets exactly the fields it asks for, nothing more''',
    ),
    (
        "code-translation/rest-to-graphql",
        r'''Translate this REST API with pagination, filtering, and sorting to GraphQL:

GET /api/products?page=2&per_page=20&sort=price:desc&category=electronics&min_price=100&max_price=500

Response:
{
  "data": [...],
  "meta": {
    "total": 342,
    "page": 2,
    "per_page": 20,
    "total_pages": 18
  }
}''',
        r'''<think>
REST pagination/filtering/sorting to GraphQL. There are two main pagination patterns in GraphQL:

1. Offset-based (page/per_page) -- matches the REST pattern directly
2. Cursor-based (Relay-style with edges/nodes/pageInfo) -- more robust for real-time data

I should show both approaches. The REST API uses offset pagination, so I'll translate that directly first, then mention cursor-based as the recommended GraphQL pattern.

For filtering, GraphQL typically uses an input type with filter fields rather than query string params. For sorting, an enum for field names and a direction enum.

This is a direct (no-thinking) pair, so I'll be concise.
</think>

```graphql
# Approach 1: Offset pagination (matches REST pattern)

enum SortDirection {
  ASC
  DESC
}

enum ProductSortField {
  PRICE
  NAME
  CREATED_AT
}

input ProductFilter {
  category: String
  minPrice: Float
  maxPrice: Float
  search: String
}

input ProductSort {
  field: ProductSortField!
  direction: SortDirection!
}

type ProductPage {
  data: [Product!]!
  meta: PageMeta!
}

type PageMeta {
  total: Int!
  page: Int!
  perPage: Int!
  totalPages: Int!
}

type Query {
  products(
    page: Int = 1
    perPage: Int = 20
    sort: ProductSort
    filter: ProductFilter
  ): ProductPage!
}
```

```graphql
# The REST call:
# GET /api/products?page=2&per_page=20&sort=price:desc
#     &category=electronics&min_price=100&max_price=500

# Becomes this GraphQL query:
query {
  products(
    page: 2
    perPage: 20
    sort: { field: PRICE, direction: DESC }
    filter: { category: "electronics", minPrice: 100, maxPrice: 500 }
  ) {
    data {
      id
      name
      price
      category
    }
    meta {
      total
      page
      perPage
      totalPages
    }
  }
}
```

```graphql
# Approach 2: Cursor-based (Relay spec, recommended for GraphQL)

type ProductConnection {
  edges: [ProductEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type ProductEdge {
  node: Product!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

type Query {
  products(
    first: Int
    after: String
    sort: ProductSort
    filter: ProductFilter
  ): ProductConnection!
}

# Usage: products(first: 20, after: "cursor_abc", ...)
```

Key differences:

- Query params (`?key=val`) -> typed input objects and arguments with defaults
- `sort=price:desc` string -> enum-based `ProductSort` input with compile-time validation
- Response wrapper `{data, meta}` -> dedicated `ProductPage` or `ProductConnection` type
- Cursor-based pagination is preferred in GraphQL because offset pagination breaks when items are inserted/deleted between pages''',
    ),
    (
        "code-translation/rest-to-graphql",
        r'''Convert this Express.js REST controller with authentication to a GraphQL resolver with auth:

// REST middleware + controller
function requireAuth(req, res, next) {
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) return res.status(401).json({ error: "Unauthorized" });
  try {
    req.user = jwt.verify(token, SECRET);
    next();
  } catch {
    res.status(401).json({ error: "Invalid token" });
  }
}

function requireRole(role) {
  return (req, res, next) => {
    if (req.user.role !== role) return res.status(403).json({ error: "Forbidden" });
    next();
  };
}

app.post("/api/posts", requireAuth, (req, res) => {
  const post = db.posts.create({ ...req.body, authorId: req.user.id });
  res.status(201).json(post);
});

app.delete("/api/posts/:id", requireAuth, requireRole("admin"), async (req, res) => {
  await db.posts.destroy(req.params.id);
  res.status(204).end();
});''',
        r'''```graphql
# Schema
type Mutation {
  createPost(input: CreatePostInput!): Post!      @auth
  deletePost(id: ID!): Boolean!                    @auth(role: "admin")
}

input CreatePostInput {
  title: String!
  content: String!
}

# The @auth directive is custom -- defined below
directive @auth(role: String) on FIELD_DEFINITION
```

```javascript
// GraphQL server setup (Apollo Server example)
const { ApolloServer, AuthenticationError, ForbiddenError } = require("apollo-server");
const jwt = require("jsonwebtoken");

// Context function -- replaces requireAuth middleware
// Runs once per request, extracts user from token
function buildContext({ req }) {
  const header = req.headers.authorization || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : null;
  let user = null;
  if (token) {
    try {
      user = jwt.verify(token, SECRET);
    } catch (e) {
      // token invalid -- user stays null
    }
  }
  return { user, db };
}

// Auth check helper -- replaces requireAuth + requireRole
function requireAuth(context, role) {
  if (!context.user) {
    throw new AuthenticationError("Unauthorized");
  }
  if (role && context.user.role !== role) {
    throw new ForbiddenError("Forbidden");
  }
  return context.user;
}

const resolvers = {
  Mutation: {
    createPost: (_, { input }, context) => {
      const user = requireAuth(context);
      return context.db.posts.create({
        ...input,
        authorId: user.id,
      });
    },
    deletePost: (_, { id }, context) => {
      requireAuth(context, "admin");
      return context.db.posts.destroy(id).then(() => true);
    },
  },
};

const server = new ApolloServer({
  typeDefs,
  resolvers,
  context: buildContext,
});
```

Key differences:

- REST middleware chain (`requireAuth`, `requireRole`) -> GraphQL context function (runs per request) + helper functions in resolvers
- `req.user` set by middleware -> `context.user` set in context builder and passed to every resolver
- HTTP status codes (401, 403) -> typed errors (`AuthenticationError`, `ForbiddenError`) that GraphQL returns in the `errors` array
- `res.status(201).json(post)` -> just return the value from the resolver; GraphQL handles serialization
- Route-level auth (`app.delete("/path", requireAuth, ...)`) -> resolver-level auth or schema directives (`@auth`)''',
    ),
    (
        "code-translation/rest-to-graphql",
        r'''Convert these REST endpoints for a file upload and real-time notifications system to GraphQL:

POST /api/upload           -> upload file (multipart form data)
GET  /api/files/:id        -> get file metadata
GET  /api/notifications    -> SSE stream of notifications for current user
POST /api/notifications/read/:id -> mark notification as read''',
        r'''```graphql
# Schema

scalar Upload    # requires graphql-upload package

type File {
  id: ID!
  filename: String!
  mimetype: String!
  size: Int!
  url: String!
  uploadedAt: String!
}

type Notification {
  id: ID!
  message: String!
  read: Boolean!
  createdAt: String!
}

type Query {
  file(id: ID!): File
}

type Mutation {
  # POST /api/upload replacement
  uploadFile(file: Upload!): File!

  # POST /api/notifications/read/:id replacement
  markNotificationRead(id: ID!): Notification!
}

type Subscription {
  # GET /api/notifications (SSE stream) replacement
  notificationReceived: Notification!
}
```

```javascript
// Resolvers
const { PubSub } = require("graphql-subscriptions");
const pubsub = new PubSub();
const NOTIFICATION_EVENT = "NEW_NOTIFICATION";

const resolvers = {
  Query: {
    file: (_, { id }, { db }) => db.files.findById(id),
  },

  Mutation: {
    uploadFile: async (_, { file }, { db, user }) => {
      // graphql-upload provides a ReadStream
      const { createReadStream, filename, mimetype } = await file;
      const stream = createReadStream();

      // Save to storage (S3, local disk, etc.)
      const savedPath = await saveToStorage(stream, filename);
      const stat = await getFileSize(savedPath);

      return db.files.create({
        filename,
        mimetype,
        size: stat,
        url: savedPath,
        uploadedBy: user.id,
      });
    },

    markNotificationRead: async (_, { id }, { db }) => {
      return db.notifications.update(id, { read: true });
    },
  },

  Subscription: {
    notificationReceived: {
      // Replaces SSE stream -- uses WebSocket under the hood
      subscribe: (_, __, { user }) => {
        return pubsub.asyncIterator([
          NOTIFICATION_EVENT + ":" + user.id,
        ]);
      },
    },
  },
};

// When creating a notification elsewhere:
// pubsub.publish(NOTIFICATION_EVENT + ":" + userId, {
//   notificationReceived: notification,
// });
```

Key REST-to-GraphQL translations:

- Multipart file upload -> `Upload` scalar type from `graphql-upload` package. The file streams through the GraphQL resolver
- SSE/EventSource stream -> GraphQL `Subscription` type using WebSockets (via `graphql-ws` protocol)
- Separate GET endpoint for file metadata -> `file(id)` query field
- POST to mark-as-read -> `markNotificationRead` mutation
- REST uses different HTTP methods and content types per endpoint; GraphQL uses one endpoint with typed operations''',
    ),
]
