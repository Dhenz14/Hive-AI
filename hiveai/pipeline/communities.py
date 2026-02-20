import logging
import os
import pickle
import threading
import networkx as nx
from hiveai.models import SessionLocal, GraphTriple, Community

logger = logging.getLogger(__name__)

GRAPH_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
GRAPH_CACHE_PATH = os.path.join(GRAPH_CACHE_DIR, "knowledge_graph.pkl")

_global_graph = None
_global_graph_lock = threading.Lock()


def _ensure_cache_dir():
    os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)


def load_global_graph():
    """Load the global knowledge graph from disk, or create empty one."""
    global _global_graph
    with _global_graph_lock:
        if _global_graph is not None:
            return _global_graph
        if os.path.exists(GRAPH_CACHE_PATH):
            try:
                with open(GRAPH_CACHE_PATH, "rb") as f:
                    _global_graph = pickle.load(f)
                logger.info(f"Loaded global graph: {len(_global_graph.nodes)} nodes, {len(_global_graph.edges)} edges")
            except Exception as e:
                logger.warning(f"Failed to load cached graph: {e}")
                _global_graph = nx.Graph()
        else:
            _global_graph = nx.Graph()
        return _global_graph


def save_global_graph():
    """Persist the global knowledge graph to disk."""
    global _global_graph
    if _global_graph is None:
        return
    _ensure_cache_dir()
    try:
        import tempfile
        with _global_graph_lock:
            fd, tmp_path = tempfile.mkstemp(dir=GRAPH_CACHE_DIR, suffix=".pkl")
            try:
                with os.fdopen(fd, "wb") as f:
                    pickle.dump(_global_graph, f)
                os.replace(tmp_path, GRAPH_CACHE_PATH)
            except:
                os.unlink(tmp_path)
                raise
        logger.info(f"Saved global graph: {len(_global_graph.nodes)} nodes, {len(_global_graph.edges)} edges")
    except Exception as e:
        logger.warning(f"Failed to save graph: {e}")


def add_triples_to_global_graph(triples, book_id=None):
    """Add triples to the global knowledge graph incrementally."""
    G = load_global_graph()
    added = 0
    for t in triples:
        subject = t.subject if hasattr(t, 'subject') else t.get('subject', '')
        obj = t.obj if hasattr(t, 'obj') else t.get('obj', '')
        predicate = t.predicate if hasattr(t, 'predicate') else t.get('predicate', '')
        if subject and obj:
            G.add_node(subject, type="entity")
            G.add_node(obj, type="entity")
            edge_data = {"predicate": predicate}
            if book_id:
                edge_data["book_id"] = book_id
            G.add_edge(subject, obj, **edge_data)
            added += 1
    save_global_graph()
    logger.info(f"Added {added} edges to global graph (total: {len(G.nodes)} nodes, {len(G.edges)} edges)")
    return added


def rebuild_global_graph():
    """Rebuild the global graph from all graph_triples in the database."""
    global _global_graph
    db = SessionLocal()
    try:
        _global_graph = nx.Graph()
        triples = db.query(GraphTriple).all()
        for t in triples:
            if t.subject and t.obj:
                _global_graph.add_node(t.subject, type="entity")
                _global_graph.add_node(t.obj, type="entity")
                _global_graph.add_edge(t.subject, t.obj, predicate=t.predicate, job_id=t.job_id)
        save_global_graph()
        logger.info(f"Rebuilt global graph: {len(_global_graph.nodes)} nodes, {len(_global_graph.edges)} edges")
        return {"nodes": len(_global_graph.nodes), "edges": len(_global_graph.edges)}
    finally:
        db.close()


def get_global_graph_stats():
    """Get statistics about the global knowledge graph."""
    G = load_global_graph()
    stats = {
        "nodes": len(G.nodes),
        "edges": len(G.edges),
        "components": nx.number_connected_components(G) if len(G.nodes) > 0 else 0,
        "cached": os.path.exists(GRAPH_CACHE_PATH),
    }
    if len(G.nodes) > 0:
        degrees = [d for _, d in G.degree()]
        stats["avg_degree"] = round(sum(degrees) / len(degrees), 2)
        stats["max_degree"] = max(degrees)
    return stats


def build_communities(job_id):
    db = SessionLocal()
    try:
        triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).all()
        if not triples:
            logger.info(f"No triples found for job {job_id}, skipping community detection")
            return []

        G = nx.Graph()
        for t in triples:
            G.add_node(t.subject)
            G.add_node(t.obj)
            G.add_edge(t.subject, t.obj, predicate=t.predicate)

        if len(G.nodes) < 3:
            logger.info(f"Graph too small ({len(G.nodes)} nodes) for community detection")
            return []

        try:
            communities = nx.community.louvain_communities(G, seed=42)
        except Exception as e:
            logger.warning(f"Louvain community detection failed: {e}")
            return []

        from hiveai.llm.client import fast
        from hiveai.llm.prompts import COMMUNITY_SUMMARY_PROMPT

        results = []
        for community_set in communities:
            if len(community_set) < 2:
                continue

            entity_list = list(community_set)
            community_triples = []
            for t in triples:
                if t.subject in community_set or t.obj in community_set:
                    community_triples.append(f"{t.subject} - {t.predicate} - {t.obj}")

            if not community_triples:
                continue

            try:
                prompt = COMMUNITY_SUMMARY_PROMPT.format(
                    entities=", ".join(entity_list[:30]),
                    triples="\n".join(community_triples[:50]),
                )
                summary = fast(prompt, max_tokens=512)
                if summary:
                    from hiveai.llm.client import clean_llm_response
                    summary = clean_llm_response(summary)
            except Exception as e:
                logger.warning(f"Failed to generate community summary: {e}")
                summary = f"Cluster of related entities: {', '.join(entity_list[:10])}"

            community_data = {
                "entities": entity_list,
                "triples": community_triples,
                "summary": summary,
            }
            results.append(community_data)

            try:
                db_community = Community(
                    job_id=job_id,
                    entities=entity_list,
                    triple_count=len(community_triples),
                    summary=summary,
                )
                db.add(db_community)
            except Exception as e:
                logger.warning(f"Failed to store community in database: {e}")

        try:
            add_triples_to_global_graph(triples, book_id=None)
        except Exception as e:
            logger.warning(f"Failed to update global graph: {e}")

        db.commit()
        logger.info(f"Community detection complete: {len(results)} communities found for job {job_id}")
        return results
    except Exception as e:
        logger.warning(f"Community detection failed: {e}")
        return []
    finally:
        db.close()


def get_community_summaries(topic, db):
    try:
        communities = db.query(Community).all()
        if not communities:
            return []

        topic_words = set(w.lower() for w in topic.split() if len(w) > 2)
        scored = []
        for community in communities:
            if not community.summary:
                continue
            entities = community.entities or []
            entity_text = " ".join(str(e).lower() for e in entities)
            summary_text = (community.summary or "").lower()
            combined = entity_text + " " + summary_text

            score = 0
            for word in topic_words:
                if word in combined:
                    score += 1

            if score > 0:
                scored.append((community.summary, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored[:5]]
    except Exception as e:
        logger.warning(f"Community summary lookup failed: {e}")
        return []
