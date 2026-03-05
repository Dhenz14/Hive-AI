"""GraphQL — schema design, resolvers, and client patterns."""

PAIRS = [
    (
        "backend/graphql-schema",
        "Show GraphQL schema design patterns: types, queries, mutations, subscriptions, and pagination with Strawberry.",
        '''GraphQL schema design with Strawberry (Python):

```python
import strawberry
from strawberry.types import Info
from strawberry.scalars import JSON
from strawberry.permission import BasePermission
from datetime import datetime
from typing import Optional, Annotated
from enum import Enum


# --- Enums ---

@strawberry.enum
class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"


@strawberry.enum
class SortDirection(Enum):
    ASC = "asc"
    DESC = "desc"


# --- Types ---

@strawberry.type
class User:
    id: strawberry.ID
    email: str
    name: str
    role: UserRole
    created_at: datetime

    @strawberry.field
    async def posts(
        self,
        info: Info,
        first: int = 10,
        after: Optional[str] = None,
    ) -> "PostConnection":
        """Lazy-loaded posts with cursor pagination."""
        loader = info.context["post_loader"]
        return await loader.load_for_user(self.id, first, after)

    @strawberry.field
    async def post_count(self, info: Info) -> int:
        """Separate field to avoid N+1 on list queries."""
        loader = info.context["count_loader"]
        return await loader.load(self.id)


@strawberry.type
class Post:
    id: strawberry.ID
    title: str
    content: str
    published: bool
    author_id: strawberry.ID
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    async def author(self, info: Info) -> User:
        loader = info.context["user_loader"]
        return await loader.load(self.author_id)


# --- Cursor-based pagination (Relay-style) ---

@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]


@strawberry.type
class PostEdge:
    cursor: str
    node: Post


@strawberry.type
class PostConnection:
    edges: list[PostEdge]
    page_info: PageInfo
    total_count: int


# --- Input types ---

@strawberry.input
class CreatePostInput:
    title: str
    content: str
    published: bool = False


@strawberry.input
class UpdatePostInput:
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None


@strawberry.input
class PostFilter:
    published: Optional[bool] = None
    author_id: Optional[strawberry.ID] = None
    search: Optional[str] = None


# --- Permissions ---

class IsAuthenticated(BasePermission):
    message = "Authentication required"

    async def has_permission(self, source, info: Info, **kwargs) -> bool:
        return info.context.get("current_user") is not None


class IsAdmin(BasePermission):
    message = "Admin access required"

    async def has_permission(self, source, info: Info, **kwargs) -> bool:
        user = info.context.get("current_user")
        return user is not None and user.role == UserRole.ADMIN


# --- Query ---

@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: Info) -> Optional[User]:
        return info.context.get("current_user")

    @strawberry.field
    async def user(self, info: Info, id: strawberry.ID) -> Optional[User]:
        return await info.context["user_repo"].find_by_id(id)

    @strawberry.field
    async def posts(
        self,
        info: Info,
        first: int = 10,
        after: Optional[str] = None,
        filter: Optional[PostFilter] = None,
        sort: SortDirection = SortDirection.DESC,
    ) -> PostConnection:
        return await info.context["post_repo"].paginate(
            first=first, after=after, filter=filter, sort=sort,
        )


# --- Mutation ---

@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def create_post(self, info: Info, input: CreatePostInput) -> Post:
        user = info.context["current_user"]
        return await info.context["post_repo"].create(
            author_id=user.id,
            title=input.title,
            content=input.content,
            published=input.published,
        )

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def update_post(
        self, info: Info, id: strawberry.ID, input: UpdatePostInput,
    ) -> Post:
        user = info.context["current_user"]
        post = await info.context["post_repo"].find_by_id(id)
        if post.author_id != user.id and user.role != UserRole.ADMIN:
            raise PermissionError("Not authorized")
        return await info.context["post_repo"].update(id, input)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def delete_user(self, info: Info, id: strawberry.ID) -> bool:
        return await info.context["user_repo"].delete(id)


# --- Subscription ---

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def post_created(self, info: Info) -> Post:
        async for post in info.context["pubsub"].subscribe("post:created"):
            yield post


# --- Schema ---

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
)


# --- FastAPI integration ---

from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI

async def get_context(request):
    user = await get_current_user(request)
    return {
        "current_user": user,
        "user_repo": UserRepository(),
        "post_repo": PostRepository(),
        "user_loader": UserDataLoader(),
        "post_loader": PostDataLoader(),
        "count_loader": CountDataLoader(),
        "pubsub": PubSub(),
    }

graphql_router = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI()
app.include_router(graphql_router, prefix="/graphql")
```

GraphQL patterns:
1. **Cursor pagination** — Relay-style `edges/nodes/pageInfo` for efficient infinite scroll
2. **DataLoaders** — batch and cache DB queries to solve N+1 problem on relations
3. **Permission classes** — `IsAuthenticated`/`IsAdmin` decorators on fields and mutations
4. **Input types** — separate `CreateInput`/`UpdateInput` with optional fields for partial updates
5. **Context injection** — pass repos, loaders, and current user via `context_getter`'''
    ),
    (
        "frontend/graphql-client",
        "Show GraphQL client patterns: queries, mutations, caching, and optimistic updates with React and urql.",
        '''GraphQL client patterns with React:

```typescript
// --- urql client setup ---

import {
  Client, Provider, cacheExchange, fetchExchange,
  subscriptionExchange,
} from "urql";
import { createClient as createWSClient } from "graphql-ws";

const wsClient = createWSClient({
  url: "ws://localhost:4000/graphql",
});

const client = new Client({
  url: "/graphql",
  exchanges: [
    cacheExchange,   // Normalized cache
    fetchExchange,
    subscriptionExchange({
      forwardSubscription: (operation) => ({
        subscribe: (sink) => ({
          unsubscribe: wsClient.subscribe(operation, sink),
        }),
      }),
    }),
  ],
  fetchOptions: () => ({
    headers: {
      Authorization: `Bearer ${getToken()}`,
    },
  }),
});

// <Provider value={client}><App /></Provider>


// --- Typed queries with codegen ---

// queries.graphql
/*
query GetPosts($first: Int!, $after: String, $filter: PostFilter) {
  posts(first: $first, after: $after, filter: $filter) {
    edges {
      cursor
      node {
        id
        title
        content
        published
        createdAt
        author {
          id
          name
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
    totalCount
  }
}

mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    id
    title
    content
    published
  }
}

mutation UpdatePost($id: ID!, $input: UpdatePostInput!) {
  updatePost(id: $id, input: $input) {
    id
    title
    content
    published
  }
}
*/


// --- React hooks ---

import { useQuery, useMutation, useSubscription } from "urql";

function PostList() {
  const [{ data, fetching, error }, reexecute] = useQuery({
    query: GET_POSTS,
    variables: { first: 20 },
  });

  if (fetching) return <Skeleton />;
  if (error) return <ErrorMessage error={error} />;

  return (
    <div>
      {data.posts.edges.map(({ node: post }) => (
        <PostCard key={post.id} post={post} />
      ))}
      {data.posts.pageInfo.hasNextPage && (
        <LoadMoreButton
          onClick={() => reexecute({
            variables: {
              first: 20,
              after: data.posts.pageInfo.endCursor,
            },
          })}
        />
      )}
    </div>
  );
}


// --- Mutation with optimistic update ---

function PostEditor({ post }) {
  const [result, updatePost] = useMutation(UPDATE_POST);

  const handlePublish = async () => {
    const { data, error } = await updatePost(
      {
        id: post.id,
        input: { published: true },
      },
      {
        // Optimistic update — show change immediately
        optimistic: {
          updatePost: () => ({
            __typename: "Post",
            id: post.id,
            published: true,
          }),
        },
      },
    );

    if (error) {
      toast.error("Failed to publish");
    }
  };

  return (
    <button onClick={handlePublish} disabled={result.fetching}>
      {result.fetching ? "Publishing..." : "Publish"}
    </button>
  );
}


// --- Subscription hook ---

function LiveNotifications() {
  const [{ data }] = useSubscription({
    query: `
      subscription {
        postCreated {
          id
          title
          author { name }
        }
      }
    `,
  });

  if (!data) return null;

  return (
    <Toast>
      New post: {data.postCreated.title} by {data.postCreated.author.name}
    </Toast>
  );
}


// --- Fragment colocation ---

// Each component owns its data requirements
const POST_CARD_FRAGMENT = `
  fragment PostCard on Post {
    id
    title
    content
    published
    createdAt
    author {
      id
      name
    }
  }
`;

// Parent query composes fragments
const GET_POSTS = `
  ${POST_CARD_FRAGMENT}
  query GetPosts($first: Int!) {
    posts(first: $first) {
      edges {
        node {
          ...PostCard
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;


// --- Error handling wrapper ---

function GraphQLErrorBoundary({ children }) {
  return (
    <ErrorBoundary
      fallback={({ error, resetErrorBoundary }) => (
        <div>
          <p>Something went wrong</p>
          <button onClick={resetErrorBoundary}>Retry</button>
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  );
}
```

GraphQL client patterns:
1. **Normalized cache** — `cacheExchange` deduplicates entities by `__typename` + `id`
2. **Cursor pagination** — `endCursor` + `hasNextPage` for infinite scroll without offset drift
3. **Optimistic updates** — show mutations instantly, rollback on error
4. **Fragment colocation** — each component declares its own data requirements
5. **Subscriptions** — real-time updates via `graphql-ws` WebSocket transport'''
    ),
]
