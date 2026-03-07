"""
Categorize v7.jsonl training data into eval-aligned categories.

Maps the messy 455 tags + 1,888 untagged pairs into the 18 eval categories
so we can train and evaluate subject-by-subject.

Usage:
    python scripts/categorize_data.py
    python scripts/categorize_data.py --output loras/training_data/v7_categorized.jsonl
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

INPUT = Path("loras/training_data/v7.jsonl")
OUTPUT = Path("loras/training_data/v7_categorized.jsonl")

# Map to the 18 eval categories + "other"
EVAL_CATEGORIES = [
    "python", "algorithms", "design_patterns", "systems", "web",
    "cpp", "rust", "go", "testing", "javascript",
    "database", "security", "devops", "hive_sdk", "hive_layer2",
    "hive_economics", "hive_architecture", "hive_security",
]

# Keywords/patterns for classification (checked against instruction + tag)
CATEGORY_RULES = [
    # Hive subcategories (check first — most specific)
    ("hive_security", [r"\bhive\b.*\b(secur|key|auth|sign|permiss)", r"hive.*private.key", r"hive.*account.*security"]),
    ("hive_economics", [r"\bhive\b.*\b(reward|econom|inflation|vest|hbd|witness.pay|power.up|power.down|delegat)", r"hive.*token"]),
    ("hive_layer2", [r"\bhive\b.*\b(layer.?2|engine|sidechain|smart.contract|hive.engine|splinterland|tribaldex)", r"hive.*dapp"]),
    ("hive_architecture", [r"\bhive\b.*\b(archit|consensus|block.produc|witness|node|api.node|dpos|chain)", r"hive.*protocol"]),
    ("hive_sdk", [r"\bhive\b", r"\bbeem\b", r"hivesigner", r"dhive", r"hive.?blockchain", r"hive.*api", r"steemit", r"hive.*custom.json"]),

    # Languages
    ("rust", [r"\brust\b", r"\bcargo\b", r"\bfn\s+\w+", r"impl\s+\w+", r"\.rs\b", r"rust.*struct", r"borrow.checker"]),
    ("go", [r"\bgo\b(?:lang)?", r"\bgoroutine", r"func\s+\w+\(", r"\.go\b", r"go.*channel", r"go.*interface"]),
    ("cpp", [r"\bc\+\+\b", r"\bcpp\b", r"#include\s*<", r"std::", r"\.cpp\b", r"\.hpp\b", r"\btemplate\s*<"]),
    ("javascript", [r"\bjavascript\b", r"\bjs\b", r"\bnode\.?js\b", r"\bnpm\b", r"\btypescript\b", r"\bts\b",
                     r"\breact\b", r"\bvue\b", r"\bangular\b", r"\bnext\.?js\b", r"\bexpress\b",
                     r"\.jsx?\b", r"\.tsx?\b", r"\basync\s+function\b", r"\bconst\s+\w+\s*="]),

    # Domains
    ("algorithms", [r"\balgorithm\b", r"\bsort\b", r"\bbinary.search\b", r"\btree\b", r"\bgraph\b",
                     r"\bdynamic.program", r"\brecurs", r"\bbfs\b", r"\bdfs\b", r"\blinked.list\b",
                     r"\bstack\b", r"\bqueue\b", r"\bhash.?map\b", r"\bheap\b", r"\btrie\b",
                     r"\bcomplexity\b", r"\bbig.o\b", r"\bO\(n"]),
    ("design_patterns", [r"\bdesign.pattern\b", r"\bfactory\b", r"\bsingleton\b", r"\bobserver\b",
                          r"\bstrategy.pattern\b", r"\bdecorator.pattern\b", r"\badapter.pattern\b",
                          r"\bSOLID\b", r"\bdependency.inject", r"\binterface.segreg",
                          r"\barchitect.*pattern", r"\bMVC\b", r"\bMVVM\b"]),
    ("systems", [r"\bsystem.design\b", r"\bdistribut", r"\bmicroservice", r"\bscalab",
                  r"\bload.balanc", r"\bcaching\b", r"\bmessage.queue\b", r"\bkafka\b",
                  r"\brabbitmq\b", r"\bredis\b", r"\brate.limit", r"\bcircuit.break",
                  r"\bevent.driven\b", r"\bcqrs\b", r"\bevent.sourc"]),
    ("web", [r"\bweb\b", r"\bhttp\b", r"\brest\b.*\bapi\b", r"\bgraphql\b", r"\bwebsocket\b",
              r"\bflask\b", r"\bdjango\b", r"\bfastapi\b", r"\bcors\b", r"\boauth\b",
              r"\bjwt\b", r"\bswagger\b", r"\bopenapi\b", r"\bhtml\b", r"\bcss\b",
              r"\bfrontend\b", r"\bfull.?stack\b"]),
    ("testing", [r"\btest\b", r"\bunit.test\b", r"\bpytest\b", r"\bjest\b", r"\bmocha\b",
                  r"\btdd\b", r"\bmock\b", r"\bstub\b", r"\bfixture\b", r"\bcoverage\b",
                  r"\bintegration.test\b", r"\be2e\b", r"\bcypress\b", r"\bplaywright\b"]),
    ("database", [r"\bdatabase\b", r"\bsql\b", r"\bpostgre", r"\bmysql\b", r"\bmongo",
                   r"\bordering\b.*\bindex", r"\bindex\b.*\bquery", r"\bjoin\b",
                   r"\bnormali[sz]", r"\borm\b", r"\bsqlalchemy\b", r"\bprisma\b",
                   r"\bmigrat\b.*\bdatab", r"\bnosql\b", r"\bredis\b"]),
    ("security", [r"\bsecur", r"\bvulnerab", r"\bencrypt", r"\bauth\b", r"\bpassword\b",
                   r"\bxss\b", r"\bsql.inject", r"\bcsrf\b", r"\bcryptograph",
                   r"\bhash\b.*\bpassword", r"\bsalt\b", r"\bowasp\b", r"\bpentesting\b"]),
    ("devops", [r"\bdevops\b", r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b", r"\bci/?cd\b",
                 r"\bgithub.actions\b", r"\bjenkins\b", r"\bterraform\b", r"\bansible\b",
                 r"\bhelm\b", r"\bmonitoring\b", r"\bprometheus\b", r"\bgrafana\b",
                 r"\binfrastructure.as.code\b", r"\bIaC\b", r"\bobservab"]),

    # Python last (broad catch — many things involve Python)
    ("python", [r"\bpython\b", r"\bpip\b", r"\bvenv\b", r"\bpandas\b", r"\bnumpy\b",
                 r"\bflask\b", r"\bdjango\b", r"\basyncio\b", r"\bdecorator\b",
                 r"\bclass\s+\w+.*:", r"\bdef\s+\w+\(", r"\.py\b"]),
]


def classify(instruction: str, tag: str) -> str:
    """Classify a training pair into one of the eval categories."""
    text = (instruction + " " + tag).lower()

    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return category

    return "other"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default=str(OUTPUT))
    parser.add_argument("--dry-run", action="store_true", help="Just show stats, don't write")
    args = parser.parse_args()

    pairs = []
    with open(INPUT) as f:
        for line in f:
            pairs.append(json.loads(line))

    stats = Counter()
    for pair in pairs:
        tag = pair.get("metadata", {}).get("tag", "")
        category = classify(pair["instruction"], tag)
        pair["metadata"]["eval_category"] = category
        stats[category] += 1

    print(f"Total: {len(pairs)} pairs")
    print(f"\nCategory distribution:")
    for cat, count in stats.most_common():
        pct = 100 * count / len(pairs)
        marker = " *" if cat in EVAL_CATEGORIES else ""
        print(f"  {cat:25s}: {count:5d} ({pct:5.1f}%){marker}")

    eval_total = sum(stats[c] for c in EVAL_CATEGORIES)
    print(f"\nEval-aligned: {eval_total} ({100*eval_total/len(pairs):.1f}%)")
    print(f"Other: {stats['other']} ({100*stats['other']/len(pairs):.1f}%)")

    if not args.dry_run:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        print(f"\nWritten to {output_path}")

        # Also write per-category files
        cat_dir = output_path.parent / "by_category"
        cat_dir.mkdir(exist_ok=True)
        by_cat = {}
        for pair in pairs:
            cat = pair["metadata"]["eval_category"]
            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append(pair)

        for cat, cat_pairs in by_cat.items():
            cat_file = cat_dir / f"{cat}.jsonl"
            with open(cat_file, "w") as f:
                for pair in cat_pairs:
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            print(f"  {cat_file}: {len(cat_pairs)} pairs")


if __name__ == "__main__":
    main()
