import logging
import re
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

KNOWN_ALIASES = {
    "javascript": ["js", "ecmascript", "es6", "es2015", "es2016", "es2017", "es2018", "es2019", "es2020", "es2021", "es2022", "es2023"],
    "typescript": ["ts"],
    "python": ["py", "cpython"],
    "machine learning": ["ml"],
    "artificial intelligence": ["ai"],
    "natural language processing": ["nlp"],
    "application programming interface": ["api", "apis"],
    "graphical user interface": ["gui"],
    "command line interface": ["cli"],
    "html": ["hypertext markup language"],
    "css": ["cascading style sheets"],
    "sql": ["structured query language"],
    "nosql": ["no-sql"],
    "json": ["javascript object notation"],
    "xml": ["extensible markup language"],
    "http": ["hypertext transfer protocol"],
    "https": ["http secure", "hypertext transfer protocol secure"],
    "rest": ["restful", "representational state transfer"],
    "database": ["db"],
    "operating system": ["os"],
    "united states": ["us", "usa", "united states of america", "u.s.", "u.s.a."],
    "european union": ["eu"],
    "united kingdom": ["uk", "u.k."],
}

def _build_alias_map():
    alias_map = {}
    for canonical, aliases in KNOWN_ALIASES.items():
        for alias in aliases:
            alias_map[alias.lower()] = canonical
        alias_map[canonical.lower()] = canonical
    return alias_map

ALIAS_MAP = _build_alias_map()

def normalize_entity(text):
    if not text:
        return text
    normalized = text.strip()
    lower = normalized.lower()
    if lower in ALIAS_MAP:
        return ALIAS_MAP[lower]
    return normalized


def _embedding_based_aliases(triples):
    try:
        all_entities = []
        for triple in triples:
            if triple.subject:
                all_entities.append(triple.subject)
            if triple.obj:
                all_entities.append(triple.obj)

        if not all_entities:
            return {}

        entity_counts = Counter(all_entities)
        if len(entity_counts) > 200:
            entities_to_process = [e for e, _ in entity_counts.most_common(200)]
        else:
            entities_to_process = list(entity_counts.keys())

        if len(entities_to_process) < 2:
            return {}

        from hiveai.llm.client import embed_texts
        import numpy as np

        embeddings = embed_texts(entities_to_process)
        embeddings_array = np.array(embeddings)
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-8, norms)
        embeddings_array = embeddings_array / norms

        similarity_threshold = 0.92
        processed = set()
        embedding_aliases = {}

        for i in range(len(entities_to_process)):
            if i in processed:
                continue

            group = [entities_to_process[i]]

            for j in range(i + 1, len(entities_to_process)):
                if j in processed:
                    continue

                similarity = float(np.dot(embeddings_array[i], embeddings_array[j]))

                if similarity > similarity_threshold:
                    group.append(entities_to_process[j])
                    processed.add(j)

            if len(group) > 1:
                canonical = max(group, key=len)

                for entity in group:
                    if entity != canonical:
                        embedding_aliases[entity] = canonical

            processed.add(i)

        if embedding_aliases:
            logger.info(f"Discovered {len(embedding_aliases)} embedding-based aliases")

        return embedding_aliases

    except Exception as e:
        logger.warning(f"Embedding-based entity resolution failed: {e}")
        return {}


def resolve_triples(triples):
    """Takes a list of GraphTriple ORM objects, normalizes their subject and obj fields.
    Returns the modified triples and a count of how many were changed."""
    changed = 0
    for triple in triples:
        new_subject = normalize_entity(triple.subject)
        new_obj = normalize_entity(triple.obj)
        if new_subject != triple.subject or new_obj != triple.obj:
            triple.subject = new_subject
            triple.obj = new_obj
            changed += 1

    embedding_aliases = _embedding_based_aliases(triples)
    embedding_changed = 0
    if embedding_aliases:
        for triple in triples:
            if triple.subject in embedding_aliases:
                triple.subject = embedding_aliases[triple.subject]
                embedding_changed += 1
            if triple.obj in embedding_aliases:
                triple.obj = embedding_aliases[triple.obj]
                embedding_changed += 1

    seen = {}
    duplicates = 0
    unique = []
    for t in triples:
        key = (
            (t.subject or "").strip().lower(),
            (t.predicate or "").strip().lower(),
            (t.obj or "").strip().lower(),
        )
        if key in seen:
            duplicates += 1
            existing = seen[key]
            existing_conf = existing.confidence if existing.confidence is not None else 0.0
            new_conf = t.confidence if t.confidence is not None else 0.0
            if new_conf > existing_conf:
                seen[key] = t
        else:
            seen[key] = t

    unique = list(seen.values())

    logger.info(f"Entity resolution: {changed} entities normalized, {embedding_changed} entities resolved by embedding similarity, {duplicates} duplicate triples merged ({len(triples)} → {len(unique)})")
    return unique, changed, duplicates
