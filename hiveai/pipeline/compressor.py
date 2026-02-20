import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

PREDICATE_MAP = {
    "is a": "type",
    "is an": "type",
    "is type of": "type",
    "is a type of": "type",
    "has type": "type",
    "was created in": "created",
    "was created on": "created",
    "created in": "created",
    "created on": "created",
    "was founded in": "founded",
    "founded in": "founded",
    "is used for": "used_for",
    "used for": "used_for",
    "is part of": "part_of",
    "part of": "part_of",
    "belongs to": "part_of",
    "has feature": "feature",
    "has features": "features",
    "supports": "supports",
    "is supported by": "supported_by",
    "was developed by": "developed_by",
    "developed by": "developed_by",
    "created by": "created_by",
    "written in": "written_in",
    "is written in": "written_in",
    "programmed in": "written_in",
    "uses": "uses",
    "has": "has",
    "contains": "contains",
    "implements": "implements",
    "extends": "extends",
    "is based on": "based_on",
    "based on": "based_on",
    "forked from": "fork_of",
    "is a fork of": "fork_of",
    "depends on": "depends_on",
    "requires": "requires",
    "provides": "provides",
    "enables": "enables",
    "is known as": "alias",
    "also known as": "alias",
    "is similar to": "similar_to",
    "is related to": "related_to",
    "has version": "version",
    "latest version": "latest_version",
    "released in": "released",
    "released on": "released",
    "has license": "license",
    "licensed under": "license",
    "is located in": "location",
    "located in": "location",
    "has population": "population",
    "has size": "size",
    "costs": "cost",
    "has price": "price",
    "invented by": "invented_by",
    "discovered by": "discovered_by",
    "published by": "published_by",
    "published in": "published_in",
    "runs on": "runs_on",
    "is compatible with": "compatible_with",
    "interacts with": "interacts_with",
    "is composed of": "composed_of",
    "succeeded by": "succeeded_by",
    "preceded by": "preceded_by",
    "is owned by": "owned_by",
    "owned by": "owned_by",
}

PREDICATE_GROUPS = {
    "token": {"governance_token", "utility_token", "stable_token", "native_token", "token", "staking_token"},
    "sdk": {"python_sdk", "javascript_sdk", "java_sdk", "ruby_sdk", "sdk", "library", "client_library"},
    "api": {"rest_api", "graphql_api", "rpc_api", "api_endpoint", "api"},
    "spec": {"block_time", "block_size", "transaction_speed", "throughput", "latency", "finality"},
    "social": {"twitter", "github", "website", "discord", "telegram", "forum"},
}


def _normalize_predicate(predicate):
    pred = predicate.lower().strip()

    if pred in PREDICATE_MAP:
        return PREDICATE_MAP[pred]

    pred = pred.replace(" ", "_")
    for prefix in ("is_", "has_", "was_", "are_", "were_"):
        if pred.startswith(prefix) and len(pred) > len(prefix) + 2:
            pred = pred[len(prefix):]
            break

    return pred


def _extract_triple_fields(t):
    if isinstance(t, dict):
        subject = t.get("subject", "")
        predicate = t.get("predicate", "")
        obj = t.get("obj", t.get("object", ""))
        confidence = t.get("confidence", 1.0)
        source_url = t.get("source_url", "")
    else:
        subject = getattr(t, "subject", "")
        predicate = getattr(t, "predicate", "")
        obj = getattr(t, "obj", "")
        confidence = getattr(t, "confidence", 1.0)
        source_url = getattr(t, "source_url", "")
    return subject, predicate, obj, confidence, source_url


def _try_group_predicates(pred, obj_text):
    obj_lower = obj_text.lower()
    for group_name, keywords in PREDICATE_GROUPS.items():
        if pred in keywords or any(kw in pred for kw in keywords):
            qualifier = pred.replace(group_name + "_", "").replace("_" + group_name, "").strip("_")
            if qualifier and qualifier != pred:
                return f"{group_name}.{qualifier}"
            return f"{group_name}.{pred}"
    return pred


def encode_triples_dense(triples, topic=""):
    if not triples:
        return ""

    entity_map = defaultdict(list)
    entity_sources = defaultdict(set)
    all_subjects = set()
    all_objects = set()

    for t in triples:
        subject, predicate, obj, confidence, source_url = _extract_triple_fields(t)
        if not (subject and predicate and obj):
            continue
        all_subjects.add(subject)
        all_objects.add(obj)
        entity_map[subject].append((predicate, obj, confidence))
        if source_url:
            entity_sources[subject].add(source_url)

    if not entity_map:
        return ""

    cross_refs = {}
    for subj in entity_map:
        refs = []
        for other_subj in entity_map:
            if other_subj == subj:
                continue
            for _, obj, _ in entity_map[other_subj]:
                if subj.lower() in obj.lower() or obj.lower() in subj.lower():
                    refs.append(other_subj)
                    break
        if refs:
            cross_refs[subj] = refs[:5]

    connectivity = {}
    for subj, preds in entity_map.items():
        outgoing = len(preds)
        incoming = sum(1 for s in entity_map for _, o, _ in entity_map[s] if subj.lower() in o.lower() and s != subj)
        connectivity[subj] = outgoing + incoming

    sorted_entities = sorted(entity_map.items(), key=lambda x: connectivity.get(x[0], 0), reverse=True)

    lines = []
    if topic:
        lines.append(f"@topic={topic}")

    unique_sources = set()
    for sources in entity_sources.values():
        unique_sources.update(sources)
    if unique_sources:
        lines.append(f"@sources={len(unique_sources)}")

    lines.append(f"@entities={len(sorted_entities)}")
    lines.append(f"@facts={sum(len(preds) for _, preds in sorted_entities)}")
    lines.append("")

    for entity, predicates in sorted_entities:
        conn = connectivity.get(entity, 0)
        lines.append(f"[{entity}]")

        pred_groups = defaultdict(list)
        pred_confidence = defaultdict(list)
        for pred, obj, conf in predicates:
            clean_pred = _normalize_predicate(pred)
            grouped_pred = _try_group_predicates(clean_pred, obj)
            pred_groups[grouped_pred].append(obj)
            pred_confidence[grouped_pred].append(conf)

        for pred, objects in pred_groups.items():
            avg_conf = sum(pred_confidence[pred]) / len(pred_confidence[pred])
            conf_marker = "" if avg_conf >= 0.8 else f" ~{avg_conf:.1f}"

            if len(objects) == 1:
                lines.append(f"::{pred}={objects[0]}{conf_marker}")
            else:
                unique_objs = list(dict.fromkeys(objects))
                vals = ", ".join(unique_objs)
                lines.append(f"::{pred}=[{vals}]{conf_marker}")

        if entity in cross_refs:
            refs = ", ".join(cross_refs[entity])
            lines.append(f"::→refs=[{refs}]")

        lines.append("")

    if unique_sources:
        lines.append("@src")
        for i, src in enumerate(sorted(unique_sources)[:20], 1):
            lines.append(f"  {i}. {src}")

    return "\n".join(lines).strip()


def compress_golden_book(book_content, triples, topic=""):
    dense = encode_triples_dense(triples, topic=topic)

    if not dense:
        return ""

    book_words = len(book_content.split()) if book_content else 0
    dense_words = len(dense.split())
    ratio = book_words / dense_words if dense_words > 0 else 0

    logger.info(f"Compressed knowledge: {book_words} words (prose) → {dense_words} words (dense), {ratio:.1f}x compression")

    return dense


def decode_dense_for_display(dense_text):
    if not dense_text:
        return "No compressed knowledge available."

    lines = dense_text.split("\n")
    readable = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("@topic="):
            readable.append(f"**Topic: {line[7:]}**")
            readable.append("")
        elif line.startswith("@sources=") or line.startswith("@entities=") or line.startswith("@facts="):
            key, val = line[1:].split("=", 1)
            readable.append(f"_{key.title()}: {val}_")
        elif line == "@src":
            readable.append("")
            readable.append("**Sources:**")
        elif line.startswith("[") and line.endswith("]"):
            readable.append("")
            readable.append(f"### {line[1:-1]}")
        elif line.startswith("::→refs="):
            refs = line[8:].strip("[]")
            readable.append(f"  - _Related to: {refs}_")
        elif line.startswith("::"):
            parts = line[2:].split("=", 1)
            if len(parts) == 2:
                key, value = parts
                conf = ""
                if " ~" in value:
                    value, conf_str = value.rsplit(" ~", 1)
                    conf = f" _(confidence: {conf_str})_"
                key_readable = key.replace("_", " ").replace(".", " → ").title()
                readable.append(f"  - **{key_readable}**: {value}{conf}")
        else:
            readable.append(line)

    return "\n".join(readable)
