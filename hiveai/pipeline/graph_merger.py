import logging
import re
import numpy as np
from hiveai.models import GraphTriple, GoldenBook, Job, BookReference

logger = logging.getLogger(__name__)


def find_overlapping_books(topic, db):
    try:
        from hiveai.llm.client import embed_text
        topic_embedding = embed_text(topic)
    except Exception as e:
        logger.warning(f"Could not embed topic for overlap search: {e}")
        return []

    try:
        from hiveai.vectorstore import vector_search_grouped
        grouped = vector_search_grouped(db, topic_embedding, max_distance=0.5, min_count=3)

        overlapping = []
        for item in grouped:
            book = db.query(GoldenBook).filter(GoldenBook.id == item["book_id"]).first()
            overlapping.append({
                "book_id": item["book_id"],
                "title": book.title if book else "Unknown",
                "matching_sections": item["match_count"],
                "compressed_content": book.compressed_content if book else None,
            })

        return overlapping
    except Exception as e:
        logger.warning(f"Overlap search query failed: {e}")
        return []


def _parse_compressed_topics(compressed_content):
    if not compressed_content:
        return []
    entities = re.findall(r'\[([^\]]+)\]', compressed_content)
    keys = re.findall(r'::(\w[\w\s]*?)(?:\n|$)', compressed_content)
    topics = list(dict.fromkeys(entities + [k.strip() for k in keys]))
    return topics[:20]


def build_knowledge_audit(topic, db):
    overlapping = find_overlapping_books(topic, db)
    if not overlapping:
        return "", []

    lines = ["=== EXISTING KNOWLEDGE (Do NOT repeat \u2014 reference these books instead) ===", ""]

    for book_info in overlapping:
        book_id = book_info["book_id"]
        title = book_info["title"]
        compressed = book_info["compressed_content"]

        topics_covered = _parse_compressed_topics(compressed)
        covers_str = ", ".join(topics_covered) if topics_covered else "general knowledge"

        triple_count = 0
        entity_count = 0
        job = db.query(Job).filter(Job.golden_book_id == book_id).first()
        if job:
            triple_count = job.triple_count or 0
            triples = db.query(GraphTriple).filter(GraphTriple.job_id == job.id).all()
            unique_subjects = set()
            for t in triples:
                if t.subject:
                    unique_subjects.add(t.subject.strip().lower())
            entity_count = len(unique_subjects)

        lines.append(f'Book: "{title}" (id={book_id})')
        lines.append(f"Already covers: {covers_str}")
        lines.append(f"Key facts: {triple_count} facts across {entity_count} entities")
        lines.append("")

    audit_text = "\n".join(lines)
    logger.info(f"Knowledge audit: {len(overlapping)} overlapping books found for topic '{topic}'")
    return audit_text, overlapping


def _triple_to_sentence(subject, predicate, obj):
    return f"{subject} {predicate} {obj}"


def _cosine_similarity_matrix(embeddings_a, embeddings_b):
    a = np.array(embeddings_a)
    b = np.array(embeddings_b)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if b.ndim == 1:
        b = b.reshape(1, -1)
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return a_norm @ b_norm.T


from hiveai.config import SEMANTIC_SIMILARITY_THRESHOLD


def filter_novel_triples(new_triples, overlapping_book_ids, db):
    if not overlapping_book_ids or not new_triples:
        return new_triples

    existing_sentences = []

    jobs = db.query(Job).filter(Job.golden_book_id.in_(overlapping_book_ids)).all()
    job_ids = [j.id for j in jobs]

    if job_ids:
        existing_triples = db.query(GraphTriple).filter(GraphTriple.job_id.in_(job_ids)).all()
        for t in existing_triples:
            s = (t.subject or "").strip().lower()
            p = (t.predicate or "").strip().lower()
            o = (t.obj or "").strip().lower()
            if s and p and o:
                existing_sentences.append(_triple_to_sentence(s, p, o))

    if not existing_sentences:
        overlapping_books = db.query(GoldenBook).filter(
            GoldenBook.id.in_(overlapping_book_ids)
        ).all()
        for book in overlapping_books:
            if book.compressed_content:
                current_entity = ""
                for line in book.compressed_content.split("\n"):
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        current_entity = line[1:-1].lower()
                    elif line.startswith("::") and not line.startswith("::\u2192") and current_entity:
                        parts = line[2:].split("=", 1)
                        if len(parts) == 2:
                            pred = parts[0].strip()
                            obj_val = parts[1].strip()
                            if " ~" in obj_val:
                                obj_val = obj_val.rsplit(" ~", 1)[0]
                            obj_val = obj_val.strip("[]")
                            existing_sentences.append(
                                _triple_to_sentence(current_entity, pred, obj_val)
                            )

    if not existing_sentences:
        logger.info(f"No existing knowledge to compare \u2014 all {len(new_triples)} triples are novel")
        return new_triples

    new_sentences = []
    for t in new_triples:
        s = (t.subject if hasattr(t, 'subject') else "").strip().lower()
        p = (t.predicate if hasattr(t, 'predicate') else "").strip().lower()
        o = (t.obj if hasattr(t, 'obj') else "").strip().lower()
        new_sentences.append(_triple_to_sentence(s, p, o))

    known_exact = set(existing_sentences)
    novel = []
    already_known_exact = 0
    already_known_semantic = 0
    candidates_for_semantic = []
    candidate_indices = []

    for i, sent in enumerate(new_sentences):
        if sent in known_exact:
            already_known_exact += 1
        else:
            candidates_for_semantic.append(sent)
            candidate_indices.append(i)

    if candidates_for_semantic and existing_sentences:
        try:
            from hiveai.llm.client import embed_texts

            all_to_embed = candidates_for_semantic + existing_sentences
            logger.info(f"Semantic novelty: embedding {len(candidates_for_semantic)} new + {len(existing_sentences)} existing facts")
            all_embeddings = embed_texts(all_to_embed)

            new_embeddings = all_embeddings[:len(candidates_for_semantic)]
            existing_embeddings = all_embeddings[len(candidates_for_semantic):]

            sim_matrix = _cosine_similarity_matrix(new_embeddings, existing_embeddings)

            for j, idx in enumerate(candidate_indices):
                max_sim = float(np.max(sim_matrix[j]))
                if max_sim >= SEMANTIC_SIMILARITY_THRESHOLD:
                    already_known_semantic += 1
                    best_match_idx = int(np.argmax(sim_matrix[j]))
                    logger.debug(
                        f"  Semantic match ({max_sim:.3f}): "
                        f"'{candidates_for_semantic[j][:60]}' \u2248 '{existing_sentences[best_match_idx][:60]}'"
                    )
                else:
                    novel.append(new_triples[idx])

        except Exception as e:
            logger.warning(f"Semantic similarity failed, accepting all candidates: {e}")
            for idx in candidate_indices:
                novel.append(new_triples[idx])
    else:
        for idx in candidate_indices:
            novel.append(new_triples[idx])

    total = len(new_triples)
    novel_count = len(novel)
    already_known_total = already_known_exact + already_known_semantic
    logger.info(
        f"Novelty filter: {total} total \u2192 {novel_count} novel, "
        f"{already_known_total} known (exact={already_known_exact}, semantic={already_known_semantic})"
    )
    return novel


def merge_triples(new_triples, existing_triples):
    def normalize_key(triple):
        s = triple.subject.strip().lower() if triple.subject else ""
        p = triple.predicate.strip().lower() if triple.predicate else ""
        o = triple.obj.strip().lower() if triple.obj else ""
        return (s, p, o)

    merged = {}

    for t in existing_triples:
        key = normalize_key(t)
        merged[key] = t

    duplicates = 0
    for t in new_triples:
        key = normalize_key(t)
        if key in merged:
            duplicates += 1
            existing = merged[key]
            existing_conf = existing.confidence if existing.confidence is not None else 0.0
            new_conf = t.confidence if t.confidence is not None else 0.0
            if new_conf > existing_conf:
                merged[key] = t
        else:
            merged[key] = t

    logger.info(f"Merge result: {len(new_triples)} new + {len(existing_triples)} existing = {len(merged)} unique ({duplicates} duplicates resolved)")

    return list(merged.values()), duplicates


def build_cross_references(triples):
    subjects = {}
    objects = {}

    for t in triples:
        s = t.subject.strip().lower() if t.subject else ""
        o = t.obj.strip().lower() if t.obj else ""
        if s:
            subjects.setdefault(s, []).append(t)
        if o:
            objects.setdefault(o, []).append(t)

    cross_refs = []
    for entity, subj_triples in subjects.items():
        if entity in objects:
            obj_triples = objects[entity]
            for st in subj_triples:
                for ot in obj_triples:
                    if st.id != ot.id and st.job_id != ot.job_id:
                        cross_refs.append({
                            "from_triple_id": ot.id,
                            "to_triple_id": st.id,
                            "connection_type": "subject_object_match",
                        })

    return cross_refs


def save_book_references(new_book_id, overlapping_books, db):
    if not overlapping_books:
        return

    db.query(BookReference).filter(BookReference.from_book_id == new_book_id).delete()

    refs_created = 0
    new_book = db.query(GoldenBook).filter(GoldenBook.id == new_book_id).first()
    new_title = new_book.title if new_book else "Unknown"

    for book_info in overlapping_books:
        other_book_id = book_info["book_id"]
        if other_book_id == new_book_id:
            continue
        title = book_info.get("title", "Unknown")

        context = f"Both cover related topics: '{new_title}' references knowledge from '{title}'"

        ref = BookReference(
            from_book_id=new_book_id,
            to_book_id=other_book_id,
            reference_context=context,
        )
        db.add(ref)
        refs_created += 1

    try:
        db.commit()
        logger.info(f"Saved {refs_created} book references for book id={new_book_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save book references: {e}")
