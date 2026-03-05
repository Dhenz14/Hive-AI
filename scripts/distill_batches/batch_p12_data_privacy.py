PAIRS = [
    (
        "data-privacy/gdpr-anonymization-techniques",
        r"""Explain data privacy engineering techniques including GDPR compliance implementation, k-anonymity and differential privacy, data anonymization and pseudonymization pipelines, consent management systems, and right-to-erasure implementation patterns.""",
        r"""## Data Privacy Engineering: GDPR Compliance, Anonymization, and Erasure Patterns

**Data privacy** has shifted from a legal checkbox to a core engineering discipline. **Because** regulations like GDPR, CCPA, and LGPD impose significant penalties (up to 4% of global revenue), privacy must be designed into systems from the start — not bolted on afterward. The **trade-off** between data utility and privacy protection drives every architectural decision.

### K-Anonymity and Generalization

**K-anonymity** ensures that each record in a dataset is indistinguishable from at least k-1 other records with respect to quasi-identifiers (attributes that could identify someone when combined). **However**, k-anonymity alone is insufficient — it's vulnerable to homogeneity attacks where all records in a group have the same sensitive value.

```python
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum

class GeneralizationLevel(Enum):
    EXACT = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    SUPPRESSED = 4

@dataclass
class QuasiIdentifier:
    column: str
    hierarchy: dict[int, Callable]  # level -> generalization function
    max_level: int = 4

@dataclass
class AnonymizationConfig:
    k: int = 5                    # k-anonymity threshold
    l: int = 2                    # l-diversity threshold
    quasi_identifiers: list[QuasiIdentifier] = field(default_factory=list)
    sensitive_columns: list[str] = field(default_factory=list)
    max_suppression_rate: float = 0.05  # max 5% record suppression

class KAnonymizer:
    # Implements k-anonymity via generalization and suppression
    # Best practice: use generalization hierarchies specific to each attribute
    # Common mistake: over-generalizing, making the data useless

    def __init__(self, config: AnonymizationConfig):
        self.config = config

    def anonymize(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()

        # Iteratively generalize quasi-identifiers until k-anonymity is achieved
        # Trade-off: more generalization = better privacy but less utility
        qi_levels = {qi.column: 0 for qi in self.config.quasi_identifiers}

        while not self._check_k_anonymity(result, self.config.k):
            # Find the quasi-identifier causing most violations
            worst_qi = self._find_worst_quasi_identifier(result)
            if worst_qi is None:
                break

            # Generalize it one level
            qi = next(q for q in self.config.quasi_identifiers if q.column == worst_qi)
            current_level = qi_levels[worst_qi]

            if current_level >= qi.max_level:
                # Suppress remaining violating records
                # Pitfall: suppressing too many records biases the dataset
                violating = self._get_violating_records(result)
                suppression_rate = len(violating) / len(result)
                if suppression_rate <= self.config.max_suppression_rate:
                    result = result.drop(violating.index)
                break

            generalize_fn = qi.hierarchy[current_level + 1]
            result[worst_qi] = result[worst_qi].apply(generalize_fn)
            qi_levels[worst_qi] = current_level + 1

        return result

    def _check_k_anonymity(self, df: pd.DataFrame, k: int) -> bool:
        qi_columns = [qi.column for qi in self.config.quasi_identifiers]
        group_sizes = df.groupby(qi_columns).size()
        return group_sizes.min() >= k if len(group_sizes) > 0 else True

    def _check_l_diversity(self, df: pd.DataFrame, l: int) -> bool:
        # L-diversity: each group must have at least l distinct sensitive values
        # Therefore, it protects against homogeneity attacks
        qi_columns = [qi.column for qi in self.config.quasi_identifiers]
        for sensitive_col in self.config.sensitive_columns:
            for _, group in df.groupby(qi_columns):
                if group[sensitive_col].nunique() < l:
                    return False
        return True

    def _find_worst_quasi_identifier(self, df: pd.DataFrame) -> Optional[str]:
        qi_columns = [qi.column for qi in self.config.quasi_identifiers]
        worst = None
        max_violations = 0
        for col in qi_columns:
            others = [c for c in qi_columns if c != col]
            if others:
                violations = df.groupby(qi_columns).size()
                count = (violations < self.config.k).sum()
                if count > max_violations:
                    max_violations = count
                    worst = col
        return worst

    def _get_violating_records(self, df: pd.DataFrame) -> pd.DataFrame:
        qi_columns = [qi.column for qi in self.config.quasi_identifiers]
        sizes = df.groupby(qi_columns).transform("size")
        return df[sizes < self.config.k]

# Example generalization hierarchies
AGE_HIERARCHY = {
    1: lambda x: f"{(x // 5) * 5}-{(x // 5) * 5 + 4}",    # 5-year ranges
    2: lambda x: f"{(x // 10) * 10}-{(x // 10) * 10 + 9}",  # 10-year ranges
    3: lambda x: f"{(x // 20) * 20}-{(x // 20) * 20 + 19}",  # 20-year ranges
    4: lambda x: "*",  # suppressed
}

ZIP_HIERARCHY = {
    1: lambda x: str(x)[:4] + "*",    # mask last digit
    2: lambda x: str(x)[:3] + "**",   # mask last 2 digits
    3: lambda x: str(x)[:2] + "***",  # mask last 3 digits
    4: lambda x: "*****",             # suppressed
}
```

### Differential Privacy

**Differential privacy** provides a mathematically rigorous privacy guarantee: the output of a query is approximately the same whether or not any individual's data is included. This is stronger than k-anonymity **because** it protects against arbitrary auxiliary information.

```python
import numpy as np
from typing import Callable, Any

class DifferentialPrivacyEngine:
    # Implements the Laplace mechanism for differential privacy
    # Best practice: use the smallest epsilon that gives acceptable accuracy
    # because lower epsilon = stronger privacy but more noise

    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5):
        self.epsilon = epsilon  # privacy budget
        self.delta = delta      # probability of privacy breach
        self.budget_used = 0.0  # track total budget consumption

    def laplace_mechanism(
        self,
        true_value: float,
        sensitivity: float,
        epsilon: Optional[float] = None,
    ) -> float:
        # Add Laplace noise calibrated to sensitivity / epsilon
        # Sensitivity = max change in output when one record changes
        # Therefore, higher sensitivity requires more noise
        eps = epsilon or self.epsilon
        scale = sensitivity / eps
        noise = np.random.laplace(0, scale)
        self.budget_used += eps
        return true_value + noise

    def gaussian_mechanism(
        self,
        true_value: float,
        sensitivity: float,
        epsilon: Optional[float] = None,
        delta: Optional[float] = None,
    ) -> float:
        # Gaussian mechanism: (epsilon, delta)-DP
        # Trade-off: tighter concentration than Laplace but requires delta > 0
        eps = epsilon or self.epsilon
        dlt = delta or self.delta
        sigma = sensitivity * np.sqrt(2 * np.log(1.25 / dlt)) / eps
        noise = np.random.normal(0, sigma)
        self.budget_used += eps
        return true_value + noise

    def private_count(self, data: pd.DataFrame, condition: Callable) -> float:
        # Sensitivity of count = 1 (adding/removing one record changes count by 1)
        true_count = condition(data).sum()
        return self.laplace_mechanism(true_count, sensitivity=1.0)

    def private_mean(
        self,
        data: pd.Series,
        lower_bound: float,
        upper_bound: float,
    ) -> float:
        # Mean sensitivity = (upper - lower) / n
        # Common mistake: not clipping values to bounds before computing mean
        # because outliers increase sensitivity and thus noise
        clipped = data.clip(lower_bound, upper_bound)
        n = len(clipped)
        sensitivity = (upper_bound - lower_bound) / n
        true_mean = clipped.mean()
        return self.laplace_mechanism(true_mean, sensitivity)

    def private_histogram(
        self,
        data: pd.Series,
        bins: list,
        epsilon_per_bin: Optional[float] = None,
    ) -> dict[str, float]:
        # Each bin count has sensitivity 1
        # However, querying k bins uses k * epsilon budget (composition theorem)
        # Pitfall: not accounting for composition when running multiple queries
        eps = epsilon_per_bin or (self.epsilon / len(bins))
        histogram = {}
        for i in range(len(bins) - 1):
            label = f"{bins[i]}-{bins[i+1]}"
            true_count = ((data >= bins[i]) & (data < bins[i+1])).sum()
            noisy_count = max(0, self.laplace_mechanism(true_count, 1.0, eps))
            histogram[label] = round(noisy_count)
        return histogram

    def remaining_budget(self) -> float:
        return max(0, self.epsilon - self.budget_used)
```

### Right-to-Erasure (GDPR Article 17) Implementation

Implementing the **right to be forgotten** is one of the most technically challenging GDPR requirements, **because** data spreads across databases, caches, backups, logs, and third-party systems.

```python
from datetime import datetime
from typing import Optional
from enum import Enum
import asyncio

class ErasureStatus(Enum):
    REQUESTED = "requested"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"

@dataclass
class ErasureRequest:
    id: str
    subject_id: str  # user whose data should be erased
    requested_at: datetime
    status: ErasureStatus = ErasureStatus.REQUESTED
    systems_processed: dict[str, bool] = field(default_factory=dict)
    completion_deadline: Optional[datetime] = None  # GDPR: 30 days max
    retention_exceptions: list[str] = field(default_factory=list)

class DataErasureOrchestrator:
    # Coordinates erasure across all data stores
    # Best practice: maintain a central registry of all systems holding PII
    # Common mistake: forgetting about backups, logs, and analytics systems

    def __init__(self):
        self.data_stores: dict[str, "DataStoreAdapter"] = {}
        self.audit_logger = None

    def register_store(self, name: str, adapter: "DataStoreAdapter"):
        self.data_stores[name] = adapter

    async def execute_erasure(self, request: ErasureRequest) -> ErasureRequest:
        request.status = ErasureStatus.IN_PROGRESS

        # Step 1: Check for legal retention obligations
        # GDPR allows retention for legal obligations, public interest, etc.
        # Therefore, not all data must be deleted
        exempt_stores = await self._check_retention_obligations(request.subject_id)
        request.retention_exceptions = exempt_stores

        # Step 2: Execute erasure in parallel across all stores
        tasks = []
        for store_name, adapter in self.data_stores.items():
            if store_name in exempt_stores:
                request.systems_processed[store_name] = True  # exempt
                continue
            tasks.append(self._erase_from_store(store_name, adapter, request))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 3: Check results
        all_success = True
        for store_name, result in zip(
            [s for s in self.data_stores if s not in exempt_stores],
            results,
        ):
            if isinstance(result, Exception):
                request.systems_processed[store_name] = False
                all_success = False
            else:
                request.systems_processed[store_name] = result

        request.status = (
            ErasureStatus.COMPLETED if all_success
            else ErasureStatus.PARTIALLY_COMPLETED
        )

        # Step 4: Audit trail (must be kept even after erasure)
        # Pitfall: deleting the audit log of the erasure itself
        await self._log_erasure_audit(request)

        return request

    async def _erase_from_store(
        self,
        store_name: str,
        adapter: "DataStoreAdapter",
        request: ErasureRequest,
    ) -> bool:
        try:
            # Soft delete first, then hard delete after verification
            # Trade-off: soft delete is reversible but still holds data
            await adapter.soft_delete(request.subject_id)
            # Verify the data is no longer accessible
            remaining = await adapter.find_subject_data(request.subject_id)
            if remaining:
                await adapter.hard_delete(request.subject_id)
            return True
        except Exception as e:
            return False

    async def _check_retention_obligations(self, subject_id: str) -> list[str]:
        # Check legal retention requirements
        # e.g., financial records must be kept for 7 years
        exempt = []
        # This would check against a retention policy database
        return exempt

    async def _log_erasure_audit(self, request: ErasureRequest):
        # Minimal audit: only store that erasure happened, not the erased data
        # Best practice: use a separate audit store with restricted access
        pass

class ConsentManager:
    # Tracks user consent for different processing purposes
    # GDPR requires: specific, informed, unambiguous, freely given consent

    def __init__(self, db):
        self.db = db

    async def record_consent(
        self,
        subject_id: str,
        purpose: str,
        granted: bool,
        ip_address: str,
        user_agent: str,
    ):
        # Store consent with full provenance
        # However, pre-checked boxes are not valid consent under GDPR
        await self.db.insert("consent_records", {
            "subject_id": subject_id,
            "purpose": purpose,
            "granted": granted,
            "timestamp": datetime.utcnow(),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "version": await self._get_policy_version(purpose),
        })

    async def check_consent(self, subject_id: str, purpose: str) -> bool:
        # Get the latest consent record for this subject and purpose
        record = await self.db.find_latest(
            "consent_records",
            {"subject_id": subject_id, "purpose": purpose},
        )
        if not record:
            return False
        # Check if consent was granted and policy hasn't changed since
        current_version = await self._get_policy_version(purpose)
        if record["version"] != current_version:
            return False  # Policy changed — need re-consent
        return record["granted"]

    async def _get_policy_version(self, purpose: str) -> str:
        return "v2.1"  # Would come from a policy version store
```

### Key Takeaways

- **K-anonymity** prevents re-identification by ensuring group sizes >= k — **however** it's vulnerable to homogeneity attacks, so combine with **l-diversity**
- **Differential privacy** provides mathematical guarantees — the **trade-off** is between epsilon (privacy budget) and data utility (noise level)
- **Common mistake**: not accounting for composition when running multiple DP queries — each query consumes privacy budget
- **Right-to-erasure** requires a data registry of all systems holding PII — **because** data spreads across databases, caches, backups, and third parties
- **Best practice**: use soft delete → verify → hard delete for erasure, with audit logging that persists
- **Pitfall**: treating privacy as a one-time implementation — **therefore** build continuous monitoring for data flows and consent validity
"""
    ),
    (
        "data-privacy/pii-detection-redaction",
        r"""Explain PII detection and redaction systems including NER-based entity recognition, regex pattern matching for structured PII, context-aware redaction strategies, reversible tokenization for data utility preservation, and audit logging for compliance.""",
        r"""## PII Detection and Redaction: Entity Recognition, Tokenization, and Compliance

**Personally Identifiable Information (PII)** detection and redaction is a critical component of data privacy engineering. **Because** PII can appear in unstructured text (logs, support tickets, comments), structured data, and even ML model outputs, a comprehensive detection system must combine multiple approaches. The **trade-off** between aggressive redaction (higher privacy) and minimal redaction (higher data utility) must be calibrated per use case.

### Multi-Layer PII Detection

**Best practice**: combine rule-based regex patterns for structured PII (SSN, credit cards, emails) with NER models for unstructured PII (names, addresses). Neither approach alone is sufficient — regex misses context-dependent PII while NER models miss structured patterns.

```python
import re
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum

class PIIType(Enum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    PERSON_NAME = "person_name"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    PASSPORT = "passport"
    CUSTOM = "custom"

@dataclass
class PIIDetection:
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float
    detector: str  # which detector found it

@dataclass
class PIIDetectorConfig:
    enabled_types: list[PIIType] = field(default_factory=lambda: list(PIIType))
    min_confidence: float = 0.7
    # Context window for NER disambiguation
    context_window: int = 50
    # Custom patterns for domain-specific PII
    custom_patterns: dict[str, str] = field(default_factory=dict)

class RegexPIIDetector:
    # Rule-based detection for structured PII patterns
    # Common mistake: only using regex — misses names and context-dependent PII
    # However, regex is essential for structured patterns that NER models miss

    PATTERNS = {
        PIIType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        PIIType.PHONE: r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
        PIIType.SSN: r'\b\d{3}-\d{2}-\d{4}\b',
        PIIType.CREDIT_CARD: r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        PIIType.IP_ADDRESS: r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        PIIType.DATE_OF_BIRTH: r'\b(?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b',
    }

    def __init__(self, config: PIIDetectorConfig):
        self.config = config
        self.compiled = {
            pii_type: re.compile(pattern)
            for pii_type, pattern in self.PATTERNS.items()
            if pii_type in config.enabled_types
        }
        # Add custom patterns
        for name, pattern in config.custom_patterns.items():
            self.compiled[PIIType.CUSTOM] = re.compile(pattern)

    def detect(self, text: str) -> list[PIIDetection]:
        detections = []
        for pii_type, pattern in self.compiled.items():
            for match in pattern.finditer(text):
                # Validate matches to reduce false positives
                if self._validate_match(match.group(), pii_type):
                    detections.append(PIIDetection(
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        pii_type=pii_type,
                        confidence=0.95,  # Regex matches are high confidence
                        detector="regex",
                    ))
        return detections

    def _validate_match(self, text: str, pii_type: PIIType) -> bool:
        if pii_type == PIIType.CREDIT_CARD:
            return self._luhn_check(text.replace("-", "").replace(" ", ""))
        if pii_type == PIIType.IP_ADDRESS:
            parts = text.split(".")
            return all(0 <= int(p) <= 255 for p in parts)
        return True

    def _luhn_check(self, number: str) -> bool:
        # Luhn algorithm validates credit card numbers
        # Pitfall: not validating matches leads to high false positive rate
        digits = [int(d) for d in number]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(divmod(d * 2, 10))
        return checksum % 10 == 0

class NERPIIDetector:
    # NER-based detection for unstructured PII (names, addresses)
    # Trade-off: higher recall for unstructured PII but slower and needs a model
    # Best practice: use a fine-tuned NER model for your domain

    def __init__(self, model_name: str = "en_core_web_trf"):
        self.model_name = model_name
        self._nlp = None

    def _load_model(self):
        if self._nlp is None:
            import spacy
            self._nlp = spacy.load(self.model_name)

    def detect(self, text: str) -> list[PIIDetection]:
        self._load_model()
        doc = self._nlp(text)
        detections = []

        entity_map = {
            "PERSON": PIIType.PERSON_NAME,
            "GPE": PIIType.ADDRESS,
            "LOC": PIIType.ADDRESS,
            "FAC": PIIType.ADDRESS,
        }

        for ent in doc.ents:
            if ent.label_ in entity_map:
                # Use entity confidence if available
                # However, spaCy doesn't expose confidence directly
                # Therefore, use a heuristic based on entity length and context
                confidence = self._estimate_confidence(ent, doc)
                if confidence >= 0.7:
                    detections.append(PIIDetection(
                        start=ent.start_char,
                        end=ent.end_char,
                        text=ent.text,
                        pii_type=entity_map[ent.label_],
                        confidence=confidence,
                        detector="ner",
                    ))

        return detections

    def _estimate_confidence(self, entity, doc) -> float:
        # Heuristic confidence estimation
        # Single-token entities in ambiguous contexts get lower confidence
        base = 0.85
        if len(entity) <= 2:
            base -= 0.15  # Short entities are often false positives
        return min(base, 0.99)
```

### Reversible Tokenization

**Reversible tokenization** (also called format-preserving pseudonymization) replaces PII with realistic-looking tokens that can be reversed with a key. This preserves data utility for analytics while protecting privacy.

```python
import hashlib
import hmac
import secrets
from typing import Optional

class ReversibleTokenizer:
    # Replaces PII with reversible tokens that preserve format
    # Because tokenization is reversible, it supports re-identification
    # when legally required (e.g., law enforcement requests)
    # Trade-off: reversibility means the token vault is a high-value target

    def __init__(self, secret_key: str, vault_backend="redis"):
        self.secret_key = secret_key.encode()
        self.vault = {}  # In production: encrypted database or HSM

    def tokenize(self, value: str, pii_type: PIIType) -> str:
        # Generate a deterministic token (same input = same token)
        # This preserves referential integrity across datasets
        # However, deterministic tokens are vulnerable to dictionary attacks
        # Best practice: use different keys per dataset to prevent cross-linking

        token_id = hmac.new(
            self.secret_key,
            f"{pii_type.value}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

        # Store mapping in vault (encrypted at rest)
        self.vault[token_id] = {
            "original": value,
            "pii_type": pii_type.value,
            "created_at": "2026-03-03T00:00:00Z",
        }

        # Format-preserving token
        if pii_type == PIIType.EMAIL:
            return f"user_{token_id[:8]}@redacted.example.com"
        elif pii_type == PIIType.PHONE:
            return f"555-000-{token_id[:4]}"
        elif pii_type == PIIType.PERSON_NAME:
            return f"PERSON_{token_id[:8]}"
        else:
            return f"[REDACTED:{pii_type.value}:{token_id[:8]}]"

    def detokenize(self, token: str) -> Optional[str]:
        # Reverse the tokenization — requires vault access
        # Pitfall: not auditing detokenization requests
        # Best practice: require MFA and approval for detokenization
        import re
        match = re.search(r'([a-f0-9]{8,16})', token)
        if match:
            token_id_prefix = match.group(1)
            for tid, entry in self.vault.items():
                if tid.startswith(token_id_prefix):
                    return entry["original"]
        return None

class PIIRedactionPipeline:
    # Orchestrates detection and redaction across multiple detectors
    # Common mistake: not deduplicating overlapping detections

    def __init__(self, detectors: list, tokenizer: ReversibleTokenizer):
        self.detectors = detectors
        self.tokenizer = tokenizer

    def process(self, text: str, mode: str = "tokenize") -> tuple[str, list[PIIDetection]]:
        # Step 1: Collect all detections
        all_detections = []
        for detector in self.detectors:
            all_detections.extend(detector.detect(text))

        # Step 2: Deduplicate and resolve overlaps
        # Take the detection with highest confidence for overlapping spans
        merged = self._merge_detections(all_detections)

        # Step 3: Apply redaction (process from end to preserve offsets)
        result = text
        for det in sorted(merged, key=lambda d: d.start, reverse=True):
            if mode == "tokenize":
                replacement = self.tokenizer.tokenize(det.text, det.pii_type)
            elif mode == "mask":
                replacement = "*" * len(det.text)
            elif mode == "category":
                replacement = f"[{det.pii_type.value.upper()}]"
            else:
                replacement = "[REDACTED]"
            result = result[:det.start] + replacement + result[det.end:]

        return result, merged

    def _merge_detections(self, detections: list[PIIDetection]) -> list[PIIDetection]:
        if not detections:
            return []
        # Sort by start position, then by confidence (descending)
        sorted_dets = sorted(detections, key=lambda d: (d.start, -d.confidence))
        merged = [sorted_dets[0]]
        for det in sorted_dets[1:]:
            if det.start >= merged[-1].end:
                merged.append(det)
            elif det.confidence > merged[-1].confidence:
                merged[-1] = det  # Replace with higher confidence
        return merged
```

### Key Takeaways

- **Multi-layer detection** combining regex and NER is essential — **because** regex catches structured PII while NER catches names and addresses in free text
- **Luhn validation** for credit cards reduces false positives — a **common mistake** is accepting any 16-digit number
- **Reversible tokenization** preserves data utility — **however** the token vault becomes a high-value target, so encrypt at rest and audit access
- **Best practice**: format-preserving tokens maintain referential integrity across datasets — **therefore** the same input always produces the same token
- **Pitfall**: using the same tokenization key across datasets enables cross-linking — use per-dataset keys
- The **trade-off** between recall (catching all PII) and precision (avoiding false redactions) should be tuned per use case — medical records need high recall while analytics need high precision
"""
    ),
]
