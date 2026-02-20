import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

OPPOSING_PREDICATES = {
    "is": "is not",
    "is not": "is",
    "supports": "does not support",
    "does not support": "supports",
    "uses": "does not use",
    "does not use": "uses",
    "has": "does not have",
    "does not have": "has",
    "enables": "disables",
    "disables": "enables",
    "increases": "decreases",
    "decreases": "increases",
    "created": "did not create",
    "was created by": "was not created by",
    "is faster than": "is slower than",
    "is slower than": "is faster than",
    "is better than": "is worse than",
    "is worse than": "is better than",
    "precedes": "follows",
    "follows": "precedes",
    "includes": "excludes",
    "excludes": "includes",
    "allows": "prohibits",
    "prohibits": "allows",
}

NUMERIC_PREDICATES = [
    "was founded in", "was created in", "was released in", "has population of",
    "costs", "weighs", "measures", "has size of", "runs at", "operates at",
    "was born in", "died in", "has speed of", "has capacity of",
]

def _normalize(text):
    if not text:
        return ""
    return text.strip().lower()

def _is_numeric_conflict(obj1, obj2):
    nums1 = re.findall(r'[\d,]+\.?\d*', obj1)
    nums2 = re.findall(r'[\d,]+\.?\d*', obj2)
    if nums1 and nums2:
        try:
            n1 = float(nums1[0].replace(',', ''))
            n2 = float(nums2[0].replace(',', ''))
            if n1 != n2:
                return True
        except ValueError:
            pass
    return False

def detect_contradictions(triples):
    subject_pred_groups = defaultdict(list)
    for t in triples:
        key = (_normalize(t.subject), _normalize(t.predicate))
        subject_pred_groups[key].append(t)

    contradictions = []

    for (subj, pred), group in subject_pred_groups.items():
        if len(group) < 2:
            continue
        
        is_numeric_pred = any(np in pred for np in NUMERIC_PREDICATES)
        if is_numeric_pred or len(group) >= 2:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    obj_i = _normalize(group[i].obj)
                    obj_j = _normalize(group[j].obj)
                    if obj_i != obj_j and _is_numeric_conflict(obj_i, obj_j):
                        contradictions.append({
                            "type": "numeric_conflict",
                            "subject": group[i].subject,
                            "predicate": group[i].predicate,
                            "triple_a": group[i],
                            "triple_b": group[j],
                        })

    for (subj, pred), group in subject_pred_groups.items():
        opp = OPPOSING_PREDICATES.get(pred)
        if opp:
            opp_key = (subj, opp)
            if opp_key in subject_pred_groups:
                for t1 in group:
                    for t2 in subject_pred_groups[opp_key]:
                        if _normalize(t1.obj) == _normalize(t2.obj):
                            contradictions.append({
                                "type": "opposing_predicate",
                                "subject": t1.subject,
                                "predicate_a": t1.predicate,
                                "predicate_b": t2.predicate,
                                "triple_a": t1,
                                "triple_b": t2,
                            })

    return contradictions


def resolve_contradictions(contradictions, db):
    resolved = 0
    deleted_ids = set()
    for c in contradictions:
        t_a = c["triple_a"]
        t_b = c["triple_b"]

        if t_a.id in deleted_ids or t_b.id in deleted_ids:
            continue

        conf_a = t_a.confidence if t_a.confidence is not None else 0.5
        conf_b = t_b.confidence if t_b.confidence is not None else 0.5

        if conf_a >= conf_b:
            winner, loser = t_a, t_b
            winner_conf, loser_conf = conf_a, conf_b
        else:
            winner, loser = t_b, t_a
            winner_conf, loser_conf = conf_b, conf_a

        logger.info(f"Contradiction resolved: kept ({winner.subject} --[{winner.predicate}]--> {winner.obj}, conf={winner_conf:.2f}), "
                     f"removed ({loser.subject} --[{loser.predicate}]--> {loser.obj}, conf={loser_conf:.2f})")
        deleted_ids.add(loser.id)
        db.delete(loser)
        resolved += 1

    if resolved > 0:
        db.commit()

    return resolved
