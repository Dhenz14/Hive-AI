PAIRS = [
    ("projects/state-machine", r'''<think>
A state machine needs clear state definitions, transitions with guards,
and actions that execute on state entry/exit. I will build a declarative
API that makes the state machine configuration readable.
</think>
Build a state machine with declarative state definitions, transitions, guards, and actions.''', r'''from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum


@dataclass
class Transition:
    """A state transition definition."""
    event: str
    source: str
    target: str
    guard: Optional[Callable] = None
    action: Optional[Callable] = None
    description: str = ""


@dataclass
class StateConfig:
    """Configuration for a single state."""
    name: str
    on_enter: Optional[Callable] = None
    on_exit: Optional[Callable] = None
    is_final: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateMachine:
    """Finite state machine with guards and actions."""

    def __init__(self, name: str, initial_state: str):
        self._name = name
        self._initial = initial_state
        self._current = initial_state
        self._states: Dict[str, StateConfig] = {}
        self._transitions: List[Transition] = []
        self._context: Dict[str, Any] = {}
        self._history: List[dict] = []
        self._listeners: List[Callable] = []

    def add_state(self, name: str, on_enter: Optional[Callable] = None, on_exit: Optional[Callable] = None, is_final: bool = False) -> "StateMachine":
        """Add a state to the machine."""
        self._states[name] = StateConfig(name=name, on_enter=on_enter, on_exit=on_exit, is_final=is_final)
        return self

    def add_transition(self, event: str, source: str, target: str, guard: Optional[Callable] = None, action: Optional[Callable] = None) -> "StateMachine":
        """Add a transition between states."""
        self._transitions.append(Transition(event=event, source=source, target=target, guard=guard, action=action))
        return self

    def send(self, event: str, **data) -> bool:
        """Send an event to trigger a transition. Returns True if transition occurred."""
        if self.is_final:
            return False

        valid_transitions = [
            t for t in self._transitions
            if t.event == event and t.source == self._current
        ]

        for transition in valid_transitions:
            # Check guard
            if transition.guard:
                if not transition.guard(self._context, data):
                    continue

            # Execute transition
            old_state = self._current
            source_config = self._states.get(old_state)
            target_config = self._states.get(transition.target)

            # Exit current state
            if source_config and source_config.on_exit:
                source_config.on_exit(self._context)

            # Execute transition action
            if transition.action:
                transition.action(self._context, data)

            # Enter new state
            self._current = transition.target
            if target_config and target_config.on_enter:
                target_config.on_enter(self._context)

            # Record history
            record = {
                "event": event,
                "from": old_state,
                "to": transition.target,
                "data": data,
            }
            self._history.append(record)

            # Notify listeners
            for listener in self._listeners:
                listener(record)

            return True

        return False

    @property
    def current_state(self) -> str:
        return self._current

    @property
    def is_final(self) -> bool:
        config = self._states.get(self._current)
        return config.is_final if config else False

    @property
    def context(self) -> Dict[str, Any]:
        return self._context

    def set_context(self, **kwargs) -> None:
        self._context.update(kwargs)

    def can(self, event: str) -> bool:
        """Check if an event can trigger a transition from current state."""
        return any(
            t.event == event and t.source == self._current
            for t in self._transitions
        )

    def available_events(self) -> List[str]:
        """Get events available from the current state."""
        return list(set(
            t.event for t in self._transitions
            if t.source == self._current
        ))

    def on_transition(self, listener: Callable) -> None:
        """Register a transition listener."""
        self._listeners.append(listener)

    def reset(self) -> None:
        """Reset to initial state."""
        self._current = self._initial
        self._context.clear()
        self._history.clear()

    def get_history(self) -> List[dict]:
        return list(self._history)

    def get_graph(self) -> dict:
        """Get the state machine as a graph representation."""
        return {
            "name": self._name,
            "initial": self._initial,
            "current": self._current,
            "states": list(self._states.keys()),
            "transitions": [
                {"event": t.event, "source": t.source, "target": t.target}
                for t in self._transitions
            ],
        }
'''),
    ("projects/state-machine", r'''Implement a state machine builder with fluent API for defining complex workflows like order processing.''', r'''from typing import Any, Callable, Dict, List, Optional


class StateBuilder:
    """Fluent builder for individual state configuration."""

    def __init__(self, sm_builder, state_name: str):
        self._builder = sm_builder
        self._name = state_name
        self._on_enter = None
        self._on_exit = None
        self._is_final = False

    def on_enter(self, callback: Callable) -> "StateBuilder":
        self._on_enter = callback
        return self

    def on_exit(self, callback: Callable) -> "StateBuilder":
        self._on_exit = callback
        return self

    def final(self) -> "StateBuilder":
        self._is_final = True
        return self

    def transition(self, event: str) -> "TransitionBuilder":
        return TransitionBuilder(self._builder, self._name, event)

    def state(self, name: str) -> "StateBuilder":
        self._builder._finalize_state(self)
        return self._builder.state(name)

    def build(self):
        self._builder._finalize_state(self)
        return self._builder.build()


class TransitionBuilder:
    """Fluent builder for transition configuration."""

    def __init__(self, sm_builder, source: str, event: str):
        self._builder = sm_builder
        self._source = source
        self._event = event
        self._target = ""
        self._guard = None
        self._action = None

    def to(self, target: str) -> "TransitionBuilder":
        self._target = target
        return self

    def when(self, guard: Callable) -> "TransitionBuilder":
        self._guard = guard
        return self

    def do(self, action: Callable) -> "TransitionBuilder":
        self._action = action
        return self

    def transition(self, event: str) -> "TransitionBuilder":
        self._builder._finalize_transition(self)
        return TransitionBuilder(self._builder, self._source, event)

    def state(self, name: str) -> "StateBuilder":
        self._builder._finalize_transition(self)
        return self._builder.state(name)

    def build(self):
        self._builder._finalize_transition(self)
        return self._builder.build()


class StateMachineBuilder:
    """Fluent API for building state machines."""

    def __init__(self, name: str):
        self._name = name
        self._initial: Optional[str] = None
        self._states: List[dict] = []
        self._transitions: List[dict] = []
        self._pending_state: Optional[StateBuilder] = None
        self._context: Dict[str, Any] = {}

    def initial(self, state_name: str) -> "StateMachineBuilder":
        self._initial = state_name
        return self

    def context(self, **kwargs) -> "StateMachineBuilder":
        self._context.update(kwargs)
        return self

    def state(self, name: str) -> StateBuilder:
        if self._pending_state:
            self._finalize_state(self._pending_state)
        sb = StateBuilder(self, name)
        self._pending_state = sb
        return sb

    def _finalize_state(self, sb: StateBuilder) -> None:
        self._states.append({
            "name": sb._name,
            "on_enter": sb._on_enter,
            "on_exit": sb._on_exit,
            "is_final": sb._is_final,
        })
        self._pending_state = None

    def _finalize_transition(self, tb: TransitionBuilder) -> None:
        self._transitions.append({
            "event": tb._event,
            "source": tb._source,
            "target": tb._target,
            "guard": tb._guard,
            "action": tb._action,
        })

    def build(self):
        if self._pending_state:
            self._finalize_state(self._pending_state)

        from . import StateMachine
        sm = StateMachine(self._name, self._initial or self._states[0]["name"])
        sm._context = dict(self._context)

        for s in self._states:
            sm.add_state(s["name"], on_enter=s["on_enter"], on_exit=s["on_exit"], is_final=s["is_final"])

        for t in self._transitions:
            sm.add_transition(t["event"], t["source"], t["target"], guard=t["guard"], action=t["action"])

        return sm


def create_order_workflow() -> Any:
    """Example: Build an order processing state machine."""

    def set_payment(ctx, data):
        ctx["payment_method"] = data.get("method", "card")

    def has_payment(ctx, data):
        return "payment_method" in ctx

    def mark_shipped(ctx, data):
        ctx["tracking_number"] = data.get("tracking", "")

    builder = StateMachineBuilder("order")
    sm = (
        builder
        .initial("pending")
        .context(order_id="", total=0)
        .state("pending")
            .transition("confirm").to("confirmed").do(set_payment)
            .transition("cancel").to("cancelled")
        .state("confirmed")
            .transition("pay").to("paid").when(has_payment)
            .transition("cancel").to("cancelled")
        .state("paid")
            .transition("ship").to("shipped").do(mark_shipped)
            .transition("refund").to("refunded")
        .state("shipped")
            .transition("deliver").to("delivered")
            .transition("return").to("returned")
        .state("delivered").final()
        .state("cancelled").final()
        .state("refunded").final()
        .state("returned")
            .transition("refund").to("refunded")
        .build()
    )
    return sm
'''),
    ("projects/state-machine", r'''Implement state machine persistence with serialization, state restoration, and event sourcing.''', r'''import json
import time
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path


class StateMachineSerializer:
    """Serializes and deserializes state machine state."""

    def serialize(self, sm) -> dict:
        """Serialize the state machine's current state."""
        return {
            "name": sm._name,
            "current_state": sm._current,
            "initial_state": sm._initial,
            "context": self._serialize_context(sm._context),
            "history": sm._history,
            "serialized_at": time.time(),
        }

    def _serialize_context(self, context: dict) -> dict:
        """Serialize context values, converting non-serializable values."""
        result = {}
        for key, value in context.items():
            try:
                json.dumps(value)
                result[key] = value
            except (TypeError, ValueError):
                result[key] = str(value)
        return result

    def to_json(self, sm) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.serialize(sm), indent=2, default=str)

    def restore(self, sm, data: dict) -> None:
        """Restore state machine state from serialized data."""
        sm._current = data["current_state"]
        sm._context = data.get("context", {})
        sm._history = data.get("history", [])


class StatePersistence:
    """Persists state machine state to disk."""

    def __init__(self, storage_dir: str = ".state_machines"):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._serializer = StateMachineSerializer()

    def save(self, sm, instance_id: str) -> None:
        """Save state machine state."""
        filepath = self._dir / f"{instance_id}.json"
        data = self._serializer.serialize(sm)
        data["instance_id"] = instance_id
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, sm, instance_id: str) -> bool:
        """Load state machine state. Returns True if found."""
        filepath = self._dir / f"{instance_id}.json"
        if not filepath.exists():
            return False
        with open(filepath, "r") as f:
            data = json.load(f)
        self._serializer.restore(sm, data)
        return True

    def delete(self, instance_id: str) -> bool:
        filepath = self._dir / f"{instance_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def list_instances(self) -> List[dict]:
        """List all saved state machine instances."""
        results = []
        for filepath in self._dir.glob("*.json"):
            with open(filepath, "r") as f:
                data = json.load(f)
            results.append({
                "instance_id": data.get("instance_id", filepath.stem),
                "name": data.get("name", ""),
                "current_state": data.get("current_state", ""),
                "serialized_at": data.get("serialized_at", 0),
            })
        return results


class EventSourcedStateMachine:
    """State machine that stores all events for replay and audit."""

    def __init__(self, sm, event_log_path: str):
        self._sm = sm
        self._log_path = Path(event_log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, event: str, **data) -> bool:
        """Send an event and log it."""
        # Log the event before processing
        log_entry = {
            "timestamp": time.time(),
            "event": event,
            "from_state": self._sm.current_state,
            "data": data,
        }

        result = self._sm.send(event, **data)

        log_entry["to_state"] = self._sm.current_state
        log_entry["success"] = result

        with open(self._log_path, "a") as f:
            f.write(json.dumps(log_entry, default=str) + "\n")

        return result

    def replay(self, sm_factory: Callable) -> Any:
        """Replay all events to rebuild state from scratch."""
        new_sm = sm_factory()

        if not self._log_path.exists():
            return new_sm

        with open(self._log_path, "r") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("success"):
                    new_sm.send(entry["event"], **entry.get("data", {}))

        return new_sm

    def get_event_log(self, limit: int = 100) -> List[dict]:
        """Read the event log."""
        events = []
        if not self._log_path.exists():
            return events

        with open(self._log_path, "r") as f:
            for line in f:
                events.append(json.loads(line))

        return events[-limit:]

    def get_audit_trail(self) -> List[dict]:
        """Get a human-readable audit trail."""
        events = self.get_event_log()
        trail = []
        for e in events:
            if e.get("success"):
                trail.append({
                    "timestamp": e["timestamp"],
                    "action": e["event"],
                    "transition": f"{e['from_state']} -> {e['to_state']}",
                })
        return trail

    @property
    def current_state(self) -> str:
        return self._sm.current_state

    @property
    def context(self) -> dict:
        return self._sm.context
'''),
    ("projects/state-machine", r'''Implement hierarchical (nested) states and parallel state regions for complex state machines.''', r'''from typing import Any, Callable, Dict, List, Optional, Set


class HierarchicalState:
    """A state that can contain sub-states (nested state machine)."""

    def __init__(self, name: str, initial_sub: Optional[str] = None):
        self.name = name
        self.initial_sub = initial_sub
        self.sub_states: Dict[str, "HierarchicalState"] = {}
        self.parent: Optional["HierarchicalState"] = None
        self.on_enter: Optional[Callable] = None
        self.on_exit: Optional[Callable] = None
        self.is_final: bool = False

    def add_sub_state(self, state: "HierarchicalState") -> None:
        state.parent = self
        self.sub_states[state.name] = state

    @property
    def is_composite(self) -> bool:
        return len(self.sub_states) > 0

    def get_path(self) -> List[str]:
        """Get the full state path from root."""
        path = [self.name]
        current = self.parent
        while current:
            path.insert(0, current.name)
            current = current.parent
        return path

    @property
    def full_name(self) -> str:
        return ".".join(self.get_path())


class HierarchicalStateMachine:
    """State machine with nested states and history."""

    def __init__(self, name: str, root_initial: str):
        self._name = name
        self._root_initial = root_initial
        self._states: Dict[str, HierarchicalState] = {}
        self._transitions: List[dict] = []
        self._active_states: List[str] = []
        self._context: Dict[str, Any] = {}
        self._history: Dict[str, str] = {}  # state -> last active sub-state
        self._listeners: List[Callable] = []

    def add_state(self, state: HierarchicalState) -> None:
        """Add a top-level or nested state."""
        self._states[state.full_name] = state

        # Also register by simple name for lookup
        self._states[state.name] = state

        for sub in state.sub_states.values():
            self.add_state(sub)

    def add_transition(self, event: str, source: str, target: str, guard: Optional[Callable] = None, action: Optional[Callable] = None) -> None:
        self._transitions.append({
            "event": event,
            "source": source,
            "target": target,
            "guard": guard,
            "action": action,
        })

    def start(self) -> None:
        """Initialize the state machine."""
        self._enter_state(self._root_initial)

    def _enter_state(self, state_name: str) -> None:
        """Enter a state, including any default sub-states."""
        state = self._states.get(state_name)
        if not state:
            return

        self._active_states.append(state_name)

        if state.on_enter:
            state.on_enter(self._context)

        # Enter initial sub-state if composite
        if state.is_composite and state.initial_sub:
            self._enter_state(state.initial_sub)

    def _exit_state(self, state_name: str) -> None:
        """Exit a state and all active sub-states."""
        state = self._states.get(state_name)
        if not state:
            return

        # Exit sub-states first (deepest first)
        for sub_name in reversed(list(self._active_states)):
            sub_state = self._states.get(sub_name)
            if sub_state and sub_state.parent and sub_state.parent.name == state_name:
                self._exit_state(sub_name)

        if state.on_exit:
            state.on_exit(self._context)

        # Save history
        if state.parent:
            self._history[state.parent.name] = state_name

        if state_name in self._active_states:
            self._active_states.remove(state_name)

    def send(self, event: str, **data) -> bool:
        """Process an event. Checks transitions from deepest active state up."""
        # Check from most specific (deepest) state first
        for state_name in reversed(list(self._active_states)):
            matching = [
                t for t in self._transitions
                if t["event"] == event and t["source"] == state_name
            ]

            for trans in matching:
                if trans["guard"] and not trans["guard"](self._context, data):
                    continue

                old_state = state_name
                self._exit_state(state_name)

                if trans["action"]:
                    trans["action"](self._context, data)

                self._enter_state(trans["target"])

                for listener in self._listeners:
                    listener({"event": event, "from": old_state, "to": trans["target"]})

                return True

        return False

    @property
    def active_states(self) -> List[str]:
        return list(self._active_states)

    @property
    def current_leaf_state(self) -> str:
        """Get the deepest active state."""
        return self._active_states[-1] if self._active_states else ""


class ParallelRegion:
    """A parallel state region that runs multiple sub-machines concurrently."""

    def __init__(self, name: str):
        self.name = name
        self._regions: Dict[str, HierarchicalStateMachine] = {}

    def add_region(self, name: str, machine: HierarchicalStateMachine) -> None:
        self._regions[name] = machine

    def start(self) -> None:
        for machine in self._regions.values():
            machine.start()

    def send(self, event: str, **data) -> Dict[str, bool]:
        """Send an event to all regions. Returns per-region results."""
        results = {}
        for name, machine in self._regions.items():
            results[name] = machine.send(event, **data)
        return results

    def get_active_states(self) -> Dict[str, List[str]]:
        return {
            name: machine.active_states
            for name, machine in self._regions.items()
        }

    def all_in_final(self) -> bool:
        """Check if all regions are in a final state."""
        for machine in self._regions.values():
            leaf = machine.current_leaf_state
            state = machine._states.get(leaf)
            if state and not state.is_final:
                return False
        return True
'''),
    ("projects/state-machine", r'''<think>
Visualizing state machines is useful for debugging and documentation.
I should implement DOT/Graphviz export and ASCII rendering so users
can see the state machine structure without external tools.
</think>
Implement state machine visualization with DOT/Graphviz export and ASCII rendering.''', r'''from typing import Dict, List, Optional, Set


class StateMachineVisualizer:
    """Generates visual representations of state machines."""

    def to_dot(self, sm, title: Optional[str] = None) -> str:
        """Generate Graphviz DOT format for the state machine."""
        name = title or sm._name
        lines = [
            f'digraph "{name}" {{',
            '  rankdir=LR;',
            '  node [shape=circle, fontname="Arial"];',
            '  edge [fontname="Arial", fontsize=10];',
            '',
        ]

        # Initial state indicator
        lines.append('  __start__ [shape=point, width=0.2];')
        lines.append(f'  __start__ -> "{sm._initial}";')
        lines.append('')

        # States
        for state_name, config in sm._states.items():
            attrs = []
            if config.is_final:
                attrs.append('shape=doublecircle')
            if state_name == sm._current:
                attrs.append('style=filled')
                attrs.append('fillcolor="#90EE90"')

            attr_str = f' [{", ".join(attrs)}]' if attrs else ''
            lines.append(f'  "{state_name}"{attr_str};')

        lines.append('')

        # Transitions
        for t in sm._transitions:
            label = t.event
            if t.guard:
                label += " [guard]"
            style = ""
            if t.source == sm._current:
                style = ', color="blue", penwidth=2'

            lines.append(f'  "{t.source}" -> "{t.target}" [label="{label}"{style}];')

        lines.append('}')
        return '\n'.join(lines)

    def to_ascii(self, sm) -> str:
        """Generate an ASCII representation of the state machine."""
        lines = []
        lines.append(f"State Machine: {sm._name}")
        lines.append(f"Current State: [{sm._current}]")
        lines.append("")

        # States section
        lines.append("States:")
        for name, config in sm._states.items():
            marker = " *" if name == sm._current else ""
            final = " (final)" if config.is_final else ""
            initial = " (initial)" if name == sm._initial else ""
            lines.append(f"  [{name}]{marker}{initial}{final}")

        lines.append("")
        lines.append("Transitions:")

        # Group transitions by source
        by_source: Dict[str, list] = {}
        for t in sm._transitions:
            if t.source not in by_source:
                by_source[t.source] = []
            by_source[t.source].append(t)

        for source, transitions in sorted(by_source.items()):
            for t in transitions:
                guard = " (guarded)" if t.guard else ""
                action = " (action)" if t.action else ""
                arrow = "-->" if source != sm._current else "==>"
                lines.append(f"  [{source}] {arrow} ({t.event}){guard}{action} {arrow} [{t.target}]")

        lines.append("")

        # Available events
        available = sm.available_events()
        if available:
            lines.append(f"Available events: {', '.join(available)}")
        else:
            lines.append("No available events (final state)")

        return '\n'.join(lines)

    def to_mermaid(self, sm) -> str:
        """Generate Mermaid diagram syntax for the state machine."""
        lines = ["stateDiagram-v2"]

        # Initial state
        lines.append(f"  [*] --> {sm._initial}")

        # Transitions
        for t in sm._transitions:
            lines.append(f"  {t.source} --> {t.target} : {t.event}")

        # Final states
        for name, config in sm._states.items():
            if config.is_final:
                lines.append(f"  {name} --> [*]")

        return '\n'.join(lines)

    def to_table(self, sm) -> str:
        """Generate a state transition table."""
        # Collect all events
        events = sorted(set(t.event for t in sm._transitions))
        states = sorted(sm._states.keys())

        # Build table
        col_width = max(12, max(len(e) for e in events) + 2) if events else 12
        state_width = max(len(s) for s in states) + 2 if states else 10

        # Header
        header = f"{'State':<{state_width}}"
        for event in events:
            header += f" | {event:^{col_width}}"
        lines = [header]
        lines.append("-" * len(header))

        # Rows
        for state in states:
            row = f"{state:<{state_width}}"
            for event in events:
                matching = [
                    t for t in sm._transitions
                    if t.source == state and t.event == event
                ]
                if matching:
                    target = matching[0].target
                    cell = f"-> {target}"
                else:
                    cell = "-"
                row += f" | {cell:^{col_width}}"
            lines.append(row)

        return '\n'.join(lines)

    def save_dot(self, sm, filepath: str) -> None:
        """Save DOT format to a file."""
        dot = self.to_dot(sm)
        with open(filepath, "w") as f:
            f.write(dot)

    def render_png(self, sm, filepath: str) -> None:
        """Render to PNG using Graphviz (requires graphviz installed)."""
        import subprocess
        dot = self.to_dot(sm)
        dot_file = filepath + ".dot"
        with open(dot_file, "w") as f:
            f.write(dot)
        try:
            subprocess.run(
                ["dot", "-Tpng", dot_file, "-o", filepath],
                check=True, capture_output=True,
            )
        finally:
            import os
            os.unlink(dot_file)
'''),
]
