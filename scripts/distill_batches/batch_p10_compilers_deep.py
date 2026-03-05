"""
Batch P10 — Advanced Compiler Construction
Covers: SSA form, register allocation, JIT compilation, GC integration, LLVM IR.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "compilers/ssa-form-construction",
        "Explain Static Single Assignment form in compilers including phi functions, dominance frontiers, the SSA construction algorithm by Cytron et al., and advantages for optimization passes, then implement SSA conversion with phi node insertion and a simple dead code elimination pass in Python with full type hints.",
        r"""# Static Single Assignment (SSA) Form in Compilers

## What Is SSA and Why It Matters

**Static Single Assignment (SSA)** form is an intermediate representation (IR) property where every variable is assigned exactly once, and every use of a variable refers to exactly one definition. This seemingly simple constraint is extraordinarily powerful because it makes **def-use chains** explicit in the program structure, enabling many optimizations to become straightforward graph algorithms rather than complex dataflow analyses.

Consider this non-SSA code:

```
x = 1
x = x + 2
y = x * 3
```

In SSA form, each assignment creates a new variable version:

```
x1 = 1
x2 = x1 + 2
y1 = x2 * 3
```

The key insight is that in SSA, the definition of every variable is **statically determinable** — you never need to ask "which assignment does this use refer to?" because each variable name maps to exactly one assignment. This property dramatically simplifies many compiler analyses and transformations.

However, control flow merges create a problem. When two branches assign different values to the same variable and control flow merges, we need a mechanism to select the correct value. This is where **phi functions** come in.

## Phi Functions and Control Flow Merges

A **phi function** is a special instruction placed at the beginning of a basic block where control flow merges. It selects a value based on which predecessor block the control flow came from:

```
# Before SSA:
if cond:
    x = 1
else:
    x = 2
print(x)

# After SSA:
if cond:
    x1 = 1
else:
    x2 = 2
x3 = phi(x1, x2)   # x3 = x1 if from then-branch, x2 if from else-branch
print(x3)
```

A **common mistake** is thinking phi functions are actual runtime instructions. They are not — phi functions are purely a bookkeeping device in the IR. During code generation, phi functions are eliminated by inserting copy instructions in predecessor blocks or through register allocation strategies. Therefore, they impose zero runtime overhead.

## Dominance and Dominance Frontiers

To construct SSA efficiently, we need the concept of **dominance**. A node A **dominates** node B in a control flow graph (CFG) if every path from the entry node to B must pass through A. The **immediate dominator** (idom) of B is the closest strict dominator of B.

The **dominance frontier** of a node A is the set of nodes where A's dominance "ends" — formally, DF(A) = {B | A dominates a predecessor of B, but A does not strictly dominate B}. Dominance frontiers tell us exactly where phi functions need to be inserted, because they identify the points where a definition from block A might "meet" definitions from other paths.

The **best practice** for computing dominance is the algorithm by Cooper, Harvey, and Simpson, which iteratively refines the dominator tree. It is simpler to implement than the Lengauer-Tarjan algorithm and performs well in practice.

### The Cytron et al. SSA Construction Algorithm

The classic SSA construction algorithm by Cytron, Ferrante, Rosen, Wegman, and Zadeck (1991) has two phases:

1. **Phi function insertion**: For each variable, find all blocks that define it, then insert phi functions at the dominance frontier of those blocks. This may require iterating because inserting a phi in a block counts as a new definition.

2. **Variable renaming**: Walk the dominator tree, maintaining a stack of current versions for each variable. When encountering a definition, push a new version. When encountering a use, replace with the current version. When encountering a phi function, fill in the operand corresponding to the current predecessor.

```python
from __future__ import annotations
import dataclasses
from typing import Optional
from collections import defaultdict


# === Core IR Data Structures ===

@dataclasses.dataclass
class Instruction:
    # Represents a single SSA instruction
    opcode: str
    dest: Optional[str] = None
    operands: list[str] = dataclasses.field(default_factory=list)
    # For phi nodes, maps predecessor block name to operand variable
    phi_sources: dict[str, str] = dataclasses.field(default_factory=dict)

    def is_phi(self) -> bool:
        return self.opcode == "phi"

    def __repr__(self) -> str:
        if self.is_phi():
            sources = ", ".join(f"{v} from {b}" for b, v in self.phi_sources.items())
            return f"{self.dest} = phi({sources})"
        ops = ", ".join(self.operands)
        if self.dest:
            return f"{self.dest} = {self.opcode} {ops}"
        return f"{self.opcode} {ops}"


@dataclasses.dataclass
class BasicBlock:
    # Represents a basic block in the CFG
    name: str
    instructions: list[Instruction] = dataclasses.field(default_factory=list)
    predecessors: list[str] = dataclasses.field(default_factory=list)
    successors: list[str] = dataclasses.field(default_factory=list)

    def add_phi(self, dest: str, sources: dict[str, str]) -> Instruction:
        phi = Instruction(opcode="phi", dest=dest, phi_sources=sources)
        # Phi nodes always go at the beginning of the block
        self.instructions.insert(0, phi)
        return phi

    def defs(self) -> set[str]:
        # Return all variables defined in this block (original names)
        result: set[str] = set()
        for inst in self.instructions:
            if inst.dest and not inst.is_phi():
                # Strip SSA subscript to get original name
                base = inst.dest.split("_v")[0] if "_v" in inst.dest else inst.dest
                result.add(base)
        return result


@dataclasses.dataclass
class CFG:
    # Control flow graph containing basic blocks
    blocks: dict[str, BasicBlock] = dataclasses.field(default_factory=dict)
    entry: str = "entry"

    def add_block(self, block: BasicBlock) -> None:
        self.blocks[block.name] = block

    def get_block(self, name: str) -> BasicBlock:
        return self.blocks[name]

    def all_blocks(self) -> list[BasicBlock]:
        return list(self.blocks.values())
```

### Computing Dominance and Dominance Frontiers

The dominator computation is the foundation of SSA construction. We use the iterative algorithm because it balances simplicity with efficiency — a **trade-off** that favors implementation clarity over the asymptotic advantage of Lengauer-Tarjan.

```python
class DominanceAnalysis:
    # Computes dominators, dominator tree, and dominance frontiers

    def __init__(self, cfg: CFG) -> None:
        self.cfg = cfg
        self.idom: dict[str, Optional[str]] = {}
        self.dom_tree_children: dict[str, list[str]] = defaultdict(list)
        self.dom_frontier: dict[str, set[str]] = defaultdict(set)
        self._compute_idoms()
        self._build_dom_tree()
        self._compute_dom_frontiers()

    def _compute_idoms(self) -> None:
        # Iterative dominator computation (Cooper, Harvey, Simpson)
        blocks = list(self.cfg.blocks.keys())
        entry = self.cfg.entry

        # Initialize: entry dominates itself, others undefined
        self.idom = {b: None for b in blocks}
        self.idom[entry] = entry

        # Reverse postorder traversal (simplified: use block order)
        rpo = self._reverse_postorder(entry)
        rpo_index = {b: i for i, b in enumerate(rpo)}

        changed = True
        while changed:
            changed = False
            for b in rpo:
                if b == entry:
                    continue
                preds = self.cfg.get_block(b).predecessors
                # Find first processed predecessor
                new_idom: Optional[str] = None
                for p in preds:
                    if self.idom[p] is not None:
                        new_idom = p
                        break
                if new_idom is None:
                    continue
                # Intersect with remaining predecessors
                for p in preds:
                    if p == new_idom or self.idom[p] is None:
                        continue
                    new_idom = self._intersect(p, new_idom, rpo_index)
                if self.idom[b] != new_idom:
                    self.idom[b] = new_idom
                    changed = True

    def _intersect(
        self, b1: str, b2: str, rpo_index: dict[str, int]
    ) -> str:
        finger1, finger2 = b1, b2
        while finger1 != finger2:
            while rpo_index.get(finger1, 0) > rpo_index.get(finger2, 0):
                finger1 = self.idom[finger1] or finger1
            while rpo_index.get(finger2, 0) > rpo_index.get(finger1, 0):
                finger2 = self.idom[finger2] or finger2
        return finger1

    def _reverse_postorder(self, entry: str) -> list[str]:
        visited: set[str] = set()
        order: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            for succ in self.cfg.get_block(node).successors:
                if succ not in visited:
                    dfs(succ)
            order.append(node)

        dfs(entry)
        order.reverse()
        return order

    def _build_dom_tree(self) -> None:
        for block, idom in self.idom.items():
            if idom is not None and idom != block:
                self.dom_tree_children[idom].append(block)

    def _compute_dom_frontiers(self) -> None:
        # For each join point (block with 2+ predecessors),
        # walk up the dominator tree from each predecessor
        for b_name, block in self.cfg.blocks.items():
            if len(block.predecessors) < 2:
                continue
            for pred in block.predecessors:
                runner = pred
                while runner != self.idom.get(b_name):
                    self.dom_frontier[runner].add(b_name)
                    runner = self.idom.get(runner, runner)
                    if runner is None:
                        break

    def dominates(self, a: str, b: str) -> bool:
        # Does block a dominate block b?
        current = b
        while current is not None:
            if current == a:
                return True
            if self.idom[current] == current:
                break
            current = self.idom.get(current)
        return False
```

### SSA Construction and Phi Insertion

Now we combine dominance frontiers with variable tracking to construct SSA form. A **pitfall** here is forgetting that phi insertion is iterative — inserting a phi in block B counts as a new definition, which may require additional phi insertions at B's dominance frontier.

```python
class SSAConstructor:
    # Converts a CFG to SSA form using the Cytron et al. algorithm

    def __init__(self, cfg: CFG) -> None:
        self.cfg = cfg
        self.dom = DominanceAnalysis(cfg)
        self.var_counter: dict[str, int] = defaultdict(int)
        self.var_stack: dict[str, list[str]] = defaultdict(list)

    def construct(self) -> None:
        # Phase 1: insert phi functions
        self._insert_phis()
        # Phase 2: rename variables
        self._rename(self.cfg.entry)

    def _insert_phis(self) -> None:
        # Collect definitions per variable
        defs_of: dict[str, set[str]] = defaultdict(set)
        for block in self.cfg.all_blocks():
            for var in block.defs():
                defs_of[var].add(block.name)

        # Iterated dominance frontier phi insertion
        for var, def_blocks in defs_of.items():
            worklist = list(def_blocks)
            phi_inserted: set[str] = set()
            while worklist:
                block_name = worklist.pop()
                for frontier_block in self.dom.dom_frontier.get(block_name, set()):
                    if frontier_block not in phi_inserted:
                        phi_inserted.add(frontier_block)
                        fb = self.cfg.get_block(frontier_block)
                        # Create phi with placeholder operands
                        sources = {p: var for p in fb.predecessors}
                        fb.add_phi(dest=var, sources=sources)
                        # This phi is a new def, so add to worklist
                        if frontier_block not in def_blocks:
                            worklist.append(frontier_block)

    def _fresh_name(self, var: str) -> str:
        self.var_counter[var] += 1
        return f"{var}_v{self.var_counter[var]}"

    def _current_name(self, var: str) -> str:
        stack = self.var_stack[var]
        return stack[-1] if stack else var

    def _rename(self, block_name: str) -> None:
        block = self.cfg.get_block(block_name)
        # Track how many names we push so we can pop them later
        pushed: dict[str, int] = defaultdict(int)

        for inst in block.instructions:
            # Rename uses first (unless phi, which is handled separately)
            if not inst.is_phi():
                new_ops: list[str] = []
                for op in inst.operands:
                    new_ops.append(self._current_name(op))
                inst.operands = new_ops

            # Rename definition
            if inst.dest:
                base = inst.dest
                new_name = self._fresh_name(base)
                self.var_stack[base].append(new_name)
                pushed[base] += 1
                inst.dest = new_name

        # Fill in phi operands in successor blocks
        for succ_name in block.successors:
            succ = self.cfg.get_block(succ_name)
            for inst in succ.instructions:
                if not inst.is_phi():
                    break
                if block_name in inst.phi_sources:
                    var = inst.phi_sources[block_name]
                    inst.phi_sources[block_name] = self._current_name(var)

        # Recurse into dominator tree children
        for child in self.dom.dom_tree_children.get(block_name, []):
            self._rename(child)

        # Pop the names we pushed
        for var, count in pushed.items():
            for _ in range(count):
                self.var_stack[var].pop()


# === Dead Code Elimination on SSA ===

class DeadCodeEliminator:
    # Removes instructions whose results are never used
    # SSA makes this straightforward because each def has exactly one name

    def __init__(self, cfg: CFG) -> None:
        self.cfg = cfg

    def eliminate(self) -> int:
        # Collect all used variables
        used: set[str] = set()
        side_effect_ops = {"call", "store", "br", "ret", "print", "branch"}

        # First pass: find all used variables
        for block in self.cfg.all_blocks():
            for inst in block.instructions:
                if inst.is_phi():
                    for var in inst.phi_sources.values():
                        used.add(var)
                else:
                    for op in inst.operands:
                        used.add(op)

        # Second pass: remove dead instructions
        removed = 0
        for block in self.cfg.all_blocks():
            live_insts: list[Instruction] = []
            for inst in block.instructions:
                if inst.dest and inst.dest not in used:
                    if inst.opcode not in side_effect_ops:
                        removed += 1
                        continue
                live_insts.append(inst)
            block.instructions = live_insts

        # Iterate until fixed point
        if removed > 0:
            removed += self.eliminate()
        return removed


def demo_ssa_construction() -> None:
    # Build a sample CFG:
    #   entry -> then, else
    #   then -> merge
    #   else -> merge
    cfg = CFG()

    entry = BasicBlock(name="entry", successors=["then", "else"])
    entry.instructions = [
        Instruction("const", "x", ["1"]),
        Instruction("const", "cond", ["true"]),
        Instruction("branch", operands=["cond", "then", "else"]),
    ]

    then_block = BasicBlock(
        name="then", predecessors=["entry"], successors=["merge"]
    )
    then_block.instructions = [
        Instruction("add", "x", ["x", "10"]),
        Instruction("const", "y", ["42"]),
    ]

    else_block = BasicBlock(
        name="else", predecessors=["entry"], successors=["merge"]
    )
    else_block.instructions = [
        Instruction("mul", "x", ["x", "2"]),
        Instruction("const", "unused", ["999"]),
    ]

    merge = BasicBlock(
        name="merge", predecessors=["then", "else"], successors=[]
    )
    merge.instructions = [
        Instruction("print", operands=["x"]),
    ]

    for b in [entry, then_block, else_block, merge]:
        cfg.add_block(b)

    print("=== Before SSA ===")
    for b in cfg.all_blocks():
        print(f"\n{b.name}:")
        for inst in b.instructions:
            print(f"  {inst}")

    constructor = SSAConstructor(cfg)
    constructor.construct()

    print("\n=== After SSA ===")
    for b in cfg.all_blocks():
        print(f"\n{b.name}:")
        for inst in b.instructions:
            print(f"  {inst}")

    dce = DeadCodeEliminator(cfg)
    removed = dce.eliminate()
    print(f"\n=== After DCE (removed {removed} instructions) ===")
    for b in cfg.all_blocks():
        print(f"\n{b.name}:")
        for inst in b.instructions:
            print(f"  {inst}")


if __name__ == "__main__":
    demo_ssa_construction()
```

## Advantages of SSA for Optimization

SSA form enables several powerful optimizations to become almost trivial:

- **Constant propagation**: Because each variable has one definition, checking if a variable is constant requires looking at just one instruction.
- **Dead code elimination**: If a variable's definition has no uses, it is dead. No complex liveness analysis needed — therefore DCE becomes a simple graph reachability problem on use-def chains.
- **Global value numbering**: Detecting redundant computations is simplified because identical operands in SSA always refer to the same values.
- **Loop-invariant code motion**: Identifying invariant computations is direct — if all operands of an instruction are defined outside the loop, the instruction is loop-invariant.

### Trade-offs and Practical Considerations

The primary **trade-off** with SSA is increased memory consumption from variable copies and phi functions, versus the simplification of analysis algorithms. In practice, the optimization improvements far outweigh the overhead. Modern compilers like GCC, LLVM, and the JVM's C2 compiler all use SSA as their primary IR.

A **pitfall** in SSA construction is handling **critical edges** — edges from a block with multiple successors to a block with multiple predecessors. These edges must be split by inserting an empty block, because phi operands in the target block need a unique predecessor to place copy instructions during phi elimination.

## Summary / Key Takeaways

- **SSA form** assigns each variable exactly once, making def-use relationships explicit and enabling efficient optimizations.
- **Phi functions** resolve the ambiguity at control flow merge points by selecting values based on the incoming edge.
- **Dominance frontiers** determine precisely where phi functions must be inserted, avoiding unnecessary overhead.
- The **Cytron et al. algorithm** constructs SSA in two phases: iterated dominance frontier phi insertion, followed by dominator-tree-guided renaming.
- SSA simplifies **constant propagation**, **dead code elimination**, and **value numbering** to straightforward graph algorithms.
- **Best practice**: always split critical edges before SSA construction to simplify subsequent phi elimination.
- The **trade-off** of slightly larger IR size is overwhelmingly justified by the optimization power SSA provides.
"""
    ),
    (
        "compilers/register-allocation-graph-coloring",
        "Explain register allocation in compilers using graph coloring and linear scan approaches, covering interference graph construction, live variable analysis, spilling strategies, coalescing, and provide a complete Python implementation of a simplified graph-coloring register allocator with interference graph building and spill cost estimation.",
        r"""# Register Allocation via Graph Coloring

## The Register Allocation Problem

**Register allocation** is one of the most critical phases in a compiler backend. CPUs have a limited number of fast registers (typically 8-32 general-purpose registers), but programs use far more virtual registers or temporaries in their IR. The register allocator must map an unbounded number of virtual registers to a finite set of physical registers, inserting **spill code** (loads and stores to memory) when the mapping is impossible.

This problem is NP-complete in general (it reduces to graph coloring), but practical algorithms produce near-optimal results. The two dominant approaches are **graph coloring** (used by GCC's IRA and LLVM's greedy allocator) and **linear scan** (used by JIT compilers like HotSpot's C1 and V8's Crankshaft, because it is faster at the cost of slightly worse allocation quality).

## Live Variable Analysis

Before building the interference graph, we must determine **liveness** — which variables are "alive" at each program point. A variable is **live** at a point if there exists some path from that point to a use of the variable that does not pass through a redefinition.

**Liveness** is computed as a backward dataflow analysis:

- **LiveOut(B)** = union of LiveIn of all successors of B
- **LiveIn(B)** = (LiveOut(B) - Def(B)) union Use(B)

Where Use(B) contains variables used before being defined in B, and Def(B) contains variables defined in B. This analysis iterates to a fixed point because the equations are monotone over set union.

A **common mistake** is computing liveness in forward order. Liveness is inherently a backward analysis — therefore you must process blocks in reverse postorder of the reverse CFG (or equivalently, postorder of the original CFG) for efficient convergence.

```python
from __future__ import annotations
import dataclasses
from typing import Optional
from collections import defaultdict


# === IR Representation ===

@dataclasses.dataclass
class IRInstruction:
    # A simple three-address instruction
    opcode: str
    dest: Optional[str] = None
    src1: Optional[str] = None
    src2: Optional[str] = None

    def uses(self) -> set[str]:
        result: set[str] = set()
        if self.src1 and not self.src1.isdigit():
            result.add(self.src1)
        if self.src2 and not self.src2.isdigit():
            result.add(self.src2)
        return result

    def defines(self) -> set[str]:
        if self.dest:
            return {self.dest}
        return set()

    def __repr__(self) -> str:
        if self.opcode == "mov":
            return f"{self.dest} = {self.src1}"
        if self.src2:
            return f"{self.dest} = {self.src1} {self.opcode} {self.src2}"
        if self.dest:
            return f"{self.dest} = {self.opcode} {self.src1 or ''}"
        return f"{self.opcode} {self.src1 or ''}"


@dataclasses.dataclass
class Block:
    name: str
    instructions: list[IRInstruction] = dataclasses.field(default_factory=list)
    successors: list[str] = dataclasses.field(default_factory=list)
    predecessors: list[str] = dataclasses.field(default_factory=list)
    live_in: set[str] = dataclasses.field(default_factory=set)
    live_out: set[str] = dataclasses.field(default_factory=set)


class LivenessAnalyzer:
    # Performs backward dataflow liveness analysis

    def __init__(self, blocks: dict[str, Block]) -> None:
        self.blocks = blocks

    def analyze(self) -> None:
        # Iterate to fixed point
        changed = True
        while changed:
            changed = False
            for block in self.blocks.values():
                # LiveOut = union of LiveIn of all successors
                new_live_out: set[str] = set()
                for succ_name in block.successors:
                    new_live_out |= self.blocks[succ_name].live_in

                # LiveIn = Use(B) union (LiveOut(B) - Def(B))
                use_set, def_set = self._use_def(block)
                new_live_in = use_set | (new_live_out - def_set)

                if new_live_in != block.live_in or new_live_out != block.live_out:
                    changed = True
                    block.live_in = new_live_in
                    block.live_out = new_live_out

    def _use_def(self, block: Block) -> tuple[set[str], set[str]]:
        # Use: variables used before being defined
        # Def: variables defined in the block
        use: set[str] = set()
        defs: set[str] = set()
        for inst in block.instructions:
            # Uses that haven't been defined yet in this block
            for u in inst.uses():
                if u not in defs:
                    use.add(u)
            defs |= inst.defines()
        return use, defs

    def live_at_instruction(
        self, block: Block, index: int
    ) -> set[str]:
        # Compute the set of variables live just after instruction[index]
        live = set(block.live_out)
        for i in range(len(block.instructions) - 1, index, -1):
            inst = block.instructions[i]
            live -= inst.defines()
            live |= inst.uses()
        return live
```

## Interference Graph Construction

The **interference graph** captures conflicts between variables. Two variables **interfere** if they are simultaneously live at some program point — meaning they cannot share the same physical register. Each variable is a node, and an edge connects two nodes that interfere.

### Building the Graph

For each instruction, we compute the set of variables live after that instruction. Every variable defined by the instruction interferes with every variable in the live-out set (except itself, and except the source of a move instruction — this exception enables **coalescing**).

```python
class InterferenceGraph:
    # Graph where nodes are variables and edges represent conflicts

    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.edges: set[frozenset[str]] = set()
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        self.move_pairs: list[tuple[str, str]] = []
        # Spill cost heuristic: usage frequency
        self.use_count: dict[str, int] = defaultdict(int)

    def add_node(self, var: str) -> None:
        self.nodes.add(var)

    def add_edge(self, u: str, v: str) -> None:
        if u == v:
            return
        edge = frozenset({u, v})
        if edge not in self.edges:
            self.edges.add(edge)
            self.adjacency[u].add(v)
            self.adjacency[v].add(u)

    def degree(self, node: str) -> int:
        return len(self.adjacency[node])

    def neighbors(self, node: str) -> set[str]:
        return set(self.adjacency[node])

    def remove_node(self, node: str) -> None:
        for neighbor in self.adjacency[node]:
            self.adjacency[neighbor].discard(node)
            self.edges.discard(frozenset({node, neighbor}))
        del self.adjacency[node]
        self.nodes.discard(node)

    def spill_cost(self, node: str) -> float:
        # Heuristic: use_count / degree
        # Low cost = good spill candidate (used rarely, many conflicts)
        deg = self.degree(node)
        if deg == 0:
            return float("inf")
        return self.use_count.get(node, 1) / deg


def build_interference_graph(
    blocks: dict[str, Block], analyzer: LivenessAnalyzer
) -> InterferenceGraph:
    # Constructs the interference graph from liveness information
    graph = InterferenceGraph()

    for block in blocks.values():
        live = set(block.live_out)

        # Walk instructions in reverse order
        for i in range(len(block.instructions) - 1, -1, -1):
            inst = block.instructions[i]

            for d in inst.defines():
                graph.add_node(d)
                for l_var in live:
                    # Move instructions: don't add interference
                    # between src and dest (enables coalescing)
                    if inst.opcode == "mov" and l_var == inst.src1:
                        graph.move_pairs.append((d, l_var))
                        continue
                    graph.add_edge(d, l_var)

            # Update liveness
            live -= inst.defines()
            for u in inst.uses():
                graph.add_node(u)
                graph.use_count[u] += 1
                live.add(u)

    return graph
```

## Graph Coloring Register Allocator

The **Chaitin-Briggs** algorithm is the classic graph coloring approach. The key insight is: if a node has fewer than K neighbors (where K is the number of available registers), it can always be colored regardless of how its neighbors are colored. Therefore, we can **simplify** the graph by repeatedly removing low-degree nodes.

The algorithm has four phases: **simplify** (remove nodes with degree < K), **spill** (select a node to spill if no low-degree nodes exist), **select** (pop nodes from the stack and assign colors), and optionally **coalesce** (merge move-related nodes).

```python
@dataclasses.dataclass
class AllocationResult:
    # Result of register allocation
    assignment: dict[str, str]  # virtual -> physical register
    spilled: set[str]           # variables that must be spilled to memory

    def __repr__(self) -> str:
        lines = ["Register Assignment:"]
        for var, reg in sorted(self.assignment.items()):
            lines.append(f"  {var} -> {reg}")
        if self.spilled:
            lines.append(f"Spilled: {', '.join(sorted(self.spilled))}")
        return "\n".join(lines)


class GraphColoringAllocator:
    # Simplified Chaitin-Briggs register allocator

    def __init__(
        self, graph: InterferenceGraph, num_registers: int = 4
    ) -> None:
        self.original_graph = graph
        self.num_registers = num_registers
        self.registers = [f"R{i}" for i in range(num_registers)]
        # Work on a copy so we can modify the graph
        self.work_nodes: set[str] = set(graph.nodes)
        self.work_adj: dict[str, set[str]] = {
            n: set(graph.adjacency[n]) for n in graph.nodes
        }

    def allocate(self) -> AllocationResult:
        stack: list[tuple[str, bool]] = []
        # (variable_name, is_potential_spill)

        # Phase 1 & 2: Simplify and select spill candidates
        remaining = set(self.work_nodes)
        while remaining:
            # Try to find a node with degree < K
            simplified = False
            for node in list(remaining):
                degree = len(self.work_adj[node] & remaining)
                if degree < self.num_registers:
                    stack.append((node, False))
                    remaining.remove(node)
                    simplified = True
                    break

            if not simplified:
                # No low-degree node found — must spill
                # Best practice: choose the node with lowest spill cost
                spill_candidate = min(
                    remaining,
                    key=lambda n: self.original_graph.spill_cost(n),
                )
                stack.append((spill_candidate, True))
                remaining.remove(spill_candidate)

        # Phase 3: Select — pop and assign colors
        assignment: dict[str, str] = {}
        spilled: set[str] = set()

        while stack:
            node, potential_spill = stack.pop()
            # Find colors used by already-assigned neighbors
            used_colors: set[str] = set()
            for neighbor in self.original_graph.adjacency.get(node, set()):
                if neighbor in assignment:
                    used_colors.add(assignment[neighbor])

            # Find available color
            available = [r for r in self.registers if r not in used_colors]

            if available:
                # Optimistic coloring succeeds even for potential spills
                assignment[node] = available[0]
            else:
                # However, if we truly cannot color, we must spill
                spilled.add(node)

        return AllocationResult(assignment=assignment, spilled=spilled)


def demo_register_allocation() -> None:
    # Create a sample program and allocate registers
    blocks: dict[str, Block] = {}

    main_block = Block(name="main", successors=["exit"])
    main_block.instructions = [
        IRInstruction("load", "a", "addr1"),
        IRInstruction("load", "b", "addr2"),
        IRInstruction("add", "c", "a", "b"),
        IRInstruction("load", "d", "addr3"),
        IRInstruction("mul", "e", "c", "d"),
        IRInstruction("add", "f", "a", "e"),
        IRInstruction("store", src1="f", src2="addr4"),
    ]
    blocks["main"] = main_block

    exit_block = Block(name="exit", predecessors=["main"])
    blocks["exit"] = exit_block

    # Run liveness analysis
    analyzer = LivenessAnalyzer(blocks)
    analyzer.analyze()

    print("=== Liveness ===")
    for bname, block in blocks.items():
        print(f"{bname}: live_in={block.live_in}, live_out={block.live_out}")

    # Build interference graph
    ig = build_interference_graph(blocks, analyzer)

    print("\n=== Interference Graph ===")
    for node in sorted(ig.nodes):
        neighbors = sorted(ig.adjacency[node])
        print(f"  {node}: interferes with {neighbors}")

    # Allocate with 3 registers (will likely need spilling)
    allocator = GraphColoringAllocator(ig, num_registers=3)
    result = allocator.allocate()
    print(f"\n=== Allocation (3 registers) ===")
    print(result)

    # Allocate with 4 registers
    allocator4 = GraphColoringAllocator(ig, num_registers=4)
    result4 = allocator4.allocate()
    print(f"\n=== Allocation (4 registers) ===")
    print(result4)


if __name__ == "__main__":
    demo_register_allocation()
```

### Linear Scan: The Fast Alternative

**Linear scan** allocation is the **trade-off** choice for JIT compilers. Instead of building an interference graph (O(V+E) space), it processes live intervals in a single pass. Variables are sorted by their start point, and registers are greedily assigned. When all registers are occupied, the variable with the farthest end point is spilled. Linear scan runs in O(n log n) time versus O(n^2) for graph coloring in the worst case.

However, linear scan produces inferior allocations because it cannot capture the full interference structure. A variable might be spilled even though a better assignment exists that graph coloring would find. Therefore, production compilers often use linear scan for fast (O1) compilation and graph coloring for optimized (O2/O3) builds.

### Spilling Strategies

A **pitfall** in spill code generation is naive spilling, where every use loads from memory and every definition stores to memory. **Best practice** is to use **spill-everywhere** only as a baseline, then apply **rematerialization** (recompute cheap values instead of loading from memory) and **split live ranges** (spill only over the region of high register pressure).

## Summary / Key Takeaways

- **Register allocation** maps virtual registers to physical registers, with spilling when registers are insufficient.
- **Liveness analysis** determines which variables are simultaneously live, forming the basis for interference detection.
- The **interference graph** connects variables that cannot share a register because they are live at the same point.
- **Graph coloring** (Chaitin-Briggs) produces high-quality allocations by iteratively simplifying the graph and optimistically coloring potential spills.
- **Linear scan** is faster but produces slightly worse allocations — a **trade-off** favored by JIT compilers.
- **Spill cost heuristics** (use count divided by degree) guide the allocator toward spilling variables that cause minimal performance impact.
- **Coalescing** eliminates unnecessary moves by merging non-interfering move-related variables, but aggressive coalescing can increase degree and cause more spills.
"""
    ),
    (
        "compilers/jit-compilation-tracing",
        "Explain JIT compilation techniques including tracing JIT versus method JIT architectures, hot path detection with profiling counters, inline caching for dynamic dispatch, deoptimization with on-stack replacement, and implement a simple tracing JIT for a bytecode interpreter in Python with hot loop detection and native code emission concepts.",
        r"""# JIT Compilation: Tracing, Method JIT, and Runtime Optimization

## Understanding JIT Compilation

**Just-In-Time (JIT) compilation** bridges the gap between interpretation and ahead-of-time (AOT) compilation by compiling code at runtime, when the program's actual behavior is observable. This enables optimizations that are impossible statically — the JIT can speculate based on observed types, inline virtual method calls, and eliminate branches that are never taken in practice.

The fundamental insight is that most programs spend the vast majority of their time executing a small fraction of their code (the **hot code**). Therefore, a JIT compiler only needs to optimize those hot regions, amortizing the compilation cost over many executions.

## Method JIT vs Tracing JIT

There are two primary JIT architectures, each with distinct **trade-offs**:

### Method JIT

A **method JIT** compiles entire functions at a time. When a function becomes hot (determined by invocation counters), the JIT compiles it to native code. Examples include the JVM's C2 compiler and V8's TurboFan.

Advantages: produces well-optimized code for entire functions, natural integration with calling conventions, and straightforward deoptimization. However, it may compile cold code within a hot function, wasting compilation time.

### Tracing JIT

A **tracing JIT** records the actual execution path through a hot loop, producing a linear **trace** — a straight-line sequence of operations with **guards** at every branch point. If a guard fails at runtime, execution falls back to the interpreter. Examples include LuaJIT and the now-retired Mozilla TraceMonkey.

Advantages: traces naturally follow hot paths across function boundaries (automatic inlining), produce simple linear IR that is easy to optimize, and never compile cold code. However, traces can "explode" with many branch points, and nested loops require trace trees or side exits.

A **common mistake** is assuming tracing JITs are always faster. Because traces only capture one path, programs with polymorphic behavior (many different types at the same call site) can cause excessive guard failures and trace invalidation. Therefore, method JITs often win for object-oriented code.

## Hot Path Detection and Profiling

### Invocation and Back-Edge Counters

The simplest profiling mechanism uses two counters per function: an **invocation counter** (incremented on entry) and a **back-edge counter** (incremented on loop iterations). When either exceeds a threshold, the function or loop is considered hot.

```python
from __future__ import annotations
import dataclasses
from typing import Any, Callable, Optional
from enum import Enum, auto
from collections import defaultdict


# === Bytecode Definitions ===

class Op(Enum):
    LOAD_CONST = auto()
    LOAD_VAR = auto()
    STORE_VAR = auto()
    ADD = auto()
    SUB = auto()
    MUL = auto()
    LT = auto()
    GT = auto()
    EQ = auto()
    JUMP = auto()
    JUMP_IF_FALSE = auto()
    JUMP_IF_TRUE = auto()
    PRINT = auto()
    CALL = auto()
    RET = auto()
    HALT = auto()


@dataclasses.dataclass
class Bytecode:
    op: Op
    arg: Any = None

    def __repr__(self) -> str:
        if self.arg is not None:
            return f"{self.op.name} {self.arg}"
        return self.op.name


# === Trace Recording ===

@dataclasses.dataclass
class TraceEntry:
    # A single recorded operation in a trace
    op: Op
    arg: Any = None
    # Guard: the condition that must hold for this trace to be valid
    guard_value: Optional[bool] = None
    # Type specialization info
    observed_types: Optional[tuple[type, ...]] = None

    def __repr__(self) -> str:
        parts = [f"{self.op.name}"]
        if self.arg is not None:
            parts.append(f"({self.arg})")
        if self.guard_value is not None:
            parts.append(f"[guard={self.guard_value}]")
        if self.observed_types:
            types_str = ", ".join(t.__name__ for t in self.observed_types)
            parts.append(f"<{types_str}>")
        return " ".join(parts)


@dataclasses.dataclass
class CompiledTrace:
    # A compiled trace ready for execution
    trace_id: int
    loop_header_pc: int
    entries: list[TraceEntry]
    guard_failures: int = 0
    executions: int = 0
    # Simulated native code (in a real JIT, this would be machine code)
    native_ops: list[Callable[..., Any]] = dataclasses.field(
        default_factory=list
    )

    def invalidated(self) -> bool:
        # Too many guard failures means the trace is not useful
        if self.executions == 0:
            return False
        failure_rate = self.guard_failures / max(self.executions, 1)
        return failure_rate > 0.3
```

### The Tracing JIT Interpreter

The interpreter below combines bytecode execution with trace recording and hot loop detection. When a back-edge (jump to a lower PC) is detected and the counter exceeds a threshold, the interpreter enters **recording mode** and captures every operation until the loop header is reached again.

```python
class TracingJITInterpreter:
    # Bytecode interpreter with tracing JIT capability

    HOTNESS_THRESHOLD: int = 3  # Low for demonstration

    def __init__(self, bytecodes: list[Bytecode]) -> None:
        self.code = bytecodes
        self.pc: int = 0
        self.stack: list[Any] = []
        self.variables: dict[str, Any] = {}
        self.output: list[str] = []

        # Profiling state
        self.back_edge_count: dict[int, int] = defaultdict(int)
        self.compiled_traces: dict[int, CompiledTrace] = {}
        self.trace_id_counter: int = 0

        # Recording state
        self.recording: bool = False
        self.recording_pc: int = -1
        self.current_trace: list[TraceEntry] = []

    def run(self) -> list[str]:
        while self.pc < len(self.code):
            bc = self.code[self.pc]

            # Check if we have a compiled trace for this PC
            if not self.recording and self.pc in self.compiled_traces:
                trace = self.compiled_traces[self.pc]
                if not trace.invalidated():
                    success = self._execute_trace(trace)
                    if success:
                        continue
                    # Guard failure: fall through to interpreter

            # Execute the bytecode in the interpreter
            self._interpret_one(bc)

        return self.output

    def _interpret_one(self, bc: Bytecode) -> None:
        # Record the operation if we are in recording mode
        if self.recording:
            self._record(bc)

        if bc.op == Op.LOAD_CONST:
            self.stack.append(bc.arg)
            self.pc += 1

        elif bc.op == Op.LOAD_VAR:
            self.stack.append(self.variables.get(bc.arg, 0))
            self.pc += 1

        elif bc.op == Op.STORE_VAR:
            self.variables[bc.arg] = self.stack.pop()
            self.pc += 1

        elif bc.op == Op.ADD:
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(a + b)
            self.pc += 1

        elif bc.op == Op.SUB:
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(a - b)
            self.pc += 1

        elif bc.op == Op.MUL:
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(a * b)
            self.pc += 1

        elif bc.op == Op.LT:
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(a < b)
            self.pc += 1

        elif bc.op == Op.GT:
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(a > b)
            self.pc += 1

        elif bc.op == Op.EQ:
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(a == b)
            self.pc += 1

        elif bc.op == Op.JUMP:
            target = bc.arg
            self._check_back_edge(target)
            self.pc = target

        elif bc.op == Op.JUMP_IF_FALSE:
            cond = self.stack.pop()
            if not cond:
                self.pc = bc.arg
            else:
                self.pc += 1

        elif bc.op == Op.JUMP_IF_TRUE:
            cond = self.stack.pop()
            if cond:
                self._check_back_edge(bc.arg)
                self.pc = bc.arg
            else:
                self.pc += 1

        elif bc.op == Op.PRINT:
            val = self.stack.pop()
            self.output.append(str(val))
            self.pc += 1

        elif bc.op == Op.HALT:
            self.pc = len(self.code)

        else:
            raise RuntimeError(f"Unknown opcode: {bc.op}")

    def _check_back_edge(self, target: int) -> None:
        # A back edge is a jump to a lower or equal PC (loop)
        if target <= self.pc:
            self.back_edge_count[target] += 1
            if (
                self.back_edge_count[target] >= self.HOTNESS_THRESHOLD
                and target not in self.compiled_traces
                and not self.recording
            ):
                # Start recording a trace
                self.recording = True
                self.recording_pc = target
                self.current_trace = []

    def _record(self, bc: Bytecode) -> None:
        entry = TraceEntry(op=bc.op, arg=bc.arg)

        # Record type specialization for arithmetic ops
        if bc.op in (Op.ADD, Op.SUB, Op.MUL) and len(self.stack) >= 2:
            entry.observed_types = (type(self.stack[-2]), type(self.stack[-1]))

        # Record guard values for conditional jumps
        if bc.op in (Op.JUMP_IF_FALSE, Op.JUMP_IF_TRUE):
            if self.stack:
                entry.guard_value = bool(self.stack[-1])

        self.current_trace.append(entry)

        # Check if we have completed a full loop iteration
        if bc.op in (Op.JUMP, Op.JUMP_IF_TRUE) and bc.arg == self.recording_pc:
            self._finish_trace()

    def _finish_trace(self) -> None:
        self.trace_id_counter += 1
        trace = CompiledTrace(
            trace_id=self.trace_id_counter,
            loop_header_pc=self.recording_pc,
            entries=list(self.current_trace),
        )
        self.compiled_traces[self.recording_pc] = trace
        self.recording = False
        self.current_trace = []

    def _execute_trace(self, trace: CompiledTrace) -> bool:
        # Execute the compiled trace, checking guards
        trace.executions += 1

        for entry in trace.entries:
            # Check type guards
            if entry.observed_types and entry.op in (Op.ADD, Op.SUB, Op.MUL):
                if len(self.stack) >= 2:
                    actual = (type(self.stack[-2]), type(self.stack[-1]))
                    if actual != entry.observed_types:
                        trace.guard_failures += 1
                        return False

            # Check branch guards
            if entry.guard_value is not None:
                if entry.op in (Op.JUMP_IF_FALSE, Op.JUMP_IF_TRUE):
                    if self.stack and bool(self.stack[-1]) != entry.guard_value:
                        trace.guard_failures += 1
                        return False

            # Execute the operation using the same interpreter
            bc = Bytecode(op=entry.op, arg=entry.arg)
            self._interpret_one(bc)

        return True
```

## Inline Caching

**Inline caching** is a technique for accelerating dynamic dispatch. At each call site, the JIT records the type it last observed. On subsequent calls, it checks if the type matches. If so, it directly calls the cached method (a **monomorphic** inline cache). If types vary, the cache becomes **polymorphic** (checking a few types) or **megamorphic** (falling back to full lookup).

This is a **best practice** in dynamic language JITs because method lookup in languages like JavaScript, Python, or Ruby involves traversing prototype chains or MRO — an expensive operation that inline caching reduces to a single type check and direct call.

## Deoptimization and On-Stack Replacement

When a JIT-compiled function's assumptions are violated (a type guard fails, a class is redefined), the runtime must **deoptimize** — transfer execution from compiled native code back to the interpreter. **On-stack replacement (OSR)** is the mechanism for doing this mid-execution, even in the middle of a loop.

OSR requires maintaining a mapping between compiled code state (register values, stack positions) and interpreter state (bytecode PC, operand stack). This is a significant engineering challenge and a **pitfall** for JIT implementers — getting the mapping wrong causes subtle correctness bugs that only manifest under specific optimization patterns.

```python
def demo_tracing_jit() -> None:
    # Program: sum = 0; for i in range(10): sum += i * 2; print(sum)
    program = [
        # 0: sum = 0
        Bytecode(Op.LOAD_CONST, 0),
        Bytecode(Op.STORE_VAR, "sum"),
        # 2: i = 0
        Bytecode(Op.LOAD_CONST, 0),
        Bytecode(Op.STORE_VAR, "i"),
        # 4: loop header - if i < 10 continue, else jump to end
        Bytecode(Op.LOAD_VAR, "i"),
        Bytecode(Op.LOAD_CONST, 10),
        Bytecode(Op.LT),
        Bytecode(Op.JUMP_IF_FALSE, 17),
        # 8: sum = sum + (i * 2)
        Bytecode(Op.LOAD_VAR, "sum"),
        Bytecode(Op.LOAD_VAR, "i"),
        Bytecode(Op.LOAD_CONST, 2),
        Bytecode(Op.MUL),
        Bytecode(Op.ADD),
        Bytecode(Op.STORE_VAR, "sum"),
        # 14: i = i + 1
        Bytecode(Op.LOAD_VAR, "i"),
        Bytecode(Op.LOAD_CONST, 1),
        Bytecode(Op.ADD),
        Bytecode(Op.STORE_VAR, "i"),
        # 18: jump back to loop header
        Bytecode(Op.JUMP, 4),
        # 19: print sum
        Bytecode(Op.LOAD_VAR, "sum"),
        Bytecode(Op.PRINT),
        Bytecode(Op.HALT),
    ]

    jit = TracingJITInterpreter(program)
    result = jit.run()
    print(f"Output: {result}")
    print(f"\nCompiled traces: {len(jit.compiled_traces)}")
    for pc, trace in jit.compiled_traces.items():
        print(f"\nTrace at PC={pc} ({len(trace.entries)} ops):")
        for entry in trace.entries:
            print(f"  {entry}")
        print(f"  Executions: {trace.executions}")
        print(f"  Guard failures: {trace.guard_failures}")


if __name__ == "__main__":
    demo_tracing_jit()
```

## Summary / Key Takeaways

- **JIT compilation** optimizes code at runtime using observed program behavior, achieving performance beyond static compilation for dynamic languages.
- **Method JIT** compiles entire functions and produces well-optimized code; **tracing JIT** records hot execution paths and naturally inlines across call boundaries — each involves a **trade-off** between code quality and compilation speed.
- **Hot path detection** uses invocation counters and back-edge counters to identify code worth optimizing, avoiding wasted compilation effort.
- **Inline caching** accelerates dynamic dispatch by remembering previously observed types at call sites — a critical **best practice** in dynamic language runtimes.
- **Deoptimization and OSR** allow the runtime to fall back to the interpreter when speculative optimizations fail, maintaining correctness while enabling aggressive optimization.
- A **common mistake** is over-specializing traces: excessive type guards lead to high failure rates and frequent recompilation, negating performance gains.
- **Best practice**: start with a simple interpreter, add profiling counters, then JIT-compile only the hottest loops and functions — the Pareto principle dominates JIT design.
"""
    ),
    (
        "compilers/gc-integration-stack-maps",
        "Explain how compilers integrate with garbage collectors including GC root identification, stack map generation, safe point insertion, write barriers and read barriers for concurrent GC, and implement a stack map generator and safe point insertion pass for a compiler backend in Python with detailed type hints and data structures.",
        r"""# Garbage Collector Integration in Compiler Backends

## The GC-Compiler Interface

Integrating a **garbage collector (GC)** with a compiler backend is one of the most intricate aspects of language runtime engineering. The compiler must cooperate with the GC to answer a fundamental question: **where are all the pointers to heap objects at every point where GC might occur?** Getting this wrong leads to dangling pointers, memory corruption, and heisenbugs that are extraordinarily difficult to diagnose.

The compiler's responsibilities include: identifying **GC roots** (registers and stack slots containing heap pointers), generating **stack maps** that describe the layout of each stack frame, inserting **safe points** where GC can safely pause execution, and emitting **write barriers** and **read barriers** for concurrent or generational collectors.

## GC Roots and Root Enumeration

A **GC root** is any reference to a heap object that the collector must know about to ensure reachability. Roots come from three sources:

1. **Stack roots**: Local variables and temporaries on the call stack that hold object references
2. **Register roots**: CPU registers currently holding object references
3. **Global roots**: Global variables, static fields, and JNI handles

The challenge is that the compiler has transformed the source program significantly — variables may be in registers, spilled to stack slots, or optimized away entirely. Therefore, the compiler must maintain metadata describing exactly which registers and stack slots contain GC-relevant pointers at each safe point.

A **common mistake** is assuming all values on the stack are potential pointers (conservative GC). While this works for languages like C, it prevents **moving collectors** (which must update all pointers when objects relocate) because a value that looks like a pointer might actually be an integer. Precise GC requires the compiler to generate exact metadata.

## Stack Maps

A **stack map** (also called a GC map or reference map) is a per-safe-point data structure that tells the GC which stack slots and registers contain live object references. The stack map is indexed by the program counter (return address) so the GC can look up the correct map when scanning each frame on the call stack.

### Stack Map Design Considerations

The **trade-off** in stack map design is between space efficiency and lookup speed. Dense bitmaps (one bit per stack slot) are fast to scan but waste space when frames are large and sparse. Compressed representations save space but require decoding. In practice, most production runtimes (HotSpot, .NET CLR, Go) use compact encodings because stack maps can consume significant memory in large applications.

```python
from __future__ import annotations
import dataclasses
from typing import Optional, Union
from enum import Enum, auto
from collections import defaultdict


# === Stack Map Data Structures ===

class SlotType(Enum):
    # Classification of stack slot contents
    REFERENCE = auto()     # GC-managed object pointer
    DERIVED_REF = auto()   # Interior pointer (base + offset)
    VALUE = auto()         # Non-pointer value (int, float)
    CALLEE_SAVED = auto()  # Register spill (needs special handling)


@dataclasses.dataclass
class StackSlot:
    # Describes a single slot in the stack frame
    offset: int            # Offset from frame pointer (negative = locals)
    slot_type: SlotType
    # For derived refs, which slot holds the base pointer
    base_slot: Optional[int] = None
    # Size in bytes
    size: int = 8

    def is_gc_relevant(self) -> bool:
        return self.slot_type in (SlotType.REFERENCE, SlotType.DERIVED_REF)


@dataclasses.dataclass
class RegisterInfo:
    # Describes a register's contents at a safe point
    register: str
    slot_type: SlotType
    # If spilled, which stack slot holds the value
    spill_slot: Optional[int] = None


@dataclasses.dataclass
class StackMapEntry:
    # Stack map for a single safe point
    # The PC/instruction offset where this map is valid
    pc_offset: int
    # Function this safe point belongs to
    function_name: str
    # Frame size in bytes
    frame_size: int
    # Stack slots containing GC references
    gc_slots: list[StackSlot] = dataclasses.field(default_factory=list)
    # Registers containing GC references
    gc_registers: list[RegisterInfo] = dataclasses.field(default_factory=list)
    # Live variables at this point (for debugging/deopt)
    live_vars: dict[str, Union[str, int]] = dataclasses.field(
        default_factory=dict
    )

    def reference_bitmap(self, max_slots: int = 32) -> int:
        # Generate a compact bitmap of which slots are references
        bitmap = 0
        for slot in self.gc_slots:
            if slot.is_gc_relevant():
                slot_index = abs(slot.offset) // 8
                if slot_index < max_slots:
                    bitmap |= (1 << slot_index)
        return bitmap

    def __repr__(self) -> str:
        refs = [s.offset for s in self.gc_slots if s.is_gc_relevant()]
        regs = [r.register for r in self.gc_registers]
        return (
            f"StackMap(pc=0x{self.pc_offset:04x}, "
            f"frame={self.frame_size}, "
            f"ref_slots={refs}, ref_regs={regs})"
        )


@dataclasses.dataclass
class StackMapTable:
    # Collection of stack maps for an entire compilation unit
    entries: list[StackMapEntry] = dataclasses.field(default_factory=list)
    # Index for fast lookup by PC
    _pc_index: dict[int, StackMapEntry] = dataclasses.field(
        default_factory=dict
    )

    def add(self, entry: StackMapEntry) -> None:
        self.entries.append(entry)
        self._pc_index[entry.pc_offset] = entry

    def lookup(self, pc: int) -> Optional[StackMapEntry]:
        return self._pc_index.get(pc)

    def total_size_bytes(self) -> int:
        # Estimate serialized size
        size = 0
        for entry in self.entries:
            # PC offset (4) + frame size (4) + slot count (2)
            size += 10
            # Each slot: offset (4) + type (1) + optional base (4)
            size += len(entry.gc_slots) * 9
            # Each register: reg id (1) + type (1)
            size += len(entry.gc_registers) * 2
        return size
```

## Safe Point Insertion

A **safe point** (also called a GC point or yield point) is a location in the compiled code where the GC is allowed to pause the thread and perform collection. At safe points, the runtime state is fully described by the stack map, so the GC can accurately enumerate roots.

### Where to Insert Safe Points

**Best practice** dictates safe points at these locations:

1. **Method entry/exit**: Ensures long-running methods can be interrupted
2. **Back edges of loops**: Prevents long-running loops from blocking GC
3. **Allocation sites**: The most natural place, since allocation may trigger GC
4. **Call sites**: The return address after a call is a natural safe point because callee-saved registers are already spilled

A **pitfall** is inserting too few safe points — a tight loop without safe points can block GC for arbitrarily long, causing pause time spikes. Conversely, too many safe points increase stack map size and may inhibit optimizations.

```python
# === Compiler IR for Safe Point Insertion ===

class IROpcode(Enum):
    LOAD = auto()
    STORE = auto()
    ADD = auto()
    SUB = auto()
    MUL = auto()
    ALLOC = auto()       # Heap allocation
    CALL = auto()        # Function call
    BRANCH = auto()      # Conditional branch
    JUMP = auto()        # Unconditional jump
    RET = auto()
    CMP = auto()
    SAFE_POINT = auto()  # Explicit GC safe point
    WRITE_BARRIER = auto()


@dataclasses.dataclass
class IRInst:
    opcode: IROpcode
    dest: Optional[str] = None
    operands: list[str] = dataclasses.field(default_factory=list)
    # Metadata
    pc_offset: int = 0
    is_reference_type: bool = False  # Does dest hold a GC reference?
    # For JUMP/BRANCH: target block
    target: Optional[str] = None

    def __repr__(self) -> str:
        ref_tag = " [ref]" if self.is_reference_type else ""
        ops = ", ".join(self.operands)
        if self.dest:
            return f"  @{self.pc_offset:04d}: {self.dest} = {self.opcode.name} {ops}{ref_tag}"
        return f"  @{self.pc_offset:04d}: {self.opcode.name} {ops}{ref_tag}"


@dataclasses.dataclass
class IRBlock:
    name: str
    instructions: list[IRInst] = dataclasses.field(default_factory=list)
    successors: list[str] = dataclasses.field(default_factory=list)
    predecessors: list[str] = dataclasses.field(default_factory=list)
    is_loop_header: bool = False


class SafePointInserter:
    # Inserts GC safe points into the IR

    def __init__(self, blocks: dict[str, IRBlock]) -> None:
        self.blocks = blocks
        self.next_pc: int = 0

    def insert_safe_points(self) -> int:
        # Returns the number of safe points inserted
        count = 0

        for block in self.blocks.values():
            new_instructions: list[IRInst] = []

            # Insert safe point at loop headers
            if block.is_loop_header:
                sp = IRInst(
                    opcode=IROpcode.SAFE_POINT,
                    pc_offset=self._next_pc(),
                )
                new_instructions.append(sp)
                count += 1

            for inst in block.instructions:
                new_instructions.append(inst)

                # Insert safe point after allocation sites
                if inst.opcode == IROpcode.ALLOC:
                    sp = IRInst(
                        opcode=IROpcode.SAFE_POINT,
                        pc_offset=self._next_pc(),
                    )
                    new_instructions.append(sp)
                    count += 1

                # Insert safe point after call sites
                if inst.opcode == IROpcode.CALL:
                    sp = IRInst(
                        opcode=IROpcode.SAFE_POINT,
                        pc_offset=self._next_pc(),
                    )
                    new_instructions.append(sp)
                    count += 1

            block.instructions = new_instructions

        return count

    def _next_pc(self) -> int:
        self.next_pc += 4
        return self.next_pc


class StackMapGenerator:
    # Generates stack maps at each safe point

    def __init__(self, blocks: dict[str, IRBlock]) -> None:
        self.blocks = blocks
        self.stack_map_table = StackMapTable()
        # Track which variables hold references
        self.ref_vars: set[str] = set()
        # Track variable to stack slot mapping (simulated register allocation)
        self.var_slots: dict[str, int] = {}
        self.next_slot_offset: int = -8  # Grows downward from FP

    def generate(self) -> StackMapTable:
        # First pass: identify all reference-typed variables
        for block in self.blocks.values():
            for inst in block.instructions:
                if inst.dest and inst.is_reference_type:
                    self.ref_vars.add(inst.dest)
                    if inst.dest not in self.var_slots:
                        self.var_slots[inst.dest] = self.next_slot_offset
                        self.next_slot_offset -= 8

        # Second pass: generate stack maps at safe points
        for block in self.blocks.values():
            live_refs = self._compute_live_refs_at_block_entry(block)

            for inst in block.instructions:
                # Update live refs
                if inst.dest and inst.dest in self.ref_vars:
                    live_refs.add(inst.dest)

                if inst.opcode == IROpcode.SAFE_POINT:
                    entry = self._create_stack_map(
                        inst.pc_offset, live_refs, block.name
                    )
                    self.stack_map_table.add(entry)

        return self.stack_map_table

    def _compute_live_refs_at_block_entry(
        self, block: IRBlock
    ) -> set[str]:
        # Simplified liveness: all ref vars defined before this block
        # In a real compiler, this would use full liveness analysis
        live: set[str] = set()
        for b in self.blocks.values():
            if b.name == block.name:
                break
            for inst in b.instructions:
                if inst.dest and inst.dest in self.ref_vars:
                    live.add(inst.dest)
        return live

    def _create_stack_map(
        self, pc: int, live_refs: set[str], func_name: str
    ) -> StackMapEntry:
        gc_slots: list[StackSlot] = []
        for var in live_refs:
            if var in self.var_slots:
                gc_slots.append(
                    StackSlot(
                        offset=self.var_slots[var],
                        slot_type=SlotType.REFERENCE,
                    )
                )
        frame_size = abs(self.next_slot_offset)
        return StackMapEntry(
            pc_offset=pc,
            function_name=func_name,
            frame_size=frame_size,
            gc_slots=gc_slots,
            live_vars={v: self.var_slots.get(v, 0) for v in live_refs},
        )
```

## Write Barriers and Read Barriers

### Write Barriers

A **write barrier** is code emitted by the compiler around every pointer store to maintain GC invariants. Generational collectors use write barriers to track old-to-young pointers (the **remembered set**). When an old-generation object stores a reference to a young-generation object, the barrier records this so the minor GC can find all roots into the young generation without scanning the entire old generation.

### Read Barriers

**Read barriers** are used by concurrent collectors (like ZGC and Shenandoah) that relocate objects concurrently with the application. A read barrier intercepts every pointer load and checks if the object has been relocated, updating the pointer if necessary. This enables **sub-millisecond GC pauses** but imposes a throughput cost on every pointer access.

The **trade-off** between write barriers and read barriers reflects a fundamental GC design choice: write barriers are cheaper per operation (stores are less frequent than loads) but limit collector design, while read barriers are more expensive but enable fully concurrent collection.

```python
class WriteBarrierInserter:
    # Inserts write barriers for generational/concurrent GC

    def __init__(
        self, blocks: dict[str, IRBlock], ref_vars: set[str]
    ) -> None:
        self.blocks = blocks
        self.ref_vars = ref_vars
        self.next_pc: int = 1000

    def insert_barriers(self) -> int:
        count = 0
        for block in self.blocks.values():
            new_insts: list[IRInst] = []
            for inst in block.instructions:
                new_insts.append(inst)
                # Insert write barrier after every reference store
                if (
                    inst.opcode == IROpcode.STORE
                    and inst.is_reference_type
                ):
                    barrier = IRInst(
                        opcode=IROpcode.WRITE_BARRIER,
                        operands=list(inst.operands),
                        pc_offset=self._next_pc(),
                    )
                    new_insts.append(barrier)
                    count += 1
            block.instructions = new_insts
        return count

    def _next_pc(self) -> int:
        self.next_pc += 4
        return self.next_pc


def demo_gc_integration() -> None:
    # Build a sample IR with allocations and reference stores
    blocks: dict[str, IRBlock] = {}

    entry = IRBlock(name="entry", successors=["loop"], predecessors=[])
    entry.instructions = [
        IRInst(IROpcode.ALLOC, "obj1", ["Node"], pc_offset=0, is_reference_type=True),
        IRInst(IROpcode.ALLOC, "obj2", ["Node"], pc_offset=4, is_reference_type=True),
        IRInst(IROpcode.STORE, operands=["obj1", "next", "obj2"],
               pc_offset=8, is_reference_type=True),
    ]
    blocks["entry"] = entry

    loop = IRBlock(
        name="loop", successors=["loop", "exit"],
        predecessors=["entry", "loop"], is_loop_header=True
    )
    loop.instructions = [
        IRInst(IROpcode.LOAD, "tmp", ["obj1", "value"], pc_offset=12),
        IRInst(IROpcode.ADD, "tmp2", ["tmp", "1"], pc_offset=16),
        IRInst(IROpcode.ALLOC, "new_node", ["Node"], pc_offset=20, is_reference_type=True),
        IRInst(IROpcode.STORE, operands=["obj1", "next", "new_node"],
               pc_offset=24, is_reference_type=True),
        IRInst(IROpcode.CMP, "cond", ["tmp2", "100"], pc_offset=28),
        IRInst(IROpcode.BRANCH, operands=["cond"], target="exit", pc_offset=32),
    ]
    blocks["loop"] = loop

    exit_block = IRBlock(name="exit", predecessors=["loop"])
    exit_block.instructions = [
        IRInst(IROpcode.RET, operands=["obj1"], pc_offset=36),
    ]
    blocks["exit"] = exit_block

    # Phase 1: Insert safe points
    sp_inserter = SafePointInserter(blocks)
    sp_count = sp_inserter.insert_safe_points()
    print(f"Inserted {sp_count} safe points")

    # Phase 2: Insert write barriers
    ref_vars = {"obj1", "obj2", "new_node"}
    wb_inserter = WriteBarrierInserter(blocks, ref_vars)
    wb_count = wb_inserter.insert_barriers()
    print(f"Inserted {wb_count} write barriers")

    # Phase 3: Generate stack maps
    sm_gen = StackMapGenerator(blocks)
    table = sm_gen.generate()
    print(f"\nGenerated {len(table.entries)} stack maps:")
    for entry in table.entries:
        print(f"  {entry}")
    print(f"\nEstimated stack map size: {table.total_size_bytes()} bytes")

    # Display final IR
    print("\n=== Final IR with GC Integration ===")
    for bname, block in blocks.items():
        header = f"{bname}" + (" [loop header]" if block.is_loop_header else "")
        print(f"\n{header}:")
        for inst in block.instructions:
            print(f"  {inst}")


if __name__ == "__main__":
    demo_gc_integration()
```

## Summary / Key Takeaways

- **GC root identification** requires the compiler to precisely track which registers and stack slots contain heap pointers at every safe point.
- **Stack maps** are per-safe-point metadata structures that encode root locations; the **trade-off** is between compact encoding (saves memory) and fast decoding (reduces GC pause time).
- **Safe points** must be inserted at loop back-edges, allocation sites, and call sites — too few cause long GC pauses, too many waste space. **Best practice** is inserting at every back-edge and allocation.
- **Write barriers** maintain remembered sets for generational GC; **read barriers** enable concurrent object relocation. However, read barriers impose a throughput cost on every pointer load.
- A **pitfall** in GC integration is failing to track derived pointers (interior pointers into objects), which can cause the base object to be collected while the derived pointer is still in use.
- **Best practice**: design the IR to distinguish reference types from value types from the start, making stack map generation a straightforward pass rather than a retrofit.
- Precise GC is essential for **moving collectors** because every pointer must be updatable — therefore the compiler must guarantee no false positives in root enumeration.
"""
    ),
    (
        "compilers/llvm-ir-optimization-passes",
        "Explain LLVM IR structure and optimization passes including LLVM IR syntax with basic blocks and SSA form, function passes versus module passes, constant folding, dead code elimination, loop-invariant code motion, and auto-vectorization, then implement LLVM IR generation for a simple language with constant folding and loop-invariant code motion passes in Python.",
        r"""# LLVM IR and Optimization Passes

## Understanding LLVM IR

**LLVM IR** (Intermediate Representation) is the backbone of the LLVM compiler infrastructure. It serves as a language-independent, target-independent representation that sits between the frontend (Clang, Rust, Swift) and the backend (x86, ARM, RISC-V code generation). Understanding LLVM IR is essential for anyone working on compiler optimization, language implementation, or performance engineering.

LLVM IR has three equivalent forms: an in-memory representation (C++ objects), a human-readable textual format (`.ll` files), and a dense bitcode encoding (`.bc` files). The textual form is what we work with most for understanding and debugging.

### Key Properties of LLVM IR

LLVM IR is in **SSA form** — every virtual register is assigned exactly once. It uses a **typed system** where every value has an explicit type (i32, float, ptr). The IR is organized into **modules** containing **functions**, which contain **basic blocks**, which contain **instructions**.

Here is a simple LLVM IR example:

```
define i32 @add(i32 %a, i32 %b) {
entry:
    %result = add i32 %a, %b
    ret i32 %result
}
```

A **common mistake** when learning LLVM IR is confusing `%` (local virtual registers) with `@` (global symbols). Local registers are function-scoped and SSA, while global symbols persist across the module.

## LLVM IR Constructs

### Basic Blocks and Control Flow

A **basic block** is a straight-line sequence of instructions with a single entry point and a single exit point (the **terminator** instruction). Terminators include `ret`, `br` (branch), `switch`, and `invoke`. Every basic block must end with exactly one terminator — this is an invariant enforced by the LLVM verifier.

### The Type System

LLVM's type system includes integer types (`i1`, `i8`, `i32`, `i64`), floating-point types (`float`, `double`), pointer types (`ptr`), aggregate types (`{ i32, float }` for structs, `[10 x i32]` for arrays), and vector types (`<4 x float>` for SIMD). The type system enables type-based optimizations and ensures code generation correctness.

```python
from __future__ import annotations
import dataclasses
from typing import Any, Optional, Union
from enum import Enum, auto
from collections import defaultdict


# === LLVM IR AST ===

class LLVMType(Enum):
    I1 = "i1"
    I8 = "i8"
    I32 = "i32"
    I64 = "i64"
    FLOAT = "float"
    DOUBLE = "double"
    VOID = "void"
    PTR = "ptr"

    def __str__(self) -> str:
        return self.value


@dataclasses.dataclass
class LLVMValue:
    # Represents a typed value in LLVM IR
    name: str
    ir_type: LLVMType
    is_constant: bool = False
    constant_value: Optional[Union[int, float]] = None

    def __str__(self) -> str:
        if self.is_constant:
            return str(self.constant_value)
        return f"%{self.name}"

    def typed_str(self) -> str:
        return f"{self.ir_type} {self}"


class LLVMOpcode(Enum):
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    SDIV = "sdiv"
    ICMP = "icmp"
    FADD = "fadd"
    FMUL = "fmul"
    LOAD = "load"
    STORE = "store"
    ALLOCA = "alloca"
    BR = "br"
    BR_COND = "br_cond"
    RET = "ret"
    CALL = "call"
    PHI = "phi"
    SEXT = "sext"
    ZEXT = "zext"


@dataclasses.dataclass
class LLVMInstruction:
    opcode: LLVMOpcode
    result: Optional[LLVMValue] = None
    operands: list[LLVMValue] = dataclasses.field(default_factory=list)
    # For icmp: the predicate (eq, ne, slt, sgt, etc.)
    predicate: Optional[str] = None
    # For br: target labels
    true_label: Optional[str] = None
    false_label: Optional[str] = None
    # For phi: list of (value, predecessor_label) pairs
    phi_entries: list[tuple[LLVMValue, str]] = dataclasses.field(
        default_factory=list
    )
    # Metadata for optimization
    is_loop_invariant: bool = False

    def to_ir(self) -> str:
        if self.opcode == LLVMOpcode.RET:
            if self.operands:
                return f"ret {self.operands[0].typed_str()}"
            return "ret void"

        if self.opcode == LLVMOpcode.BR:
            return f"br label %{self.true_label}"

        if self.opcode == LLVMOpcode.BR_COND:
            cond = self.operands[0]
            return (
                f"br {cond.typed_str()}, "
                f"label %{self.true_label}, "
                f"label %{self.false_label}"
            )

        if self.opcode == LLVMOpcode.ALLOCA:
            assert self.result is not None
            return f"%{self.result.name} = alloca {self.result.ir_type}"

        if self.opcode == LLVMOpcode.STORE:
            val, ptr = self.operands[0], self.operands[1]
            return f"store {val.typed_str()}, ptr %{ptr.name}"

        if self.opcode == LLVMOpcode.LOAD:
            assert self.result is not None
            ptr = self.operands[0]
            return f"%{self.result.name} = load {self.result.ir_type}, ptr %{ptr.name}"

        if self.opcode == LLVMOpcode.ICMP:
            assert self.result is not None
            a, b = self.operands[0], self.operands[1]
            return (
                f"%{self.result.name} = icmp {self.predicate} "
                f"{a.typed_str()}, {b}"
            )

        if self.opcode == LLVMOpcode.PHI:
            assert self.result is not None
            entries = ", ".join(
                f"[ {v}, %{label} ]" for v, label in self.phi_entries
            )
            return f"%{self.result.name} = phi {self.result.ir_type} {entries}"

        if self.opcode in (
            LLVMOpcode.ADD, LLVMOpcode.SUB,
            LLVMOpcode.MUL, LLVMOpcode.SDIV,
            LLVMOpcode.FADD, LLVMOpcode.FMUL,
        ):
            assert self.result is not None
            a, b = self.operands[0], self.operands[1]
            return (
                f"%{self.result.name} = {self.opcode.value} "
                f"{a.ir_type} {a}, {b}"
            )

        return f"; unknown: {self.opcode}"


@dataclasses.dataclass
class LLVMBasicBlock:
    label: str
    instructions: list[LLVMInstruction] = dataclasses.field(
        default_factory=list
    )
    predecessors: list[str] = dataclasses.field(default_factory=list)
    successors: list[str] = dataclasses.field(default_factory=list)
    is_loop_header: bool = False

    def to_ir(self) -> str:
        lines = [f"{self.label}:"]
        for inst in self.instructions:
            lines.append(f"    {inst.to_ir()}")
        return "\n".join(lines)


@dataclasses.dataclass
class LLVMFunction:
    name: str
    return_type: LLVMType
    params: list[LLVMValue] = dataclasses.field(default_factory=list)
    blocks: dict[str, LLVMBasicBlock] = dataclasses.field(
        default_factory=dict
    )
    block_order: list[str] = dataclasses.field(default_factory=list)

    def add_block(self, block: LLVMBasicBlock) -> None:
        self.blocks[block.label] = block
        self.block_order.append(block.label)

    def to_ir(self) -> str:
        params = ", ".join(p.typed_str() for p in self.params)
        lines = [f"define {self.return_type} @{self.name}({params}) {{"]
        for label in self.block_order:
            lines.append(self.blocks[label].to_ir())
        lines.append("}")
        return "\n".join(lines)
```

## Optimization Passes

LLVM organizes optimizations into **passes** that transform the IR. There are several categories:

- **Function passes**: Operate on one function at a time (most optimizations)
- **Module passes**: Operate on the entire module (interprocedural optimizations, dead global elimination)
- **Loop passes**: Operate on natural loops (LICM, loop unrolling, vectorization)
- **SCC passes**: Operate on strongly connected components of the call graph (inlining)

### Constant Folding

**Constant folding** evaluates expressions with constant operands at compile time. This is one of the simplest yet most impactful optimizations because it cascades — folding one expression may reveal new constants that enable further folding.

### Loop-Invariant Code Motion (LICM)

**LICM** moves computations that produce the same result on every loop iteration out of the loop body and into the **preheader** block. An instruction is loop-invariant if all its operands are defined outside the loop or are themselves loop-invariant.

A **pitfall** with LICM is moving instructions that might trap (division by zero, null dereference) — the instruction might not execute on every path through the loop, so hoisting it could introduce a fault that the original program would not have. Therefore, LICM must verify that the instruction's block dominates all loop exits (guaranteeing it would have executed).

```python
# === Optimization Passes ===

class ConstantFoldingPass:
    # Evaluates constant expressions at compile time
    # This is a function pass that operates on one function

    def __init__(self, function: LLVMFunction) -> None:
        self.function = function
        self.constants: dict[str, Union[int, float]] = {}
        self.folded_count: int = 0

    def run(self) -> int:
        # Iterate to fixed point because folding may reveal new constants
        total_folded = 0
        changed = True
        while changed:
            changed = False
            for label in self.function.block_order:
                block = self.function.blocks[label]
                new_insts: list[LLVMInstruction] = []
                for inst in block.instructions:
                    folded = self._try_fold(inst)
                    if folded is not None:
                        new_insts.append(folded)
                        changed = True
                        total_folded += 1
                    else:
                        new_insts.append(inst)
                block.instructions = new_insts
        return total_folded

    def _try_fold(self, inst: LLVMInstruction) -> Optional[LLVMInstruction]:
        # Only fold arithmetic instructions
        foldable_ops = {
            LLVMOpcode.ADD, LLVMOpcode.SUB,
            LLVMOpcode.MUL, LLVMOpcode.SDIV,
        }
        if inst.opcode not in foldable_ops:
            return None
        if not inst.result or len(inst.operands) != 2:
            return None

        a_val = self._get_constant(inst.operands[0])
        b_val = self._get_constant(inst.operands[1])

        if a_val is None or b_val is None:
            return None

        # Evaluate the operation
        result_val: Optional[Union[int, float]] = None
        if inst.opcode == LLVMOpcode.ADD:
            result_val = a_val + b_val
        elif inst.opcode == LLVMOpcode.SUB:
            result_val = a_val - b_val
        elif inst.opcode == LLVMOpcode.MUL:
            result_val = a_val * b_val
        elif inst.opcode == LLVMOpcode.SDIV:
            if b_val != 0:
                result_val = int(a_val) // int(b_val)

        if result_val is None:
            return None

        # Record the constant and create a trivial instruction
        self.constants[inst.result.name] = result_val
        # Replace with a constant-producing instruction
        const_val = LLVMValue(
            name=f"const_{result_val}",
            ir_type=inst.result.ir_type,
            is_constant=True,
            constant_value=int(result_val),
        )
        # Replace uses of this result with the constant
        self._replace_uses(inst.result.name, const_val)
        # Return an add-zero to preserve the assignment
        return LLVMInstruction(
            opcode=LLVMOpcode.ADD,
            result=inst.result,
            operands=[const_val, LLVMValue(
                "0", inst.result.ir_type, is_constant=True, constant_value=0
            )],
        )

    def _get_constant(self, val: LLVMValue) -> Optional[Union[int, float]]:
        if val.is_constant:
            return val.constant_value
        return self.constants.get(val.name)

    def _replace_uses(self, old_name: str, new_val: LLVMValue) -> None:
        for label in self.function.block_order:
            block = self.function.blocks[label]
            for inst in block.instructions:
                for i, op in enumerate(inst.operands):
                    if not op.is_constant and op.name == old_name:
                        inst.operands[i] = new_val


class LICMPass:
    # Loop-Invariant Code Motion
    # Moves invariant computations out of loop bodies

    def __init__(self, function: LLVMFunction) -> None:
        self.function = function
        self.loop_blocks: set[str] = set()
        self.loop_header: Optional[str] = None
        self.preheader: Optional[str] = None
        self.moved_count: int = 0

    def run(self) -> int:
        # Detect natural loops (simplified: look for loop_header markers)
        self._detect_loops()
        if not self.loop_header:
            return 0

        # Ensure preheader exists
        self._ensure_preheader()

        # Find and move loop-invariant instructions
        self._move_invariant_code()

        return self.moved_count

    def _detect_loops(self) -> None:
        for label, block in self.function.blocks.items():
            if block.is_loop_header:
                self.loop_header = label
                # Simple loop detection: all blocks that have the
                # header as a successor or are between header and back-edge
                self.loop_blocks = self._find_loop_body(label)
                break

    def _find_loop_body(self, header: str) -> set[str]:
        # Find all blocks in the natural loop with the given header
        body: set[str] = {header}
        # Find back edge: a successor of some block that is the header
        worklist: list[str] = []
        for label, block in self.function.blocks.items():
            if header in block.successors and label != header:
                if label not in body:
                    worklist.append(label)
                    body.add(label)

        # Walk backwards from back-edge source to header
        while worklist:
            node = worklist.pop()
            block = self.function.blocks.get(node)
            if block:
                for pred in block.predecessors:
                    if pred not in body:
                        body.add(pred)
                        worklist.append(pred)

        return body

    def _ensure_preheader(self) -> None:
        # Create a preheader block if one does not exist
        assert self.loop_header is not None
        preheader_label = f"{self.loop_header}.preheader"

        if preheader_label in self.function.blocks:
            self.preheader = preheader_label
            return

        # Create preheader that jumps to the loop header
        preheader = LLVMBasicBlock(
            label=preheader_label,
            instructions=[
                LLVMInstruction(
                    opcode=LLVMOpcode.BR,
                    true_label=self.loop_header,
                )
            ],
            successors=[self.loop_header],
        )

        # Insert preheader before the loop header in block order
        header_idx = self.function.block_order.index(self.loop_header)
        self.function.block_order.insert(header_idx, preheader_label)
        self.function.blocks[preheader_label] = preheader
        self.preheader = preheader_label

        # Redirect non-loop predecessors to preheader
        header_block = self.function.blocks[self.loop_header]
        for pred_label in list(header_block.predecessors):
            if pred_label not in self.loop_blocks:
                pred_block = self.function.blocks.get(pred_label)
                if pred_block:
                    # Update successor to point to preheader
                    pred_block.successors = [
                        preheader_label if s == self.loop_header else s
                        for s in pred_block.successors
                    ]
                    preheader.predecessors.append(pred_label)

    def _move_invariant_code(self) -> None:
        assert self.preheader is not None
        preheader_block = self.function.blocks[self.preheader]

        # Find definitions inside the loop
        loop_defs: set[str] = set()
        for label in self.loop_blocks:
            block = self.function.blocks[label]
            for inst in block.instructions:
                if inst.result:
                    loop_defs.add(inst.result.name)

        # An instruction is loop-invariant if all operands are
        # defined outside the loop or are constants
        changed = True
        invariant_names: set[str] = set()

        while changed:
            changed = False
            for label in self.loop_blocks:
                block = self.function.blocks[label]
                for inst in block.instructions:
                    if not inst.result:
                        continue
                    if inst.result.name in invariant_names:
                        continue
                    if inst.opcode in (
                        LLVMOpcode.PHI, LLVMOpcode.LOAD,
                        LLVMOpcode.STORE, LLVMOpcode.CALL,
                        LLVMOpcode.BR, LLVMOpcode.BR_COND,
                        LLVMOpcode.RET,
                    ):
                        # These have side effects or depend on loop state
                        continue

                    if self._is_invariant(inst, loop_defs, invariant_names):
                        invariant_names.add(inst.result.name)
                        inst.is_loop_invariant = True
                        changed = True

        # Move invariant instructions to preheader
        for label in list(self.loop_blocks):
            block = self.function.blocks[label]
            remaining: list[LLVMInstruction] = []
            for inst in block.instructions:
                if inst.is_loop_invariant:
                    # Insert before the terminator in preheader
                    insert_pos = max(0, len(preheader_block.instructions) - 1)
                    preheader_block.instructions.insert(insert_pos, inst)
                    self.moved_count += 1
                else:
                    remaining.append(inst)
            block.instructions = remaining

    def _is_invariant(
        self,
        inst: LLVMInstruction,
        loop_defs: set[str],
        known_invariant: set[str],
    ) -> bool:
        for op in inst.operands:
            if op.is_constant:
                continue
            if op.name in known_invariant:
                continue
            if op.name in loop_defs:
                # Defined in loop and not yet proven invariant
                return False
        return True


def demo_llvm_ir() -> None:
    # Generate LLVM IR for: sum = 0; for i in 0..n: sum += i * 5 + 3
    func = LLVMFunction(
        name="compute_sum",
        return_type=LLVMType.I32,
        params=[LLVMValue("n", LLVMType.I32)],
    )

    # Entry block
    entry = LLVMBasicBlock(label="entry", successors=["loop.preheader"])
    entry.instructions = [
        LLVMInstruction(
            opcode=LLVMOpcode.BR, true_label="loop.preheader"
        ),
    ]
    func.add_block(entry)

    # Loop preheader (will receive hoisted code)
    preheader = LLVMBasicBlock(
        label="loop.preheader",
        predecessors=["entry"],
        successors=["loop"],
    )
    preheader.instructions = [
        LLVMInstruction(opcode=LLVMOpcode.BR, true_label="loop"),
    ]
    func.add_block(preheader)

    # Loop header
    loop = LLVMBasicBlock(
        label="loop",
        predecessors=["loop.preheader", "loop"],
        successors=["loop", "exit"],
        is_loop_header=True,
    )

    i_phi = LLVMValue("i", LLVMType.I32)
    sum_phi = LLVMValue("sum", LLVMType.I32)
    zero = LLVMValue("0", LLVMType.I32, is_constant=True, constant_value=0)
    five = LLVMValue("5", LLVMType.I32, is_constant=True, constant_value=5)
    three = LLVMValue("3", LLVMType.I32, is_constant=True, constant_value=3)
    one = LLVMValue("1", LLVMType.I32, is_constant=True, constant_value=1)
    two = LLVMValue("2", LLVMType.I32, is_constant=True, constant_value=2)
    six = LLVMValue("6", LLVMType.I32, is_constant=True, constant_value=6)

    loop.instructions = [
        # PHI nodes for i and sum
        LLVMInstruction(
            opcode=LLVMOpcode.PHI, result=i_phi,
            phi_entries=[(zero, "loop.preheader"), (LLVMValue("i.next", LLVMType.I32), "loop")],
        ),
        LLVMInstruction(
            opcode=LLVMOpcode.PHI, result=sum_phi,
            phi_entries=[(zero, "loop.preheader"), (LLVMValue("sum.next", LLVMType.I32), "loop")],
        ),
        # Loop-invariant: const_mul = 2 * 3 (should be folded to 6)
        LLVMInstruction(
            opcode=LLVMOpcode.MUL,
            result=LLVMValue("const_mul", LLVMType.I32),
            operands=[two, three],
        ),
        # Loop-invariant after folding: offset = const_mul + 3
        LLVMInstruction(
            opcode=LLVMOpcode.ADD,
            result=LLVMValue("offset", LLVMType.I32),
            operands=[LLVMValue("const_mul", LLVMType.I32), three],
        ),
        # Loop-variant: tmp = i * 5
        LLVMInstruction(
            opcode=LLVMOpcode.MUL,
            result=LLVMValue("tmp", LLVMType.I32),
            operands=[i_phi, five],
        ),
        # Loop-variant: val = tmp + offset
        LLVMInstruction(
            opcode=LLVMOpcode.ADD,
            result=LLVMValue("val", LLVMType.I32),
            operands=[LLVMValue("tmp", LLVMType.I32), LLVMValue("offset", LLVMType.I32)],
        ),
        # sum.next = sum + val
        LLVMInstruction(
            opcode=LLVMOpcode.ADD,
            result=LLVMValue("sum.next", LLVMType.I32),
            operands=[sum_phi, LLVMValue("val", LLVMType.I32)],
        ),
        # i.next = i + 1
        LLVMInstruction(
            opcode=LLVMOpcode.ADD,
            result=LLVMValue("i.next", LLVMType.I32),
            operands=[i_phi, one],
        ),
        # cmp = i.next < n
        LLVMInstruction(
            opcode=LLVMOpcode.ICMP,
            result=LLVMValue("cmp", LLVMType.I1),
            operands=[LLVMValue("i.next", LLVMType.I32), LLVMValue("n", LLVMType.I32)],
            predicate="slt",
        ),
        # br cmp, loop, exit
        LLVMInstruction(
            opcode=LLVMOpcode.BR_COND,
            operands=[LLVMValue("cmp", LLVMType.I1)],
            true_label="loop",
            false_label="exit",
        ),
    ]
    func.add_block(loop)

    # Exit block
    exit_block = LLVMBasicBlock(
        label="exit", predecessors=["loop"], successors=[]
    )
    exit_block.instructions = [
        LLVMInstruction(
            opcode=LLVMOpcode.RET,
            operands=[LLVMValue("sum.next", LLVMType.I32)],
        ),
    ]
    func.add_block(exit_block)

    print("=== Original LLVM IR ===")
    print(func.to_ir())

    # Run constant folding
    cf = ConstantFoldingPass(func)
    folded = cf.run()
    print(f"\n=== After Constant Folding ({folded} expressions folded) ===")
    print(func.to_ir())

    # Run LICM
    licm = LICMPass(func)
    moved = licm.run()
    print(f"\n=== After LICM ({moved} instructions hoisted) ===")
    print(func.to_ir())


if __name__ == "__main__":
    demo_llvm_ir()
```

## Auto-Vectorization

LLVM's **loop vectorizer** transforms scalar loops into SIMD operations. It analyzes loop-carried dependencies, memory access patterns, and data types to determine if and how a loop can be vectorized. The vectorizer uses a **cost model** to decide the optimal vector width — because wider vectors reduce loop iterations but may cause more expensive spills and alignment issues.

A **best practice** when writing code for auto-vectorization is to use simple loop patterns with predictable memory access (stride-1), avoid complex control flow inside loops, and ensure data types match the target's SIMD capabilities.

### Pass Ordering and Phase Ordering Problem

The order in which optimization passes run matters significantly. For example, constant folding should run before LICM (as our demo shows), because folding may reveal loop-invariant expressions. Inlining should run before most other optimizations because it exposes more code to local analysis. However, the optimal ordering depends on the specific program — this is the **phase ordering problem**, which is NP-hard in general. Therefore, LLVM uses a carefully tuned default pipeline that works well empirically.

## Summary / Key Takeaways

- **LLVM IR** is a typed, SSA-based intermediate representation that serves as the universal language for LLVM's optimization and code generation infrastructure.
- **Basic blocks** are straight-line instruction sequences terminated by control flow instructions; functions are collections of basic blocks forming a control flow graph.
- **Constant folding** evaluates compile-time-known expressions, cascading to reveal further optimization opportunities — a simple but high-impact pass.
- **Loop-Invariant Code Motion** hoists computations whose results do not change across iterations into a loop preheader, reducing redundant work. A **pitfall** is hoisting potentially trapping instructions without dominance guarantees.
- **Pass ordering** significantly affects optimization quality; the **trade-off** is between compilation time (fewer passes) and code quality (more passes). **Best practice** is to run cleanup passes (DCE, constant folding) between major transformations.
- LLVM's **modular pass infrastructure** allows composing optimizations independently, but understanding pass interactions is essential for writing effective custom passes.
- The **common mistake** of ignoring LLVM's cost model leads to optimizations that improve theoretical complexity but harm real-world performance due to cache effects and register pressure.
"""
    ),
]
