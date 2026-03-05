"""Neo4j/Graph databases — Cypher queries, graph data modeling, traversal patterns, path finding, recommendation queries, knowledge graphs."""

PAIRS = [
    (
        "databases/neo4j-cypher-queries",
        "Show advanced Cypher query patterns for Neo4j: complex MATCH clauses, MERGE for idempotent writes, UNWIND for batch operations, and aggregation with COLLECT.",
        '''Advanced Cypher query patterns for Neo4j:

```cypher
// === Complex MATCH patterns: multi-hop traversals ===

// Find users who purchased products also bought by their friends
MATCH (user:User {email: 'alice@example.com'})-[:FRIENDS_WITH]->(friend:User)
MATCH (friend)-[:PURCHASED]->(product:Product)<-[:PURCHASED]-(user)
WITH user, product, COLLECT(DISTINCT friend.name) AS mutual_buyers
WHERE SIZE(mutual_buyers) >= 2
RETURN product.name AS product,
       product.price AS price,
       mutual_buyers,
       SIZE(mutual_buyers) AS shared_count
ORDER BY shared_count DESC
LIMIT 10;


// === MERGE for idempotent upserts ===
// Create or update nodes and relationships atomically

// Upsert a user and their company relationship
MERGE (u:User {user_id: $userId})
ON CREATE SET
    u.email = $email,
    u.name = $name,
    u.created_at = datetime(),
    u.login_count = 1
ON MATCH SET
    u.last_seen = datetime(),
    u.login_count = u.login_count + 1

WITH u
MERGE (c:Company {domain: $companyDomain})
ON CREATE SET
    c.name = $companyName,
    c.created_at = datetime()

MERGE (u)-[r:WORKS_AT]->(c)
ON CREATE SET
    r.since = date($startDate),
    r.role = $role
ON MATCH SET
    r.role = $role,
    r.updated_at = datetime()

RETURN u, c, r;


// === UNWIND for batch operations ===
// Bulk import from a list of maps

UNWIND $events AS event
MATCH (u:User {user_id: event.userId})
MERGE (p:Product {sku: event.productSku})
ON CREATE SET
    p.name = event.productName,
    p.category = event.category,
    p.price = event.price

CREATE (u)-[a:VIEWED {
    timestamp: datetime(event.timestamp),
    session_id: event.sessionId,
    duration_sec: event.duration,
    source: event.source
}]->(p)

RETURN COUNT(a) AS events_created;


// === Advanced aggregation with COLLECT and map projection ===

// User activity summary with nested collections
MATCH (u:User)-[p:PURCHASED]->(product:Product)-[:IN_CATEGORY]->(cat:Category)
WHERE p.purchased_at > datetime() - duration({months: 3})
WITH u, cat,
     COLLECT({
         name: product.name,
         price: p.amount,
         date: p.purchased_at
     }) AS purchases,
     SUM(p.amount) AS category_spend
ORDER BY category_spend DESC
WITH u,
     COLLECT({
         category: cat.name,
         spend: category_spend,
         item_count: SIZE(purchases),
         top_item: purchases[0].name
     }) AS spending_by_category,
     SUM(category_spend) AS total_spend
RETURN u.name AS customer,
       u.email AS email,
       total_spend,
       spending_by_category[0].category AS top_category,
       spending_by_category,
       SIZE(spending_by_category) AS categories_shopped
ORDER BY total_spend DESC
LIMIT 50;


// === Conditional logic with CASE and COALESCE ===
MATCH (u:User)
OPTIONAL MATCH (u)-[p:PURCHASED]->(:Product)
WHERE p.purchased_at > datetime() - duration({days: 90})
WITH u, COUNT(p) AS recent_purchases, SUM(COALESCE(p.amount, 0)) AS recent_spend
RETURN u.name,
       recent_purchases,
       recent_spend,
       CASE
           WHEN recent_spend > 1000 THEN 'vip'
           WHEN recent_spend > 500 THEN 'active'
           WHEN recent_purchases > 0 THEN 'casual'
           ELSE 'dormant'
       END AS segment;


// === Subqueries with CALL {} for complex filtering ===
MATCH (u:User)
WHERE u.created_at > datetime() - duration({months: 6})

// Correlated subquery: check if user has high engagement
CALL {
    WITH u
    MATCH (u)-[r:VIEWED]->(p:Product)
    WHERE r.timestamp > datetime() - duration({days: 30})
    RETURN COUNT(r) AS view_count,
           COUNT(DISTINCT p) AS unique_products
}

// Another subquery: get latest purchase
CALL {
    WITH u
    MATCH (u)-[p:PURCHASED]->(prod:Product)
    RETURN p.purchased_at AS last_purchase, prod.name AS last_product
    ORDER BY p.purchased_at DESC
    LIMIT 1
}

WHERE view_count > 10
RETURN u.name, view_count, unique_products, last_purchase, last_product
ORDER BY view_count DESC;
```

Key patterns:
1. **MERGE for idempotency** -- ON CREATE / ON MATCH clauses handle first-time vs. repeat writes; always prefer MERGE over CREATE for entities that may already exist
2. **UNWIND batch imports** -- pass a parameter list (`$events`) and UNWIND to process thousands of records in a single transaction
3. **Map projections** -- `COLLECT({key: value})` builds nested JSON-like structures directly in Cypher; avoids post-processing
4. **CALL subqueries** -- correlated subqueries (`WITH u` inside CALL) let you compute per-node aggregations without flattening the entire result
5. **Parameterize everything** -- use `$param` syntax instead of string interpolation to prevent injection and enable query plan caching'''
    ),
    (
        "databases/neo4j-graph-data-modeling",
        "Explain Neo4j graph data modeling: node vs relationship properties, label design, index strategies, and common modeling patterns (tree, timeline, linked list).",
        '''Neo4j graph data modeling patterns and best practices:

```cypher
// === Schema design: labels, properties, relationships ===

// --- Constraint and index definitions ---
// Uniqueness constraints (also create indexes)
CREATE CONSTRAINT user_email_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.email IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order) REQUIRE o.order_id IS UNIQUE;

// Existence constraints (require property to be present)
CREATE CONSTRAINT user_email_exists IF NOT EXISTS
FOR (u:User) REQUIRE u.email IS NOT NULL;

// Composite index for frequent lookups
CREATE INDEX user_name_idx IF NOT EXISTS
FOR (u:User) ON (u.last_name, u.first_name);

// Full-text index for search
CREATE FULLTEXT INDEX product_search IF NOT EXISTS
FOR (p:Product) ON EACH [p.name, p.description, p.brand];

// Range index for date queries
CREATE RANGE INDEX order_date_idx IF NOT EXISTS
FOR (o:Order) ON (o.created_at);

// Relationship property index
CREATE INDEX reviewed_rating_idx IF NOT EXISTS
FOR ()-[r:REVIEWED]-() ON (r.rating);


// === Pattern: E-commerce domain model ===

// Create the core domain with proper relationship semantics
// Nodes represent entities; relationships represent verbs

// User places Order containing OrderLines for Products in Categories
CREATE (u:User:Customer {
    user_id: 'usr_001',
    email: 'alice@example.com',
    name: 'Alice Chen',
    created_at: datetime('2024-03-15'),
    tier: 'gold'
})

CREATE (o:Order {
    order_id: 'ord_10042',
    created_at: datetime('2025-12-01T14:30:00'),
    status: 'shipped',
    total: 159.97,
    currency: 'USD'
})

CREATE (p1:Product {
    sku: 'WIDGET-001',
    name: 'Premium Widget',
    price: 49.99,
    brand: 'WidgetCo'
})

CREATE (p2:Product {sku: 'GADGET-002', name: 'Smart Gadget', price: 109.98})

CREATE (cat:Category {name: 'Electronics', slug: 'electronics'})
CREATE (subcat:Category {name: 'Smart Home', slug: 'smart-home'})

// Relationships encode actions and context
CREATE (u)-[:PLACED {channel: 'web', ip: '192.168.1.1'}]->(o)
CREATE (o)-[:CONTAINS {quantity: 1, unit_price: 49.99}]->(p1)
CREATE (o)-[:CONTAINS {quantity: 1, unit_price: 109.98}]->(p2)
CREATE (p1)-[:IN_CATEGORY]->(subcat)
CREATE (p2)-[:IN_CATEGORY]->(subcat)
CREATE (subcat)-[:CHILD_OF]->(cat)
CREATE (u)-[:REVIEWED {rating: 5, text: 'Excellent quality', date: date('2025-12-10')}]->(p1);


// === Pattern: Tree / Hierarchy (category taxonomy) ===

// Query: full path from leaf to root
MATCH path = (leaf:Category {slug: 'smart-home'})-[:CHILD_OF*]->(root:Category)
WHERE NOT (root)-[:CHILD_OF]->()  // root has no parent
RETURN [node IN nodes(path) | node.name] AS category_path;
// Result: ['Smart Home', 'Electronics']

// Query: all descendants of a category
MATCH (parent:Category {slug: 'electronics'})<-[:CHILD_OF*0..]-(descendant:Category)
RETURN descendant.name, length(shortestPath(
    (parent)<-[:CHILD_OF*]-(descendant)
)) AS depth;


// === Pattern: Timeline / Event chain (linked list) ===

// Each event points to the next via :NEXT
MATCH (u:User {user_id: 'usr_001'})
CREATE (u)-[:LATEST_EVENT]->(e3:Event {
    type: 'purchase', timestamp: datetime(), data: 'ord_10042'
})
CREATE (e3)-[:NEXT]->(e2:Event {
    type: 'add_to_cart', timestamp: datetime() - duration({minutes: 5})
})
CREATE (e2)-[:NEXT]->(e1:Event {
    type: 'page_view', timestamp: datetime() - duration({minutes: 15})
});

// Query recent events for a user (traverse linked list)
MATCH (u:User {user_id: 'usr_001'})-[:LATEST_EVENT]->(latest:Event)
MATCH path = (latest)-[:NEXT*0..9]->(event:Event)
RETURN event.type, event.timestamp, event.data
ORDER BY event.timestamp DESC;


// === Pattern: Bi-temporal modeling ===
// Track both "valid time" (real world) and "transaction time" (when recorded)

CREATE (emp:Employee {employee_id: 'emp_042', name: 'Bob Smith'})
CREATE (dept:Department {name: 'Engineering'})
CREATE (emp)-[:BELONGS_TO {
    valid_from: date('2024-01-15'),
    valid_to: date('9999-12-31'),     // open-ended = current
    recorded_at: datetime(),
    recorded_by: 'hr_system'
}]->(dept);

// Query: who was in Engineering on a specific date?
MATCH (emp:Employee)-[r:BELONGS_TO]->(d:Department {name: 'Engineering'})
WHERE r.valid_from <= date('2025-06-01') AND r.valid_to >= date('2025-06-01')
RETURN emp.name, r.valid_from, r.valid_to;


// === Anti-patterns to avoid ===

// BAD: encoding relationship type in a property
// CREATE (a)-[:RELATES_TO {type: 'friend'}]->(b)

// GOOD: use distinct relationship types
// CREATE (a)-[:FRIENDS_WITH]->(b)

// BAD: deeply nested properties (treat graph as document store)
// CREATE (u:User {address_street: '...', address_city: '...', ...})

// GOOD: model address as separate node when shared/queried independently
// CREATE (u:User)-[:LIVES_AT]->(a:Address {street: '...', city: '...'})
```

Key patterns:
1. **Nodes = nouns, relationships = verbs** -- users PLACE orders, orders CONTAIN products; relationship types should be meaningful verbs
2. **Properties on relationships** -- quantity, rating, timestamps belong on relationships; they describe the connection, not the entity
3. **Multiple labels** -- `(:User:Customer)` enables both general User queries and specific Customer queries without duplication
4. **Hierarchy traversal** -- `[:CHILD_OF*0..]` with variable-length paths handles arbitrary depth; `shortestPath()` avoids cycles
5. **Index strategy** -- unique constraints double as indexes; use composite indexes for multi-property lookups, full-text for search, range for date filters'''
    ),
    (
        "databases/neo4j-path-finding",
        "Demonstrate Neo4j path finding algorithms: shortest path, all shortest paths, Dijkstra weighted paths, and graph projection with GDS library.",
        '''Neo4j path finding from built-in Cypher to GDS library algorithms:

```cypher
// === Built-in Cypher path finding ===

// 1. Shortest path between two nodes (unweighted, BFS)
MATCH (start:User {name: 'Alice'}), (end:User {name: 'Dave'})
MATCH path = shortestPath((start)-[:FRIENDS_WITH*..10]-(end))
RETURN path,
       length(path) AS hops,
       [node IN nodes(path) | node.name] AS path_names,
       [rel IN relationships(path) | type(rel)] AS rel_types;


// 2. All shortest paths (same length, different routes)
MATCH (start:City {name: 'New York'}), (end:City {name: 'Los Angeles'})
MATCH paths = allShortestPaths((start)-[:CONNECTED_TO*..15]-(end))
RETURN [node IN nodes(paths) | node.name] AS route,
       length(paths) AS stops,
       REDUCE(dist = 0, r IN relationships(paths) |
           dist + r.distance_km
       ) AS total_distance_km
ORDER BY total_distance_km
LIMIT 5;


// 3. Variable-length path with filtering
// Find all paths between two users through trusted connections only
MATCH path = (a:User {name: 'Alice'})-[:FRIENDS_WITH*1..6]-(b:User {name: 'Eve'})
WHERE ALL(r IN relationships(path) WHERE r.trust_score > 0.7)
  AND ALL(n IN nodes(path) WHERE n.active = true)
  AND length(path) = SIZE(
      apoc.coll.toSet([n IN nodes(path) | id(n)])
  )  // no repeated nodes
RETURN path, length(path) AS hops,
       REDUCE(trust = 1.0, r IN relationships(path) |
           trust * r.trust_score
       ) AS chain_trust
ORDER BY chain_trust DESC
LIMIT 10;


// === GDS (Graph Data Science) library algorithms ===

// Step 1: Create a graph projection (in-memory subgraph)
CALL gds.graph.project(
    'social-network',                     // projection name
    ['User'],                             // node labels
    {
        FRIENDS_WITH: {
            type: 'FRIENDS_WITH',
            orientation: 'UNDIRECTED',    // treat as undirected
            properties: ['trust_score']   // include as weight
        },
        FOLLOWS: {
            type: 'FOLLOWS',
            orientation: 'NATURAL'        // directed
        }
    },
    {
        nodeProperties: ['age', 'active'],
        readConcurrency: 4
    }
)
YIELD graphName, nodeCount, relationshipCount;


// Step 2: Dijkstra's shortest path (weighted)
MATCH (source:User {name: 'Alice'}), (target:User {name: 'Frank'})
CALL gds.shortestPath.dijkstra.stream('social-network', {
    sourceNode: source,
    targetNode: target,
    relationshipWeightProperty: 'trust_score'
})
YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs, path
RETURN
    [nodeId IN nodeIds | gds.util.asNode(nodeId).name] AS route,
    totalCost AS total_weight,
    costs AS cumulative_costs,
    SIZE(nodeIds) AS hop_count;


// Step 3: A* shortest path (with heuristic for geo-located nodes)
MATCH (source:City {name: 'New York'}), (target:City {name: 'San Francisco'})
CALL gds.shortestPath.astar.stream('city-network', {
    sourceNode: source,
    targetNode: target,
    relationshipWeightProperty: 'distance_km',
    latitudeProperty: 'latitude',
    longitudeProperty: 'longitude'
})
YIELD totalCost, nodeIds
RETURN totalCost AS distance_km,
       [nId IN nodeIds | gds.util.asNode(nId).name] AS route;


// Step 4: Yen's K-shortest paths (find alternatives)
MATCH (source:City {name: 'New York'}), (target:City {name: 'Los Angeles'})
CALL gds.shortestPath.yens.stream('city-network', {
    sourceNode: source,
    targetNode: target,
    relationshipWeightProperty: 'distance_km',
    k: 5  // find top 5 shortest paths
})
YIELD index, totalCost, nodeIds
RETURN index + 1 AS rank,
       ROUND(totalCost, 1) AS distance_km,
       [nId IN nodeIds | gds.util.asNode(nId).name] AS route;


// Step 5: Community detection (Louvain)
CALL gds.louvain.stream('social-network', {
    relationshipWeightProperty: 'trust_score'
})
YIELD nodeId, communityId
WITH communityId, COLLECT(gds.util.asNode(nodeId).name) AS members
RETURN communityId,
       SIZE(members) AS community_size,
       members[0..5] AS sample_members
ORDER BY community_size DESC
LIMIT 20;


// Step 6: PageRank for influence scoring
CALL gds.pageRank.stream('social-network', {
    maxIterations: 20,
    dampingFactor: 0.85,
    relationshipWeightProperty: 'trust_score'
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS user, score
SET user.pagerank = score
RETURN user.name, ROUND(score, 4) AS influence_score
ORDER BY score DESC
LIMIT 20;


// Step 7: Clean up projection when done
CALL gds.graph.drop('social-network') YIELD graphName;
```

Key patterns:
1. **shortestPath() vs GDS** -- built-in `shortestPath()` is fine for single queries; GDS projections are needed for batch analytics across the whole graph
2. **Graph projections** -- `gds.graph.project()` creates an in-memory copy optimized for algorithms; always drop when done to free memory
3. **Weight properties** -- Dijkstra/A* use `relationshipWeightProperty`; without it, all edges are treated as cost 1
4. **K-shortest paths** -- Yen's algorithm finds alternative routes; essential for routing, supply chain, and network resilience analysis
5. **Write-back** -- use `.mutate` mode to add computed properties (pagerank, communityId) back to the projection, then `.write` to persist to the database'''
    ),
    (
        "databases/neo4j-recommendation-queries",
        "Build recommendation engines with Neo4j: collaborative filtering, content-based similarity, hybrid recommendations, and real-time personalization.",
        '''Neo4j recommendation engine patterns:

```cypher
// === 1. Collaborative filtering: "users who bought X also bought Y" ===

// Find products frequently co-purchased with items in user's cart
MATCH (me:User {user_id: $userId})-[:PURCHASED]->(my_product:Product)
MATCH (other:User)-[:PURCHASED]->(my_product)
WHERE other <> me
MATCH (other)-[:PURCHASED]->(rec:Product)
WHERE NOT (me)-[:PURCHASED]->(rec)
  AND NOT (me)-[:WISHLISTED]->(rec)  // exclude already seen

WITH rec,
     COUNT(DISTINCT other) AS co_purchasers,
     COLLECT(DISTINCT my_product.name)[0..3] AS because_you_bought

// Weight by recency: recent co-purchases count more
WHERE co_purchasers >= 3
RETURN rec.name AS recommendation,
       rec.sku,
       rec.price,
       co_purchasers AS score,
       because_you_bought
ORDER BY score DESC
LIMIT 20;


// === 2. Content-based: similar products by shared attributes ===

MATCH (target:Product {sku: $productSku})

// Find products sharing multiple attributes
MATCH (target)-[:IN_CATEGORY]->(cat:Category)<-[:IN_CATEGORY]-(similar:Product)
WHERE similar <> target

OPTIONAL MATCH (target)-[:HAS_TAG]->(tag:Tag)<-[:HAS_TAG]-(similar)
OPTIONAL MATCH (target)-[:MADE_BY]->(brand:Brand)<-[:MADE_BY]-(similar)

WITH similar, target,
     COUNT(DISTINCT cat) AS shared_categories,
     COUNT(DISTINCT tag) AS shared_tags,
     CASE WHEN COUNT(DISTINCT brand) > 0 THEN 1 ELSE 0 END AS same_brand,
     ABS(similar.price - target.price) / target.price AS price_diff_ratio

// Weighted similarity score
WITH similar,
     (shared_categories * 3.0 +
      shared_tags * 2.0 +
      same_brand * 1.5 +
      CASE WHEN price_diff_ratio < 0.2 THEN 2.0
           WHEN price_diff_ratio < 0.5 THEN 1.0
           ELSE 0 END
     ) AS similarity_score,
     shared_categories, shared_tags

WHERE similarity_score > 3
RETURN similar.name AS product,
       similar.sku,
       similar.price,
       ROUND(similarity_score, 2) AS score,
       shared_categories,
       shared_tags
ORDER BY score DESC
LIMIT 10;


// === 3. Hybrid: combine collaborative + content + social signals ===

MATCH (me:User {user_id: $userId})

// Collaborative signal: what similar users purchased
OPTIONAL MATCH (me)-[:PURCHASED]->(mp:Product)<-[:PURCHASED]-(peer:User)
OPTIONAL MATCH (peer)-[:PURCHASED]->(collab_rec:Product)
WHERE NOT (me)-[:PURCHASED]->(collab_rec)

// Social signal: what friends recommend
OPTIONAL MATCH (me)-[:FRIENDS_WITH]->(friend:User)
OPTIONAL MATCH (friend)-[:REVIEWED {rating: 5}]->(social_rec:Product)
WHERE NOT (me)-[:PURCHASED]->(social_rec)

// Content signal: products similar to highly rated ones
OPTIONAL MATCH (me)-[r:REVIEWED]->(liked:Product)
WHERE r.rating >= 4
OPTIONAL MATCH (liked)-[:IN_CATEGORY]->(cat:Category)<-[:IN_CATEGORY]-(content_rec:Product)
WHERE NOT (me)-[:PURCHASED]->(content_rec)

// Combine all signals into a unified score
WITH me,
     COLLECT(DISTINCT {
         product: collab_rec,
         source: 'collaborative',
         weight: 1.0
     }) + COLLECT(DISTINCT {
         product: social_rec,
         source: 'social',
         weight: 1.5
     }) + COLLECT(DISTINCT {
         product: content_rec,
         source: 'content',
         weight: 0.8
     }) AS all_recs

UNWIND all_recs AS rec
WHERE rec.product IS NOT NULL

WITH rec.product AS product,
     SUM(rec.weight) AS combined_score,
     COLLECT(DISTINCT rec.source) AS signal_sources

// Boost new arrivals and trending products
OPTIONAL MATCH (product)<-[r:PURCHASED]-(anyone:User)
WHERE r.purchased_at > datetime() - duration({days: 7})
WITH product, combined_score, signal_sources,
     COUNT(r) AS recent_purchases,
     combined_score + (CASE WHEN COUNT(r) > 10 THEN 2.0 ELSE 0 END) +
     (CASE WHEN product.created_at > datetime() - duration({days: 30})
           THEN 1.0 ELSE 0 END) AS final_score

RETURN product.name AS recommendation,
       product.sku,
       product.price,
       ROUND(final_score, 2) AS score,
       signal_sources,
       recent_purchases AS trending_signal
ORDER BY final_score DESC
LIMIT 15;


// === 4. Real-time personalization: context-aware recommendations ===

// Recommend based on current browsing session + user profile
MATCH (me:User {user_id: $userId})

// Current session context (last 5 views)
MATCH (me)-[v:VIEWED]->(recent:Product)
WHERE v.timestamp > datetime() - duration({minutes: 30})
WITH me, COLLECT(recent) AS session_products
ORDER BY v.timestamp DESC
LIMIT 5

// Extract session intent (most common category in session)
UNWIND session_products AS sp
MATCH (sp)-[:IN_CATEGORY]->(cat:Category)
WITH me, session_products, cat, COUNT(*) AS cat_frequency
ORDER BY cat_frequency DESC
LIMIT 1

// Recommend within inferred category, boosted by user's preferences
WITH me, cat AS intent_category, session_products
MATCH (intent_category)<-[:IN_CATEGORY]-(rec:Product)
WHERE NOT rec IN session_products
  AND NOT (me)-[:PURCHASED]->(rec)

// Factor in ratings from similar users
OPTIONAL MATCH (rec)<-[r:REVIEWED]-(reviewer:User)
WITH me, rec, intent_category,
     AVG(r.rating) AS avg_rating,
     COUNT(r) AS review_count

WHERE avg_rating IS NULL OR avg_rating >= 3.5
RETURN rec.name AS product,
       rec.sku,
       rec.price,
       intent_category.name AS inferred_intent,
       COALESCE(ROUND(avg_rating, 1), 0) AS avg_rating,
       review_count,
       // Score combines relevance + quality + popularity
       ROUND(
           COALESCE(avg_rating, 3.5) * 2 +
           LOG(review_count + 1) +
           CASE WHEN rec.price < 50 THEN 1 ELSE 0 END,
           2
       ) AS score
ORDER BY score DESC
LIMIT 10;
```

Key patterns:
1. **Collaborative filtering** -- traverse 2-hop paths (me -> product <- other_user -> recommendation); filter by co-purchaser threshold
2. **Content-based similarity** -- count shared categories, tags, brands; weight each signal; normalize price difference as a feature
3. **Hybrid scoring** -- combine multiple signal sources with weights; use COLLECT + UNWIND to merge heterogeneous recommendation lists
4. **Session intent** -- analyze last N viewed products to infer category intent; recommend within that category for relevance
5. **Popularity decay** -- boost recently purchased or newly added products; use LOG(count) to dampen runaway popularity effects'''
    ),
    (
        "databases/neo4j-knowledge-graphs",
        "Build a knowledge graph with Neo4j: ontology modeling, entity resolution, inference queries, and graph-powered RAG (retrieval-augmented generation).",
        '''Knowledge graph construction and querying with Neo4j:

```cypher
// === 1. Ontology / Schema layer ===
// Define the knowledge graph schema as nodes/relationships

// Entity types (ontology classes)
CREATE (:OntologyClass {name: 'Person', description: 'A human individual'})
CREATE (:OntologyClass {name: 'Organization', description: 'A company or institution'})
CREATE (:OntologyClass {name: 'Technology', description: 'A technology, framework, or tool'})
CREATE (:OntologyClass {name: 'Concept', description: 'An abstract concept or topic'})
CREATE (:OntologyClass {name: 'Document', description: 'A document, article, or paper'})

// Relationship types (ontology properties)
MATCH (person:OntologyClass {name: 'Person'}),
      (org:OntologyClass {name: 'Organization'}),
      (tech:OntologyClass {name: 'Technology'}),
      (concept:OntologyClass {name: 'Concept'}),
      (doc:OntologyClass {name: 'Document'})

CREATE (person)-[:HAS_RELATION {name: 'WORKS_AT', inverse: 'EMPLOYS'}]->(org)
CREATE (person)-[:HAS_RELATION {name: 'KNOWS', inverse: 'KNOWN_BY'}]->(tech)
CREATE (tech)-[:HAS_RELATION {name: 'IMPLEMENTS', inverse: 'IMPLEMENTED_BY'}]->(concept)
CREATE (doc)-[:HAS_RELATION {name: 'MENTIONS', inverse: 'MENTIONED_IN'}]->(person)
CREATE (doc)-[:HAS_RELATION {name: 'COVERS', inverse: 'COVERED_BY'}]->(concept);


// === 2. Entity resolution: merge duplicate entities ===

// Create a staging area for raw extracted entities
UNWIND $extractedEntities AS entity
MERGE (e:RawEntity {text: entity.text, source: entity.source})
SET e.entity_type = entity.type,
    e.confidence = entity.confidence,
    e.context = entity.context;

// Entity resolution: fuzzy matching + graph-based disambiguation
MATCH (raw:RawEntity)
WHERE raw.resolved = false OR raw.resolved IS NULL

// Find candidate matches using full-text search
CALL db.index.fulltext.queryNodes('entity_search', raw.text + '~')
YIELD node AS candidate, score
WHERE score > 0.8
  AND labels(candidate) <> ['RawEntity']  // skip other raw entities

WITH raw, candidate, score
ORDER BY score DESC
LIMIT 1

// Link raw entity to resolved entity
MERGE (raw)-[:RESOLVED_TO {
    score: score,
    method: 'fulltext_fuzzy',
    resolved_at: datetime()
}]->(candidate)
SET raw.resolved = true

RETURN raw.text, labels(candidate)[0] AS matched_type,
       candidate.name AS resolved_name, score;


// === 3. Knowledge extraction: populate from documents ===

// Batch import extracted triples (subject, predicate, object)
UNWIND $triples AS triple

// Resolve or create subject
MERGE (subj {name: triple.subject})
ON CREATE SET subj:Entity,
    subj.first_seen = datetime(),
    subj.source_count = 1
ON MATCH SET
    subj.source_count = subj.source_count + 1

// Resolve or create object
MERGE (obj {name: triple.object})
ON CREATE SET obj:Entity,
    obj.first_seen = datetime(),
    obj.source_count = 1
ON MATCH SET
    obj.source_count = obj.source_count + 1

// Create the relationship with provenance
WITH subj, obj, triple
CALL apoc.create.relationship(subj, triple.predicate, {
    confidence: triple.confidence,
    source_doc: triple.source,
    extracted_at: datetime(),
    context: triple.context_sentence
}, obj)
YIELD rel
RETURN COUNT(rel) AS triples_created;


// === 4. Inference queries: derive new knowledge ===

// Transitive inference: if A works_at B and B is_subsidiary_of C,
// then A indirectly works for C
MATCH (person:Person)-[:WORKS_AT]->(subsidiary:Organization)
      -[:SUBSIDIARY_OF*1..3]->(parent:Organization)
WHERE NOT (person)-[:WORKS_AT]->(parent)
MERGE (person)-[:INDIRECTLY_EMPLOYED_BY {
    inferred: true,
    hops: length(shortestPath(
        (subsidiary)-[:SUBSIDIARY_OF*]->(parent)
    )),
    inferred_at: datetime()
}]->(parent);


// Expertise inference: if person authored documents about topic X,
// they likely have expertise in X
MATCH (p:Person)-[:AUTHORED]->(d:Document)-[:COVERS]->(c:Concept)
WITH p, c, COUNT(d) AS doc_count, COLLECT(d.title) AS papers
WHERE doc_count >= 3
MERGE (p)-[e:HAS_EXPERTISE]->(c)
SET e.confidence = CASE
        WHEN doc_count >= 10 THEN 'high'
        WHEN doc_count >= 5 THEN 'medium'
        ELSE 'emerging'
    END,
    e.evidence_count = doc_count,
    e.sample_papers = papers[0..3],
    e.inferred_at = datetime()
RETURN p.name, c.name, e.confidence, doc_count;


// === 5. Graph-powered RAG: retrieve context for LLM queries ===

// Given a user question, find relevant subgraph for context
// Step 1: Extract key entities from the question (done externally)
// Step 2: Expand neighborhood around matched entities

UNWIND $questionEntities AS entityName
MATCH (e {name: entityName})

// Get 2-hop neighborhood
CALL {
    WITH e
    MATCH path = (e)-[*1..2]-(neighbor)
    WHERE neighbor <> e
    RETURN path, neighbor
    LIMIT 50
}

// Collect all facts as natural language triples
WITH e, neighbor, relationships(path) AS rels
UNWIND rels AS r
WITH startNode(r) AS from_node, endNode(r) AS to_node, type(r) AS rel_type,
     properties(r) AS rel_props
RETURN DISTINCT
    from_node.name AS subject,
    rel_type AS predicate,
    to_node.name AS object,
    rel_props.confidence AS confidence,
    rel_props.context AS source_context
ORDER BY confidence DESC
LIMIT 100;


// === 6. Query: multi-hop reasoning ===

// "What technologies are used by companies where AI researchers work?"
MATCH (p:Person)-[:HAS_EXPERTISE]->(:Concept {name: 'Artificial Intelligence'})
MATCH (p)-[:WORKS_AT]->(org:Organization)
MATCH (org)-[:USES]->(tech:Technology)
WITH tech, COLLECT(DISTINCT org.name) AS companies,
     COLLECT(DISTINCT p.name) AS researchers
RETURN tech.name AS technology,
       SIZE(companies) AS company_count,
       companies[0..5] AS sample_companies,
       SIZE(researchers) AS researcher_count
ORDER BY company_count DESC;


// "Trace the provenance of a fact"
MATCH (p:Person {name: 'Dr. Smith'})-[e:HAS_EXPERTISE]->(c:Concept {name: 'NLP'})
MATCH (p)-[:AUTHORED]->(d:Document)-[:COVERS]->(c)
RETURN p.name AS expert,
       c.name AS expertise,
       e.confidence AS confidence_level,
       e.evidence_count AS supporting_documents,
       COLLECT(d.title) AS evidence_papers;
```

Key patterns:
1. **Ontology as graph** -- schema itself lives in the graph as OntologyClass nodes; enables meta-queries about the schema
2. **Entity resolution** -- use full-text fuzzy matching + confidence scoring to deduplicate extracted entities before linking
3. **Provenance tracking** -- every relationship stores source, confidence, extraction timestamp; enables fact auditing and trust scoring
4. **Inference rules** -- transitive closure (SUBSIDIARY_OF*) and co-occurrence patterns create new relationships marked `inferred: true`
5. **RAG context retrieval** -- expand 2-hop neighborhood around question entities, return as (subject, predicate, object) triples for LLM prompt context'''
    ),
]
