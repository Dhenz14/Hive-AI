"""Quantum computing for developers — Qiskit, quantum algorithms, hybrid."""

PAIRS = [
    (
        "emerging/quantum-basics",
        "Show quantum computing basics for developers: qubits, quantum gates, measurement, and circuit construction with Qiskit.",
        '''Quantum computing with Qiskit:

```python
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.primitives import Sampler
from qiskit.visualization import plot_histogram
import numpy as np


def quantum_basics():
    """Fundamental quantum operations."""
    # Create circuit: 2 qubits, 2 classical bits
    qr = QuantumRegister(2, "q")
    cr = ClassicalRegister(2, "c")
    qc = QuantumCircuit(qr, cr)

    # Hadamard gate: |0⟩ → (|0⟩ + |1⟩)/√2 (superposition)
    qc.h(qr[0])

    # CNOT gate: entangle qubits (Bell state)
    qc.cx(qr[0], qr[1])  # |00⟩ → (|00⟩ + |11⟩)/√2

    # Measure both qubits
    qc.measure(qr, cr)

    # Run on simulator
    sampler = Sampler()
    result = sampler.run(qc, shots=1000).result()
    # Expected: ~50% "00", ~50% "11" (entangled)
    return result


def grovers_search(n_qubits: int = 3, target: int = 5):
    """Grover's algorithm: search unsorted database in O(√N).

    Classical: O(N) checks. Quantum: O(√N) checks.
    For 8 items (3 qubits): classical needs ~4, Grover needs ~2.
    """
    N = 2 ** n_qubits
    n_iterations = int(np.pi / 4 * np.sqrt(N))

    qc = QuantumCircuit(n_qubits, n_qubits)

    # Step 1: Initialize superposition
    qc.h(range(n_qubits))

    for _ in range(n_iterations):
        # Step 2: Oracle — flip sign of target state
        oracle_bits = format(target, f"0{n_qubits}b")
        for i, bit in enumerate(reversed(oracle_bits)):
            if bit == "0":
                qc.x(i)
        qc.h(n_qubits - 1)
        qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)  # Multi-controlled X
        qc.h(n_qubits - 1)
        for i, bit in enumerate(reversed(oracle_bits)):
            if bit == "0":
                qc.x(i)

        # Step 3: Diffusion operator (amplitude amplification)
        qc.h(range(n_qubits))
        qc.x(range(n_qubits))
        qc.h(n_qubits - 1)
        qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
        qc.h(n_qubits - 1)
        qc.x(range(n_qubits))
        qc.h(range(n_qubits))

    qc.measure(range(n_qubits), range(n_qubits))

    sampler = Sampler()
    result = sampler.run(qc, shots=1000).result()
    # Target state should have highest probability
    return result


def quantum_teleportation():
    """Quantum teleportation: transfer qubit state using entanglement.

    Alice has qubit in unknown state |ψ⟩.
    She sends it to Bob using 1 entangled pair + 2 classical bits.
    """
    qc = QuantumCircuit(3, 2)

    # Prepare Alice's qubit in some state
    qc.rx(np.pi / 4, 0)  # |ψ⟩ = Rx(π/4)|0⟩

    # Create Bell pair (qubits 1 & 2)
    qc.h(1)
    qc.cx(1, 2)

    # Alice's operations
    qc.cx(0, 1)  # CNOT with her qubit and her half of Bell pair
    qc.h(0)
    qc.measure([0, 1], [0, 1])

    # Bob's corrections (conditional on Alice's measurements)
    qc.x(2).c_if(1, 1)  # If Alice measured 1 on qubit 1
    qc.z(2).c_if(0, 1)  # If Alice measured 1 on qubit 0

    # Qubit 2 now holds |ψ⟩
    return qc
```

Key concepts:
1. **Superposition** — qubit in both |0⟩ and |1⟩ simultaneously; Hadamard gate creates it
2. **Entanglement** — CNOT creates correlated qubits; measuring one determines the other
3. **Grover's algorithm** — O(√N) search via amplitude amplification; quadratic speedup
4. **Oracle** — black-box function that flips sign of target; problem-specific
5. **Teleportation** — transfer quantum state using entanglement + 2 classical bits'''
    ),
    (
        "emerging/hybrid-quantum",
        "Show hybrid quantum-classical computing: variational quantum circuits, QAOA for optimization, and quantum ML.",
        '''Hybrid quantum-classical algorithms:

```python
from qiskit import QuantumCircuit
from qiskit.primitives import Estimator
from qiskit.circuit import Parameter
import numpy as np
from scipy.optimize import minimize


class VQE:
    """Variational Quantum Eigensolver.

    Find ground state energy of a Hamiltonian using
    parameterized quantum circuit + classical optimizer.
    """

    def __init__(self, n_qubits: int, n_layers: int = 2):
        self.n_qubits = n_qubits
        self.n_layers = n_layers
        self.circuit = self._build_ansatz()
        self.estimator = Estimator()

    def _build_ansatz(self) -> QuantumCircuit:
        """Build parameterized ansatz circuit."""
        qc = QuantumCircuit(self.n_qubits)
        params = []

        for layer in range(self.n_layers):
            # Rotation layer
            for q in range(self.n_qubits):
                theta = Parameter(f"θ_{layer}_{q}")
                params.append(theta)
                qc.ry(theta, q)

            # Entangling layer
            for q in range(self.n_qubits - 1):
                qc.cx(q, q + 1)

        return qc

    def cost_function(self, params: np.ndarray, hamiltonian) -> float:
        """Evaluate ⟨ψ(θ)|H|ψ(θ)⟩."""
        job = self.estimator.run(self.circuit, hamiltonian,
                                  parameter_values=params)
        return job.result().values[0]

    def optimize(self, hamiltonian, n_iterations: int = 100) -> dict:
        """Classical optimization of quantum circuit parameters."""
        n_params = len(self.circuit.parameters)
        initial = np.random.uniform(0, 2 * np.pi, n_params)

        result = minimize(
            self.cost_function,
            initial,
            args=(hamiltonian,),
            method="COBYLA",
            options={"maxiter": n_iterations},
        )

        return {
            "energy": result.fun,
            "optimal_params": result.x,
            "n_iterations": result.nfev,
        }


class QAOA:
    """Quantum Approximate Optimization Algorithm.

    Solve combinatorial optimization (MaxCut, TSP, etc.)
    using quantum-classical hybrid approach.
    """

    def __init__(self, n_qubits: int, p_layers: int = 2):
        self.n_qubits = n_qubits
        self.p = p_layers

    def maxcut_circuit(self, edges: list[tuple],
                        gammas: list[float],
                        betas: list[float]) -> QuantumCircuit:
        """QAOA circuit for MaxCut problem."""
        qc = QuantumCircuit(self.n_qubits)

        # Initial superposition
        qc.h(range(self.n_qubits))

        for layer in range(self.p):
            # Problem unitary (encodes graph structure)
            for i, j in edges:
                qc.cx(i, j)
                qc.rz(gammas[layer], j)
                qc.cx(i, j)

            # Mixer unitary (explores solution space)
            for q in range(self.n_qubits):
                qc.rx(2 * betas[layer], q)

        qc.measure_all()
        return qc

    def evaluate_cut(self, bitstring: str, edges: list[tuple]) -> int:
        """Count edges crossing the cut."""
        cut_value = 0
        for i, j in edges:
            if bitstring[i] != bitstring[j]:
                cut_value += 1
        return cut_value
```

Key patterns:
1. **Variational circuits** — parameterized quantum circuits optimized by classical optimizer
2. **VQE** — find ground state energy; useful for chemistry and materials science
3. **QAOA** — quantum optimization for combinatorial problems; alternating problem/mixer layers
4. **Hybrid loop** — quantum circuit evaluates cost, classical optimizer updates parameters
5. **Near-term quantum** — variational algorithms work on noisy intermediate-scale quantum (NISQ) devices'''
    ),
]
"""
