"""Neo4j graph database — Cypher queries, data modeling, graph algorithms, and Python integration."""

PAIRS = [
    (
        "databases/neo4j-cypher",
        "Show Neo4j Cypher query patterns: MATCH, MERGE, path traversal, and advanced filtering.",
        '''Neo4j Cypher query language patterns:

```cypher
// === MATCH: Pattern matching and reading ===

// Basic node and relationship matching
MATCH (p:Person {name: 'Alice'})-[:FRIENDS_WITH]->(friend:Person)
RETURN friend.name, friend.age
ORDER BY friend.name;

// Multi-hop traversal (friends of friends)
MATCH (p:Person {name: 'Alice'})-[:FRIENDS_WITH*2]->(fof:Person)
WHERE fof <> p  // Exclude self
RETURN DISTINCT fof.name AS friend_of_friend;

// Variable-length path (1 to 5 hops)
MATCH path = (start:Person {name: 'Alice'})-[:FRIENDS_WITH*1..5]->(end:Person)
WHERE end.name = 'Zara'
RETURN path, length(path) AS hops
ORDER BY hops
LIMIT 1;

// Pattern with relationship properties
MATCH (p:Person)-[r:WORKS_AT {role: 'Engineer'}]->(c:Company)
WHERE r.since >= date('2020-01-01')
RETURN p.name, c.name, r.role, r.since;

// Optional match (LEFT JOIN equivalent)
MATCH (p:Person)
OPTIONAL MATCH (p)-[:HAS_ADDRESS]->(a:Address)
RETURN p.name, a.city, a.country;

// Multiple patterns in one MATCH
MATCH (p:Person)-[:WORKS_AT]->(c:Company),
      (p)-[:LIVES_IN]->(city:City)
WHERE c.industry = 'Technology'
RETURN p.name, c.name AS company, city.name AS city;


// === WHERE: Advanced filtering ===

// String matching
MATCH (p:Person)
WHERE p.name STARTS WITH 'A'
   OR p.name CONTAINS 'son'
   OR p.email =~ '.*@gmail\\.com'   // Regex
RETURN p.name;

// List predicates
MATCH (p:Person)
WHERE p.skills IS NOT NULL
  AND ANY(skill IN p.skills WHERE skill IN ['Python', 'Rust'])
  AND SIZE(p.skills) >= 3
RETURN p.name, p.skills;

// EXISTS subquery
MATCH (p:Person)
WHERE EXISTS {
    MATCH (p)-[:PUBLISHED]->(article:Article)
    WHERE article.citations > 100
}
RETURN p.name AS prolific_author;

// NOT EXISTS (people with no orders)
MATCH (c:Customer)
WHERE NOT EXISTS {
    MATCH (c)-[:PLACED]->(o:Order)
    WHERE o.date >= date() - duration({months: 6})
}
RETURN c.name AS inactive_customer;
```

```cypher
// === CREATE, MERGE, SET, DELETE ===

// CREATE: always creates new nodes/relationships
CREATE (p:Person {
    name: 'Bob',
    age: 30,
    email: 'bob@example.com',
    skills: ['Python', 'Neo4j'],
    created_at: datetime()
})
RETURN p;

// MERGE: create if not exists, match if exists (idempotent)
MERGE (p:Person {email: 'bob@example.com'})
ON CREATE SET
    p.name = 'Bob',
    p.created_at = datetime()
ON MATCH SET
    p.last_seen = datetime(),
    p.login_count = COALESCE(p.login_count, 0) + 1
RETURN p;

// MERGE relationship
MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'})
MERGE (a)-[r:FRIENDS_WITH]->(b)
ON CREATE SET r.since = date()
RETURN r;


// === Aggregation and COLLECT ===

// Group by with aggregation
MATCH (p:Person)-[:WORKS_AT]->(c:Company)
WITH c, COUNT(p) AS employee_count, COLLECT(p.name) AS employees
WHERE employee_count >= 5
RETURN c.name, employee_count, employees
ORDER BY employee_count DESC;

// WITH for pipeline-style queries (subquery results)
MATCH (p:Person)-[:PUBLISHED]->(a:Article)
WITH p, COUNT(a) AS article_count, AVG(a.citations) AS avg_citations
WHERE article_count >= 3
MATCH (p)-[:WORKS_AT]->(c:Company)
RETURN p.name, article_count, avg_citations, c.name AS company
ORDER BY avg_citations DESC;

// UNWIND: expand list into rows
WITH ['Python', 'Java', 'Rust', 'Go'] AS languages
UNWIND languages AS lang
MATCH (p:Person)
WHERE lang IN p.skills
RETURN lang, COUNT(p) AS developers
ORDER BY developers DESC;


// === Path queries ===

// Shortest path
MATCH path = shortestPath(
    (a:Person {name: 'Alice'})-[:FRIENDS_WITH*..10]->(b:Person {name: 'Zara'})
)
RETURN [n IN nodes(path) | n.name] AS names,
       length(path) AS distance;

// All shortest paths
MATCH path = allShortestPaths(
    (a:Person {name: 'Alice'})-[:FRIENDS_WITH*..10]->(b:Person {name: 'Zara'})
)
RETURN [n IN nodes(path) | n.name] AS route,
       length(path) AS hops;

// Path with filters on intermediate nodes
MATCH path = (start:City {name: 'New York'})-[:CONNECTED_TO*1..5]->(end:City {name: 'Tokyo'})
WHERE ALL(r IN relationships(path) WHERE r.active = true)
  AND ALL(n IN nodes(path) WHERE n.population > 100000)
RETURN [n IN nodes(path) | n.name] AS route,
       REDUCE(cost = 0, r IN relationships(path) | cost + r.distance) AS total_distance
ORDER BY total_distance
LIMIT 5;
```

```cypher
// === CALL subqueries and FOREACH ===

// CALL subquery for complex operations
MATCH (c:Company {name: 'TechCorp'})
CALL {
    WITH c
    MATCH (c)<-[:WORKS_AT]-(p:Person)
    RETURN COUNT(p) AS emp_count, AVG(p.salary) AS avg_salary
}
RETURN c.name, emp_count, avg_salary;

// CALL IN TRANSACTIONS for large batch operations
CALL {
    MATCH (p:Person)
    WHERE p.last_active < datetime() - duration({days: 365})
    WITH p LIMIT 1000
    SET p.status = 'inactive'
    RETURN COUNT(*) AS updated
} IN TRANSACTIONS OF 500 ROWS
RETURN updated;

// FOREACH for conditional side effects
MATCH path = shortestPath(
    (a:Person {name: 'Alice'})-[:KNOWS*]->(b:Person {name: 'Bob'})
)
FOREACH (n IN nodes(path) |
    SET n.on_path = true
);

// CASE expressions
MATCH (p:Person)
RETURN p.name,
    CASE
        WHEN p.age < 18 THEN 'minor'
        WHEN p.age < 65 THEN 'adult'
        ELSE 'senior'
    END AS age_group,
    CASE p.status
        WHEN 'active' THEN 1
        WHEN 'inactive' THEN 0
        ELSE -1
    END AS status_code;

// Index creation for performance
CREATE INDEX person_email IF NOT EXISTS FOR (p:Person) ON (p.email);
CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name);
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
    FOR (p:Person) REQUIRE p.email IS UNIQUE;

// Composite index
CREATE INDEX company_industry_size IF NOT EXISTS
    FOR (c:Company) ON (c.industry, c.size);

// Full-text index
CREATE FULLTEXT INDEX article_search IF NOT EXISTS
    FOR (a:Article) ON EACH [a.title, a.content];

// Use full-text index
CALL db.index.fulltext.queryNodes('article_search', 'graph database')
YIELD node, score
RETURN node.title, score
ORDER BY score DESC
LIMIT 10;
```

Key Cypher patterns:

| Operation | Syntax | Use Case |
|---|---|---|
| MATCH | (a)-[r:TYPE]->(b) | Read patterns from graph |
| MERGE | Like MATCH + CREATE | Idempotent writes |
| WITH | Pipeline results | Chain query stages |
| shortestPath | shortestPath((a)-[*]-(b)) | Shortest connection |
| COLLECT | COLLECT(node.prop) | Aggregate into lists |
| UNWIND | UNWIND list AS item | Expand lists to rows |
| EXISTS {} | Subquery existence | Correlated filtering |

1. **MERGE for idempotent writes** -- ON CREATE / ON MATCH for conditional updates
2. **WITH for query pipelining** -- filter and transform between stages
3. **Variable-length paths** -- [:TYPE*1..5] for bounded traversal
4. **CALL IN TRANSACTIONS** -- batch large writes to avoid memory issues
5. **Index everything you MATCH on** -- label + property indexes for fast lookups'''
    ),
    (
        "databases/neo4j-modeling",
        "Explain graph data modeling in Neo4j: nodes, relationships, properties, and modeling patterns.",
        '''Graph data modeling patterns in Neo4j:

```cypher
// === Core modeling principles ===

// Principle 1: Relationships are first-class citizens
// BAD: Storing relationships as properties
// (:Person {friends: ['Alice', 'Bob']})

// GOOD: Explicit relationship edges
// (:Person)-[:FRIENDS_WITH {since: date()}]->(:Person)


// Principle 2: Model for your queries (not for normalization)

// === E-commerce domain model ===

// Customer places orders containing products
CREATE (customer:Customer {
    customer_id: 'CUST-001',
    name: 'Alice Smith',
    email: 'alice@example.com',
    created_at: datetime()
})

CREATE (order:Order {
    order_id: 'ORD-001',
    placed_at: datetime(),
    status: 'delivered',
    total: 249.99
})

CREATE (product:Product {
    product_id: 'PROD-001',
    name: 'Wireless Headphones',
    price: 79.99,
    category: 'Electronics'
})

CREATE (category:Category {
    name: 'Electronics',
    slug: 'electronics'
})

// Relationships with properties
CREATE (customer)-[:PLACED {channel: 'web'}]->(order)
CREATE (order)-[:CONTAINS {quantity: 2, unit_price: 79.99}]->(product)
CREATE (product)-[:BELONGS_TO]->(category)
CREATE (customer)-[:REVIEWED {
    rating: 5, text: 'Great sound quality!', date: date()
}]->(product)
CREATE (customer)-[:LIVES_IN]->(address:Address {
    street: '123 Main St', city: 'Portland', state: 'OR', zip: '97201'
})


// === Social network model ===

// Users follow users, post content, join groups
CREATE (user1:User {username: 'alice', name: 'Alice'}),
       (user2:User {username: 'bob', name: 'Bob'}),
       (post1:Post {content: 'Hello world!', created_at: datetime()}),
       (group1:Group {name: 'Graph Enthusiasts', created_at: date()})

CREATE (user1)-[:FOLLOWS {since: date()}]->(user2)
CREATE (user2)-[:FOLLOWS {since: date()}]->(user1)
CREATE (user1)-[:PUBLISHED]->(post1)
CREATE (user2)-[:LIKED {at: datetime()}]->(post1)
CREATE (user1)-[:MEMBER_OF {role: 'admin', joined: date()}]->(group1)
CREATE (user2)-[:MEMBER_OF {role: 'member', joined: date()}]->(group1)
CREATE (post1)-[:TAGGED_WITH]->(:Tag {name: 'introduction'})
```

```cypher
// === Advanced modeling patterns ===

// Pattern 1: Intermediate nodes for rich relationships
// Instead of: (a)-[:EMPLOYED_AT {role, dept, salary, start, end}]->(c)
// Use intermediate node when relationship has many properties:

CREATE (p:Person {name: 'Alice'})
CREATE (c:Company {name: 'TechCorp'})
CREATE (position:Position {
    title: 'Senior Engineer',
    department: 'Backend',
    salary: 150000,
    start_date: date('2022-01-15'),
    end_date: null
})
CREATE (p)-[:HOLDS]->(position)-[:AT]->(c);

// Enables queries like:
// "Find all positions at TechCorp with salary > 100k"
// MATCH (pos:Position)-[:AT]->(c:Company {name: 'TechCorp'})
// WHERE pos.salary > 100000


// Pattern 2: Temporal modeling with relationship versioning
// Track state changes over time

CREATE (account:Account {id: 'ACC-001'})
CREATE (plan1:Plan {name: 'Basic', price: 9.99})
CREATE (plan2:Plan {name: 'Pro', price: 29.99})

CREATE (account)-[:SUBSCRIBED_TO {
    from: date('2024-01-01'),
    to: date('2024-06-30'),
    status: 'expired'
}]->(plan1)

CREATE (account)-[:SUBSCRIBED_TO {
    from: date('2024-07-01'),
    to: null,          // null = current
    status: 'active'
}]->(plan2);


// Pattern 3: Hyperedges via intermediate nodes
// When a relationship connects 3+ entities

// "Alice recommended Bob for the Engineer role at TechCorp"
CREATE (rec:Recommendation {
    date: date(),
    strength: 'strong',
    notes: 'Excellent candidate'
})
CREATE (alice)-[:MADE]->(rec)
CREATE (rec)-[:FOR_CANDIDATE]->(bob)
CREATE (rec)-[:FOR_ROLE]->(role:Role {title: 'Staff Engineer'})
CREATE (rec)-[:AT_COMPANY]->(techcorp);


// Pattern 4: Access control / authorization graph
CREATE (user:User {name: 'Alice'})
CREATE (role:Role {name: 'editor'})
CREATE (perm:Permission {action: 'write', resource: 'articles'})
CREATE (resource:Resource {type: 'article', id: 'ART-001'})

CREATE (user)-[:HAS_ROLE]->(role)
CREATE (role)-[:GRANTS]->(perm)
CREATE (perm)-[:ON]->(resource);

// Check authorization: can Alice write article ART-001?
// MATCH (u:User {name: 'Alice'})-[:HAS_ROLE]->(:Role)
//       -[:GRANTS]->(:Permission {action: 'write'})
//       -[:ON]->(r:Resource {id: 'ART-001'})
// RETURN COUNT(*) > 0 AS authorized;
```

```python
# --- Data modeling utilities ---

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Cardinality(Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"


@dataclass
class NodeLabel:
    """Define a node label (entity type) in the graph model."""
    name: str
    properties: dict[str, str]     # name -> type
    indexes: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_cypher_constraints(self) -> list[str]:
        """Generate Cypher constraint statements."""
        statements: list[str] = []
        for prop in self.constraints:
            statements.append(
                f"CREATE CONSTRAINT {self.name.lower()}_{prop}_unique "
                f"IF NOT EXISTS FOR (n:{self.name}) "
                f"REQUIRE n.{prop} IS UNIQUE;"
            )
        for prop in self.indexes:
            statements.append(
                f"CREATE INDEX {self.name.lower()}_{prop}_idx "
                f"IF NOT EXISTS FOR (n:{self.name}) ON (n.{prop});"
            )
        return statements


@dataclass
class RelationshipType:
    """Define a relationship type in the graph model."""
    name: str
    from_label: str
    to_label: str
    cardinality: Cardinality
    properties: dict[str, str] = field(default_factory=dict)
    directed: bool = True


@dataclass
class GraphModel:
    """Complete graph data model definition."""
    nodes: list[NodeLabel]
    relationships: list[RelationshipType]

    def validate(self) -> list[str]:
        """Validate model for common anti-patterns."""
        issues: list[str] = []
        label_names = {n.name for n in self.nodes}

        for rel in self.relationships:
            if rel.from_label not in label_names:
                issues.append(f"Relationship {rel.name}: unknown from_label '{rel.from_label}'")
            if rel.to_label not in label_names:
                issues.append(f"Relationship {rel.name}: unknown to_label '{rel.to_label}'")
            if len(rel.properties) > 5:
                issues.append(
                    f"Relationship {rel.name} has {len(rel.properties)} properties "
                    "-- consider using an intermediate node"
                )

        for node in self.nodes:
            if not node.constraints and not node.indexes:
                issues.append(f"Node {node.name}: no indexes or constraints defined")

        return issues

    def generate_schema_cypher(self) -> str:
        """Generate Cypher DDL for the entire model."""
        statements: list[str] = []
        for node in self.nodes:
            statements.extend(node.to_cypher_constraints())
        return "\n".join(statements)


# Modeling guidelines:
# | Question | Node | Relationship | Property |
# |---|---|---|---|
# | Is it an entity? | Yes | | |
# | Does it connect entities? | | Yes | |
# | Is it an attribute? | | | Yes |
# | Does it have its own relationships? | Yes (promote!) | | |
# | > 5 properties on a relationship? | Intermediate node | | |
# | Need to query by this attribute? | Consider label | Index | |
```

Key graph modeling patterns:

| Pattern | When to Use | Example |
|---|---|---|
| Direct relationship | Simple connections | (:User)-[:FOLLOWS]->(:User) |
| Intermediate node | Rich multi-property connections | (:Person)-[:HOLDS]->(:Position)-[:AT]->(:Company) |
| Temporal versioning | Track state over time | Relationship with from/to dates |
| Hyperedge node | 3+ entities in one event | (:Recommendation) connecting recommender, candidate, role |
| Authorization graph | RBAC/ABAC access control | User->Role->Permission->Resource |

1. **Relationships are first-class** -- never store graph structure in properties
2. **Model for queries** -- design your graph to match traversal patterns
3. **Promote rich relationships** -- if > 5 properties, use an intermediate node
4. **Index lookup properties** -- every property used in MATCH WHERE needs an index
5. **Bidirectional when needed** -- Neo4j stores direction but can query both ways'''
    ),
    (
        "databases/neo4j-algorithms",
        "Demonstrate graph algorithms in Neo4j: PageRank, community detection, shortest path, and centrality.",
        '''Graph algorithms in Neo4j using Graph Data Science (GDS) library:

```cypher
// === Graph projection for algorithms ===

// Step 1: Create an in-memory graph projection
// Algorithms run on projected graphs, not the database directly

CALL gds.graph.project(
    'social-network',               // Graph name
    'Person',                        // Node labels
    {
        FOLLOWS: {
            type: 'FOLLOWS',
            orientation: 'NATURAL',  // NATURAL, REVERSE, UNDIRECTED
            properties: ['weight']    // Relationship properties to include
        },
        FRIENDS_WITH: {
            type: 'FRIENDS_WITH',
            orientation: 'UNDIRECTED'
        }
    },
    {
        nodeProperties: ['age', 'follower_count']
    }
);

// Check projection stats
CALL gds.graph.list()
YIELD graphName, nodeCount, relationshipCount, memoryUsage
RETURN *;


// === PageRank: find influential nodes ===

// PageRank in stream mode (returns results, does not write)
CALL gds.pageRank.stream('social-network', {
    maxIterations: 20,
    dampingFactor: 0.85,
    relationshipTypes: ['FOLLOWS']
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS person, score
RETURN person.name, ROUND(score, 4) AS pagerank
ORDER BY pagerank DESC
LIMIT 20;

// PageRank with write-back to database
CALL gds.pageRank.write('social-network', {
    maxIterations: 20,
    dampingFactor: 0.85,
    writeProperty: 'pagerank_score'
})
YIELD nodePropertiesWritten, ranIterations, computeMillis;


// === Community Detection: Louvain ===

// Detect communities (clusters) in the graph
CALL gds.louvain.stream('social-network', {
    relationshipTypes: ['FRIENDS_WITH'],
    includeIntermediateCommunities: true
})
YIELD nodeId, communityId, intermediateCommunityIds
WITH gds.util.asNode(nodeId) AS person, communityId
RETURN communityId,
       COUNT(*) AS community_size,
       COLLECT(person.name) AS members
ORDER BY community_size DESC;

// Label Propagation (faster alternative to Louvain)
CALL gds.labelPropagation.stream('social-network', {
    relationshipTypes: ['FRIENDS_WITH']
})
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS person, communityId
RETURN communityId, COLLECT(person.name) AS members
ORDER BY SIZE(COLLECT(person.name)) DESC;


// === Betweenness Centrality: bridge nodes ===

CALL gds.betweenness.stream('social-network')
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS person, score
WHERE score > 0
RETURN person.name, ROUND(score, 2) AS betweenness
ORDER BY betweenness DESC
LIMIT 10;
```

```cypher
// === Shortest Path algorithms ===

// Dijkstra: weighted shortest path
CALL gds.shortestPath.dijkstra.stream('social-network', {
    sourceNode: gds.util.nodeId('Person', {name: 'Alice'}),
    targetNode: gds.util.nodeId('Person', {name: 'Zara'}),
    relationshipWeightProperty: 'weight'
})
YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs, path
RETURN
    [nodeId IN nodeIds | gds.util.asNode(nodeId).name] AS route,
    totalCost AS total_weight,
    costs AS step_costs;

// A* with heuristic (geographic coordinates)
CALL gds.shortestPath.astar.stream('road-network', {
    sourceNode: sourceId,
    targetNode: targetId,
    latitudeProperty: 'latitude',
    longitudeProperty: 'longitude',
    relationshipWeightProperty: 'distance_km'
})
YIELD totalCost, nodeIds
RETURN totalCost AS distance_km,
    [nId IN nodeIds | gds.util.asNode(nId).name] AS route;

// All shortest paths from one source (BFS)
CALL gds.bfs.stream('social-network', {
    sourceNode: gds.util.nodeId('Person', {name: 'Alice'}),
    targetNodes: [
        gds.util.nodeId('Person', {name: 'Bob'}),
        gds.util.nodeId('Person', {name: 'Charlie'})
    ]
})
YIELD sourceNode, targetNode, nodeIds
RETURN
    gds.util.asNode(sourceNode).name AS source,
    gds.util.asNode(targetNode).name AS target,
    [nId IN nodeIds | gds.util.asNode(nId).name] AS path;


// === Node Similarity ===

// Find similar nodes based on shared neighbors
CALL gds.nodeSimilarity.stream('social-network', {
    similarityCutoff: 0.5,         // Minimum Jaccard similarity
    topK: 10                        // Top K similar per node
})
YIELD node1, node2, similarity
WITH gds.util.asNode(node1) AS person1,
     gds.util.asNode(node2) AS person2,
     similarity
RETURN person1.name, person2.name,
       ROUND(similarity, 3) AS jaccard_similarity
ORDER BY jaccard_similarity DESC
LIMIT 20;


// === Link Prediction ===

// Predict likely future connections
CALL gds.linkPrediction.adamicAdar.stream('social-network', {
    topK: 10,
    relationshipTypes: ['FRIENDS_WITH']
})
YIELD node1, node2, score
WITH gds.util.asNode(node1) AS p1,
     gds.util.asNode(node2) AS p2,
     score
WHERE NOT EXISTS { MATCH (p1)-[:FRIENDS_WITH]-(p2) }
RETURN p1.name, p2.name, ROUND(score, 4) AS prediction_score
ORDER BY prediction_score DESC
LIMIT 10;
```

```python
# --- Graph algorithm patterns in Python ---

from neo4j import GraphDatabase
from typing import Any
from dataclasses import dataclass


@dataclass
class AlgorithmResult:
    """Unified result from graph algorithms."""
    algorithm: str
    node_count: int
    execution_ms: int
    results: list[dict[str, Any]]


class GraphAnalytics:
    """Run graph algorithms via Neo4j Python driver."""

    def __init__(self, uri: str, auth: tuple[str, str]) -> None:
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def close(self) -> None:
        self.driver.close()

    def project_graph(
        self,
        graph_name: str,
        node_labels: list[str],
        relationship_types: list[str],
    ) -> dict[str, Any]:
        """Create in-memory graph projection."""
        with self.driver.session() as session:
            result = session.run("""
                CALL gds.graph.project($name, $nodes, $rels)
                YIELD graphName, nodeCount, relationshipCount
                RETURN *
            """, name=graph_name, nodes=node_labels, rels=relationship_types)
            return result.single().data()

    def pagerank(
        self,
        graph_name: str,
        damping: float = 0.85,
        iterations: int = 20,
        top_n: int = 20,
    ) -> AlgorithmResult:
        """Run PageRank and return top N results."""
        with self.driver.session() as session:
            result = session.run("""
                CALL gds.pageRank.stream($graph, {
                    maxIterations: $iterations,
                    dampingFactor: $damping
                })
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) AS node, score
                RETURN node.name AS name, round(score, 6) AS score
                ORDER BY score DESC
                LIMIT $limit
            """, graph=graph_name, iterations=iterations,
                 damping=damping, limit=top_n)

            records = [r.data() for r in result]
            return AlgorithmResult(
                algorithm="PageRank",
                node_count=len(records),
                execution_ms=0,
                results=records,
            )

    def community_detection(
        self,
        graph_name: str,
        algorithm: str = "louvain",
    ) -> AlgorithmResult:
        """Run community detection (Louvain or Label Propagation)."""
        algo_map = {
            "louvain": "gds.louvain.stream",
            "label_propagation": "gds.labelPropagation.stream",
        }

        proc = algo_map.get(algorithm, "gds.louvain.stream")

        with self.driver.session() as session:
            result = session.run(f"""
                CALL {proc}($graph)
                YIELD nodeId, communityId
                WITH communityId, COLLECT(gds.util.asNode(nodeId).name) AS members
                RETURN communityId, SIZE(members) AS size, members
                ORDER BY size DESC
            """, graph=graph_name)

            records = [r.data() for r in result]
            return AlgorithmResult(
                algorithm=algorithm,
                node_count=sum(r["size"] for r in records),
                execution_ms=0,
                results=records,
            )

    def shortest_path(
        self,
        graph_name: str,
        source_name: str,
        target_name: str,
        weight_property: str | None = None,
    ) -> dict[str, Any]:
        """Find shortest path between two nodes."""
        with self.driver.session() as session:
            if weight_property:
                result = session.run("""
                    MATCH (source {name: $source}), (target {name: $target})
                    CALL gds.shortestPath.dijkstra.stream($graph, {
                        sourceNode: source,
                        targetNode: target,
                        relationshipWeightProperty: $weight
                    })
                    YIELD totalCost, nodeIds
                    RETURN totalCost,
                        [nId IN nodeIds | gds.util.asNode(nId).name] AS path
                """, graph=graph_name, source=source_name,
                     target=target_name, weight=weight_property)
            else:
                result = session.run("""
                    MATCH path = shortestPath(
                        (a {name: $source})-[*]-(b {name: $target})
                    )
                    RETURN [n IN nodes(path) | n.name] AS path,
                           length(path) AS hops
                """, source=source_name, target=target_name)

            record = result.single()
            return record.data() if record else {"path": [], "totalCost": -1}

    def drop_graph(self, graph_name: str) -> None:
        """Drop in-memory graph projection."""
        with self.driver.session() as session:
            session.run(
                "CALL gds.graph.drop($name, false)",
                name=graph_name,
            )
```

Key graph algorithm patterns:

| Algorithm | Category | Use Case | Complexity |
|---|---|---|---|
| PageRank | Centrality | Influence, importance ranking | O(V + E) per iteration |
| Betweenness | Centrality | Bridge/bottleneck detection | O(V * E) |
| Louvain | Community | Cluster/group detection | O(V * log V) |
| Label Propagation | Community | Fast clustering | O(V + E) |
| Dijkstra | Path | Weighted shortest path | O(E + V log V) |
| Node Similarity | Similarity | Recommendation systems | O(V^2) worst case |
| Adamic-Adar | Link Prediction | Predict future connections | O(V * avg_degree) |

1. **Project before running** -- algorithms run on in-memory projections, not the DB
2. **Stream vs write** -- stream for exploration, write for persisting scores
3. **Choose community algorithm** -- Louvain for quality, Label Propagation for speed
4. **Weighted paths** -- use Dijkstra with weight property for realistic routing
5. **Drop projections** -- clean up in-memory graphs to free heap space'''
    ),
    (
        "databases/neo4j-python",
        "Show Neo4j Python integration: driver patterns, transactions, OGM, and production best practices.",
        '''Neo4j Python driver patterns for production applications:

```python
# --- Neo4j driver setup and connection management ---

from neo4j import (
    GraphDatabase,
    Session,
    ManagedTransaction,
    Result,
    AsyncGraphDatabase,
)
from typing import Any, TypeVar, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration."""
    uri: str = "neo4j://localhost:7687"
    username: str = "neo4j"
    password: str = ""
    database: str = "neo4j"
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: float = 60.0


class Neo4jClient:
    """Production Neo4j client with connection pooling."""

    def __init__(self, config: Neo4jConfig) -> None:
        self.config = config
        self.driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
            max_connection_pool_size=config.max_connection_pool_size,
            connection_acquisition_timeout=config.connection_acquisition_timeout,
        )
        # Verify connectivity
        self.driver.verify_connectivity()
        logger.info(f"Connected to Neo4j at {config.uri}")

    def close(self) -> None:
        """Close driver and release connections."""
        self.driver.close()

    @contextmanager
    def session(self, database: str | None = None):
        """Get a session with automatic cleanup."""
        session = self.driver.session(
            database=database or self.config.database
        )
        try:
            yield session
        finally:
            session.close()

    def read_transaction(
        self,
        work: Callable[[ManagedTransaction], T],
        database: str | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute a read transaction with automatic retry."""
        with self.session(database) as session:
            return session.execute_read(work, **kwargs)

    def write_transaction(
        self,
        work: Callable[[ManagedTransaction], T],
        database: str | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute a write transaction with automatic retry."""
        with self.session(database) as session:
            return session.execute_write(work, **kwargs)

    def health_check(self) -> dict[str, Any]:
        """Check database health and connectivity."""
        with self.session() as session:
            result = session.run("""
                CALL dbms.components()
                YIELD name, versions, edition
                RETURN name, versions[0] AS version, edition
            """)
            record = result.single()
            return {
                "name": record["name"],
                "version": record["version"],
                "edition": record["edition"],
                "connected": True,
            }
```

```python
# --- Repository pattern for domain objects ---

from dataclasses import dataclass
from datetime import datetime, date
from neo4j import ManagedTransaction


@dataclass
class Person:
    """Domain model for a person node."""
    name: str
    email: str
    age: int | None = None
    created_at: datetime | None = None
    node_id: int | None = None    # Internal Neo4j ID


class PersonRepository:
    """Repository for Person CRUD operations.

    Best practices:
      - Use parameterized queries (never string interpolation)
      - Use managed transactions (auto-retry on transient errors)
      - Separate read and write transactions for routing
      - Return domain objects, not raw records
    """

    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    def create(self, person: Person) -> Person:
        """Create a person node."""
        def _create(tx: ManagedTransaction, p: Person) -> Person:
            result = tx.run("""
                CREATE (n:Person {
                    name: $name,
                    email: $email,
                    age: $age,
                    created_at: datetime()
                })
                RETURN n, elementId(n) AS node_id
            """, name=p.name, email=p.email, age=p.age)

            record = result.single()
            node = record["n"]
            return Person(
                name=node["name"],
                email=node["email"],
                age=node["age"],
                created_at=node["created_at"],
                node_id=record["node_id"],
            )

        return self.client.write_transaction(_create, p=person)

    def find_by_email(self, email: str) -> Person | None:
        """Find person by email (read transaction)."""
        def _find(tx: ManagedTransaction, email: str) -> Person | None:
            result = tx.run("""
                MATCH (n:Person {email: $email})
                RETURN n, elementId(n) AS node_id
            """, email=email)

            record = result.single()
            if not record:
                return None

            node = record["n"]
            return Person(
                name=node["name"],
                email=node["email"],
                age=node.get("age"),
                created_at=node.get("created_at"),
                node_id=record["node_id"],
            )

        return self.client.read_transaction(_find, email=email)

    def find_friends(
        self,
        email: str,
        depth: int = 1,
    ) -> list[Person]:
        """Find friends up to N hops away."""
        def _find_friends(
            tx: ManagedTransaction, email: str, depth: int
        ) -> list[Person]:
            result = tx.run("""
                MATCH (p:Person {email: $email})
                      -[:FRIENDS_WITH*1..$depth]->(friend:Person)
                WHERE friend.email <> $email
                RETURN DISTINCT friend AS n, elementId(friend) AS node_id
                ORDER BY friend.name
            """, email=email, depth=depth)

            return [
                Person(
                    name=r["n"]["name"],
                    email=r["n"]["email"],
                    age=r["n"].get("age"),
                    node_id=r["node_id"],
                )
                for r in result
            ]

        return self.client.read_transaction(
            _find_friends, email=email, depth=depth
        )

    def add_friendship(
        self, email1: str, email2: str
    ) -> bool:
        """Create bidirectional friendship."""
        def _add(tx: ManagedTransaction, e1: str, e2: str) -> bool:
            result = tx.run("""
                MATCH (a:Person {email: $e1}), (b:Person {email: $e2})
                MERGE (a)-[r:FRIENDS_WITH]->(b)
                ON CREATE SET r.since = date()
                RETURN COUNT(r) AS created
            """, e1=e1, e2=e2)
            return result.single()["created"] > 0

        return self.client.write_transaction(_add, e1=email1, e2=email2)
```

```python
# --- Batch operations and async driver ---

import asyncio
from neo4j import AsyncGraphDatabase, AsyncManagedTransaction


class BatchImporter:
    """Efficient batch import for large datasets."""

    def __init__(self, client: Neo4jClient, batch_size: int = 1000) -> None:
        self.client = client
        self.batch_size = batch_size

    def import_nodes(
        self,
        label: str,
        data: list[dict[str, Any]],
        merge_key: str = "id",
    ) -> int:
        """Batch import nodes using UNWIND.

        UNWIND is 10-100x faster than individual CREATE statements.
        """
        total = 0

        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]

            def _import_batch(
                tx: ManagedTransaction,
                batch: list[dict[str, Any]],
                label: str,
                merge_key: str,
            ) -> int:
                result = tx.run(f"""
                    UNWIND $batch AS row
                    MERGE (n:{label} {{{merge_key}: row.{merge_key}}})
                    SET n += row
                    RETURN COUNT(n) AS count
                """, batch=batch)
                return result.single()["count"]

            count = self.client.write_transaction(
                _import_batch, batch=batch, label=label, merge_key=merge_key
            )
            total += count
            logger.info(f"Imported {total}/{len(data)} {label} nodes")

        return total

    def import_relationships(
        self,
        from_label: str,
        to_label: str,
        rel_type: str,
        data: list[dict[str, Any]],
        from_key: str = "from_id",
        to_key: str = "to_id",
    ) -> int:
        """Batch import relationships using UNWIND."""
        total = 0

        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]

            def _import_rels(
                tx: ManagedTransaction,
                batch: list[dict[str, Any]],
            ) -> int:
                result = tx.run(f"""
                    UNWIND $batch AS row
                    MATCH (a:{from_label} {{id: row.{from_key}}})
                    MATCH (b:{to_label} {{id: row.{to_key}}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r += row.properties
                    RETURN COUNT(r) AS count
                """, batch=batch)
                return result.single()["count"]

            count = self.client.write_transaction(_import_rels, batch=batch)
            total += count

        return total


# --- Async driver for high-throughput applications ---

async def async_query_example() -> None:
    """Async Neo4j driver for concurrent operations."""
    driver = AsyncGraphDatabase.driver(
        "neo4j://localhost:7687",
        auth=("neo4j", "password"),
    )

    async with driver.session() as session:
        # Async read transaction
        result = await session.execute_read(
            _async_find_people,
            min_age=25,
        )
        print(f"Found {len(result)} people")

    await driver.close()


async def _async_find_people(
    tx: AsyncManagedTransaction,
    min_age: int,
) -> list[dict[str, Any]]:
    """Async transaction function."""
    result = await tx.run("""
        MATCH (p:Person)
        WHERE p.age >= $min_age
        RETURN p.name AS name, p.age AS age
        ORDER BY p.age DESC
        LIMIT 100
    """, min_age=min_age)

    return [record.data() async for record in result]


# Production checklist:
# 1. Always use parameterized queries ($param, not f-strings)
# 2. Use execute_read for reads, execute_write for writes
# 3. UNWIND for batch operations (10-100x faster)
# 4. Create indexes/constraints for MATCH lookup properties
# 5. Close drivers on shutdown (connection pool cleanup)
# 6. Handle ServiceUnavailable and TransientError
# 7. Set reasonable timeouts and pool sizes
```

Key Neo4j Python patterns:

| Pattern | Method | Benefit |
|---|---|---|
| Managed transactions | execute_read / execute_write | Auto-retry on transient errors |
| Parameterized queries | $param syntax | SQL injection prevention |
| Repository pattern | Domain-specific classes | Clean separation of concerns |
| UNWIND batch import | UNWIND $batch AS row | 10-100x faster than individual writes |
| Async driver | AsyncGraphDatabase | High concurrency applications |
| Connection pooling | max_connection_pool_size | Reuse connections efficiently |

1. **Managed transactions** -- always use execute_read/execute_write for auto-retry
2. **Never string-interpolate Cypher** -- always use $parameters for security and caching
3. **UNWIND for batch** -- send lists and process with UNWIND, not individual statements
4. **Separate read and write** -- enables read replicas and causal consistency
5. **Repository pattern** -- wrap Cypher in domain-specific methods that return models'''
    ),
]
