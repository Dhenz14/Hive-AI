PAIRS = [
    (
        "knowledge-graphs/construction-entity-extraction",
        r"""Explain knowledge graph construction techniques including entity extraction with NER and relation extraction, ontology design patterns, graph schema modeling with RDF and property graphs, entity resolution and deduplication, and incremental graph updates.""",
        r"""## Knowledge Graph Construction: Entity Extraction, Ontology Design, and Incremental Updates

**Knowledge graphs** represent structured information as entities (nodes) and relationships (edges), enabling reasoning, question answering, and discovery that flat databases cannot support. **However**, constructing a high-quality knowledge graph from unstructured sources is one of the most challenging problems in NLP and data engineering. The **trade-off** between automation (NLP-based extraction) and manual curation determines both scale and quality.

### Entity Extraction Pipeline

The first step is identifying entities in text — people, organizations, concepts, technical terms. **Best practice**: combine NER models with domain-specific dictionaries and pattern matching, **because** NER alone misses domain jargon while dictionaries miss novel entities.

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class EntityType(Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    LOCATION = "location"
    EVENT = "event"

@dataclass
class Entity:
    id: str
    name: str
    entity_type: EntityType
    aliases: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    confidence: float = 1.0
    source: str = ""

@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str
    properties: dict = field(default_factory=dict)
    confidence: float = 1.0
    evidence: str = ""  # text span supporting this relation

class EntityExtractor:
    # Multi-strategy entity extraction
    # Common mistake: relying solely on generic NER models
    # because they miss domain-specific entities like library names, protocols, etc.

    def __init__(self, ner_model, dictionary: dict[str, EntityType] = None):
        self.ner_model = ner_model
        self.dictionary = dictionary or {}
        self._compiled_patterns = self._compile_dictionary()

    def _compile_dictionary(self):
        import re
        patterns = {}
        for term, etype in self.dictionary.items():
            # Word boundary matching for dictionary terms
            pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            patterns[term] = (pattern, etype)
        return patterns

    def extract(self, text: str) -> list[Entity]:
        entities = []
        seen_spans = set()

        # Strategy 1: NER model extraction
        ner_entities = self.ner_model.predict(text)
        for ent in ner_entities:
            span = (ent["start"], ent["end"])
            if span not in seen_spans:
                seen_spans.add(span)
                entities.append(Entity(
                    id=self._generate_id(ent["text"]),
                    name=ent["text"],
                    entity_type=self._map_ner_label(ent["label"]),
                    confidence=ent.get("score", 0.8),
                    source="ner",
                ))

        # Strategy 2: Dictionary matching (higher precision for known terms)
        for term, (pattern, etype) in self._compiled_patterns.items():
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    entities.append(Entity(
                        id=self._generate_id(term),
                        name=match.group(),
                        entity_type=etype,
                        confidence=0.95,  # Dictionary matches are high confidence
                        source="dictionary",
                    ))

        return entities

    def _map_ner_label(self, label: str) -> EntityType:
        mapping = {
            "PER": EntityType.PERSON,
            "ORG": EntityType.ORGANIZATION,
            "LOC": EntityType.LOCATION,
            "MISC": EntityType.CONCEPT,
        }
        return mapping.get(label, EntityType.CONCEPT)

    def _generate_id(self, text: str) -> str:
        import hashlib
        return "ent_" + hashlib.md5(text.lower().encode()).hexdigest()[:12]

class RelationExtractor:
    # Extracts relations between entities from text
    # Trade-off: pattern-based extraction is precise but low recall
    # NLI/LLM-based extraction has higher recall but lower precision

    RELATION_PATTERNS = {
        "uses": [r"{E1}\s+(?:uses?|utilizes?|employs?)\s+{E2}"],
        "created_by": [r"{E2}\s+(?:created?|developed?|built)\s+(?:by\s+)?{E1}"],
        "part_of": [r"{E1}\s+(?:is\s+)?(?:part\s+of|component\s+of|included?\s+in)\s+{E2}"],
        "implements": [r"{E1}\s+(?:implements?|provides?)\s+{E2}"],
        "depends_on": [r"{E1}\s+(?:depends?\s+on|requires?)\s+{E2}"],
    }

    def extract_relations(
        self,
        text: str,
        entities: list[Entity],
    ) -> list[Relation]:
        import re
        relations = []

        # Check all entity pairs
        for i, e1 in enumerate(entities):
            for j, e2 in enumerate(entities):
                if i == j:
                    continue
                for rel_type, patterns in self.RELATION_PATTERNS.items():
                    for pattern_template in patterns:
                        pattern = pattern_template.replace(
                            "{E1}", re.escape(e1.name)
                        ).replace(
                            "{E2}", re.escape(e2.name)
                        )
                        if re.search(pattern, text, re.IGNORECASE):
                            relations.append(Relation(
                                source_id=e1.id,
                                target_id=e2.id,
                                relation_type=rel_type,
                                confidence=0.8,
                                evidence=text[:200],
                            ))
        return relations
```

### Entity Resolution and Deduplication

**Entity resolution** (also called record linkage) identifies that different mentions refer to the same real-world entity. **Therefore**, it's essential for preventing duplicate nodes in the graph.

```python
from typing import Optional
import numpy as np

class EntityResolver:
    # Resolves different mentions to the same canonical entity
    # Best practice: use both string similarity and embedding similarity
    # Pitfall: case-sensitive matching misses "Python" vs "python"

    def __init__(self, embedding_model, similarity_threshold: float = 0.85):
        self.embedding_model = embedding_model
        self.threshold = similarity_threshold
        self.canonical_entities: dict[str, Entity] = {}
        self.entity_embeddings: dict[str, np.ndarray] = {}

    def resolve(self, entity: Entity) -> Entity:
        # Step 1: Check exact alias match (fast path)
        normalized_name = entity.name.lower().strip()
        for canonical_id, canonical in self.canonical_entities.items():
            all_names = [canonical.name.lower()] + [a.lower() for a in canonical.aliases]
            if normalized_name in all_names:
                return canonical

        # Step 2: Embedding similarity (handles paraphrases)
        # "React.js" and "ReactJS" may not match exactly but embed similarly
        entity_emb = self.embedding_model.encode(entity.name)

        best_match = None
        best_score = 0.0
        for canonical_id, canonical_emb in self.entity_embeddings.items():
            similarity = self._cosine_similarity(entity_emb, canonical_emb)
            if similarity > best_score:
                best_score = similarity
                best_match = canonical_id

        if best_match and best_score >= self.threshold:
            # Merge into existing entity
            canonical = self.canonical_entities[best_match]
            if entity.name not in canonical.aliases and entity.name != canonical.name:
                canonical.aliases.append(entity.name)
            # Update confidence (take max)
            canonical.confidence = max(canonical.confidence, entity.confidence)
            return canonical

        # Step 3: New entity — add to canonical set
        self.canonical_entities[entity.id] = entity
        self.entity_embeddings[entity.id] = entity_emb
        return entity

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        # However, embedding models can give false positives for short strings
        # Common mistake: using a low threshold that merges distinct entities
        dot = np.dot(a, b)
        return dot / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

class IncrementalGraphUpdater:
    # Updates the knowledge graph incrementally from new documents
    # Trade-off: batch rebuilds are simpler but expensive
    # Incremental updates are efficient but must handle conflicts

    def __init__(self, graph_store, entity_resolver: EntityResolver):
        self.graph = graph_store
        self.resolver = entity_resolver

    async def process_document(
        self,
        doc_id: str,
        entities: list[Entity],
        relations: list[Relation],
    ) -> dict:
        stats = {"entities_added": 0, "entities_merged": 0, "relations_added": 0}

        # Resolve entities (deduplicate against existing graph)
        resolved_map = {}  # old_id -> canonical_id
        for entity in entities:
            canonical = self.resolver.resolve(entity)
            resolved_map[entity.id] = canonical.id

            if canonical.id == entity.id:
                # New entity
                await self.graph.add_node(canonical)
                stats["entities_added"] += 1
            else:
                # Merged into existing
                await self.graph.update_node(canonical)
                stats["entities_merged"] += 1

        # Add relations with resolved entity IDs
        for relation in relations:
            resolved_relation = Relation(
                source_id=resolved_map.get(relation.source_id, relation.source_id),
                target_id=resolved_map.get(relation.target_id, relation.target_id),
                relation_type=relation.relation_type,
                properties={**relation.properties, "source_doc": doc_id},
                confidence=relation.confidence,
                evidence=relation.evidence,
            )

            # Check for duplicate relations
            existing = await self.graph.find_relation(
                resolved_relation.source_id,
                resolved_relation.target_id,
                resolved_relation.relation_type,
            )
            if existing:
                # Update confidence (aggregate evidence)
                # Best practice: increase confidence when multiple sources agree
                new_confidence = 1 - (1 - existing.confidence) * (1 - resolved_relation.confidence)
                await self.graph.update_relation(existing.id, confidence=new_confidence)
            else:
                await self.graph.add_edge(resolved_relation)
                stats["relations_added"] += 1

        return stats
```

### Graph Schema and Quality Scoring

```python
@dataclass
class GraphQualityMetrics:
    # Measures knowledge graph quality
    total_entities: int = 0
    total_relations: int = 0
    avg_entity_degree: float = 0.0  # avg relations per entity
    orphan_ratio: float = 0.0       # entities with no relations
    duplicate_ratio: float = 0.0     # suspected duplicates
    avg_confidence: float = 0.0
    schema_violations: int = 0

class GraphQualityScorer:
    # Scores knowledge graph quality for training data curation
    # Therefore, only high-quality subgraphs should be used for training

    def __init__(self, min_confidence: float = 0.7, min_degree: int = 1):
        self.min_confidence = min_confidence
        self.min_degree = min_degree

    async def score_graph(self, graph_store) -> GraphQualityMetrics:
        entities = await graph_store.get_all_entities()
        relations = await graph_store.get_all_relations()

        metrics = GraphQualityMetrics()
        metrics.total_entities = len(entities)
        metrics.total_relations = len(relations)

        # Degree distribution
        degree_map = {}
        for rel in relations:
            degree_map[rel.source_id] = degree_map.get(rel.source_id, 0) + 1
            degree_map[rel.target_id] = degree_map.get(rel.target_id, 0) + 1

        if entities:
            degrees = [degree_map.get(e.id, 0) for e in entities]
            metrics.avg_entity_degree = sum(degrees) / len(degrees)
            metrics.orphan_ratio = sum(1 for d in degrees if d == 0) / len(degrees)
            # Pitfall: high orphan ratio indicates poor relation extraction
            # or over-aggressive entity extraction

        # Confidence distribution
        all_confidences = [e.confidence for e in entities] + [r.confidence for r in relations]
        if all_confidences:
            metrics.avg_confidence = sum(all_confidences) / len(all_confidences)

        return metrics

    def filter_high_quality(
        self,
        entities: list[Entity],
        relations: list[Relation],
    ) -> tuple[list[Entity], list[Relation]]:
        # Filter to high-quality subgraph for training
        # Common mistake: using the entire graph including low-confidence edges
        good_entities = {
            e.id: e for e in entities
            if e.confidence >= self.min_confidence
        }

        good_relations = [
            r for r in relations
            if r.confidence >= self.min_confidence
            and r.source_id in good_entities
            and r.target_id in good_entities
        ]

        return list(good_entities.values()), good_relations
```

### Key Takeaways

- **Multi-strategy extraction** (NER + dictionary + patterns) captures more entities — **because** generic NER misses domain-specific terms
- **Entity resolution** prevents graph fragmentation — **however** setting the similarity threshold too low merges distinct entities (a **common mistake**)
- **Incremental updates** are essential for living knowledge graphs — the **trade-off** is complexity vs. avoiding expensive full rebuilds
- **Confidence aggregation** from multiple sources strengthens assertions — **therefore** when multiple documents agree on a relation, confidence should increase
- **Best practice**: separate entity extraction, resolution, and graph construction into pipeline stages
- **Pitfall**: treating the knowledge graph as static — in practice, entities change, relations evolve, and confidence degrades over time
"""
    ),
    (
        "knowledge-graphs/graph-querying-reasoning",
        r"""Explain knowledge graph querying and reasoning techniques including SPARQL and Cypher query patterns, graph traversal algorithms for path finding, rule-based inference engines, graph neural networks for link prediction, and embedding-based reasoning methods.""",
        r"""## Knowledge Graph Querying and Reasoning: From SPARQL to Graph Neural Networks

**Knowledge graph querying** goes far beyond simple lookups — it enables multi-hop reasoning, pattern discovery, and inference of implicit facts. **Because** real-world knowledge is incomplete, reasoning systems must infer missing relationships from the existing graph structure. The **trade-off** between explicit rules (interpretable but brittle) and learned embeddings (flexible but opaque) defines the spectrum of reasoning approaches.

### Graph Query Patterns

**Cypher** (Neo4j) and **SPARQL** (RDF) are the two dominant query languages. **Best practice**: choose based on your data model — property graphs for application-centric use cases, RDF for interoperability and standards compliance.

```python
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

class QueryLanguage(Enum):
    CYPHER = "cypher"
    SPARQL = "sparql"
    GREMLIN = "gremlin"

@dataclass
class GraphQuery:
    language: QueryLanguage
    query_string: str
    parameters: dict = field(default_factory=dict)
    timeout_ms: int = 30000

class GraphQueryBuilder:
    # Builds type-safe graph queries programmatically
    # Common mistake: string concatenation for queries (injection risk)
    # Best practice: use parameterized queries

    def __init__(self, language: QueryLanguage = QueryLanguage.CYPHER):
        self.language = language

    def find_paths(
        self,
        start_entity: str,
        end_entity: str,
        max_hops: int = 3,
        relation_types: Optional[list[str]] = None,
    ) -> GraphQuery:
        if self.language == QueryLanguage.CYPHER:
            # Variable-length path pattern in Cypher
            rel_filter = ""
            if relation_types:
                rel_filter = ":" + "|".join(relation_types)

            query = (
                "MATCH path = (start {id: $start_id})"
                f"-[*1..{max_hops}]-"
                "(end {id: $end_id}) "
                "RETURN path, length(path) as hops "
                "ORDER BY hops ASC LIMIT 10"
            )
            return GraphQuery(
                language=self.language,
                query_string=query,
                parameters={"start_id": start_entity, "end_id": end_entity},
            )

        elif self.language == QueryLanguage.SPARQL:
            # SPARQL property path syntax
            # Trade-off: SPARQL is more standardized but less intuitive for paths
            query = (
                "SELECT ?path WHERE { "
                f"  <{start_entity}> (<>|!<>){{1,{max_hops}}} <{end_entity}> . "
                "} LIMIT 10"
            )
            return GraphQuery(language=self.language, query_string=query)

    def semantic_search(
        self,
        entity_type: str,
        properties: dict[str, Any],
        depth: int = 2,
    ) -> GraphQuery:
        # Multi-hop neighborhood retrieval for context enrichment
        # Therefore, this is useful for RAG when you want related context
        conditions = " AND ".join([
            f"n.{k} = ${k}" for k in properties
        ])
        query = (
            f"MATCH (n:{entity_type}) WHERE {conditions} "
            f"CALL apoc.path.subgraphAll(n, {{maxLevel: {depth}}}) "
            "YIELD nodes, relationships "
            "RETURN nodes, relationships"
        )
        return GraphQuery(
            language=QueryLanguage.CYPHER,
            query_string=query,
            parameters=properties,
        )

class MultiHopReasoner:
    # Answers multi-hop questions by graph traversal
    # "What technologies does the company that created Python use?"
    # → Company(created, Python) → Company.uses → [technologies]

    def __init__(self, graph_store):
        self.graph = graph_store

    async def reason(self, query_plan: list[dict]) -> list[dict]:
        # Execute a chain of graph lookups
        # Each step narrows the result set
        results = None

        for step in query_plan:
            if results is None:
                # Initial lookup
                results = await self.graph.query(
                    step["entity_type"],
                    step.get("filter", {}),
                )
            else:
                # Traverse from previous results
                next_results = []
                for entity in results:
                    neighbors = await self.graph.get_neighbors(
                        entity["id"],
                        relation_type=step.get("relation"),
                        direction=step.get("direction", "outgoing"),
                    )
                    next_results.extend(neighbors)
                results = next_results

        return results or []
```

### Graph Embeddings for Link Prediction

**Knowledge graph embeddings** represent entities and relations as vectors in a continuous space, enabling prediction of missing links. **However**, different embedding methods have different strengths.

```python
import numpy as np
from typing import Optional

class TransEModel:
    # TransE: head + relation ~= tail (translation in embedding space)
    # Simple but effective for one-to-one relations
    # Pitfall: TransE struggles with one-to-many and many-to-many relations
    # because it maps all tails of a relation to the same point

    def __init__(self, n_entities: int, n_relations: int, dim: int = 100):
        self.dim = dim
        # Initialize embeddings
        self.entity_embeddings = np.random.randn(n_entities, dim) * 0.01
        self.relation_embeddings = np.random.randn(n_relations, dim) * 0.01
        # Normalize entity embeddings to unit sphere
        norms = np.linalg.norm(self.entity_embeddings, axis=1, keepdims=True)
        self.entity_embeddings /= (norms + 1e-8)

    def score_triple(self, head_id: int, relation_id: int, tail_id: int) -> float:
        # Score = -||h + r - t||  (higher is better)
        # Therefore, plausible triples have h + r close to t
        h = self.entity_embeddings[head_id]
        r = self.relation_embeddings[relation_id]
        t = self.entity_embeddings[tail_id]
        return -float(np.linalg.norm(h + r - t))

    def predict_tails(self, head_id: int, relation_id: int, k: int = 10) -> list[tuple[int, float]]:
        # Find most likely tail entities
        h = self.entity_embeddings[head_id]
        r = self.relation_embeddings[relation_id]
        target = h + r  # expected tail position

        # Compute distances to all entities
        diffs = self.entity_embeddings - target
        distances = np.linalg.norm(diffs, axis=1)
        top_k = np.argsort(distances)[:k]
        return [(int(idx), -float(distances[idx])) for idx in top_k]

    def train_step(
        self,
        positive_triples: list[tuple[int, int, int]],
        negative_triples: list[tuple[int, int, int]],
        learning_rate: float = 0.01,
        margin: float = 1.0,
    ):
        # Margin-based ranking loss: max(0, margin + d_pos - d_neg)
        # Best practice: use corruption-based negative sampling
        # (replace head or tail with random entity)
        for (h, r, t), (hn, rn, tn) in zip(positive_triples, negative_triples):
            d_pos = np.linalg.norm(
                self.entity_embeddings[h] + self.relation_embeddings[r]
                - self.entity_embeddings[t]
            )
            d_neg = np.linalg.norm(
                self.entity_embeddings[hn] + self.relation_embeddings[rn]
                - self.entity_embeddings[tn]
            )

            loss = max(0, margin + d_pos - d_neg)
            if loss > 0:
                # Gradient update
                grad_h = self.entity_embeddings[h] + self.relation_embeddings[r] - self.entity_embeddings[t]
                grad_h_norm = grad_h / (np.linalg.norm(grad_h) + 1e-8)

                self.entity_embeddings[h] -= learning_rate * grad_h_norm
                self.relation_embeddings[r] -= learning_rate * grad_h_norm
                self.entity_embeddings[t] += learning_rate * grad_h_norm

class RotatEModel:
    # RotatE: models relations as rotations in complex space
    # Therefore, it handles composition, symmetry, and inversion patterns
    # Trade-off: more expressive than TransE but more compute-intensive

    def __init__(self, n_entities: int, n_relations: int, dim: int = 100):
        self.dim = dim
        # Entity embeddings in complex space (real + imaginary)
        self.entity_re = np.random.randn(n_entities, dim) * 0.01
        self.entity_im = np.random.randn(n_entities, dim) * 0.01
        # Relation embeddings are rotation angles
        self.relation_phase = np.random.uniform(-np.pi, np.pi, (n_relations, dim))

    def score_triple(self, head_id: int, relation_id: int, tail_id: int) -> float:
        # h * r ~= t in complex space, where r = e^(i*theta)
        h_re = self.entity_re[head_id]
        h_im = self.entity_im[head_id]
        t_re = self.entity_re[tail_id]
        t_im = self.entity_im[tail_id]
        phase = self.relation_phase[relation_id]

        # Complex multiplication: (h_re + i*h_im) * (cos(phase) + i*sin(phase))
        rot_re = h_re * np.cos(phase) - h_im * np.sin(phase)
        rot_im = h_re * np.sin(phase) + h_im * np.cos(phase)

        # Distance in complex space
        diff_re = rot_re - t_re
        diff_im = rot_im - t_im
        distance = np.sqrt(diff_re**2 + diff_im**2).sum()
        return -float(distance)

class RuleBasedInference:
    # Derives new facts from existing ones using logical rules
    # Common mistake: not handling rule conflicts or circular derivations
    # However, rules are interpretable unlike embedding methods

    def __init__(self):
        self.rules = []

    def add_rule(self, head_relation: str, body: list[tuple[str, str]], confidence: float = 1.0):
        # Horn clause: head(X,Z) :- body1(X,Y), body2(Y,Z)
        self.rules.append({
            "head": head_relation,
            "body": body,
            "confidence": confidence,
        })

    async def infer(self, graph_store, max_iterations: int = 10) -> list[Relation]:
        # Forward chaining inference
        new_facts = []
        for iteration in range(max_iterations):
            iteration_facts = []
            for rule in self.rules:
                # Find variable bindings that satisfy the body
                bindings = await self._match_body(graph_store, rule["body"])
                for binding in bindings:
                    # Create new relation from head + bindings
                    new_rel = Relation(
                        source_id=binding["X"],
                        target_id=binding.get("Z", binding.get("Y")),
                        relation_type=rule["head"],
                        confidence=rule["confidence"],
                        properties={"inferred": True, "rule": str(rule)},
                    )
                    # Check if this fact already exists
                    existing = await graph_store.find_relation(
                        new_rel.source_id, new_rel.target_id, new_rel.relation_type
                    )
                    if not existing:
                        iteration_facts.append(new_rel)

            if not iteration_facts:
                break  # Fixed point reached
            new_facts.extend(iteration_facts)
            for fact in iteration_facts:
                await graph_store.add_edge(fact)

        return new_facts

    async def _match_body(self, graph_store, body: list[tuple[str, str]]) -> list[dict]:
        # Simple join-based matching for two-body rules
        # Trade-off: scalability vs. expressiveness
        if len(body) == 2:
            rel1_type, vars1 = body[0]
            rel2_type, vars2 = body[1]
            # Find: rel1(X,Y) AND rel2(Y,Z)
            rels1 = await graph_store.get_relations_by_type(rel1_type)
            rels2 = await graph_store.get_relations_by_type(rel2_type)
            # Join on shared variable
            bindings = []
            y_to_z = {}
            for r2 in rels2:
                y_to_z.setdefault(r2.source_id, []).append(r2.target_id)
            for r1 in rels1:
                if r1.target_id in y_to_z:
                    for z in y_to_z[r1.target_id]:
                        bindings.append({"X": r1.source_id, "Y": r1.target_id, "Z": z})
            return bindings
        return []
```

### Key Takeaways

- **Parameterized graph queries** prevent injection — a **common mistake** is concatenating user input into Cypher/SPARQL strings
- **TransE** is simple and effective for one-to-one relations — **however** it fails on complex relation patterns (one-to-many, symmetric)
- **RotatE** models relations as rotations — **therefore** it captures composition, symmetry, and inversion naturally
- **Rule-based inference** provides interpretable reasoning — the **trade-off** is that rules are brittle and require domain expertise to write
- **Best practice**: combine embeddings (high recall) with rules (high precision) for production reasoning systems
- **Pitfall**: running unbounded inference — always set max iterations and monitor for circular rule applications
"""
    ),
]
