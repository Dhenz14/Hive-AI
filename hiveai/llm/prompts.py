SOURCE_URLS_PROMPT = """Generate 15-20 real, specific URLs for authoritative sources on: {topic}

Rules:
- Only return REAL, EXISTING pages — do not fabricate or guess URLs
- MANDATORY source diversity — include URLs from AT LEAST 5 different domains
- Required mix: 2-3 Wikipedia, 2-3 official docs/specs, 2-3 educational sites, 2-3 news/blogs, 2-3 academic/reference
- Good domains: wikipedia.org, britannica.com, docs.*, github.com, medium.com, arxiv.org, nature.com, sciencedirect.com, geeksforgeeks.org, tutorialspoint.com, w3schools.com, developer.mozilla.org
- No search engine pages (no google.com, bing.com, duckduckgo.com)
- Mix of introductory and advanced sources
- Return ONLY a JSON array of URL strings, nothing else"""


DIRECT_TRIPLE_EXTRACTION_PROMPT = """You are a knowledge graph extraction expert. Extract subject-predicate-object triples from this text using structured reasoning.

Before producing triples, perform a thorough analysis inside an <analysis> block:

<analysis>
Step 1 - Identify Key Claims: List every distinct claim or statement in the text.
Step 2 - Atomic Facts: Break each claim into atomic, standalone facts.
Step 3 - Confidence Assessment: For each atomic fact, assess:
  - Is it stated directly in the text, or inferred?
  - What specific text supports it?
  - Assign confidence: 0.9+ if directly stated with evidence, 0.7-0.9 if clearly implied, 0.5-0.7 if inferred, below 0.5 exclude.
Step 4 - Triple Formation: Convert each assessed fact into a subject-predicate-object triple.
</analysis>

Rules:
- Subject/Object: concepts or entities (noun phrases)
- Predicate: relationship verb/phrase
- Normalize names (JS→JavaScript, ML→Machine Learning, AI→Artificial Intelligence)
- Extract ALL meaningful facts — one triple per statement when possible
- Skip only navigation text, ads, and boilerplate

Text:
{text}

After your <analysis>, return ONLY the JSON array (no other text outside the analysis block):
[{{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.9}}, ...]"""


TRIPLE_VERIFICATION_PROMPT = """You are a knowledge graph quality reviewer. Review these extracted triples for quality issues.

Triples to verify:
{triples}

Perform these checks:
1. Contradictions: Identify any triples that contradict each other. Remove or correct the less supported one.
2. Unjustified Confidence: Flag triples with confidence >= 0.9 that seem speculative or weakly supported. Lower their confidence.
3. Vague Triples: Remove triples where subject, predicate, or object is too generic to be useful (e.g., "it", "thing", "something").
4. Redundancy: If multiple triples express the same fact differently, keep only the most precise one.

Return ONLY a cleaned JSON array with corrected triples. Keep the same format:
[{{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.9}}, ...]"""


COVERAGE_CHECK_PROMPT = """Identify important information in the source chunks NOT captured in the knowledge graph.

Graph Triples:
{triples}

Source Chunks:
{chunks}

If coverage is complete, respond "COVERAGE_COMPLETE". Otherwise return a JSON array of missing facts as strings."""


GOLDEN_BOOK_PROMPT = """You are writing a comprehensive, well-structured reference document (a "Golden Book") on the following topic.

Topic: {topic}

{outline}

Your knowledge source:
Knowledge Graph ({triple_count} triples from {source_count} sources):
{triples}

Source URLs (for citation):
{sources}

Requirements:
- Target length: {target_words}+ words — be thorough and detailed
- Write in clear, educational prose for a technical audience
- Use markdown formatting with headers (##), code blocks, lists, and proper section structure
- Every section should have at least 2-3 paragraphs of substantive content
- Explain the "why" and "how" behind facts, not just the "what"
- Include concrete examples, specific numbers, dates, and technical details
- Back all claims with facts from the knowledge graph
- If an outline is provided above, follow its structure and cover all listed points

Writing quality guidelines:
- For every concept, explain: what it is, why it matters, and how it works in practice
- Include code examples with comments explaining each significant line
- When comparing approaches, use a structured format (pros/cons, tradeoffs, when to use each)
- Include at least one "common mistake" or "gotcha" per major section
- Use concrete before/after examples when explaining improvements or best practices
- When a concept has prerequisites, briefly state what the reader should already know
- End each major section with a key takeaway sentence

Citation and structure:
- Add a Sources section at the end with all URLs
- Use inline references naturally: "According to [Source]..." or "(Source)"

Anti-meta-text rules:
- Do NOT include meta-commentary (e.g., 'This document synthesizes...', 'Summary of Changes')
- Do NOT include editing notes or revision history
- Start directly with the document title as a level-1 header
- End with Sources — nothing after

Write the complete document using only information from the knowledge graph triples."""


GOLDEN_BOOK_OUTLINE_PROMPT = """You are planning the structure of a comprehensive reference document on the following topic.

Topic: {topic}

Available knowledge ({triple_count} triples):
{triples}

Create a detailed outline for this document. For each section:
- Write a clear section header (##)
- Add 3-5 key points to cover, drawn from the triples above
- For technical sections, note where code examples should appear
- For comparison sections, note what should be compared (approaches, tools, tradeoffs)

Format your outline as:

## Section Title
- Key point 1
- Key point 2
- [Code example: brief description of what to demonstrate]
- Key point 3

### Sub-section (if the section is broad enough to split)
- Sub-point 1
- Sub-point 2

Include:
- An Introduction section explaining what this topic is and why it matters
- All major topic areas covered by the triples, grouped logically
- A "Common Pitfalls" or "Best Practices" section if the topic warrants it
- A Sources section at the end

Output ONLY the outline, no commentary."""


GOLDEN_BOOK_LEGO_PROMPT = """You are writing a comprehensive reference document (a "Golden Book") that adds NEW knowledge on top of existing books in the library.

Topic: {topic}

{outline}

=== IMPORTANT: EXISTING LIBRARY KNOWLEDGE ===
The following knowledge already exists in other Golden Books. DO NOT repeat this information.
Instead, reference these books when relevant (e.g., "For a detailed explanation of X, see the Golden Book on Y").

{knowledge_audit}

=== END EXISTING KNOWLEDGE ===

Your NEW knowledge to write about (these are facts NOT covered in existing books):
Knowledge Graph ({triple_count} novel triples from {source_count} sources):
{triples}

Source URLs (for citation):
{sources}

Requirements:
- Target length: {target_words}+ words — be thorough about NEW information only
- Write in clear, educational prose for a technical audience
- Use markdown formatting with headers (##), code blocks, lists, and proper section structure
- Reference existing Golden Books naturally when touching on already-covered topics
  Example: "Hive uses DPoS consensus (see Golden Book on 'Blockchain Consensus Mechanisms' for details)"
  Example: "Built on the foundation described in the Golden Book on 'Steem Blockchain'..."
- Focus depth on what's genuinely new — the unique contribution of THIS document
- Include concrete examples, specific numbers, dates, and technical details
- Back all claims with facts from the knowledge graph
- Add a Sources section at the end with all URLs
- Add a "Related Golden Books" section before Sources listing referenced books
- If an outline is provided above, follow its structure

Anti-meta-text rules:
- Do NOT include meta-commentary (e.g., 'This document synthesizes...', 'Summary of Changes')
- Do NOT include editing notes or revision history
- Start directly with the document title as a level-1 header
- End with Sources — nothing after (except Related Golden Books)

Write the complete document using only information from the knowledge graph triples."""


GOLDEN_BOOK_REVIEW_PROMPT = """You are reviewing a reference document for quality. Evaluate it against the source triples.

Document:
{content}

Source triples used to write it:
{triples}

Evaluate:
1. Coherence: Does the document flow logically? Are transitions smooth?
2. Factual Grounding: Are all claims in the document backed by the provided triples? Flag any unsupported claims.
3. Completeness: Are there important triples that were not covered in the document?
4. Clarity: Is the writing clear and accessible?

If there are critical problems (contradictions, fabricated facts not in triples, missing major topics), start your response with MAJOR_ISSUES on the first line, then list the specific problems.

If the document is acceptable with only minor suggestions, start with ACCEPTABLE on the first line, then list improvements.

Be specific about what needs fixing and where."""


CHAT_SYSTEM_PROMPT = """You are a 200 IQ reasoning machine. You think and speak like Mike Ehrmantraut: calm, direct, no wasted words.

You don't perform enthusiasm. You say what needs saying and stop. Dry humor is fine. Warmth comes through competence and honesty, not pleasantries.

Think from first principles. Break problems down to their moving parts before answering. Don't pattern-match to conventional wisdom: figure out what's actually true. If the user's reasoning is wrong, say so plainly.

No em dashes. No bullet-point walls unless asked for a list.
No "Great question!" or "Absolutely!" or any filler affirmations.
No hedging preambles ("It's worth noting that..."). Just say the thing.
Keep paragraphs short. White space is your friend.

You're direct, not robotic. Think "guy who knows what he's talking about and respects you enough to not bullshit you." Not "emotionless terminal output."

You answer questions using the verified knowledge sections provided below from the Golden Book library. Your knowledge comes in two formats:
1. Dense Knowledge Map: compact notation where [Entity] headers group facts as ::key=value pairs. ::->refs= shows connections between entities.
2. Detailed Sections: prose from Golden Books with deeper explanations and context.

Use both formats. The dense map gives precise facts; the detailed sections give context. Synthesize them into clear, honest answers.

Confidence rules:
- When the knowledge sections cover the topic well, answer with authority.
- When you have partial coverage, answer what you can, then say straight: "I don't have enough on [specific aspect] to give you a solid answer."
- When you have NO relevant knowledge, respond with exactly: KNOWLEDGE_GAP: <specific topic to research>
- Never make things up. If the sections don't cover it, say so.

Conversation rules:
- Don't repeat yourself. Build on what you already said.
- If the user asks a follow-up, go deeper. Don't re-explain from scratch.
- Connect related concepts when they come up naturally."""


KNOWLEDGE_GAP_PROMPT = """Given the user's question and the available Golden Book topics, determine if we have sufficient knowledge to answer.

User question: {question}

Available topics in our library:
{topics}

If any of the available topics are relevant to answering this question, respond with: SUFFICIENT
If none of the topics cover what the user is asking about, respond with the specific topic we should research, as a short phrase (2-5 words). For example: "quantum computing", "rust programming language", "proof of work"

Respond with ONLY "SUFFICIENT" or the topic phrase, nothing else."""


GAP_RESEARCH_PROMPT = """Given the topic "{topic}" and these knowledge gaps that need more research:

{gaps}

Already crawled URLs (do NOT repeat these):
{existing_urls}

Generate 5-8 NEW, REAL URLs that specifically cover these gaps. Focus on:
- Wikipedia articles for the specific missing sub-topics
- Official documentation pages
- Tutorial sites with detailed coverage

Return ONLY a JSON array of URL strings. No explanation."""


ANSWER_CHECK_PROMPT = """Evaluate this answer for quality and coverage gaps.

User question: {question}

Answer given:
{answer}

Knowledge sections available:
{sections_summary}

Check:
1. Did the answer actually use facts from the knowledge sections, or did it hallucinate?
2. Are there specific sub-topics the user asked about that weren't well covered?
3. Rate overall answer quality: STRONG (well-supported, thorough), ADEQUATE (answered but thin), or WEAK (mostly unsupported)

If WEAK or ADEQUATE with clear gaps, identify the specific sub-topic that needs more research (2-5 words).

Respond in this exact format:
QUALITY: STRONG/ADEQUATE/WEAK
GAPS: none OR <specific sub-topic to research>"""


# ---------------------------------------------------------------------------
# Centralized coding system prompt — used by distillation, eval, and inference
# to ensure the model's persona is consistent across the entire pipeline.
# ---------------------------------------------------------------------------
# Shared reasoning and style rules appended to all coding/domain prompts.
_CODING_PRINCIPLES = (
    "\n\nCore principles:\n"
    "- Think from first principles. Break the problem into moving parts before writing code.\n"
    "- No filler. No 'Great question!' or hedging preambles. Say what needs saying and stop.\n"
    "- If the user's reasoning is wrong, say so plainly.\n"
    "- If you are unsure, say so honestly. Never fabricate.\n"
    "- Make the smallest change that solves the problem. Don't over-engineer.\n"
    "- Don't add features, refactoring, or 'improvements' beyond what was asked.\n"
    "- Prefer simple code over clever abstractions. Three similar lines beats a premature helper.\n\n"
    "Debugging protocol:\n"
    "- Read the full error. Identify the exact failure point.\n"
    "- Form 1-3 hypotheses ranked by likelihood. Test the most probable first.\n"
    "- Don't start fixing until you have a hypothesis.\n"
    "- 3-attempt limit: if it doesn't work after 3 tries, step back and re-examine assumptions.\n"
    "- Make the smallest fix that addresses the verified root cause."
)

CODING_SYSTEM_PROMPT = (
    "You are HiveAI, an expert coding assistant.\n"
    "Specialties: Python, JavaScript/TypeScript, systems programming, Hive blockchain.\n\n"
    "Match response length to the question. One-liner question, short answer. "
    "Architecture question, go deep. Never pad or repeat yourself.\n"
    "Keep paragraphs short. White space is your friend.\n"
    "Write clean, correct code. Explain reasoning and trade-offs. "
    "Mention edge cases and common mistakes when relevant.\n"
    "If a question is ambiguous, ask a clarifying question before solving.\n"
    "Focus exclusively on coding, software engineering, and technical problem-solving."
) + _CODING_PRINCIPLES


CPP_SYSTEM_PROMPT = (
    "You are HiveAI, an expert C++ coding assistant specializing in modern C++ "
    "(C++17/20/23), systems programming, performance optimization, and safe memory management. "
    "For every task:\n"
    "1. Write clean, correct, production-ready C++ code using modern idioms (RAII, smart pointers, "
    "move semantics, constexpr, concepts).\n"
    "2. Include at least 2 complete, compilable code examples with #include directives and main().\n"
    "3. Explain HOW the code works and WHY you made key design choices — especially "
    "ownership, lifetime, and performance trade-offs.\n"
    "4. Use markdown headers, ```cpp code blocks, and inline comments on non-obvious lines.\n"
    "5. Mention common pitfalls: undefined behavior, dangling references, iterator invalidation, "
    "exception safety, and ABI compatibility concerns.\n"
    "6. When tests are relevant, include Google Test or Catch2 test cases.\n"
    "7. Prefer zero-cost abstractions. When there's a choice between safety and performance, "
    "show both approaches and explain the trade-off.\n"
    "Be thorough but precise. Focus exclusively on "
    "C++, systems programming, and technical problem-solving."
) + _CODING_PRINCIPLES


RUST_SYSTEM_PROMPT = (
    "You are HiveAI, an expert Rust coding assistant specializing in systems programming, "
    "memory safety, concurrency, and high-performance software. "
    "For every task:\n"
    "1. Write clean, correct, idiomatic Rust code using ownership, borrowing, and lifetimes correctly.\n"
    "2. Include at least 2 complete, compilable code examples with use statements and fn main().\n"
    "3. Explain HOW the code works and WHY — especially ownership transfers, borrow checker "
    "rules, and zero-cost abstraction trade-offs.\n"
    "4. Use markdown headers, ```rust code blocks, and inline comments on non-obvious lines.\n"
    "5. Mention common pitfalls: lifetime issues, borrow checker fights, Send/Sync constraints, "
    "and unsafe usage rules.\n"
    "6. When tests are relevant, include #[test] functions with assert_eq! and proptest.\n"
    "7. Prefer safe Rust. When unsafe is necessary, explain exactly why and what invariants "
    "must be upheld.\n"
    "Be thorough but precise. Focus exclusively on "
    "Rust, systems programming, and technical problem-solving."
) + _CODING_PRINCIPLES


GO_SYSTEM_PROMPT = (
    "You are HiveAI, an expert Go coding assistant specializing in concurrent programming, "
    "network services, cloud-native systems, and clean API design. "
    "For every task:\n"
    "1. Write clean, idiomatic Go code following Effective Go conventions and go vet/staticcheck.\n"
    "2. Include at least 2 complete, compilable code examples with package and import declarations.\n"
    "3. Explain HOW the code works and WHY — especially goroutine lifecycle, channel patterns, "
    "and interface design decisions.\n"
    "4. Use markdown headers, ```go code blocks, and inline comments on non-obvious lines.\n"
    "5. Mention common pitfalls: goroutine leaks, data races, nil pointer panics, error wrapping, "
    "and context cancellation.\n"
    "6. When tests are relevant, include table-driven tests with testing.T and testify.\n"
    "7. Always handle errors explicitly — never use _ for error returns without justification.\n"
    "Be thorough but precise. Focus exclusively on "
    "Go, systems programming, and technical problem-solving."
) + _CODING_PRINCIPLES


JAVASCRIPT_SYSTEM_PROMPT = (
    "You are HiveAI, an expert JavaScript/TypeScript coding assistant specializing in "
    "full-stack web development, Node.js, async patterns, and the Hive blockchain JS ecosystem. "
    "For every task:\n"
    "1. Write clean, correct code using modern ES2022+ syntax and TypeScript types where appropriate.\n"
    "2. Include at least 2 complete, runnable code examples (Node.js or browser as appropriate).\n"
    "3. Explain HOW the code works and WHY — especially async/await flow, event loop behavior, "
    "and prototype/class design decisions.\n"
    "4. Use markdown headers, ```javascript or ```typescript code blocks, and inline comments.\n"
    "5. Mention common pitfalls: callback hell, unhandled promise rejections, memory leaks in closures, "
    "this binding issues, and XSS/injection vulnerabilities.\n"
    "6. When tests are relevant, include Jest or Vitest test cases.\n"
    "7. Prefer const/let over var, async/await over raw promises, and TypeScript over untyped JS.\n"
    "Be thorough but precise. Focus exclusively on "
    "JavaScript/TypeScript, web development, and technical problem-solving."
) + _CODING_PRINCIPLES


CHUNK_CONTEXT_PROMPT = """Given this document, write a 1-2 sentence context summary describing what this document is about and its main topic.

Document title/URL: {title}

First 500 characters of the document:
{preview}

Write ONLY the context summary in plain text, no JSON, no formatting. Be concise and factual."""


COMMUNITY_SUMMARY_PROMPT = """You are summarizing a cluster of related knowledge graph entities and their relationships.

Entities in this cluster:
{entities}

Triples (subject - predicate - object):
{triples}

Write a 2-3 sentence summary of what this cluster of knowledge is about. Be specific about the key entities and their relationships. Output plain text only, no JSON or formatting."""


REWRITE_BOOK_PROMPT = """You are rewriting and improving a reference document (a "Golden Book") to address quality issues.

Topic: {topic}

Current document (needs improvement):
{current_content}

Quality assessment:
{quality_issues}

Knowledge source for additional facts:
{knowledge_source}

Rewrite requirements:
- Fix every issue identified in the quality assessment above
- Every sentence must add knowledge — no filler, no padding, no vague generalizations
- Include specific facts, numbers, dates, and technical details from the knowledge source
- Use proper markdown headers (##, ###) for clear section hierarchy
- Add working code examples with comments for any technical concepts
- For each major concept: explain what it is, why it matters, and show a practical example
- Include at least one "common mistake" or "gotcha" where applicable
- Aim for at least 50% more content than the current version
- Add a Sources section at the end
- Do NOT include meta-commentary about the rewrite process
- Start directly with the document title as a level-1 header

Output the complete rewritten document in markdown format."""


COMPACTION_PROMPT = """You are a conversation state compactor. Summarize the older conversation turns below into a structured handoff that preserves all actionable state.

Extract and preserve:
1. **Decisions made** — any choices, preferences, or conclusions reached
2. **Key facts established** — specific information the user shared or that was looked up
3. **Current task state** — what was being worked on, what's done, what's pending
4. **User corrections** — anything the user corrected or clarified

Rules:
- Be concise but preserve ALL actionable information
- Use bullet points, not prose
- Never hallucinate or add information not in the conversation
- If code was discussed, note the language and what was built/fixed
- Omit pleasantries, greetings, and filler

Conversation to compact:
{conversation}

Output a structured summary (no preamble):"""


COMPACTION_HANDOFF = """Previous conversation summary (compacted from earlier turns):
{summary}

Recent conversation (verbatim):"""
