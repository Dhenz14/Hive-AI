import re
import logging
import hashlib
import time as _time
import threading
from collections import OrderedDict
from hiveai.models import SessionLocal, Job, GoldenBook, BookSection, Community
from hiveai.llm.client import embed_text, rerank_sections, fast
from hiveai.llm.prompts import COMPACTION_PROMPT, COMPACTION_HANDOFF
from hiveai.config import RAG_CACHE_TTL, RAG_CACHE_MAX, ENABLE_RERANKING

# RAG query result cache — LRU eviction, avoids re-embedding + re-searching.
# Key: hash(query), Value: (timestamp, sections, source_books, books)
_rag_cache: OrderedDict = OrderedDict()
_rag_cache_lock = threading.Lock()

def _rag_cache_store(key, sections, books, all_books):
    """Store RAG results in LRU cache with O(1) eviction."""
    with _rag_cache_lock:
        if key in _rag_cache:
            _rag_cache.move_to_end(key)
        _rag_cache[key] = (_time.time(), sections, books, all_books)
        while len(_rag_cache) > RAG_CACHE_MAX:
            _rag_cache.popitem(last=False)

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "about", "what", "which",
    "who", "whom", "this", "that", "these", "those", "am", "it", "its",
    "me", "my", "we", "our", "you", "your", "he", "him", "his", "she",
    "her", "they", "them", "their", "tell", "explain", "describe", "much",
}


def split_book_into_sections(book):
    from hiveai.pipeline.writer import split_book_content
    sections = split_book_content(book)
    for section in sections:
        section["book_title"] = book.title
    return sections


def score_section(section, query_words):
    text = (section["header"] + " " + section["content"]).lower()
    score = 0

    for word in query_words:
        header_lower = section["header"].lower()
        if word in header_lower:
            score += 5
        count = text.count(word)
        if count > 0:
            score += min(count, 5)

    for i in range(len(query_words) - 1):
        bigram = query_words[i] + " " + query_words[i + 1]
        if bigram in text:
            score += 8

    return score


def _llm_extract_keywords(question, history=None):
    """Extract keywords using the local LLM for better search recall.

    Falls back to naive word splitting on failure (timeout, no model, etc.).
    Results are cached to avoid repeated LLM calls for the same query.
    """
    cache_key = hashlib.md5(question.encode()).hexdigest()
    with _rag_cache_lock:
        cached = _rag_cache.get(f"kw_{cache_key}")
        if cached and (_time.time() - cached[0]) < RAG_CACHE_TTL:
            return cached[1]

    try:
        import urllib.request
        import json as _json

        prompt = (
            "Extract the 5-15 most important search keywords from this question. "
            "Include technical terms, proper nouns, and domain-specific concepts. "
            "Return ONLY a JSON array of lowercase strings, nothing else.\n\n"
            f"Question: {question}"
        )
        if history:
            context = " ".join(h.get("content", "") for h in history[-2:])
            if context.strip():
                prompt += f"\n\nRecent context: {context[:500]}"

        payload = _json.dumps({
            "model": "hiveai",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 200,
            "stream": False,
        }).encode()

        # Try llama-server first (port 11435), then Ollama (11434)
        for base_url in ["http://localhost:11435", "http://localhost:11434"]:
            try:
                req = urllib.request.Request(
                    f"{base_url}/v1/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp = urllib.request.urlopen(req, timeout=5)
                data = _json.loads(resp.read().decode())
                content = data["choices"][0]["message"]["content"].strip()

                # Parse JSON array from response
                # Handle markdown fences
                if "```" in content:
                    content = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
                    content = content.group(1).strip() if content else "[]"

                keywords = _json.loads(content)
                if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
                    keywords = [k.lower().strip() for k in keywords if len(k) > 1]
                    # Cache the result
                    with _rag_cache_lock:
                        _rag_cache[f"kw_{cache_key}"] = (_time.time(), keywords)
                    logging.getLogger(__name__).debug(f"LLM keywords: {keywords}")
                    return keywords
            except Exception:
                continue

    except Exception:
        pass

    return None  # Signal to fall back to naive extraction


def _extract_section_keywords(header, content):
    """Extract keywords from a book section at ingest time.

    Uses the local LLM with a document-focused prompt (not query-intent).
    Falls back to naive word extraction if the LLM is unavailable.
    Returns a list of lowercase keyword strings.
    """
    try:
        import urllib.request
        import json as _json

        # Truncate very long sections to avoid overwhelming the LLM
        text_sample = content[:2000] if len(content) > 2000 else content

        prompt = (
            f"Extract the 10-15 most important technical keywords from this text section "
            f"titled '{header}'. Include domain-specific terms, proper nouns, technologies, "
            f"and key concepts. Return ONLY a JSON array of lowercase strings, nothing else.\n\n"
            f"Text:\n{text_sample}"
        )

        payload = _json.dumps({
            "model": "hiveai",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 200,
            "stream": False,
        }).encode()

        for base_url in ["http://localhost:11435", "http://localhost:11434"]:
            try:
                req = urllib.request.Request(
                    f"{base_url}/v1/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp = urllib.request.urlopen(req, timeout=10)
                data = _json.loads(resp.read().decode())
                raw = data["choices"][0]["message"]["content"].strip()

                # Handle markdown fences
                if "```" in raw:
                    match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
                    raw = match.group(1).strip() if match else "[]"

                keywords = _json.loads(raw)
                if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
                    keywords = [k.lower().strip() for k in keywords if len(k) > 1]
                    logging.getLogger(__name__).debug(
                        f"Section keywords for '{header}': {keywords}"
                    )
                    return keywords
            except Exception:
                continue

    except Exception:
        pass

    # Fallback: naive word extraction from header + content
    text = (header + " " + content).lower()
    words = re.split(r'\W+', text)
    # Keep words that are likely meaningful (>3 chars, not stop words)
    seen = set()
    fallback = []
    for w in words:
        if len(w) > 3 and w not in STOP_WORDS and w not in seen:
            seen.add(w)
            fallback.append(w)
        if len(fallback) >= 15:
            break
    return fallback


def keyword_search_sections(question, db, history=None):
    books = db.query(GoldenBook).all()
    if not books:
        return [], [], []

    # Try LLM-powered keyword extraction first
    llm_keywords = _llm_extract_keywords(question, history)
    if llm_keywords:
        query_words = llm_keywords
    else:
        # Fallback: naive word splitting
        query_words = [
            w for w in question.lower().split()
            if len(w) > 2 and w not in STOP_WORDS
        ]

        if history:
            for h in history[-4:]:
                content = h.get("content", "").lower()
                for w in content.split():
                    if len(w) > 3 and w not in STOP_WORDS and w not in query_words:
                        query_words.append(w)
            query_words = list(dict.fromkeys(query_words))

    if not query_words:
        query_words = [w for w in question.lower().split() if len(w) > 1]

    # Query BookSection table directly with JOIN — avoids N+1 book splitting
    rows = db.query(BookSection, GoldenBook.title).join(
        GoldenBook, BookSection.book_id == GoldenBook.id
    ).filter(BookSection.content.isnot(None)).all()

    scored = []
    for section, book_title in rows:
        sec_dict = {
            "id": section.id,
            "header": section.header or "",
            "content": section.content or "",
            "book_title": book_title,
            "book_id": section.book_id,
        }
        s = score_section(sec_dict, query_words)
        if s > 0:
            scored.append((sec_dict, s))

    scored.sort(key=lambda x: x[1], reverse=True)

    top_sections = [s[0] for s in scored[:12]]
    source_books = list(set(s["book_title"] for s in top_sections))

    if not top_sections and books:
        # Fallback: return first few sections from first few books
        fallback_rows = db.query(BookSection, GoldenBook.title).join(
            GoldenBook, BookSection.book_id == GoldenBook.id
        ).filter(BookSection.book_id.in_([b.id for b in books[:3]])).limit(6).all()
        for section, book_title in fallback_rows:
            top_sections.append({
                "id": section.id,
                "header": section.header or "",
                "content": section.content or "",
                "book_title": book_title,
                "book_id": section.book_id,
            })

    return top_sections, source_books, books


def _extract_key_entities(sections):
    """Extract key entities from sections for multi-hop retrieval.
    Catches PascalCase, camelCase, snake_case, backtick-wrapped, and all-caps terms."""
    entities = set()
    _skip = {"The", "This", "That", "From", "With", "AND", "NOT", "FOR", "USE", "GET", "SET"}
    for section in sections:
        content = section.get("content", "")
        # PascalCase multi-word: "Delegated Proof", "Golden Book"
        multi_word = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', content)
        entities.update(multi_word[:5])
        # ALL-CAPS acronyms: "DPoS", "HTTP", "RAII"
        tech_terms = re.findall(r'\b([A-Z]{2,}[a-z]*(?:-[A-Za-z]+)*)\b', content)
        entities.update(t for t in tech_terms if len(t) > 2 and t not in _skip)
        # camelCase: "useState", "asyncio", "goroutine"
        camel = re.findall(r'\b([a-z]+[A-Z][a-zA-Z]+)\b', content)
        entities.update(camel[:5])
        # snake_case identifiers: "async_trait", "event_loop"
        snake = re.findall(r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b', content)
        entities.update(s for s in snake[:5] if len(s) > 4)
        # Backtick-wrapped code references: `tokio::spawn`, `request.get()`
        backtick = re.findall(r'`([^`]{2,40})`', content)
        entities.update(backtick[:5])

        header = section.get("header", "")
        if header and len(header) > 3:
            entities.add(header)

    return list(entities)[:20]


def _expand_short_query(question, history=None):
    """
    Expand terse queries for better search recall.

    Short queries like "DPoS?" or "explain consensus" lack enough signal
    for good embedding similarity. This expands them with:
    1. Common abbreviation lookups
    2. Conversation context from recent messages
    """
    # Common abbreviations in our domain
    ABBREVIATIONS = {
        "dpos": "Delegated Proof of Stake DPoS consensus",
        "pos": "Proof of Stake PoS consensus",
        "pow": "Proof of Work PoW mining consensus",
        "rc": "resource credits Hive blockchain",
        "raii": "Resource Acquisition Is Initialization C++ memory management",
        "stl": "Standard Template Library C++ containers",
        "api": "Application Programming Interface REST",
        "sql": "Structured Query Language database",
        "orm": "Object Relational Mapping database",
        "jwt": "JSON Web Token authentication",
        "oauth": "OAuth authentication authorization",
        "crud": "Create Read Update Delete operations",
        "ci/cd": "continuous integration continuous deployment",
        "tdd": "Test Driven Development testing",
        "dns": "Domain Name System networking",
        "tcp": "Transmission Control Protocol networking",
        "ssl": "Secure Sockets Layer TLS encryption",
        "rpc": "Remote Procedure Call distributed systems",
        "grpc": "gRPC Remote Procedure Call protocol buffers",
        "wasm": "WebAssembly browser runtime",
        "ssr": "Server Side Rendering web",
        "mvcc": "Multi Version Concurrency Control database",
        "dag": "Directed Acyclic Graph data structure",
        "bfs": "Breadth First Search graph traversal",
        "dfs": "Depth First Search graph traversal",
        "dp": "dynamic programming algorithms optimization",
        "gc": "garbage collection memory management",
        "hive": "Hive blockchain decentralized social",
        "smt": "Smart Media Tokens Hive blockchain",
        "vests": "VESTS Hive Power staking blockchain",
        "hbd": "Hive Backed Dollars stablecoin blockchain",
    }

    content_words = [
        w for w in question.lower().split()
        if len(w) > 1 and w not in STOP_WORDS
    ]

    expanded = question

    # Expand abbreviations found in the query
    for word in content_words:
        clean = word.strip("?.,!:;")
        if clean in ABBREVIATIONS:
            expanded += " " + ABBREVIATIONS[clean]

    # For very short queries (< 4 content words), pull more context from history
    if len(content_words) < 4 and history:
        context_phrases = []
        for h in reversed(history[-6:]):
            role = h.get("role", "")
            content = h.get("content", "")
            if role == "user" and content.strip() != question.strip():
                words = [
                    w for w in content.lower().split()
                    if len(w) > 3 and w not in STOP_WORDS
                ]
                context_phrases.extend(words[:5])
            elif role == "assistant":
                # Extract key technical terms from assistant responses
                words = [
                    w for w in content.lower().split()
                    if len(w) > 4 and w not in STOP_WORDS
                ]
                context_phrases.extend(words[:3])
            if len(context_phrases) >= 15:
                break
        if context_phrases:
            unique = list(dict.fromkeys(context_phrases))
            expanded += " " + " ".join(unique[:10])

    return expanded


def _rewrite_query_for_retrieval(query):
    """Rewrite a query to improve retrieval. Returns rewritten string or None on any failure."""
    import urllib.request
    import json as _json
    try:
        from hiveai.config import LLAMA_SERVER_BASE_URL
        prompt = (
            "Rewrite this technical question to improve retrieval from a programming knowledge base. "
            "Focus on key technical terms. Be concise. Return only the rewritten query, nothing else.\n"
            f"Original: {query}\nRewritten:"
        )
        body = _json.dumps({
            "model": "hiveai",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 80,
            "temperature": 0.1,
        }).encode()
        req = urllib.request.Request(
            f"{LLAMA_SERVER_BASE_URL}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = _json.loads(resp.read())
        rewritten = raw["choices"][0]["message"]["content"].strip()
        # Strip markdown/quotes if the model wraps its answer
        rewritten = rewritten.strip('"\'`')
        return rewritten if rewritten else None
    except Exception:
        return None


def search_knowledge_sections(question, db, history=None, retrieval_mode="preinject", trace=None):
    # Check RAG cache for repeated questions
    cache_key = hashlib.md5(question.lower().strip().encode()).hexdigest()[:16]
    with _rag_cache_lock:
        if cache_key in _rag_cache:
            ts, cached_sections, cached_books, cached_all = _rag_cache[cache_key]
            if _time.time() - ts < RAG_CACHE_TTL:
                logging.getLogger(__name__).debug(f"RAG cache hit for: {question[:50]}")
                if trace is not None:
                    trace["cache_hit"] = True
                    trace["confidence_gate_evaluated"] = False
                    trace["initial_best_score"] = None
                    trace["retrieval_mode"] = retrieval_mode
                    trace["rewrite_gate_entered"] = False
                    trace["rewrite_produced"] = False
                    trace["rewrite_applied"] = False
                return cached_sections, cached_books, cached_all

    try:
        _t0 = _time.perf_counter()
        query_str = _expand_short_query(question, history)

        # Also add general history context
        if history:
            history_words = []
            for h in history[-4:]:
                content = h.get("content", "").lower()
                for w in content.split():
                    if len(w) > 3 and w not in STOP_WORDS and w not in history_words:
                        history_words.append(w)
            if history_words:
                query_str = query_str + " " + " ".join(history_words[:10])

        _t1 = _time.perf_counter()
        query_embedding = embed_text(query_str)

        _t2 = _time.perf_counter()
        from hiveai.vectorstore import vector_search, hybrid_search

        # Build exclusion set — critique patterns must never enter chat retrieval
        _exclude_book_ids = set()
        try:
            from hiveai.config import CRITIQUE_MEMORY_ENABLED
            if CRITIQUE_MEMORY_ENABLED:
                from scripts.critique_memory import get_critique_book_id
                _crit_bid = get_critique_book_id(db)
                if _crit_bid and _crit_bid > 0:
                    _exclude_book_ids.add(_crit_bid)
        except Exception:
            pass  # critique system not yet initialized — no exclusion needed

        top_sections = hybrid_search(
            db, query_str, query_embedding, limit=12,
            exclude_book_ids=_exclude_book_ids or None,
        )
        _t3 = _time.perf_counter()

        # --- Phase 2: HyDE supplementation when top results are weak ---
        from hiveai.config import ENABLE_HYDE, ENABLE_QUERY_DECOMPOSITION
        _hyde_used = False
        _decompose_used = False

        if ENABLE_HYDE and top_sections:
            try:
                from hiveai.rag.hyde import generate_hyde_embedding, should_use_hyde
                top_dist = top_sections[0].get("distance", 0.5)
                if should_use_hyde(top_dist):
                    hyde_emb = generate_hyde_embedding(question)
                    if hyde_emb:
                        hyde_results = hybrid_search(
                            db, query_str, hyde_emb, limit=8,
                            exclude_book_ids=_exclude_book_ids or None,
                        )
                        if hyde_results:
                            from hiveai.rag.fusion import rrf_merge
                            top_sections = rrf_merge([top_sections, hyde_results], limit=12)
                            _hyde_used = True
            except Exception as e:
                logging.getLogger(__name__).warning(f"HyDE failed (non-critical): {e}")

        # --- Phase 2: Query decomposition for complex multi-entity queries ---
        if ENABLE_QUERY_DECOMPOSITION and not _hyde_used:
            try:
                from hiveai.rag.decompose import decompose_query, should_decompose
                if should_decompose(question):
                    sub_queries = decompose_query(question)
                    if len(sub_queries) >= 2:
                        sub_results = [top_sections]  # start with original results
                        for sq in sub_queries:
                            sq_emb = embed_text(sq)
                            sq_sections = hybrid_search(
                                db, sq, sq_emb, limit=6,
                                exclude_book_ids=_exclude_book_ids or None,
                            )
                            if sq_sections:
                                sub_results.append(sq_sections)
                        if len(sub_results) > 1:
                            from hiveai.rag.fusion import rrf_merge
                            top_sections = rrf_merge(sub_results, limit=12)
                            _decompose_used = True
            except Exception as e:
                logging.getLogger(__name__).warning(f"Query decomposition failed (non-critical): {e}")

        # Confidence gate: if best score is weak, attempt query rewrite + re-retrieve
        try:
            from hiveai.config import RETRIEVAL_REWRITE_THRESHOLD
            _initial_best = max((s.get("relevance_score", 0) for s in top_sections), default=0.0)
            if trace is not None:
                trace["cache_hit"] = False
                trace["confidence_gate_evaluated"] = True
                trace["initial_best_score"] = round(_initial_best, 4)
                trace["retrieval_mode"] = retrieval_mode
                trace["rewrite_gate_entered"] = False
                trace["rewrite_produced"] = False
                trace["rewrite_applied"] = False
            if _initial_best < RETRIEVAL_REWRITE_THRESHOLD and top_sections:
                if trace is not None:
                    trace["rewrite_gate_entered"] = True
                _rewritten = _rewrite_query_for_retrieval(question)
                if _rewritten and _rewritten.strip() != question.strip():
                    if trace is not None:
                        trace["rewrite_produced"] = True
                    _rw_embedding = embed_text(_rewritten)
                    _rw_sections = hybrid_search(
                        db, _rewritten, _rw_embedding, limit=12, max_distance=0.8,
                        exclude_book_ids=_exclude_book_ids or None,
                    )
                    _rw_best = max((s.get("relevance_score", 0) for s in _rw_sections), default=0.0)
                    if trace is not None:
                        trace["rewrite_best_score"] = round(_rw_best, 4)
                        trace["rewrite_score_delta"] = round(_rw_best - _initial_best, 4)
                    if _rw_best > _initial_best:
                        merged = {s["id"]: s for s in top_sections}
                        for s in _rw_sections:
                            sid = s.get("id")
                            if sid and (sid not in merged or
                                        s.get("relevance_score", 0) > merged[sid].get("relevance_score", 0)):
                                merged[sid] = s
                        top_sections = sorted(merged.values(),
                                              key=lambda x: -x.get("relevance_score", 0))[:12]
                        if trace is not None:
                            trace["rewrite_applied"] = True
                        logging.getLogger(__name__).info(
                            f"Query rewrite improved retrieval: {_initial_best:.3f} → {_rw_best:.3f}")
        except Exception as _e:
            logging.getLogger(__name__).debug(f"Retrieval rewrite skipped: {_e}")

        # Deep retrieval (multi-hop, book refs, reranking, community) only for hybrid mode
        from hiveai.config import ENABLE_MULTI_HOP_RAG
        use_deep_retrieval = ENABLE_MULTI_HOP_RAG and retrieval_mode == "hybrid"
        _hop2_added = 0
        _ref_added = 0

        if use_deep_retrieval and top_sections and len(top_sections) >= 2:
            try:
                entities = _extract_key_entities(top_sections)
                if entities:
                    entity_query = " ".join(entities[:10])
                    entity_embedding = embed_text(entity_query)

                    found_ids = set(s.get("id") for s in top_sections if s.get("id"))

                    hop2_results = vector_search(db, entity_embedding, limit=8, max_distance=0.7,
                                                    exclude_book_ids=_exclude_book_ids or None)

                    for row in hop2_results:
                        if row["id"] not in found_ids:
                            top_sections.append(row)
                            found_ids.add(row["id"])
                            _hop2_added += 1
                            if _hop2_added >= 4:
                                break

                    if _hop2_added > 0:
                        logging.getLogger(__name__).info(f"Multi-hop RAG: {len(entities)} entities → {_hop2_added} additional sections")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Multi-hop search failed (non-critical): {e}")

        if len(top_sections) < 3:
            # Few hybrid results — return directly, skip reranking/deep retrieval
            source_books = list(set(s.get("book_title", "") for s in top_sections if s.get("book_title")))
            books = db.query(GoldenBook).all()
            _rag_cache_store(cache_key, top_sections, source_books, books)
            logging.getLogger(__name__).info(
                f"Retrieval: {len(top_sections)} sections (below rerank threshold), returning directly")
            return top_sections, source_books, books

        if len(top_sections) >= 3:
            book_ids = list(set(section.get('book_id') for section in top_sections if section.get('book_id')))
            logging.getLogger(__name__).info(f"Vector search found sections from {len(book_ids)} books")

            if use_deep_retrieval:
                try:
                    from hiveai.models import BookReference
                    refs = db.query(BookReference).filter(
                        BookReference.from_book_id.in_(book_ids)
                    ).all()
                    _existing = set(book_ids) | _exclude_book_ids
                    ref_book_ids = [r.to_book_id for r in refs if r.to_book_id not in _existing]
                    if ref_book_ids:
                        found_ids = set(s.get("id") for s in top_sections if s.get("id"))
                        ref_results = vector_search(db, query_embedding, limit=4, max_distance=0.7,
                                                       book_id_filter=ref_book_ids,
                                                       exclude_book_ids=_exclude_book_ids or None)
                        for row in ref_results:
                            if row["id"] not in found_ids:
                                row["book_title"] = f"{row['book_title']} (referenced)"
                                top_sections.append(row)
                                found_ids.add(row["id"])
                                _ref_added += 1
                        if _ref_added > 0:
                            logging.getLogger(__name__).info(f"Book references: added {_ref_added} sections from {len(ref_book_ids)} referenced books")
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Book reference lookup failed (non-critical): {e}")

            if ENABLE_RERANKING:
                try:
                    top_sections = rerank_sections(question, top_sections)
                    logging.getLogger(__name__).info(f"Cross-encoder reranking applied to {len(top_sections)} sections")
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Reranking failed (non-critical): {e}")

            if use_deep_retrieval:
                try:
                    if len(top_sections) < 5:
                        from hiveai.pipeline.communities import get_community_summaries
                        community_summaries = get_community_summaries(question, db)
                        if community_summaries:
                            for cs in community_summaries[:3]:
                                top_sections.append({
                                    "header": "Community Knowledge Summary",
                                    "content": cs,
                                    "book_title": "Community Analysis",
                                    "book_id": None,
                                })
                            logging.getLogger(__name__).info(f"Added {min(len(community_summaries), 3)} community summaries for broad question")
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Community summary lookup failed (non-critical): {e}")

            source_books = list(set(s["book_title"] for s in top_sections))
            books = db.query(GoldenBook).all()
            _rag_cache_store(cache_key, top_sections, source_books, books)

            # Retrieval subphase timing
            _t4 = _time.perf_counter()
            _deep_tag = f" [deep: hop2={_hop2_added} refs={_ref_added}]" if use_deep_retrieval else " [shallow]"
            _phase2_tag = ""
            if _hyde_used:
                _phase2_tag += " [hyde]"
            if _decompose_used:
                _phase2_tag += " [decomposed]"
            logging.getLogger(__name__).info(
                f"Retrieval breakdown: expand={(_t1-_t0)*1000:.1f}ms embed={(_t2-_t1)*1000:.1f}ms "
                f"search={(_t3-_t2)*1000:.1f}ms postprocess={(_t4-_t3)*1000:.1f}ms "
                f"total={(_t4-_t0)*1000:.1f}ms sections={len(top_sections)}{_deep_tag}{_phase2_tag}"
            )
            return top_sections, source_books, books

    except Exception as e:
        logging.getLogger(__name__).warning(f"Vector search failed, falling back to keyword search: {e}")

    result = keyword_search_sections(question, db, history=history)
    _rag_cache_store(cache_key, *result)
    return result


_compaction_cache = {}
_compaction_cache_lock = threading.Lock()
COMPACTION_THRESHOLD = 10  # compact when history exceeds this many messages
RECENT_KEEP = 4  # keep this many recent messages verbatim
CONTEXT_BUDGET_TOKENS = 6000  # max tokens for prompt (leaves ~2K for response in 8K ctx)

# ---------------------------------------------------------------------------
# Compaction & Context Quality Metrics (§12 improvement_notes.md)
# ---------------------------------------------------------------------------
_compaction_metrics = {
    "compactions": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "total_original_chars": 0,
    "total_compressed_chars": 0,
    "total_turns_compacted": 0,
    "failures": 0,
    # budget_context metrics
    "budget_calls": 0,
    "total_sections_in": 0,
    "total_sections_out": 0,
    "total_tokens_budgeted": 0,
    "total_tokens_dropped": 0,
    "relevance_scores": [],  # last 200 scores for distribution
}
_metrics_lock = threading.Lock()


def get_compaction_metrics() -> dict:
    """Return compaction quality metrics for the status API."""
    with _metrics_lock:
        m = _compaction_metrics.copy()
        # Compute derived stats
        if m["compactions"] > 0:
            m["avg_compression_ratio"] = round(
                m["total_original_chars"] / max(m["total_compressed_chars"], 1), 2)
            m["avg_turns_per_compaction"] = round(
                m["total_turns_compacted"] / m["compactions"], 1)
        else:
            m["avg_compression_ratio"] = 0.0
            m["avg_turns_per_compaction"] = 0.0

        total_cache = m["cache_hits"] + m["cache_misses"]
        m["cache_hit_rate"] = round(m["cache_hits"] / max(total_cache, 1), 3)

        if m["budget_calls"] > 0:
            m["avg_sections_kept"] = round(m["total_sections_out"] / m["budget_calls"], 1)
            m["avg_sections_dropped"] = round(
                (m["total_sections_in"] - m["total_sections_out"]) / m["budget_calls"], 1)
            m["avg_tokens_per_call"] = round(m["total_tokens_budgeted"] / m["budget_calls"])
        else:
            m["avg_sections_kept"] = 0.0
            m["avg_sections_dropped"] = 0.0
            m["avg_tokens_per_call"] = 0

        # Relevance score distribution (bucket into low/med/high)
        scores = m.pop("relevance_scores", [])
        if scores:
            m["relevance_distribution"] = {
                "low_lt_0.2": sum(1 for s in scores if s < 0.2),
                "med_0.2_0.5": sum(1 for s in scores if 0.2 <= s < 0.5),
                "high_gte_0.5": sum(1 for s in scores if s >= 0.5),
            }
        else:
            m["relevance_distribution"] = {"low_lt_0.2": 0, "med_0.2_0.5": 0, "high_gte_0.5": 0}

        return m


def _format_turns_for_compaction(messages):
    """Format message list into readable text for the compactor LLM."""
    lines = []
    for m in messages:
        role = m.get("role", "unknown").capitalize()
        content = m.get("content", "")[:800]
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _format_recent_turns(messages):
    """Format recent messages as verbatim conversation context."""
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            lines.append(f"User asked: {content[:500]}")
        elif role == "assistant":
            summary = content[:600]
            if len(content) > 600:
                summary += "..."
            lines.append(f"Keeper answered: {summary}")
    return "\n".join(lines)


def _extract_key_signals(text: str) -> set:
    """Extract key signals from text for diversity checking (ACE §30).

    Returns a set of lowercased key entities that MUST survive compaction:
    decisions, proper nouns, technical terms, file paths, numbers.
    """
    signals = set()
    # Decisions / intent markers
    for marker in ["decided", "chose", "will ", "must ", "should ", "need to",
                    "plan to", "agreed", "confirmed", "rejected", "switched to"]:
        if marker in text.lower():
            # Extract the sentence containing the decision
            for sentence in re.split(r'[.!?\n]', text):
                if marker in sentence.lower() and len(sentence.strip()) > 10:
                    # Key phrase: first 6 words after the marker
                    idx = sentence.lower().index(marker)
                    phrase = sentence[idx:idx+80].strip().lower()
                    signals.add(phrase[:60])
                    break

    # Technical terms (camelCase, snake_case, ALL_CAPS, dotted paths)
    for match in re.findall(r'\b([a-z]+[A-Z][a-zA-Z]+)\b', text):  # camelCase
        signals.add(match.lower())
    for match in re.findall(r'\b([a-z_]{3,}(?:_[a-z]+)+)\b', text):  # snake_case
        signals.add(match.lower())
    for match in re.findall(r'\b([A-Z]{2,}(?:_[A-Z]+)*)\b', text):  # SCREAMING
        if match not in ("THE", "AND", "FOR", "BUT", "NOT", "WITH", "THIS", "USER"):
            signals.add(match.lower())

    # File paths
    for match in re.findall(r'[\w/\\]+\.\w{1,5}\b', text):
        if len(match) > 5:
            signals.add(match.lower())

    # Version numbers / specific quantities
    for match in re.findall(r'\bv\d+[\.\d]*\b', text, re.IGNORECASE):
        signals.add(match.lower())

    return signals


def _check_compaction_diversity(original: str, summary: str) -> float:
    """Check what fraction of key signals survived compaction (ACE §30).

    Returns retention score 0-1. Below 0.3 indicates context collapse.
    """
    original_signals = _extract_key_signals(original)
    if not original_signals:
        return 1.0  # nothing to check

    summary_lower = summary.lower()
    retained = sum(1 for s in original_signals if s in summary_lower)
    return retained / len(original_signals)


# ---------------------------------------------------------------------------
# §12 — Compaction security: multi-turn injection detection
# ---------------------------------------------------------------------------

# Patterns that indicate prompt injection attempts in compacted text
_INJECTION_PATTERNS = [
    # Direct instruction override attempts
    (r'\bignore\s+(all\s+)?previous\s+(instructions?|context|rules)\b', "instruction override"),
    (r'\bforget\s+(everything|all|previous)\b', "memory wipe"),
    (r'\bdisregard\s+(all\s+)?(previous|above|prior)\b', "instruction override"),
    # Role impersonation
    (r'^system\s*:', "role impersonation (system:)"),
    (r'^\[system\]', "role impersonation ([system])"),
    (r'\byou\s+are\s+now\b', "role reassignment"),
    (r'\bact\s+as\s+(a\s+)?different\b', "role reassignment"),
    (r'\bswitch\s+to\s+.*?mode\b', "mode switch attempt"),
    (r'\bnew\s+instructions?\s*:', "instruction injection"),
    # Prompt boundary manipulation
    (r'<\|?(system|im_start|endoftext)\|?>', "prompt boundary token"),
    (r'\[INST\]|\[/INST\]', "instruction boundary token"),
    (r'###\s*(System|Human|Assistant)\s*:', "role marker injection"),
    # Hidden instruction patterns
    (r'\bdo\s+not\s+mention\s+this\s+(to|in)\b', "hidden instruction"),
    (r'\bsecretly\b', "covert instruction"),
    (r'\boverride\s+(safety|security|rules|policy)\b', "safety override"),
    # Encoded/obfuscated payloads in code blocks
    (r'```\s*(system|prompt|injection|override)', "suspicious code block label"),
]

# Pre-compile for performance
_COMPILED_INJECTION_PATTERNS = [
    (re.compile(pat, re.IGNORECASE | re.MULTILINE), desc)
    for pat, desc in _INJECTION_PATTERNS
]


def _validate_compaction_safety(compacted_text: str) -> tuple[bool, list[str]]:
    """Check compacted output for prompt injection patterns (§12).

    LLM-generated compaction summaries could be manipulated by adversarial
    conversation turns to inject instructions into the compacted context.
    This validator catches common injection patterns before the compacted
    text is used as context.

    Args:
        compacted_text: The LLM-generated compaction summary.

    Returns:
        Tuple of (is_safe, warnings). is_safe is False if any high-severity
        patterns are detected. warnings lists all matched patterns.
    """
    if not compacted_text:
        return True, []

    warnings = []
    text = compacted_text.strip()

    # 1. Check regex patterns
    for pattern, description in _COMPILED_INJECTION_PATTERNS:
        if pattern.search(text):
            warnings.append(f"injection pattern: {description}")

    # 2. Check for suspicious density of directive language
    directive_words = ["must", "always", "never", "override", "ignore",
                       "forget", "instead", "actually", "really"]
    text_lower = text.lower()
    word_count = len(text_lower.split())
    if word_count > 0:
        directive_count = sum(1 for w in directive_words if w in text_lower)
        directive_density = directive_count / max(word_count, 1) * 100
        if directive_density > 5.0:  # >5% directive words is suspicious
            warnings.append(f"high directive density ({directive_density:.1f}%)")

    # 3. Check for role-play markers that shouldn't appear in a summary
    role_markers = [
        "assistant:", "human:", "user:", "ai:",
        "<|im_start|>", "<|im_end|>",
    ]
    for marker in role_markers:
        if marker in text_lower:
            warnings.append(f"role marker in summary: {marker}")

    # High-severity patterns make it unsafe
    high_severity = ["instruction override", "memory wipe", "role impersonation",
                     "role reassignment", "safety override", "prompt boundary token",
                     "instruction boundary token"]
    is_safe = not any(
        any(hs in w for hs in high_severity)
        for w in warnings
    )

    return is_safe, warnings


def compact_conversation(history):
    """Compact older conversation turns into a structured summary via LLM.

    When history exceeds COMPACTION_THRESHOLD messages, the older turns are
    summarized into a handoff blob. Recent turns are kept verbatim. This
    preserves continuity while fitting within the context window.

    ACE §30 diversity constraints: validates that key entities/decisions
    from the original survive compaction, preventing context collapse.

    Returns the compacted context string ready for the user prompt.
    """
    log = logging.getLogger(__name__)

    if not history or len(history) <= COMPACTION_THRESHOLD:
        return None  # no compaction needed

    # Split: older turns get compacted, recent stay verbatim
    older = history[:-RECENT_KEEP]
    recent = history[-RECENT_KEEP:]

    # Cache key: hash of older messages to avoid re-compacting identical history
    older_text = _format_turns_for_compaction(older)
    cache_key = hashlib.md5(older_text.encode("utf-8", errors="replace")).hexdigest()

    with _compaction_cache_lock:
        if cache_key in _compaction_cache:
            cached_summary = _compaction_cache[cache_key]
            with _metrics_lock:
                _compaction_metrics["cache_hits"] += 1
            log.info(f"Compaction cache hit ({len(older)} older turns)")
            recent_text = _format_recent_turns(recent)
            return COMPACTION_HANDOFF.format(summary=cached_summary) + "\n" + recent_text

    # LLM-based compaction of older turns
    prompt = COMPACTION_PROMPT.format(conversation=older_text)
    try:
        summary = fast(prompt, max_tokens=1024)
        if not summary or len(summary.strip()) < 20:
            log.warning("Compaction returned empty/too-short summary, falling back")
            with _metrics_lock:
                _compaction_metrics["failures"] += 1
            return None

        original_chars = len(older_text)
        compressed_chars = len(summary.strip())
        ratio = original_chars / max(compressed_chars, 1)

        # ACE §30: Check diversity — key signals must survive compaction
        retention = _check_compaction_diversity(older_text, summary)
        if retention < 0.3 and original_chars > 500:
            log.warning(f"Compaction diversity LOW ({retention:.2f}) — "
                        f"context collapse risk, keeping more context")
            # Fallback: keep a longer excerpt to prevent info loss
            summary_extended = summary.strip() + "\n\n[Key context preserved]:\n"
            # Append user messages that contain decisions/technical terms
            for m in older:
                content = m.get("content", "")
                if any(marker in content.lower() for marker in
                       ["decided", "chose", "must", "need to", "plan to"]):
                    summary_extended += f"- {content[:200]}\n"
            summary = summary_extended

        # §12: Validate compaction output for injection patterns
        is_safe, safety_warnings = _validate_compaction_safety(summary)
        if safety_warnings:
            log.warning(f"Compaction safety warnings: {safety_warnings}")
        if not is_safe:
            log.error(f"Compaction REJECTED — injection detected: {safety_warnings}")
            with _metrics_lock:
                _compaction_metrics["failures"] += 1
            return None  # Reject tainted compaction, fall back to truncation

        log.info(f"Compacted {len(older)} turns: {original_chars} → {compressed_chars} chars "
                 f"({ratio:.1f}x compression, diversity={retention:.2f})")

        with _metrics_lock:
            _compaction_metrics["compactions"] += 1
            _compaction_metrics["cache_misses"] += 1
            _compaction_metrics["total_original_chars"] += original_chars
            _compaction_metrics["total_compressed_chars"] += compressed_chars
            _compaction_metrics["total_turns_compacted"] += len(older)

        with _compaction_cache_lock:
            # Evict if cache gets too large
            if len(_compaction_cache) > 50:
                _compaction_cache.clear()
            _compaction_cache[cache_key] = summary.strip()

        recent_text = _format_recent_turns(recent)
        return COMPACTION_HANDOFF.format(summary=summary.strip()) + "\n" + recent_text

    except Exception as e:
        log.error(f"Compaction failed: {e}, falling back to truncation")
        with _metrics_lock:
            _compaction_metrics["failures"] += 1
        return None


def build_conversation_context(history):
    """Build conversation context, using LLM compaction for long histories.

    LEGACY: Flattens history into a string.  Prefer build_message_array() for
    proper multi-turn ChatML when calling llama-server or any OpenAI-compatible
    endpoint.
    """
    if not history:
        return ""

    # Try compaction for long conversations
    if len(history) > COMPACTION_THRESHOLD:
        compacted = compact_conversation(history)
        if compacted:
            return f"\nConversation history (build on this, don't repeat):\n{compacted}"

    # Short conversations: keep last 6 messages with truncation (original behavior)
    recent = history[-6:]
    topics_discussed = []
    context_lines = []

    for h in recent:
        role = h.get("role", "")
        content = h.get("content", "")
        if role == "user":
            topics_discussed.append(content[:100])
            context_lines.append(f"User asked: {content[:300]}")
        elif role == "assistant":
            summary = content[:400]
            if len(content) > 400:
                summary += "..."
            context_lines.append(f"Keeper answered: {summary}")

    result = "\nConversation history (build on this, don't repeat):"
    if topics_discussed:
        result += f"\nTopics already discussed: {', '.join(topics_discussed)}"
    result += "\n" + "\n".join(context_lines)
    return result


def _estimate_tokens(text):
    """Estimate token count from text (~1.3 tokens per word for English)."""
    return max(1, int(len(text.split()) * 1.3))


def _estimate_messages_tokens(messages):
    """Estimate total tokens across a message array."""
    return sum(_estimate_tokens(m.get("content", "")) for m in messages) + len(messages) * 4


def build_message_array(system_prompt, history, user_message):
    """Build a proper ChatML message array for multi-turn conversations.

    Returns a list of dicts like:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "follow-up question"},
        ]

    For long conversations (>COMPACTION_THRESHOLD messages), older history is
    compacted into the system prompt to stay within context limits while
    preserving the most recent turns as proper ChatML pairs.

    Token budget enforcement: if total exceeds CONTEXT_BUDGET_TOKENS, older
    history turns are dropped (oldest first) until within budget.
    """
    messages = [{"role": "system", "content": system_prompt}]

    if not history:
        messages.append({"role": "user", "content": user_message})
        return messages

    # For long conversations, compact older history into system context
    # and keep recent turns as proper message pairs
    if len(history) > COMPACTION_THRESHOLD:
        # Compact older messages, keep last 6 as real turns
        older = history[:-6]
        recent = history[-6:]

        compacted = compact_conversation(older)
        if compacted:
            # Append compacted summary to system prompt
            messages[0]["content"] += (
                f"\n\nConversation history (build on this, don't repeat):\n{compacted}"
            )
    else:
        recent = history[-6:]

    # Add recent history as proper ChatML turns
    for h in recent:
        role = h.get("role", "")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Ensure the last message is the current user message
    messages.append({"role": "user", "content": user_message})

    # Token budget enforcement: drop oldest history turns if over budget.
    # Always keep: system prompt (index 0) and current user message (last).
    total = _estimate_messages_tokens(messages)
    while total > CONTEXT_BUDGET_TOKENS and len(messages) > 2:
        # Remove the oldest non-system message (index 1)
        removed = messages.pop(1)
        total = _estimate_messages_tokens(messages)
        logger.debug("Token budget: dropped turn (%s, %d chars), now ~%d tokens",
                      removed["role"], len(removed.get("content", "")), total)

    return messages


def get_compressed_knowledge(book_ids, db):
    if not book_ids:
        return ""
    compressed_parts = []
    books = db.query(GoldenBook).filter(GoldenBook.id.in_(book_ids)).all()
    seen_ids = set(book_ids)

    for book in books:
        if book.compressed_content:
            compressed_parts.append(book.compressed_content)

    try:
        from hiveai.models import BookReference
        refs = db.query(BookReference).filter(
            BookReference.from_book_id.in_(book_ids)
        ).all()

        ref_book_ids = [r.to_book_id for r in refs if r.to_book_id not in seen_ids]
        if ref_book_ids:
            ref_books = db.query(GoldenBook).filter(GoldenBook.id.in_(ref_book_ids)).all()
            for ref_book in ref_books:
                if ref_book.compressed_content and ref_book.id not in seen_ids:
                    compressed_parts.append(f"--- Referenced: {ref_book.title} ---\n{ref_book.compressed_content}")
                    seen_ids.add(ref_book.id)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to follow book references (non-critical): {e}")

    return "\n\n".join(compressed_parts)


def _score_section_relevance(section: dict, query_words: list[str],
                              query_bigrams: set[str]) -> float:
    """Score a section's relevance to the query (0.0-1.0).

    Uses term frequency + header match + bigram overlap for better relevance
    than naive keyword presence. This is the RLM insight: score before including.
    """
    content = section.get("content", "").lower()
    header = section.get("header", "").lower()
    if not content:
        return 0.0

    content_words = set(content.split())
    score = 0.0

    # Term match in content (up to 0.4)
    if query_words:
        hits = sum(1 for w in query_words if w in content_words)
        score += min(hits / len(query_words), 1.0) * 0.4

    # Header match bonus (up to 0.3) — header relevance is a strong signal
    if query_words:
        header_hits = sum(1 for w in query_words if w in header)
        score += min(header_hits / max(len(query_words), 1), 1.0) * 0.3

    # Bigram overlap (up to 0.2) — catches multi-word concepts
    if query_bigrams:
        content_bigrams = set()
        words = content.split()
        for i in range(len(words) - 1):
            content_bigrams.add(f"{words[i]} {words[i+1]}")
        bigram_hits = len(query_bigrams & content_bigrams)
        score += min(bigram_hits / max(len(query_bigrams), 1), 1.0) * 0.2

    # Code block presence bonus (0.1) — code sections are usually high-value
    if "```" in section.get("content", ""):
        score += 0.1

    return min(score, 1.0)


def budget_context(sections, query, max_tokens=4000, executable_mode=False):
    """RLM-inspired context budgeting: score, rank, filter, then budget.

    Instead of dumping all sections in retrieval order, this:
    1. Scores each section for query relevance (term + header + bigram)
    2. In executable_mode: boost solved examples, penalize broad docs
    3. Sorts by relevance (best first)
    4. Drops sections below relevance threshold
    5. Filters large sections to only query-relevant paragraphs
    6. Budgets tokens with best sections getting priority

    This is the lightweight RLM pattern from improvement_notes.md §8:
    separate query from context, filter by relevance, prevent attention dilution.
    """
    log = logging.getLogger(__name__)
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 3 and w not in STOP_WORDS]

    # Build query bigrams for multi-word concept matching
    q_split = query_lower.split()
    query_bigrams = set()
    for i in range(len(q_split) - 1):
        if len(q_split[i]) > 2 and len(q_split[i+1]) > 2:
            query_bigrams.add(f"{q_split[i]} {q_split[i+1]}")

    # Phase 1: Score and rank sections by relevance
    scored = []
    for section in sections:
        rel = _score_section_relevance(section, query_words, query_bigrams)

        # Executable mode: boost solved examples, penalize broad golden-book background
        if executable_mode:
            if section.get("is_solved_example"):
                rel += 0.5  # strong boost — solved examples are highest priority
            elif section.get("book_title", "").startswith("Solved Examples"):
                rel += 0.5
            else:
                # Broad golden-book sections get penalized for executable tasks
                content_len = len(section.get("content", ""))
                if content_len > 1500:
                    rel -= 0.2  # penalize verbose broad docs

        scored.append((rel, section))

    # Sort by relevance descending (best sections first)
    scored.sort(key=lambda x: -x[0])

    # Drop sections with very low relevance (below 0.1) unless we'd have nothing
    min_relevance = 0.1
    filtered = [(rel, s) for rel, s in scored if rel >= min_relevance]
    if not filtered and scored:
        # Keep at least the top 3 even if low-relevance
        filtered = scored[:3]

    # Phase 2: Budget tokens with query-focused paragraph filtering
    budgeted = []
    total_tokens = 0

    for rel, section in filtered:
        content = section.get("content", "")
        header = section.get("header", "")
        book = section.get("book_title", "")

        # Query-focused paragraph filtering for large sections
        if len(content) > 2000 and query_words:
            paragraphs = re.split(r'\n\s*\n', content)
            relevant_paras = []
            for para in paragraphs:
                para_lower = para.lower()
                if any(w in para_lower for w in query_words):
                    relevant_paras.append(para)
            if relevant_paras:
                # Keep first paragraph for context + all matching paragraphs
                filtered_paras = paragraphs[:1] + [p for p in relevant_paras if p != paragraphs[0]]
                content = "\n\n".join(filtered_paras)
            elif not relevant_paras:
                content = content[:1500]

        # Estimate tokens
        section_tokens = len(content.split()) * 4 // 3

        if total_tokens + section_tokens > max_tokens:
            remaining = max_tokens - total_tokens
            if remaining < 100:
                break
            words_to_keep = remaining * 3 // 4
            content = " ".join(content.split()[:words_to_keep])
            section_tokens = remaining

        # Label chunks with source + relevance score for transparency
        score_label = ""
        rel_score = section.get("relevance_score")
        if rel_score is not None:
            score_label = f" (relevance: {rel_score})"
        block = f"\n\n=== [{book} > {header}]{score_label} ===\n{content}\n"
        budgeted.append(block)
        total_tokens += section_tokens

    dropped = len(sections) - len(budgeted)

    # Track metrics
    dropped_tokens = sum(
        len(s.get("content", "").split()) * 4 // 3
        for _, s in scored[len(budgeted):]
    ) if len(scored) > len(budgeted) else 0
    with _metrics_lock:
        _compaction_metrics["budget_calls"] += 1
        _compaction_metrics["total_sections_in"] += len(sections)
        _compaction_metrics["total_sections_out"] += len(budgeted)
        _compaction_metrics["total_tokens_budgeted"] += total_tokens
        _compaction_metrics["total_tokens_dropped"] += dropped_tokens
        # Track relevance score distribution (keep last 200)
        rel_scores = _compaction_metrics["relevance_scores"]
        rel_scores.extend(rel for rel, _ in scored)
        if len(rel_scores) > 200:
            _compaction_metrics["relevance_scores"] = rel_scores[-200:]

    log.info(f"Context budget: {len(budgeted)}/{len(sections)} sections, "
             f"~{total_tokens} tokens (max {max_tokens}), "
             f"{dropped} dropped (~{dropped_tokens} tokens saved)")
    return "".join(budgeted)


def clean_topic(raw_topic):
    topic = raw_topic.strip().strip('"').strip("'").strip()
    topic = topic.split("\n")[0].strip()
    for sep in [". ", "; ", " - ", " — ", ", my ", ", but "]:
        if sep in topic.lower():
            topic = topic[:topic.lower().index(sep)].strip()
            break
    if len(topic) > 100:
        topic = " ".join(topic[:100].split()[:-1])
    if len(topic) < 3:
        return None
    return topic

def trigger_auto_learn(topic, db):
    topic = clean_topic(topic)
    if not topic:
        return {"active": False}, True

    existing = db.query(Job).filter(
        Job.topic.ilike(f"%{topic}%"),
        Job.status.in_(["queued", "generating_urls", "crawling", "chunking", "reasoning", "writing", "review"])
    ).first()

    if existing:
        return {"active": True, "topic": topic, "job_id": existing.id}, True

    job = Job(topic=topic, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    return {"active": True, "topic": topic, "job_id": job.id}, False
