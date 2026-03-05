"""Threat modeling — STRIDE methodology, attack trees, security controls mapping, data flow diagrams, risk scoring, automated threat analysis."""

PAIRS = [
    (
        "security/stride-methodology",
        "Implement a comprehensive STRIDE threat modeling framework in Python that can analyze system components, identify threats per category, map mitigations, and generate prioritized threat reports.",
        '''A comprehensive STRIDE threat modeling framework with automated analysis and reporting:

```python
"""
STRIDE threat modeling framework: systematic threat identification,
risk scoring, mitigation mapping, and report generation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class STRIDECategory(str, Enum):
    SPOOFING = "Spoofing"
    TAMPERING = "Tampering"
    REPUDIATION = "Repudiation"
    INFORMATION_DISCLOSURE = "Information Disclosure"
    DENIAL_OF_SERVICE = "Denial of Service"
    ELEVATION_OF_PRIVILEGE = "Elevation of Privilege"


class TrustLevel(str, Enum):
    UNTRUSTED = "untrusted"       # Internet, anonymous users
    PARTIALLY_TRUSTED = "partial"  # Authenticated but limited
    TRUSTED = "trusted"            # Internal services
    HIGHLY_TRUSTED = "highly_trusted"  # Admin, infrastructure


class ComponentType(str, Enum):
    PROCESS = "process"
    DATA_STORE = "data_store"
    DATA_FLOW = "data_flow"
    EXTERNAL_ENTITY = "external_entity"
    TRUST_BOUNDARY = "trust_boundary"


class RiskSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class MitigationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    ACCEPTED_RISK = "accepted_risk"


# --- Data flow diagram components ---

@dataclass
class Component:
    """A component in the system's data flow diagram."""
    id: str
    name: str
    component_type: ComponentType
    description: str = ""
    technology: str = ""
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    handles_pii: bool = False
    handles_credentials: bool = False
    internet_facing: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class DataFlow:
    """A data flow between two components."""
    id: str
    name: str
    source_id: str
    destination_id: str
    protocol: str = ""  # HTTPS, gRPC, TCP, etc.
    data_classification: str = "internal"  # public|internal|confidential|restricted
    authenticated: bool = False
    encrypted: bool = False
    crosses_trust_boundary: bool = False


@dataclass
class TrustBoundary:
    """A trust boundary enclosing components."""
    id: str
    name: str
    trust_level: TrustLevel
    component_ids: list[str] = field(default_factory=list)


# --- Threat and mitigation models ---

@dataclass
class Threat:
    """An identified threat from STRIDE analysis."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: STRIDECategory = STRIDECategory.SPOOFING
    title: str = ""
    description: str = ""
    affected_component_id: str = ""
    affected_flow_id: Optional[str] = None
    attack_vector: str = ""
    severity: RiskSeverity = RiskSeverity.MEDIUM
    likelihood: float = 0.5  # 0.0 to 1.0
    impact: float = 0.5      # 0.0 to 1.0
    risk_score: float = 0.0  # Computed: likelihood * impact * severity_weight
    mitigations: list["Mitigation"] = field(default_factory=list)
    cwe_ids: list[str] = field(default_factory=list)
    owasp_refs: list[str] = field(default_factory=list)

    def compute_risk_score(self) -> float:
        severity_weights = {
            RiskSeverity.CRITICAL: 1.0,
            RiskSeverity.HIGH: 0.8,
            RiskSeverity.MEDIUM: 0.5,
            RiskSeverity.LOW: 0.2,
            RiskSeverity.INFORMATIONAL: 0.05,
        }
        weight = severity_weights.get(self.severity, 0.5)
        self.risk_score = round(self.likelihood * self.impact * weight, 3)
        return self.risk_score


@dataclass
class Mitigation:
    """A security control that mitigates a threat."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    control_type: str = ""  # preventive|detective|corrective
    status: MitigationStatus = MitigationStatus.NOT_STARTED
    effectiveness: float = 0.8  # 0.0 to 1.0
    owner: str = ""
    implementation_notes: str = ""


# --- STRIDE threat analyzer ---

class STRIDEAnalyzer:
    """
    Automated STRIDE analysis engine that identifies threats
    based on component characteristics and data flows.
    """

    # Threat patterns per STRIDE category, keyed by triggering conditions
    THREAT_PATTERNS: dict[STRIDECategory, list[dict[str, Any]]] = {
        STRIDECategory.SPOOFING: [
            {
                "condition": lambda c, f: (
                    c.internet_facing and c.component_type == ComponentType.PROCESS
                ),
                "title": "Identity spoofing on {component}",
                "description": (
                    "An attacker could impersonate a legitimate user "
                    "by forging authentication tokens or session cookies."
                ),
                "severity": RiskSeverity.HIGH,
                "attack_vector": "Forged JWT, stolen session, credential stuffing",
                "cwe_ids": ["CWE-287", "CWE-290"],
                "mitigations": [
                    ("Implement MFA", "preventive", 0.9),
                    ("Use short-lived tokens with rotation", "preventive", 0.8),
                    ("Rate-limit authentication attempts", "preventive", 0.7),
                ],
            },
            {
                "condition": lambda c, f: (
                    f is not None and not f.authenticated
                    and f.crosses_trust_boundary
                ),
                "title": "Service spoofing on {flow}",
                "description": (
                    "Unauthenticated flow crossing trust boundary "
                    "allows a rogue service to impersonate a legitimate one."
                ),
                "severity": RiskSeverity.HIGH,
                "attack_vector": "Man-in-the-middle, DNS hijacking",
                "cwe_ids": ["CWE-290", "CWE-295"],
                "mitigations": [
                    ("Implement mTLS between services", "preventive", 0.95),
                    ("Service mesh with identity verification", "preventive", 0.9),
                ],
            },
        ],
        STRIDECategory.TAMPERING: [
            {
                "condition": lambda c, f: (
                    f is not None and not f.encrypted
                    and f.data_classification in ("confidential", "restricted")
                ),
                "title": "Data tampering on {flow}",
                "description": (
                    "Sensitive data transmitted without encryption "
                    "could be modified in transit."
                ),
                "severity": RiskSeverity.HIGH,
                "attack_vector": "Man-in-the-middle, ARP spoofing",
                "cwe_ids": ["CWE-319", "CWE-345"],
                "mitigations": [
                    ("Encrypt all data in transit with TLS 1.3", "preventive", 0.95),
                    ("Add HMAC integrity verification", "detective", 0.85),
                ],
            },
            {
                "condition": lambda c, f: (
                    c.component_type == ComponentType.DATA_STORE
                    and c.handles_pii
                ),
                "title": "Data store tampering on {component}",
                "description": (
                    "PII in data store could be modified without detection "
                    "if integrity controls are insufficient."
                ),
                "severity": RiskSeverity.HIGH,
                "attack_vector": "SQL injection, direct DB access",
                "cwe_ids": ["CWE-89", "CWE-494"],
                "mitigations": [
                    ("Use parameterized queries exclusively", "preventive", 0.95),
                    ("Implement audit logging on all writes", "detective", 0.85),
                    ("Add checksums for critical records", "detective", 0.8),
                ],
            },
        ],
        STRIDECategory.REPUDIATION: [
            {
                "condition": lambda c, f: (
                    c.component_type == ComponentType.PROCESS
                    and (c.handles_pii or c.handles_credentials)
                ),
                "title": "Repudiation of actions on {component}",
                "description": (
                    "Users could deny performing sensitive operations "
                    "without comprehensive audit logging."
                ),
                "severity": RiskSeverity.MEDIUM,
                "attack_vector": "Claiming another user performed the action",
                "cwe_ids": ["CWE-778"],
                "mitigations": [
                    ("Structured audit logging with tamper-proof storage", "detective", 0.9),
                    ("Digital signatures on critical transactions", "preventive", 0.95),
                ],
            },
        ],
        STRIDECategory.INFORMATION_DISCLOSURE: [
            {
                "condition": lambda c, f: (
                    c.internet_facing and c.handles_pii
                ),
                "title": "PII exposure from {component}",
                "description": (
                    "Internet-facing component handling PII could leak "
                    "sensitive data through error messages, logs, or side channels."
                ),
                "severity": RiskSeverity.CRITICAL,
                "attack_vector": "Error disclosure, verbose logging, IDOR",
                "cwe_ids": ["CWE-200", "CWE-209", "CWE-532"],
                "mitigations": [
                    ("Sanitize all error responses", "preventive", 0.85),
                    ("Implement field-level encryption for PII", "preventive", 0.9),
                    ("Add data loss prevention scanning", "detective", 0.8),
                ],
            },
        ],
        STRIDECategory.DENIAL_OF_SERVICE: [
            {
                "condition": lambda c, f: c.internet_facing,
                "title": "DoS attack on {component}",
                "description": (
                    "Internet-facing component is vulnerable to volumetric "
                    "or application-layer denial of service."
                ),
                "severity": RiskSeverity.MEDIUM,
                "attack_vector": "HTTP flood, slowloris, resource exhaustion",
                "cwe_ids": ["CWE-400", "CWE-770"],
                "mitigations": [
                    ("Deploy WAF with rate limiting", "preventive", 0.8),
                    ("Implement circuit breakers and bulkheads", "corrective", 0.75),
                    ("Use CDN with DDoS protection", "preventive", 0.85),
                ],
            },
        ],
        STRIDECategory.ELEVATION_OF_PRIVILEGE: [
            {
                "condition": lambda c, f: (
                    c.component_type == ComponentType.PROCESS
                    and c.handles_credentials
                ),
                "title": "Privilege escalation via {component}",
                "description": (
                    "Component handling credentials could allow "
                    "unauthorized privilege escalation through "
                    "injection or logic flaws."
                ),
                "severity": RiskSeverity.CRITICAL,
                "attack_vector": "IDOR, broken access control, injection",
                "cwe_ids": ["CWE-269", "CWE-285", "CWE-862"],
                "mitigations": [
                    ("Enforce least privilege with RBAC/ABAC", "preventive", 0.85),
                    ("Server-side authorization on every request", "preventive", 0.95),
                    ("Regular privilege audit reviews", "detective", 0.7),
                ],
            },
        ],
    }

    def __init__(self):
        self.components: dict[str, Component] = {}
        self.flows: list[DataFlow] = []
        self.boundaries: list[TrustBoundary] = []
        self.threats: list[Threat] = []

    def add_component(self, component: Component) -> None:
        self.components[component.id] = component

    def add_flow(self, flow: DataFlow) -> None:
        self.flows.append(flow)

    def add_boundary(self, boundary: TrustBoundary) -> None:
        self.boundaries.append(boundary)

    def analyze(self) -> list[Threat]:
        """Run STRIDE analysis across all components and flows."""
        self.threats.clear()

        for component in self.components.values():
            # Analyze component-level threats
            for category, patterns in self.THREAT_PATTERNS.items():
                for pattern in patterns:
                    if pattern["condition"](component, None):
                        threat = self._create_threat(
                            pattern, category, component
                        )
                        self.threats.append(threat)

            # Analyze flow-level threats
            for flow in self.flows:
                if (flow.source_id == component.id
                        or flow.destination_id == component.id):
                    for category, patterns in self.THREAT_PATTERNS.items():
                        for pattern in patterns:
                            if pattern["condition"](component, flow):
                                threat = self._create_threat(
                                    pattern, category, component, flow
                                )
                                self.threats.append(threat)

        # Compute risk scores
        for threat in self.threats:
            threat.compute_risk_score()

        # Sort by risk score descending
        self.threats.sort(key=lambda t: t.risk_score, reverse=True)
        return self.threats

    def _create_threat(
        self,
        pattern: dict[str, Any],
        category: STRIDECategory,
        component: Component,
        flow: Optional[DataFlow] = None,
    ) -> Threat:
        title = pattern["title"].format(
            component=component.name,
            flow=flow.name if flow else "",
        )
        mitigations = [
            Mitigation(
                title=m[0], control_type=m[1], effectiveness=m[2]
            )
            for m in pattern.get("mitigations", [])
        ]
        return Threat(
            category=category,
            title=title,
            description=pattern["description"],
            affected_component_id=component.id,
            affected_flow_id=flow.id if flow else None,
            attack_vector=pattern.get("attack_vector", ""),
            severity=pattern["severity"],
            likelihood=0.6 if component.internet_facing else 0.3,
            impact=0.9 if component.handles_pii else 0.5,
            mitigations=mitigations,
            cwe_ids=pattern.get("cwe_ids", []),
        )

    def generate_report(self) -> dict[str, Any]:
        """Generate a structured threat model report."""
        by_severity = {}
        for threat in self.threats:
            sev = threat.severity.value
            by_severity.setdefault(sev, []).append(threat.title)

        by_category = {}
        for threat in self.threats:
            cat = threat.category.value
            by_category.setdefault(cat, 0)
            by_category[cat] += 1

        return {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "components_analyzed": len(self.components),
                "flows_analyzed": len(self.flows),
                "total_threats": len(self.threats),
            },
            "summary": {
                "by_severity": by_severity,
                "by_category": by_category,
                "top_risks": [
                    {
                        "title": t.title,
                        "risk_score": t.risk_score,
                        "category": t.category.value,
                        "severity": t.severity.value,
                    }
                    for t in self.threats[:10]
                ],
            },
            "threats": [
                {
                    "id": t.id,
                    "category": t.category.value,
                    "title": t.title,
                    "severity": t.severity.value,
                    "risk_score": t.risk_score,
                    "attack_vector": t.attack_vector,
                    "cwe_ids": t.cwe_ids,
                    "mitigations": [
                        {"title": m.title, "status": m.status.value}
                        for m in t.mitigations
                    ],
                }
                for t in self.threats
            ],
        }


# --- Usage example ---

def demo():
    analyzer = STRIDEAnalyzer()

    # Define components
    analyzer.add_component(Component(
        id="api-gateway", name="API Gateway",
        component_type=ComponentType.PROCESS,
        technology="Kong", trust_level=TrustLevel.PARTIALLY_TRUSTED,
        internet_facing=True, handles_credentials=True,
    ))
    analyzer.add_component(Component(
        id="user-db", name="User Database",
        component_type=ComponentType.DATA_STORE,
        technology="PostgreSQL", trust_level=TrustLevel.TRUSTED,
        handles_pii=True, handles_credentials=True,
    ))
    analyzer.add_component(Component(
        id="patient-svc", name="Patient Service",
        component_type=ComponentType.PROCESS,
        technology="Python/FastAPI", trust_level=TrustLevel.TRUSTED,
        handles_pii=True, internet_facing=True,
    ))

    # Define flows
    analyzer.add_flow(DataFlow(
        id="f1", name="API to Patient Service",
        source_id="api-gateway", destination_id="patient-svc",
        protocol="gRPC", data_classification="confidential",
        authenticated=True, encrypted=True,
        crosses_trust_boundary=False,
    ))
    analyzer.add_flow(DataFlow(
        id="f2", name="Patient Service to DB",
        source_id="patient-svc", destination_id="user-db",
        protocol="PostgreSQL", data_classification="restricted",
        authenticated=True, encrypted=False,
        crosses_trust_boundary=True,
    ))

    threats = analyzer.analyze()
    report = analyzer.generate_report()
    print(json.dumps(report, indent=2))
```

**STRIDE category mapping:**

| Category | Security Property | Primary Controls |
|---|---|---|
| Spoofing | Authentication | MFA, mTLS, token rotation |
| Tampering | Integrity | TLS, HMAC, parameterized queries |
| Repudiation | Non-repudiation | Audit logs, digital signatures |
| Information Disclosure | Confidentiality | Encryption, field-level masking |
| Denial of Service | Availability | Rate limiting, WAF, circuit breakers |
| Elevation of Privilege | Authorization | RBAC/ABAC, least privilege |

**Key patterns:**
- Model system as components, data flows, and trust boundaries for DFD analysis
- Apply pattern-matching rules per STRIDE category based on component properties
- Compute risk scores as likelihood x impact x severity weight for prioritization
- Map each threat to CWE IDs and OWASP references for standard vulnerability tracking
- Generate mitigations with control type (preventive/detective/corrective) and effectiveness
- Internet-facing components with PII trigger higher likelihood and impact scores
- Trust boundary crossings without authentication flag spoofing and tampering threats'''
    ),
    (
        "security/attack-trees",
        "Build an attack tree modeling system that can represent multi-step attack scenarios, calculate aggregate probabilities, estimate costs, and identify the cheapest or most likely attack paths.",
        '''Attack tree modeling system with probability propagation, cost analysis, and path optimization:

```python
"""
Attack tree modeling: hierarchical decomposition of threats
with probability/cost propagation and path analysis.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class GateType(str, Enum):
    """How child nodes combine to achieve the parent goal."""
    AND = "AND"   # All children must succeed
    OR = "OR"     # Any child is sufficient
    SAND = "SAND"  # Sequential AND (ordered execution)


class NodeType(str, Enum):
    GOAL = "goal"           # Root attack objective
    SUB_GOAL = "sub_goal"   # Intermediate objective
    ATTACK = "attack"       # Leaf-level attack action


@dataclass
class AttackNode:
    """A node in the attack tree."""
    id: str
    name: str
    node_type: NodeType
    description: str = ""

    # Gate for combining children (None for leaf nodes)
    gate: Optional[GateType] = None
    children: list["AttackNode"] = field(default_factory=list)

    # Leaf node properties (only for attack/leaf nodes)
    probability: float = 0.0    # 0.0 to 1.0
    cost: float = 0.0           # Attacker cost in arbitrary units
    difficulty: str = "medium"  # low | medium | high | expert
    requires_insider: bool = False
    requires_physical: bool = False
    detectable: bool = True
    skill_level: int = 5        # 1-10 scale

    # Computed properties (set by propagation)
    _computed_probability: Optional[float] = field(
        default=None, repr=False
    )
    _computed_cost: Optional[float] = field(default=None, repr=False)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def computed_probability(self) -> float:
        if self._computed_probability is not None:
            return self._computed_probability
        return self.probability

    def computed_cost(self) -> float:
        if self._computed_cost is not None:
            return self._computed_cost
        return self.cost


class AttackTree:
    """
    Attack tree with probability/cost propagation,
    path enumeration, and risk analysis.
    """

    def __init__(self, root: AttackNode):
        self.root = root
        self._all_paths: list[list[AttackNode]] = []

    def propagate(self) -> None:
        """Propagate probabilities and costs from leaves to root."""
        self._propagate_node(self.root)

    def _propagate_node(self, node: AttackNode) -> None:
        """Recursively compute probability and cost for a node."""
        if node.is_leaf:
            node._computed_probability = node.probability
            node._computed_cost = node.cost
            return

        # Propagate children first
        for child in node.children:
            self._propagate_node(child)

        child_probs = [c.computed_probability() for c in node.children]
        child_costs = [c.computed_cost() for c in node.children]

        if node.gate == GateType.AND or node.gate == GateType.SAND:
            # AND: all must succeed, multiply probabilities
            node._computed_probability = math.prod(child_probs)
            # AND: attacker pays all costs
            node._computed_cost = sum(child_costs)
        elif node.gate == GateType.OR:
            # OR: any can succeed
            # P(at least one) = 1 - product(1 - p_i)
            node._computed_probability = 1.0 - math.prod(
                1.0 - p for p in child_probs
            )
            # OR: attacker picks cheapest path
            node._computed_cost = min(child_costs) if child_costs else 0

    def enumerate_paths(self) -> list[list[AttackNode]]:
        """Find all leaf-to-root attack paths."""
        self._all_paths = []
        self._find_paths(self.root, [])
        return self._all_paths

    def _find_paths(
        self, node: AttackNode, current_path: list[AttackNode]
    ) -> None:
        current_path = current_path + [node]

        if node.is_leaf:
            self._all_paths.append(current_path)
            return

        if node.gate == GateType.AND or node.gate == GateType.SAND:
            # For AND, a path must include all children
            child_paths: list[list[list[AttackNode]]] = []
            for child in node.children:
                sub_paths: list[list[AttackNode]] = []
                self._all_paths_temp = []
                self._find_paths(child, [])
                child_paths.append(self._all_paths_temp)

            # Combine: cartesian product of all children paths
            combined = self._cartesian_paths(child_paths)
            for combo in combined:
                full_path = current_path.copy()
                for sub in combo:
                    full_path.extend(sub)
                self._all_paths.append(full_path)
        else:
            # OR: each child represents an alternative
            for child in node.children:
                self._find_paths(child, current_path)

    def _cartesian_paths(
        self, child_paths: list[list[list[AttackNode]]]
    ) -> list[list[list[AttackNode]]]:
        if not child_paths:
            return [[]]
        result = [[]]
        for paths in child_paths:
            new_result = []
            for existing in result:
                for path in paths:
                    new_result.append(existing + [path])
            result = new_result
        return result

    def find_cheapest_attack(self) -> dict[str, Any]:
        """Find the minimum cost path to achieve the root goal."""
        return self._find_optimal(self.root, minimize_cost=True)

    def find_most_likely_attack(self) -> dict[str, Any]:
        """Find the highest probability path to root goal."""
        return self._find_optimal(self.root, minimize_cost=False)

    def _find_optimal(
        self, node: AttackNode, minimize_cost: bool
    ) -> dict[str, Any]:
        if node.is_leaf:
            return {
                "path": [node.name],
                "probability": node.probability,
                "cost": node.cost,
                "steps": [
                    {
                        "name": node.name,
                        "difficulty": node.difficulty,
                        "skill_level": node.skill_level,
                        "detectable": node.detectable,
                    }
                ],
            }

        child_results = [
            self._find_optimal(child, minimize_cost)
            for child in node.children
        ]

        if node.gate == GateType.AND or node.gate == GateType.SAND:
            # Must achieve all children
            combined_path = [node.name]
            combined_steps = []
            total_cost = 0
            total_prob = 1.0
            for r in child_results:
                combined_path.extend(r["path"])
                combined_steps.extend(r["steps"])
                total_cost += r["cost"]
                total_prob *= r["probability"]
            return {
                "path": combined_path,
                "probability": total_prob,
                "cost": total_cost,
                "steps": combined_steps,
            }
        else:
            # OR: pick best child
            if minimize_cost:
                best = min(child_results, key=lambda r: r["cost"])
            else:
                best = max(child_results, key=lambda r: r["probability"])
            return {
                "path": [node.name] + best["path"],
                "probability": best["probability"],
                "cost": best["cost"],
                "steps": best["steps"],
            }

    def risk_summary(self) -> dict[str, Any]:
        """Generate a risk summary for the attack tree."""
        self.propagate()
        cheapest = self.find_cheapest_attack()
        most_likely = self.find_most_likely_attack()

        leaf_nodes = self._collect_leaves(self.root)
        return {
            "root_goal": self.root.name,
            "overall_probability": round(
                self.root.computed_probability(), 4
            ),
            "minimum_attack_cost": round(
                self.root.computed_cost(), 2
            ),
            "total_attack_vectors": len(leaf_nodes),
            "cheapest_attack": cheapest,
            "most_likely_attack": most_likely,
            "insider_threats": [
                n.name for n in leaf_nodes if n.requires_insider
            ],
            "undetectable_attacks": [
                n.name for n in leaf_nodes if not n.detectable
            ],
            "high_skill_attacks": [
                n.name for n in leaf_nodes if n.skill_level >= 8
            ],
        }

    def _collect_leaves(self, node: AttackNode) -> list[AttackNode]:
        if node.is_leaf:
            return [node]
        leaves = []
        for child in node.children:
            leaves.extend(self._collect_leaves(child))
        return leaves


# --- Usage example ---

def demo():
    # Build attack tree: steal patient data
    root = AttackNode(
        id="goal", name="Steal Patient Data",
        node_type=NodeType.GOAL, gate=GateType.OR,
        children=[
            AttackNode(
                id="web-attack", name="Web Application Attack",
                node_type=NodeType.SUB_GOAL, gate=GateType.OR,
                children=[
                    AttackNode(
                        id="sqli", name="SQL Injection",
                        node_type=NodeType.ATTACK,
                        probability=0.3, cost=100,
                        difficulty="medium", skill_level=5,
                    ),
                    AttackNode(
                        id="idor", name="IDOR on Patient API",
                        node_type=NodeType.ATTACK,
                        probability=0.4, cost=50,
                        difficulty="low", skill_level=3,
                    ),
                ],
            ),
            AttackNode(
                id="insider", name="Insider Threat",
                node_type=NodeType.SUB_GOAL, gate=GateType.SAND,
                children=[
                    AttackNode(
                        id="get-access",
                        name="Obtain Database Credentials",
                        node_type=NodeType.ATTACK,
                        probability=0.2, cost=500,
                        difficulty="high", requires_insider=True,
                        skill_level=4, detectable=False,
                    ),
                    AttackNode(
                        id="exfil", name="Exfiltrate Data",
                        node_type=NodeType.ATTACK,
                        probability=0.7, cost=200,
                        difficulty="medium", requires_insider=True,
                        skill_level=5,
                    ),
                ],
            ),
            AttackNode(
                id="social", name="Social Engineering",
                node_type=NodeType.ATTACK,
                probability=0.25, cost=300,
                difficulty="medium", skill_level=6,
            ),
        ],
    )

    tree = AttackTree(root)
    summary = tree.risk_summary()
    print(json.dumps(summary, indent=2))
```

**Attack tree gate semantics:**

| Gate | Probability | Cost | Meaning |
|---|---|---|---|
| OR | 1 - prod(1-p_i) | min(costs) | Any child achieves goal |
| AND | prod(p_i) | sum(costs) | All children required |
| SAND | prod(p_i) | sum(costs) | All children in sequence |

**Key patterns:**
- Model multi-step attacks as trees with AND/OR/SAND gates for composition
- Propagate probabilities bottom-up using multiplicative (AND) and complementary (OR) rules
- Compute minimum cost path to identify cheapest attack vector
- Compute maximum probability path to identify most likely attack vector
- Flag insider threats and undetectable attacks for special attention
- SAND gates enforce sequential ordering for attacks that require specific step order
- Use skill_level scoring to assess required attacker sophistication'''
    ),
    (
        "security/security-controls-mapping",
        "Create a security controls mapping system that maps threats to controls across frameworks (NIST CSF, CIS, ISO 27001), tracks implementation status, and generates gap analysis reports.",
        '''Security controls mapping across frameworks with gap analysis and implementation tracking:

```python
"""
Security controls mapping: cross-framework control mapping,
gap analysis, and implementation status tracking.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Framework(str, Enum):
    NIST_CSF = "NIST CSF 2.0"
    CIS_V8 = "CIS Controls v8"
    ISO_27001 = "ISO 27001:2022"
    SOC2_TSC = "SOC2 TSC"
    OWASP_ASVS = "OWASP ASVS 4.0"


class ControlStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    PARTIAL = "partial"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    NOT_APPLICABLE = "not_applicable"


class ControlPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Control:
    """A security control from a specific framework."""
    id: str               # e.g., "NIST-PR.AC-1", "CIS-6.1"
    framework: Framework
    title: str
    description: str
    category: str         # e.g., "Access Control", "Data Protection"
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    priority: ControlPriority = ControlPriority.MEDIUM
    owner: str = ""
    evidence: str = ""
    implementation_notes: str = ""
    last_assessed: Optional[datetime] = None
    # Cross-references
    mapped_controls: list[str] = field(default_factory=list)
    mitigates_threats: list[str] = field(default_factory=list)


# --- Cross-framework control mappings ---

CONTROL_MAPPINGS: dict[str, dict[str, list[str]]] = {
    "access_control": {
        Framework.NIST_CSF.value: [
            "PR.AA-01", "PR.AA-02", "PR.AA-03",
            "PR.AA-04", "PR.AA-05",
        ],
        Framework.CIS_V8.value: [
            "CIS-5.1", "CIS-5.2", "CIS-5.3", "CIS-5.4",
            "CIS-6.1", "CIS-6.2", "CIS-6.3", "CIS-6.4", "CIS-6.5",
        ],
        Framework.ISO_27001.value: [
            "A.5.15", "A.5.16", "A.5.17", "A.5.18",
            "A.8.2", "A.8.3", "A.8.5",
        ],
        Framework.SOC2_TSC.value: ["CC6.1", "CC6.2", "CC6.3"],
    },
    "data_protection": {
        Framework.NIST_CSF.value: [
            "PR.DS-01", "PR.DS-02", "PR.DS-10", "PR.DS-11",
        ],
        Framework.CIS_V8.value: [
            "CIS-3.1", "CIS-3.2", "CIS-3.3",
            "CIS-3.10", "CIS-3.11", "CIS-3.12",
        ],
        Framework.ISO_27001.value: [
            "A.5.33", "A.5.34", "A.8.10", "A.8.11", "A.8.12",
        ],
        Framework.SOC2_TSC.value: ["CC6.1", "CC6.5", "CC6.7"],
    },
    "incident_response": {
        Framework.NIST_CSF.value: [
            "RS.MA-01", "RS.MA-02", "RS.MA-03",
            "RS.AN-03", "RS.AN-06", "RS.AN-07",
        ],
        Framework.CIS_V8.value: [
            "CIS-17.1", "CIS-17.2", "CIS-17.3",
            "CIS-17.4", "CIS-17.5", "CIS-17.6",
        ],
        Framework.ISO_27001.value: [
            "A.5.24", "A.5.25", "A.5.26", "A.5.27", "A.5.28",
        ],
        Framework.SOC2_TSC.value: ["CC7.3", "CC7.4", "CC7.5"],
    },
    "logging_monitoring": {
        Framework.NIST_CSF.value: [
            "DE.CM-01", "DE.CM-02", "DE.CM-03", "DE.CM-06", "DE.CM-09",
        ],
        Framework.CIS_V8.value: [
            "CIS-8.1", "CIS-8.2", "CIS-8.3", "CIS-8.5",
            "CIS-8.9", "CIS-8.11", "CIS-8.12",
        ],
        Framework.ISO_27001.value: [
            "A.8.15", "A.8.16", "A.8.17",
        ],
        Framework.SOC2_TSC.value: ["CC7.1", "CC7.2"],
    },
    "vulnerability_management": {
        Framework.NIST_CSF.value: [
            "ID.RA-01", "ID.RA-02", "ID.RA-05",
            "PR.PS-02", "RS.MI-01",
        ],
        Framework.CIS_V8.value: [
            "CIS-7.1", "CIS-7.2", "CIS-7.3", "CIS-7.4",
            "CIS-7.5", "CIS-7.6", "CIS-7.7",
        ],
        Framework.ISO_27001.value: [
            "A.8.8", "A.8.9",
        ],
        Framework.SOC2_TSC.value: ["CC7.1", "CC8.1"],
    },
}


class SecurityControlsManager:
    """Manages controls across frameworks with gap analysis."""

    def __init__(self):
        self.controls: dict[str, Control] = {}
        self._framework_controls: dict[
            Framework, list[Control]
        ] = defaultdict(list)

    def add_control(self, control: Control) -> None:
        self.controls[control.id] = control
        self._framework_controls[control.framework].append(control)

    def update_status(
        self, control_id: str, status: ControlStatus,
        evidence: str = "", notes: str = "",
    ) -> None:
        if control_id in self.controls:
            ctrl = self.controls[control_id]
            ctrl.status = status
            ctrl.evidence = evidence
            ctrl.implementation_notes = notes
            ctrl.last_assessed = datetime.now(timezone.utc)

    def gap_analysis(
        self, framework: Framework
    ) -> dict[str, Any]:
        """Generate gap analysis for a specific framework."""
        controls = self._framework_controls.get(framework, [])
        if not controls:
            return {"framework": framework.value, "error": "No controls loaded"}

        by_status: dict[str, int] = defaultdict(int)
        by_category: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        gaps: list[dict[str, Any]] = []

        for ctrl in controls:
            by_status[ctrl.status.value] += 1
            by_category[ctrl.category][ctrl.status.value] += 1

            if ctrl.status in (
                ControlStatus.NOT_IMPLEMENTED,
                ControlStatus.PARTIAL,
            ):
                gaps.append({
                    "control_id": ctrl.id,
                    "title": ctrl.title,
                    "category": ctrl.category,
                    "status": ctrl.status.value,
                    "priority": ctrl.priority.value,
                    "owner": ctrl.owner,
                })

        total = len(controls)
        implemented = sum(
            1 for c in controls
            if c.status in (
                ControlStatus.IMPLEMENTED, ControlStatus.VERIFIED
            )
        )

        return {
            "framework": framework.value,
            "total_controls": total,
            "implementation_rate": round(
                implemented / total * 100, 1
            ) if total > 0 else 0,
            "by_status": dict(by_status),
            "by_category": {
                cat: dict(statuses)
                for cat, statuses in by_category.items()
            },
            "gaps": sorted(
                gaps,
                key=lambda g: (
                    ["critical", "high", "medium", "low"].index(
                        g["priority"]
                    )
                ),
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def cross_framework_coverage(
        self, domain: str
    ) -> dict[str, Any]:
        """Check coverage across frameworks for a domain."""
        mapping = CONTROL_MAPPINGS.get(domain, {})
        coverage: dict[str, dict[str, Any]] = {}

        for fw_name, control_ids in mapping.items():
            implemented = 0
            total = len(control_ids)
            missing = []

            for cid in control_ids:
                ctrl = self.controls.get(cid)
                if ctrl and ctrl.status in (
                    ControlStatus.IMPLEMENTED,
                    ControlStatus.VERIFIED,
                ):
                    implemented += 1
                else:
                    missing.append(cid)

            coverage[fw_name] = {
                "total": total,
                "implemented": implemented,
                "coverage_pct": round(
                    implemented / total * 100, 1
                ) if total > 0 else 0,
                "missing": missing,
            }

        return {
            "domain": domain,
            "frameworks": coverage,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def remediation_roadmap(
        self, framework: Framework, quarters: int = 4
    ) -> list[dict[str, Any]]:
        """Generate a prioritized remediation roadmap."""
        gaps = self.gap_analysis(framework)["gaps"]
        priority_order = ["critical", "high", "medium", "low"]

        roadmap = []
        items_per_quarter = max(1, len(gaps) // quarters)

        for i, gap in enumerate(gaps):
            quarter = min(i // items_per_quarter + 1, quarters)
            roadmap.append({
                "quarter": f"Q{quarter}",
                "control_id": gap["control_id"],
                "title": gap["title"],
                "priority": gap["priority"],
                "current_status": gap["status"],
                "target_status": "implemented",
                "owner": gap["owner"],
            })

        return roadmap
```

**Cross-framework control domain coverage:**

| Domain | NIST CSF 2.0 | CIS v8 | ISO 27001 | SOC2 TSC |
|---|---|---|---|---|
| Access Control | PR.AA-01..05 | CIS-5.x, 6.x | A.5.15-18, A.8.2-5 | CC6.1-3 |
| Data Protection | PR.DS-01..11 | CIS-3.x | A.5.33-34, A.8.10-12 | CC6.1,5,7 |
| Incident Response | RS.MA-01..03 | CIS-17.x | A.5.24-28 | CC7.3-5 |
| Logging/Monitoring | DE.CM-01..09 | CIS-8.x | A.8.15-17 | CC7.1-2 |
| Vuln Management | ID.RA, PR.PS | CIS-7.x | A.8.8-9 | CC7.1, CC8.1 |

**Key patterns:**
- Map controls bidirectionally across frameworks for cross-compliance coverage
- Track implementation status with evidence links for audit readiness
- Generate gap analysis per framework showing implementation rate by category
- Create prioritized remediation roadmaps split across quarters
- Cross-framework coverage report identifies domains with incomplete protection
- Control owners enable accountability tracking across the organization'''
    ),
    (
        "security/data-flow-threat-analysis",
        "Build an automated data flow diagram (DFD) analyzer that identifies trust boundary crossings, classifies data sensitivity, and automatically applies STRIDE threats based on DFD patterns.",
        '''Automated DFD analyzer with trust boundary detection and pattern-based STRIDE threat identification:

```python
"""
Automated Data Flow Diagram analyzer: models system architecture,
detects trust boundary crossings, and applies STRIDE threat
patterns based on component and flow characteristics.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DataSensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    REGULATED = "regulated"  # PII, PHI, PCI


class TrustZone(str, Enum):
    INTERNET = "internet"
    DMZ = "dmz"
    INTERNAL_NETWORK = "internal_network"
    SECURE_ZONE = "secure_zone"
    DATA_ZONE = "data_zone"
    MANAGEMENT_ZONE = "management_zone"


# Trust zone ordering: lower = less trusted
TRUST_ZONE_LEVELS: dict[TrustZone, int] = {
    TrustZone.INTERNET: 0,
    TrustZone.DMZ: 1,
    TrustZone.INTERNAL_NETWORK: 2,
    TrustZone.SECURE_ZONE: 3,
    TrustZone.DATA_ZONE: 4,
    TrustZone.MANAGEMENT_ZONE: 5,
}


@dataclass
class DFDProcess:
    """A process node in the DFD."""
    id: str
    name: str
    trust_zone: TrustZone
    technology: str = ""
    authenticated: bool = False
    authorization_model: str = ""  # none|rbac|abac|acl
    input_validation: bool = False
    output_encoding: bool = False
    logging_enabled: bool = False
    runs_as_root: bool = False
    handles_sensitive_data: list[DataSensitivity] = field(
        default_factory=list
    )


@dataclass
class DFDDataStore:
    """A data store node in the DFD."""
    id: str
    name: str
    trust_zone: TrustZone
    technology: str = ""  # PostgreSQL, Redis, S3, etc.
    encrypted_at_rest: bool = False
    access_controlled: bool = False
    backup_enabled: bool = False
    data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    contains_credentials: bool = False
    audit_logged: bool = False


@dataclass
class DFDExternalEntity:
    """An external entity in the DFD."""
    id: str
    name: str
    trust_zone: TrustZone = TrustZone.INTERNET
    entity_type: str = "user"  # user|service|partner|admin
    authenticated: bool = False
    mfa_enabled: bool = False


@dataclass
class DFDFlow:
    """A data flow between DFD elements."""
    id: str
    name: str
    source_id: str
    target_id: str
    protocol: str = ""
    encrypted: bool = False
    authenticated: bool = False
    data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    data_types: list[str] = field(default_factory=list)
    bidirectional: bool = False


@dataclass
class ThreatFinding:
    """An automatically identified threat from DFD analysis."""
    id: str
    stride_category: str
    severity: str
    title: str
    description: str
    affected_element: str
    affected_flow: Optional[str] = None
    trust_boundary_crossing: bool = False
    recommendations: list[str] = field(default_factory=list)
    cwe_ids: list[str] = field(default_factory=list)


class DFDAnalyzer:
    """Automated DFD analysis engine with STRIDE threat identification."""

    def __init__(self):
        self.processes: dict[str, DFDProcess] = {}
        self.data_stores: dict[str, DFDDataStore] = {}
        self.external_entities: dict[str, DFDExternalEntity] = {}
        self.flows: list[DFDFlow] = []
        self.findings: list[ThreatFinding] = []
        self._finding_counter = 0

    def add_process(self, process: DFDProcess) -> None:
        self.processes[process.id] = process

    def add_data_store(self, store: DFDDataStore) -> None:
        self.data_stores[store.id] = store

    def add_external_entity(self, entity: DFDExternalEntity) -> None:
        self.external_entities[entity.id] = entity

    def add_flow(self, flow: DFDFlow) -> None:
        self.flows.append(flow)

    def analyze(self) -> list[ThreatFinding]:
        """Run comprehensive DFD analysis."""
        self.findings.clear()
        self._finding_counter = 0

        self._analyze_trust_boundaries()
        self._analyze_data_stores()
        self._analyze_processes()
        self._analyze_external_entities()
        self._analyze_flows()

        # Sort by severity
        severity_order = {
            "critical": 0, "high": 1, "medium": 2, "low": 3
        }
        self.findings.sort(
            key=lambda f: severity_order.get(f.severity, 99)
        )
        return self.findings

    def _next_id(self) -> str:
        self._finding_counter += 1
        return f"THREAT-{self._finding_counter:03d}"

    def _get_zone(self, element_id: str) -> Optional[TrustZone]:
        """Get the trust zone of any DFD element."""
        if element_id in self.processes:
            return self.processes[element_id].trust_zone
        if element_id in self.data_stores:
            return self.data_stores[element_id].trust_zone
        if element_id in self.external_entities:
            return self.external_entities[element_id].trust_zone
        return None

    def _crosses_boundary(self, flow: DFDFlow) -> bool:
        """Check if a flow crosses a trust boundary."""
        src_zone = self._get_zone(flow.source_id)
        tgt_zone = self._get_zone(flow.target_id)
        if src_zone is None or tgt_zone is None:
            return False
        return TRUST_ZONE_LEVELS.get(
            src_zone, 0
        ) != TRUST_ZONE_LEVELS.get(tgt_zone, 0)

    def _analyze_trust_boundaries(self) -> None:
        """Find flows crossing trust boundaries without protection."""
        for flow in self.flows:
            if not self._crosses_boundary(flow):
                continue

            src_zone = self._get_zone(flow.source_id)
            tgt_zone = self._get_zone(flow.target_id)

            if not flow.encrypted:
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Information Disclosure",
                    severity="high",
                    title=(
                        f"Unencrypted flow '{flow.name}' crosses "
                        f"trust boundary ({src_zone} -> {tgt_zone})"
                    ),
                    description=(
                        "Data flows across trust boundaries must be "
                        "encrypted to prevent eavesdropping."
                    ),
                    affected_element=flow.source_id,
                    affected_flow=flow.id,
                    trust_boundary_crossing=True,
                    recommendations=[
                        "Implement TLS 1.3 for all cross-boundary flows",
                        "Consider mTLS for service-to-service communication",
                    ],
                    cwe_ids=["CWE-319"],
                ))

            if not flow.authenticated:
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Spoofing",
                    severity="high",
                    title=(
                        f"Unauthenticated flow '{flow.name}' crosses "
                        f"trust boundary"
                    ),
                    description=(
                        "Cross-boundary flows without authentication "
                        "allow identity spoofing."
                    ),
                    affected_element=flow.source_id,
                    affected_flow=flow.id,
                    trust_boundary_crossing=True,
                    recommendations=[
                        "Add mTLS or API key authentication",
                        "Implement service mesh identity verification",
                    ],
                    cwe_ids=["CWE-287", "CWE-306"],
                ))

    def _analyze_data_stores(self) -> None:
        """Analyze data stores for security issues."""
        for store in self.data_stores.values():
            if (
                store.data_sensitivity
                in (DataSensitivity.CONFIDENTIAL, DataSensitivity.RESTRICTED,
                    DataSensitivity.REGULATED)
                and not store.encrypted_at_rest
            ):
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Information Disclosure",
                    severity="critical",
                    title=(
                        f"Sensitive data store '{store.name}' "
                        f"not encrypted at rest"
                    ),
                    description=(
                        f"Data store contains {store.data_sensitivity.value} "
                        f"data without encryption at rest."
                    ),
                    affected_element=store.id,
                    recommendations=[
                        "Enable encryption at rest (AES-256)",
                        "Use KMS-managed encryption keys",
                    ],
                    cwe_ids=["CWE-311"],
                ))

            if store.contains_credentials and not store.access_controlled:
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Elevation of Privilege",
                    severity="critical",
                    title=(
                        f"Credential store '{store.name}' "
                        f"without access controls"
                    ),
                    description=(
                        "Credentials stored without access controls "
                        "enable privilege escalation."
                    ),
                    affected_element=store.id,
                    recommendations=[
                        "Use a secrets manager (Vault, AWS Secrets Manager)",
                        "Implement strict IAM policies for credential access",
                        "Enable audit logging on credential retrieval",
                    ],
                    cwe_ids=["CWE-522", "CWE-269"],
                ))

            if not store.audit_logged and store.data_sensitivity in (
                DataSensitivity.RESTRICTED, DataSensitivity.REGULATED
            ):
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Repudiation",
                    severity="medium",
                    title=(
                        f"No audit logging on '{store.name}' "
                        f"({store.data_sensitivity.value} data)"
                    ),
                    description=(
                        "Regulated data store without audit logging "
                        "prevents accountability."
                    ),
                    affected_element=store.id,
                    recommendations=[
                        "Enable database audit logging",
                        "Forward audit logs to SIEM",
                    ],
                    cwe_ids=["CWE-778"],
                ))

    def _analyze_processes(self) -> None:
        """Analyze processes for security issues."""
        for proc in self.processes.values():
            if proc.runs_as_root:
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Elevation of Privilege",
                    severity="high",
                    title=f"Process '{proc.name}' runs as root",
                    description=(
                        "Running as root increases blast radius "
                        "of any compromise."
                    ),
                    affected_element=proc.id,
                    recommendations=[
                        "Run as non-root user with minimal permissions",
                        "Use Linux capabilities instead of root",
                    ],
                    cwe_ids=["CWE-250"],
                ))

            if not proc.input_validation and proc.trust_zone in (
                TrustZone.DMZ, TrustZone.INTERNET
            ):
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Tampering",
                    severity="high",
                    title=(
                        f"No input validation on internet-facing "
                        f"process '{proc.name}'"
                    ),
                    description=(
                        "Untrusted input without validation enables "
                        "injection attacks."
                    ),
                    affected_element=proc.id,
                    recommendations=[
                        "Implement schema validation on all inputs",
                        "Use allowlists for expected values",
                        "Apply output encoding for rendered content",
                    ],
                    cwe_ids=["CWE-20", "CWE-79", "CWE-89"],
                ))

    def _analyze_external_entities(self) -> None:
        """Analyze external entities for authentication gaps."""
        for entity in self.external_entities.values():
            if entity.entity_type == "admin" and not entity.mfa_enabled:
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Spoofing",
                    severity="critical",
                    title=(
                        f"Admin entity '{entity.name}' without MFA"
                    ),
                    description=(
                        "Admin accounts without MFA are high-value "
                        "targets for credential attacks."
                    ),
                    affected_element=entity.id,
                    recommendations=[
                        "Require hardware security keys for admin access",
                        "Implement phishing-resistant MFA (WebAuthn/FIDO2)",
                    ],
                    cwe_ids=["CWE-308"],
                ))

    def _analyze_flows(self) -> None:
        """Analyze data flows for sensitivity mismatches."""
        for flow in self.flows:
            if (
                flow.data_sensitivity
                in (DataSensitivity.RESTRICTED, DataSensitivity.REGULATED)
                and not flow.encrypted
            ):
                self.findings.append(ThreatFinding(
                    id=self._next_id(),
                    stride_category="Information Disclosure",
                    severity="critical",
                    title=(
                        f"Regulated data in unencrypted flow '{flow.name}'"
                    ),
                    description=(
                        "Regulated/restricted data must be encrypted "
                        "in transit regardless of trust zone."
                    ),
                    affected_element=flow.source_id,
                    affected_flow=flow.id,
                    recommendations=[
                        "Encrypt with TLS 1.3 minimum",
                        "Consider application-layer encryption for PII/PHI",
                    ],
                    cwe_ids=["CWE-319", "CWE-311"],
                ))

    def generate_report(self) -> dict[str, Any]:
        """Generate the full DFD threat analysis report."""
        by_stride = defaultdict(int)
        by_severity = defaultdict(int)
        boundary_crossings = sum(
            1 for f in self.findings if f.trust_boundary_crossing
        )

        for f in self.findings:
            by_stride[f.stride_category] += 1
            by_severity[f.severity] += 1

        return {
            "summary": {
                "total_findings": len(self.findings),
                "by_stride_category": dict(by_stride),
                "by_severity": dict(by_severity),
                "trust_boundary_issues": boundary_crossings,
                "components_analyzed": (
                    len(self.processes) + len(self.data_stores)
                    + len(self.external_entities)
                ),
                "flows_analyzed": len(self.flows),
            },
            "findings": [
                {
                    "id": f.id,
                    "stride": f.stride_category,
                    "severity": f.severity,
                    "title": f.title,
                    "element": f.affected_element,
                    "boundary_crossing": f.trust_boundary_crossing,
                    "recommendations": f.recommendations,
                    "cwe_ids": f.cwe_ids,
                }
                for f in self.findings
            ],
        }
```

**Trust zone hierarchy and analysis triggers:**

| Zone | Level | Inbound Crossing Triggers |
|---|---|---|
| Internet | 0 | Always requires auth + encryption |
| DMZ | 1 | Input validation mandatory |
| Internal Network | 2 | Authentication recommended |
| Secure Zone | 3 | mTLS + authorization required |
| Data Zone | 4 | Encryption at rest + audit logging |
| Management Zone | 5 | MFA + privileged access management |

**Key patterns:**
- Model systems as DFD with processes, data stores, external entities, and flows
- Automatically detect trust boundary crossings by comparing zone levels
- Apply STRIDE threats based on component properties (internet-facing, handles PII, etc.)
- Flag unencrypted flows carrying regulated data regardless of trust zone
- Detect missing audit logging on stores with regulated/restricted data
- Identify admin entities without MFA as critical spoofing risks
- Generate prioritized findings sorted by severity with CWE references'''
    ),
    (
        "security/risk-scoring-automated",
        "Implement a quantitative risk scoring system using FAIR (Factor Analysis of Information Risk) methodology that computes annualized loss expectancy, Monte Carlo simulations for risk ranges, and generates executive risk dashboards.",
        '''Quantitative risk scoring using FAIR methodology with Monte Carlo simulation:

```python
"""
FAIR risk analysis: quantitative risk scoring with Monte Carlo
simulation for annualized loss expectancy estimation.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ThreatType(str, Enum):
    EXTERNAL_MALICIOUS = "external_malicious"
    INTERNAL_MALICIOUS = "internal_malicious"
    INTERNAL_ACCIDENTAL = "internal_accidental"
    PARTNER = "partner"
    ENVIRONMENTAL = "environmental"


@dataclass
class BetaPERTDistribution:
    """
    PERT distribution for modeling uncertainty in risk parameters.
    Uses minimum, most likely, and maximum values.
    """
    minimum: float
    most_likely: float
    maximum: float
    confidence: float = 4.0  # Lambda parameter (4 = standard PERT)

    def sample(self) -> float:
        """Sample from the PERT distribution using Beta approximation."""
        if self.minimum >= self.maximum:
            return self.most_likely

        mu = (
            self.minimum
            + self.confidence * self.most_likely
            + self.maximum
        ) / (self.confidence + 2)

        if mu == self.minimum or mu == self.maximum:
            return mu

        alpha = (
            (mu - self.minimum)
            * (2 * self.most_likely - self.minimum - self.maximum)
        ) / (
            (self.most_likely - mu)
            * (self.maximum - self.minimum)
        )

        if alpha <= 0:
            alpha = 1.0

        beta_param = (
            alpha * (self.maximum - mu) / (mu - self.minimum)
        )
        if beta_param <= 0:
            beta_param = 1.0

        raw = random.betavariate(alpha, beta_param)
        return self.minimum + raw * (self.maximum - self.minimum)

    @property
    def mean(self) -> float:
        return (
            self.minimum
            + self.confidence * self.most_likely
            + self.maximum
        ) / (self.confidence + 2)


@dataclass
class ThreatEventFrequency:
    """How often does the threat event occur per year?"""
    contact_frequency: BetaPERTDistribution  # Times attacker contacts asset/year
    probability_of_action: BetaPERTDistribution  # P(attacker acts given contact)

    def sample(self) -> float:
        cf = max(0, self.contact_frequency.sample())
        pa = max(0, min(1, self.probability_of_action.sample()))
        return cf * pa


@dataclass
class Vulnerability:
    """How likely is the threat to succeed given an attempt?"""
    threat_capability: BetaPERTDistribution  # Attacker skill/resources
    resistance_strength: BetaPERTDistribution  # Defender controls

    def sample(self) -> float:
        tc = max(0, min(1, self.threat_capability.sample()))
        rs = max(0, min(1, self.resistance_strength.sample()))
        # Vulnerability = P(threat capability > resistance)
        return max(0, min(1, tc - rs + 0.5))


@dataclass
class LossMagnitude:
    """Estimated financial loss per incident."""
    primary_loss: BetaPERTDistribution    # Direct costs (response, replacement)
    secondary_loss: BetaPERTDistribution  # Indirect (reputation, legal, fines)

    def sample(self) -> float:
        primary = max(0, self.primary_loss.sample())
        secondary = max(0, self.secondary_loss.sample())
        return primary + secondary


@dataclass
class FAIRScenario:
    """A complete FAIR risk analysis scenario."""
    id: str
    name: str
    description: str
    threat_type: ThreatType
    asset_name: str
    asset_value: float

    # FAIR components
    threat_event_frequency: ThreatEventFrequency
    vulnerability: Vulnerability
    loss_magnitude: LossMagnitude

    # Results (populated after simulation)
    simulation_results: Optional["SimulationResults"] = None


@dataclass
class SimulationResults:
    """Monte Carlo simulation results."""
    iterations: int
    ale_samples: list[float]  # Annualized Loss Expectancy samples

    @property
    def ale_mean(self) -> float:
        return statistics.mean(self.ale_samples)

    @property
    def ale_median(self) -> float:
        return statistics.median(self.ale_samples)

    @property
    def ale_p90(self) -> float:
        return self._percentile(90)

    @property
    def ale_p95(self) -> float:
        return self._percentile(95)

    @property
    def ale_p99(self) -> float:
        return self._percentile(99)

    @property
    def ale_std_dev(self) -> float:
        return statistics.stdev(self.ale_samples)

    def _percentile(self, p: int) -> float:
        sorted_samples = sorted(self.ale_samples)
        idx = int(len(sorted_samples) * p / 100)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    def histogram(self, bins: int = 20) -> list[dict[str, Any]]:
        """Generate histogram data for visualization."""
        min_val = min(self.ale_samples)
        max_val = max(self.ale_samples)
        bin_width = (max_val - min_val) / bins if max_val > min_val else 1

        hist: list[dict[str, Any]] = []
        for i in range(bins):
            lo = min_val + i * bin_width
            hi = lo + bin_width
            count = sum(1 for v in self.ale_samples if lo <= v < hi)
            hist.append({
                "bin_start": round(lo, 2),
                "bin_end": round(hi, 2),
                "count": count,
                "frequency": round(count / len(self.ale_samples), 4),
            })
        return hist


class FAIRAnalyzer:
    """Run FAIR Monte Carlo simulations on risk scenarios."""

    def __init__(self, iterations: int = 10_000, seed: int = 42):
        self.iterations = iterations
        self.seed = seed
        self.scenarios: list[FAIRScenario] = []

    def add_scenario(self, scenario: FAIRScenario) -> None:
        self.scenarios.append(scenario)

    def simulate(self, scenario: FAIRScenario) -> SimulationResults:
        """Run Monte Carlo simulation for a FAIR scenario."""
        random.seed(self.seed)
        ale_samples: list[float] = []

        for _ in range(self.iterations):
            # Step 1: Loss Event Frequency = TEF * Vulnerability
            tef = scenario.threat_event_frequency.sample()
            vuln = scenario.vulnerability.sample()
            lef = tef * vuln  # Loss events per year

            # Step 2: Loss Magnitude per event
            lm = scenario.loss_magnitude.sample()

            # Step 3: ALE = LEF * LM
            ale = lef * lm
            ale_samples.append(ale)

        results = SimulationResults(
            iterations=self.iterations,
            ale_samples=ale_samples,
        )
        scenario.simulation_results = results
        return results

    def simulate_all(self) -> None:
        """Simulate all registered scenarios."""
        for scenario in self.scenarios:
            self.simulate(scenario)

    def executive_dashboard(self) -> dict[str, Any]:
        """Generate executive risk dashboard."""
        self.simulate_all()

        scenario_summaries = []
        total_ale_mean = 0
        total_ale_p90 = 0

        for s in self.scenarios:
            if s.simulation_results is None:
                continue
            r = s.simulation_results
            total_ale_mean += r.ale_mean
            total_ale_p90 += r.ale_p90

            scenario_summaries.append({
                "scenario": s.name,
                "threat_type": s.threat_type.value,
                "asset": s.asset_name,
                "ale_mean": round(r.ale_mean, 2),
                "ale_median": round(r.ale_median, 2),
                "ale_p90": round(r.ale_p90, 2),
                "ale_p95": round(r.ale_p95, 2),
                "risk_rating": self._rate_risk(r.ale_mean),
            })

        scenario_summaries.sort(
            key=lambda x: x["ale_mean"], reverse=True
        )

        return {
            "dashboard": {
                "total_expected_annual_loss": round(total_ale_mean, 2),
                "total_p90_annual_loss": round(total_ale_p90, 2),
                "scenarios_analyzed": len(self.scenarios),
                "simulation_iterations": self.iterations,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "scenarios": scenario_summaries,
            "risk_distribution": {
                "critical": sum(
                    1 for s in scenario_summaries
                    if s["risk_rating"] == "critical"
                ),
                "high": sum(
                    1 for s in scenario_summaries
                    if s["risk_rating"] == "high"
                ),
                "medium": sum(
                    1 for s in scenario_summaries
                    if s["risk_rating"] == "medium"
                ),
                "low": sum(
                    1 for s in scenario_summaries
                    if s["risk_rating"] == "low"
                ),
            },
        }

    def _rate_risk(self, ale: float) -> str:
        if ale > 1_000_000:
            return "critical"
        elif ale > 250_000:
            return "high"
        elif ale > 50_000:
            return "medium"
        else:
            return "low"


# --- Usage example ---

def demo():
    analyzer = FAIRAnalyzer(iterations=10_000, seed=42)

    analyzer.add_scenario(FAIRScenario(
        id="data-breach",
        name="Patient Data Breach via Web App",
        description="External attacker exfiltrates patient records",
        threat_type=ThreatType.EXTERNAL_MALICIOUS,
        asset_name="Patient Database",
        asset_value=5_000_000,
        threat_event_frequency=ThreatEventFrequency(
            contact_frequency=BetaPERTDistribution(50, 200, 500),
            probability_of_action=BetaPERTDistribution(0.01, 0.05, 0.15),
        ),
        vulnerability=Vulnerability(
            threat_capability=BetaPERTDistribution(0.3, 0.5, 0.8),
            resistance_strength=BetaPERTDistribution(0.4, 0.6, 0.85),
        ),
        loss_magnitude=LossMagnitude(
            primary_loss=BetaPERTDistribution(50_000, 200_000, 1_000_000),
            secondary_loss=BetaPERTDistribution(100_000, 500_000, 5_000_000),
        ),
    ))

    analyzer.add_scenario(FAIRScenario(
        id="insider-leak",
        name="Insider Data Leak",
        description="Employee accidentally exposes sensitive data",
        threat_type=ThreatType.INTERNAL_ACCIDENTAL,
        asset_name="Customer Records",
        asset_value=2_000_000,
        threat_event_frequency=ThreatEventFrequency(
            contact_frequency=BetaPERTDistribution(100, 500, 2000),
            probability_of_action=BetaPERTDistribution(0.001, 0.01, 0.05),
        ),
        vulnerability=Vulnerability(
            threat_capability=BetaPERTDistribution(0.2, 0.4, 0.6),
            resistance_strength=BetaPERTDistribution(0.3, 0.5, 0.7),
        ),
        loss_magnitude=LossMagnitude(
            primary_loss=BetaPERTDistribution(10_000, 50_000, 200_000),
            secondary_loss=BetaPERTDistribution(20_000, 100_000, 500_000),
        ),
    ))

    dashboard = analyzer.executive_dashboard()
    print(json.dumps(dashboard, indent=2))
```

**FAIR decomposition model:**

| Factor | Formula | Description |
|---|---|---|
| TEF | Contact Freq x P(Action) | How often threats attempt |
| Vulnerability | P(Capability > Resistance) | Likelihood of success |
| LEF | TEF x Vulnerability | Loss events per year |
| Loss Magnitude | Primary + Secondary loss | Cost per incident |
| ALE | LEF x Loss Magnitude | Annual expected loss |

**Key patterns:**
- Model uncertainty with PERT distributions (min, most likely, max) for all inputs
- Monte Carlo simulation (10K+ iterations) produces loss distribution, not single point estimates
- Report percentiles (P90, P95, P99) alongside mean for executive risk communication
- Decompose risk into frequency (TEF) and magnitude components per FAIR ontology
- Separate primary losses (incident response, remediation) from secondary (reputation, legal)
- Risk ratings based on ALE thresholds enable portfolio-level prioritization
- Reproducible results via seed parameter for consistent reporting'''
    ),
]
