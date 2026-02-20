import logging
import networkx as nx
from hiveai.models import SessionLocal, GraphTriple

logger = logging.getLogger(__name__)


def load_graph(job_id):
    db = SessionLocal()
    try:
        triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).all()
        G = nx.DiGraph()

        for t in triples:
            G.add_edge(t.subject, t.obj, predicate=t.predicate, confidence=t.confidence)

        logger.info(f"Loaded graph for job {job_id}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G
    finally:
        db.close()


def get_graph_stats(job_id):
    G = load_graph(job_id)
    if G.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0, "components": 0, "density": 0}

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "components": nx.number_weakly_connected_components(G),
        "density": round(nx.density(G), 4),
        "top_nodes": sorted(G.degree(), key=lambda x: x[1], reverse=True)[:10],
    }


def get_graph_json(job_id):
    db = SessionLocal()
    try:
        triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).all()

        nodes = set()
        edges = []
        for t in triples:
            nodes.add(t.subject)
            nodes.add(t.obj)
            edges.append({
                "source": t.subject,
                "target": t.obj,
                "label": t.predicate,
                "confidence": t.confidence,
            })

        return {
            "nodes": [{"id": n, "label": n} for n in nodes],
            "edges": edges,
        }
    finally:
        db.close()
