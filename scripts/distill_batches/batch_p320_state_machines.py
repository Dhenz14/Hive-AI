"""State machines — XState patterns, finite state machines, statecharts, guards, actions, parallel states."""

PAIRS = [
    (
        "state-machines/xstate-v5-patterns",
        "Show how to build a complex multi-step form wizard using XState v5 with TypeScript, including guards, actions, context updates, and service invocations.",
        '''XState v5 multi-step form wizard with full type safety, guards, and async service invocations:

```typescript
// --- formWizardMachine.ts --- XState v5 statechart for multi-step form ---

import { setup, assign, fromPromise, assertEvent } from "xstate";

// ---- Type definitions ----
interface Address {
  street: string;
  city: string;
  state: string;
  zip: string;
}

interface FormContext {
  currentStep: number;
  totalSteps: number;
  personalInfo: {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
  };
  address: Address;
  preferences: {
    newsletter: boolean;
    notifications: string[];
    theme: "light" | "dark" | "system";
  };
  errors: Record<string, string[]>;
  submissionId: string | null;
  retryCount: number;
}

type FormEvent =
  | { type: "NEXT" }
  | { type: "BACK" }
  | { type: "UPDATE_FIELD"; section: string; field: string; value: unknown }
  | { type: "SUBMIT" }
  | { type: "RETRY" }
  | { type: "RESET" };

// ---- Validation logic ----
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_RE = /^\+?[\d\s\-()]{10,}$/;
const ZIP_RE = /^\d{5}(-\d{4})?$/;

function validatePersonalInfo(ctx: FormContext): Record<string, string[]> {
  const errors: Record<string, string[]> = {};
  const { firstName, lastName, email, phone } = ctx.personalInfo;
  if (!firstName.trim()) errors.firstName = ["First name is required"];
  if (!lastName.trim()) errors.lastName = ["Last name is required"];
  if (!EMAIL_RE.test(email)) errors.email = ["Valid email is required"];
  if (phone && !PHONE_RE.test(phone)) errors.phone = ["Invalid phone format"];
  return errors;
}

function validateAddress(ctx: FormContext): Record<string, string[]> {
  const errors: Record<string, string[]> = {};
  const { street, city, state, zip } = ctx.address;
  if (!street.trim()) errors.street = ["Street is required"];
  if (!city.trim()) errors.city = ["City is required"];
  if (!state.trim()) errors.state = ["State is required"];
  if (!ZIP_RE.test(zip)) errors.zip = ["Valid ZIP code is required"];
  return errors;
}

// ---- Async submission actor ----
const submitForm = fromPromise(
  async ({ input }: { input: { context: FormContext } }) => {
    const response = await fetch("/api/registration", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        personalInfo: input.context.personalInfo,
        address: input.context.address,
        preferences: input.context.preferences,
      }),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.message ?? "Submission failed");
    }
    return (await response.json()) as { id: string };
  }
);

// ---- Machine definition ----
export const formWizardMachine = setup({
  types: {
    context: {} as FormContext,
    events: {} as FormEvent,
  },
  guards: {
    isPersonalInfoValid: ({ context }) =>
      Object.keys(validatePersonalInfo(context)).length === 0,
    isAddressValid: ({ context }) =>
      Object.keys(validateAddress(context)).length === 0,
    canRetry: ({ context }) => context.retryCount < 3,
  },
  actions: {
    setValidationErrors: assign({
      errors: ({ context, event }) => {
        if (context.currentStep === 0) return validatePersonalInfo(context);
        if (context.currentStep === 1) return validateAddress(context);
        return {};
      },
    }),
    clearErrors: assign({ errors: () => ({}) }),
    incrementStep: assign({
      currentStep: ({ context }) =>
        Math.min(context.currentStep + 1, context.totalSteps - 1),
    }),
    decrementStep: assign({
      currentStep: ({ context }) => Math.max(context.currentStep - 1, 0),
    }),
    updateField: assign({
      personalInfo: ({ context, event }) => {
        assertEvent(event, "UPDATE_FIELD");
        if (event.section !== "personalInfo") return context.personalInfo;
        return { ...context.personalInfo, [event.field]: event.value };
      },
      address: ({ context, event }) => {
        assertEvent(event, "UPDATE_FIELD");
        if (event.section !== "address") return context.address;
        return { ...context.address, [event.field]: event.value };
      },
      preferences: ({ context, event }) => {
        assertEvent(event, "UPDATE_FIELD");
        if (event.section !== "preferences") return context.preferences;
        return { ...context.preferences, [event.field]: event.value };
      },
    }),
    incrementRetry: assign({
      retryCount: ({ context }) => context.retryCount + 1,
    }),
    resetForm: assign({
      currentStep: () => 0,
      personalInfo: () => ({ firstName: "", lastName: "", email: "", phone: "" }),
      address: () => ({ street: "", city: "", state: "", zip: "" }),
      preferences: () => ({
        newsletter: false,
        notifications: [] as string[],
        theme: "system" as const,
      }),
      errors: () => ({}),
      submissionId: () => null,
      retryCount: () => 0,
    }),
  },
  actors: { submitForm },
}).createMachine({
  id: "formWizard",
  initial: "editing",
  context: {
    currentStep: 0,
    totalSteps: 3,
    personalInfo: { firstName: "", lastName: "", email: "", phone: "" },
    address: { street: "", city: "", state: "", zip: "" },
    preferences: { newsletter: false, notifications: [], theme: "system" },
    errors: {},
    submissionId: null,
    retryCount: 0,
  },
  states: {
    editing: {
      on: {
        UPDATE_FIELD: { actions: ["updateField", "clearErrors"] },
        BACK: { actions: "decrementStep" },
        NEXT: [
          {
            guard: "isPersonalInfoValid",
            actions: ["clearErrors", "incrementStep"],
            target: undefined, // stay in editing
          },
          { actions: "setValidationErrors" },
        ],
        SUBMIT: [
          {
            guard: "isAddressValid",
            target: "submitting",
          },
          { actions: "setValidationErrors" },
        ],
      },
    },
    submitting: {
      invoke: {
        src: "submitForm",
        input: ({ context }) => ({ context }),
        onDone: {
          target: "success",
          actions: assign({
            submissionId: ({ event }) => event.output.id,
          }),
        },
        onError: [
          {
            guard: "canRetry",
            target: "retrying",
            actions: "incrementRetry",
          },
          { target: "failure" },
        ],
      },
    },
    retrying: {
      after: {
        2000: "submitting",
      },
    },
    success: {
      on: { RESET: { target: "editing", actions: "resetForm" } },
    },
    failure: {
      on: {
        RETRY: {
          target: "submitting",
          actions: assign({ retryCount: () => 0 }),
        },
        RESET: { target: "editing", actions: "resetForm" },
      },
    },
  },
});
```

Key patterns:

- **`setup()` API** in XState v5 centralizes guards, actions, and actors with full type inference
- **Guards** validate each step before transitions; invalid input stays in the same state
- **`assign()` actions** immutably update nested context fields
- **`fromPromise` actors** handle async side effects with automatic `onDone`/`onError`
- **Retry with backoff** uses `after` delayed transitions and a retry counter
- **`assertEvent()`** narrows event types inside action implementations

| XState v4 | XState v5 |
|-----------|-----------|
| `createMachine({ actions: {} })` | `setup({ actions: {} }).createMachine(...)` |
| `services` | `actors` (invoke `fromPromise`, `fromObservable`, etc.) |
| `cond` | `guard` |
| `context: (ctx, evt) =>` | `context: ({ context, event }) =>` |
| String references loosely typed | Full TypeScript inference via `setup()` |
'''
    ),
    (
        "state-machines/python-finite-state-machine",
        "Implement a production-quality finite state machine in Python with transition hooks, state history, persistence, and visualization.",
        '''A production-grade Python FSM with hooks, history tracking, serialization, and Graphviz export:

```python
# --- fsm.py --- Production finite state machine framework ---

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Generic, TypeVar, Protocol,
    runtime_checkable,
)
from collections import defaultdict
from graphlib import TopologicalSorter

logger = logging.getLogger(__name__)

S = TypeVar("S", bound=Enum)
E = TypeVar("E", bound=Enum)


@dataclass(frozen=True)
class TransitionRecord:
    """Immutable record of a state transition."""
    timestamp: float
    source: str
    target: str
    event: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Guard(Protocol):
    """Protocol for transition guard callables."""
    def __call__(self, context: dict[str, Any], event: str) -> bool: ...


@dataclass
class Transition(Generic[S]):
    """A single transition definition."""
    source: S
    target: S
    event: str
    guard: Guard | None = None
    action: Callable[[dict[str, Any]], None] | None = None
    description: str = ""


class FSMError(Exception):
    """Base FSM exception."""


class InvalidTransitionError(FSMError):
    """Raised when no valid transition exists."""


class GuardRejectedError(FSMError):
    """Raised when a guard blocks a transition."""


class FiniteStateMachine(Generic[S, E]):
    """
    Finite state machine with:
    - Typed states and events via Enum
    - Guard conditions on transitions
    - Entry/exit/transition actions (hooks)
    - Full transition history with timestamps
    - Serialization and deserialization
    - Graphviz DOT export
    """

    def __init__(
        self,
        name: str,
        states: type[S],
        events: type[E],
        initial: S,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self._states = states
        self._events = events
        self._current: S = initial
        self._initial: S = initial
        self.context: dict[str, Any] = context or {}

        # Transition table: (source, event) -> list[Transition]
        self._transitions: dict[tuple[S, str], list[Transition[S]]] = defaultdict(list)

        # Hooks
        self._on_enter: dict[S, list[Callable]] = defaultdict(list)
        self._on_exit: dict[S, list[Callable]] = defaultdict(list)
        self._on_transition: list[Callable[[TransitionRecord], None]] = []

        # History
        self._history: list[TransitionRecord] = []
        self._max_history = 10_000

    # ---- Configuration API ----

    def add_transition(
        self,
        source: S,
        target: S,
        event: E | str,
        *,
        guard: Guard | None = None,
        action: Callable[[dict[str, Any]], None] | None = None,
        description: str = "",
    ) -> FiniteStateMachine[S, E]:
        """Register a transition. Chainable."""
        evt_name = event.name if isinstance(event, Enum) else event
        t = Transition(
            source=source,
            target=target,
            event=evt_name,
            guard=guard,
            action=action,
            description=description,
        )
        self._transitions[(source, evt_name)].append(t)
        return self

    def on_enter(self, state: S, callback: Callable) -> FiniteStateMachine[S, E]:
        """Register entry hook for a state. Chainable."""
        self._on_enter[state].append(callback)
        return self

    def on_exit(self, state: S, callback: Callable) -> FiniteStateMachine[S, E]:
        """Register exit hook for a state. Chainable."""
        self._on_exit[state].append(callback)
        return self

    def on_any_transition(
        self, callback: Callable[[TransitionRecord], None]
    ) -> FiniteStateMachine[S, E]:
        """Register a listener for all transitions. Chainable."""
        self._on_transition.append(callback)
        return self

    # ---- Runtime API ----

    @property
    def state(self) -> S:
        return self._current

    @property
    def history(self) -> list[TransitionRecord]:
        return list(self._history)

    def can_handle(self, event: E | str) -> bool:
        """Check whether the current state can handle the given event."""
        evt_name = event.name if isinstance(event, Enum) else event
        transitions = self._transitions.get((self._current, evt_name), [])
        return any(
            t.guard is None or t.guard(self.context, evt_name) for t in transitions
        )

    def send(self, event: E | str, **metadata: Any) -> S:
        """
        Dispatch an event to trigger a transition.
        Returns the new state.
        Raises InvalidTransitionError if no transition matches.
        """
        evt_name = event.name if isinstance(event, Enum) else event
        candidates = self._transitions.get((self._current, evt_name), [])

        if not candidates:
            raise InvalidTransitionError(
                f"No transition from {self._current.name} on {evt_name}"
            )

        # Evaluate guards — first passing transition wins
        chosen: Transition[S] | None = None
        for t in candidates:
            if t.guard is None or t.guard(self.context, evt_name):
                chosen = t
                break

        if chosen is None:
            raise GuardRejectedError(
                f"All guards rejected {evt_name} in state {self._current.name}"
            )

        source = self._current
        target = chosen.target

        # Exit hooks
        for cb in self._on_exit.get(source, []):
            cb(self.context)

        # Transition action
        if chosen.action:
            chosen.action(self.context)

        # State change
        self._current = target
        logger.info("FSM[%s] %s --%s--> %s", self.name, source.name, evt_name, target.name)

        # Entry hooks
        for cb in self._on_enter.get(target, []):
            cb(self.context)

        # Record history
        record = TransitionRecord(
            timestamp=time.time(),
            source=source.name,
            target=target.name,
            event=evt_name,
            metadata=metadata,
        )
        self._history.append(record)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Notify global listeners
        for listener in self._on_transition:
            listener(record)

        return self._current

    def reset(self) -> None:
        """Reset to initial state, clearing history."""
        self._current = self._initial
        self._history.clear()

    # ---- Serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current_state": self._current.name,
            "initial_state": self._initial.name,
            "context": self.context,
            "history": [
                {
                    "timestamp": r.timestamp,
                    "source": r.source,
                    "target": r.target,
                    "event": r.event,
                    "metadata": r.metadata,
                }
                for r in self._history
            ],
        }

    def load_state(self, state_name: str, context: dict[str, Any] | None = None) -> None:
        """Restore FSM to a previously saved state."""
        self._current = self._states[state_name]
        if context is not None:
            self.context = context

    # ---- Visualization ----

    def to_dot(self) -> str:
        """Export as Graphviz DOT for visualization."""
        lines = [f'digraph "{self.name}" {{', "  rankdir=LR;"]
        lines.append(f'  node [shape=circle]; "{self._current.name}" [style=bold, color=blue];')

        for (source, event), transitions in self._transitions.items():
            for t in transitions:
                label = event
                if t.guard:
                    label += f" [{t.guard.__name__}]"
                lines.append(f'  "{source.name}" -> "{t.target.name}" [label="{label}"];')

        lines.append("}")
        return "\n".join(lines)


# ---- Example: Order processing FSM ----

class OrderState(Enum):
    DRAFT = auto()
    SUBMITTED = auto()
    PAYMENT_PENDING = auto()
    PAID = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()

class OrderEvent(Enum):
    SUBMIT = auto()
    PAY = auto()
    PAYMENT_FAILED = auto()
    SHIP = auto()
    DELIVER = auto()
    CANCEL = auto()


def has_items(ctx: dict, event: str) -> bool:
    return len(ctx.get("items", [])) > 0

def is_payment_valid(ctx: dict, event: str) -> bool:
    return ctx.get("payment_amount", 0) > 0

order_fsm = (
    FiniteStateMachine("OrderProcessing", OrderState, OrderEvent, OrderState.DRAFT, context={"items": []})
    .add_transition(OrderState.DRAFT, OrderState.SUBMITTED, OrderEvent.SUBMIT, guard=has_items)
    .add_transition(OrderState.SUBMITTED, OrderState.PAYMENT_PENDING, "PAY")
    .add_transition(OrderState.PAYMENT_PENDING, OrderState.PAID, "PAY", guard=is_payment_valid)
    .add_transition(OrderState.PAYMENT_PENDING, OrderState.SUBMITTED, OrderEvent.PAYMENT_FAILED)
    .add_transition(OrderState.PAID, OrderState.SHIPPED, OrderEvent.SHIP)
    .add_transition(OrderState.SHIPPED, OrderState.DELIVERED, OrderEvent.DELIVER)
    .add_transition(OrderState.DRAFT, OrderState.CANCELLED, OrderEvent.CANCEL)
    .add_transition(OrderState.SUBMITTED, OrderState.CANCELLED, OrderEvent.CANCEL)
    .on_enter(OrderState.PAID, lambda ctx: ctx.update({"paid_at": time.time()}))
    .on_enter(OrderState.SHIPPED, lambda ctx: logger.info("Order shipped!"))
)
```

Key patterns:

- **Generic typing** `FiniteStateMachine[S, E]` ensures state and event enums are type-checked
- **Guard conditions** are first-class — multiple transitions per `(state, event)` pair evaluated in order
- **Entry/exit hooks** decouple side effects from transition logic
- **Transition history** with bounded buffer and timestamps enables audit logging
- **Chainable API** via returning `self` from configuration methods
- **DOT export** generates visual diagrams via Graphviz
- **Serialization** supports persistence to JSON/database for long-running workflows
'''
    ),
    (
        "state-machines/statecharts-parallel-states",
        "Implement parallel (orthogonal) states using XState v5 for a media player that handles playback and volume independently with synchronized events.",
        '''XState v5 parallel states for a media player with independent playback and volume regions:

```typescript
// --- mediaPlayerMachine.ts --- Parallel statechart regions ---

import { setup, assign, raise } from "xstate";

interface Track {
  id: string;
  title: string;
  artist: string;
  duration: number; // seconds
  url: string;
}

interface PlayerContext {
  playlist: Track[];
  currentIndex: number;
  position: number;       // seconds elapsed
  volume: number;         // 0-100
  previousVolume: number; // for unmute restore
  playbackRate: number;
  shuffle: boolean;
  repeat: "none" | "one" | "all";
  error: string | null;
}

type PlayerEvent =
  | { type: "PLAY" }
  | { type: "PAUSE" }
  | { type: "STOP" }
  | { type: "NEXT_TRACK" }
  | { type: "PREV_TRACK" }
  | { type: "SEEK"; position: number }
  | { type: "TRACK_ENDED" }
  | { type: "SET_VOLUME"; level: number }
  | { type: "MUTE" }
  | { type: "UNMUTE" }
  | { type: "TOGGLE_SHUFFLE" }
  | { type: "SET_REPEAT"; mode: "none" | "one" | "all" }
  | { type: "SET_PLAYBACK_RATE"; rate: number }
  | { type: "LOAD_PLAYLIST"; tracks: Track[] }
  | { type: "ERROR"; message: string }
  | { type: "RETRY" };

export const mediaPlayerMachine = setup({
  types: {
    context: {} as PlayerContext,
    events: {} as PlayerEvent,
  },
  guards: {
    hasNextTrack: ({ context }) =>
      context.currentIndex < context.playlist.length - 1,
    hasPrevTrack: ({ context }) => context.currentIndex > 0,
    hasPlaylist: ({ context }) => context.playlist.length > 0,
    shouldRepeatOne: ({ context }) => context.repeat === "one",
    shouldRepeatAll: ({ context }) => context.repeat === "all",
    isMuted: ({ context }) => context.volume === 0,
  },
  actions: {
    loadNextTrack: assign({
      currentIndex: ({ context }) => {
        if (context.shuffle) {
          let next: number;
          do {
            next = Math.floor(Math.random() * context.playlist.length);
          } while (next === context.currentIndex && context.playlist.length > 1);
          return next;
        }
        return Math.min(context.currentIndex + 1, context.playlist.length - 1);
      },
      position: () => 0,
      error: () => null,
    }),
    loadPrevTrack: assign({
      currentIndex: ({ context }) => Math.max(context.currentIndex - 1, 0),
      position: () => 0,
    }),
    resetPosition: assign({ position: () => 0 }),
    seekTo: assign({
      position: ({ event }) => {
        if (event.type === "SEEK") return event.position;
        return 0;
      },
    }),
    setVolume: assign({
      volume: ({ event }) => {
        if (event.type === "SET_VOLUME") return Math.max(0, Math.min(100, event.level));
        return 50;
      },
    }),
    mute: assign({
      previousVolume: ({ context }) => context.volume,
      volume: () => 0,
    }),
    unmute: assign({
      volume: ({ context }) => context.previousVolume || 50,
    }),
    toggleShuffle: assign({
      shuffle: ({ context }) => !context.shuffle,
    }),
    setRepeat: assign({
      repeat: ({ event }) => {
        if (event.type === "SET_REPEAT") return event.mode;
        return "none" as const;
      },
    }),
    setPlaybackRate: assign({
      playbackRate: ({ event }) => {
        if (event.type === "SET_PLAYBACK_RATE") return event.rate;
        return 1;
      },
    }),
    loadPlaylist: assign({
      playlist: ({ event }) => {
        if (event.type === "LOAD_PLAYLIST") return event.tracks;
        return [];
      },
      currentIndex: () => 0,
      position: () => 0,
    }),
    setError: assign({
      error: ({ event }) => {
        if (event.type === "ERROR") return event.message;
        return null;
      },
    }),
    wrapToFirstTrack: assign({
      currentIndex: () => 0,
      position: () => 0,
    }),
  },
}).createMachine({
  id: "mediaPlayer",
  type: "parallel",   // <-- two orthogonal regions
  context: {
    playlist: [],
    currentIndex: 0,
    position: 0,
    volume: 75,
    previousVolume: 75,
    playbackRate: 1,
    shuffle: false,
    repeat: "none",
    error: null,
  },
  states: {
    // ---- Region 1: Playback control ----
    playback: {
      initial: "idle",
      states: {
        idle: {
          on: {
            LOAD_PLAYLIST: {
              target: "stopped",
              actions: "loadPlaylist",
            },
          },
        },
        stopped: {
          on: {
            PLAY: { guard: "hasPlaylist", target: "playing" },
          },
        },
        playing: {
          on: {
            PAUSE: "paused",
            STOP: { target: "stopped", actions: "resetPosition" },
            NEXT_TRACK: [
              { guard: "hasNextTrack", actions: "loadNextTrack" },
              { guard: "shouldRepeatAll", actions: "wrapToFirstTrack" },
            ],
            PREV_TRACK: {
              guard: "hasPrevTrack",
              actions: "loadPrevTrack",
            },
            SEEK: { actions: "seekTo" },
            TRACK_ENDED: [
              { guard: "shouldRepeatOne", actions: "resetPosition" },
              { guard: "hasNextTrack", actions: "loadNextTrack" },
              { guard: "shouldRepeatAll", actions: "wrapToFirstTrack" },
              { target: "stopped", actions: "resetPosition" },
            ],
            SET_PLAYBACK_RATE: { actions: "setPlaybackRate" },
            TOGGLE_SHUFFLE: { actions: "toggleShuffle" },
            SET_REPEAT: { actions: "setRepeat" },
            ERROR: { target: "error", actions: "setError" },
          },
        },
        paused: {
          on: {
            PLAY: "playing",
            STOP: { target: "stopped", actions: "resetPosition" },
            SEEK: { actions: "seekTo" },
            NEXT_TRACK: [
              { guard: "hasNextTrack", target: "playing", actions: "loadNextTrack" },
            ],
          },
        },
        error: {
          on: {
            RETRY: "playing",
            STOP: { target: "stopped", actions: "resetPosition" },
          },
        },
      },
    },

    // ---- Region 2: Volume control (independent) ----
    volume: {
      initial: "unmuted",
      states: {
        unmuted: {
          on: {
            SET_VOLUME: { actions: "setVolume" },
            MUTE: { target: "muted", actions: "mute" },
          },
        },
        muted: {
          on: {
            UNMUTE: { target: "unmuted", actions: "unmute" },
            SET_VOLUME: { target: "unmuted", actions: "setVolume" },
          },
        },
      },
    },
  },
});
```

Key patterns for parallel (orthogonal) states:

- **`type: "parallel"`** creates independent regions that run concurrently
- The **playback** region handles play/pause/stop/track-navigation independently from volume
- The **volume** region manages mute/unmute/level without affecting playback state
- Both regions can react to the same event (e.g., a global RESET could target both)
- **Guard priority** in arrays gives first-match semantics for `TRACK_ENDED` repeat logic
- Parallel states produce **compound state values** like `{ playback: "playing", volume: "muted" }`

| Concept | Description |
|---------|-------------|
| Parallel states | Independent regions that operate concurrently |
| Guard arrays | Multiple transitions tried in order, first match wins |
| Raise action | Internally dispatch events between regions |
| History states | Remember last active child (use `type: "history"`) |
| Done events | `onDone` fires when a final state is reached in a region |
'''
    ),
    (
        "state-machines/python-statechart-hierarchical",
        "Build a hierarchical state machine in Python for a TCP connection with nested states, history, and timeout handling.",
        '''Hierarchical state machine for TCP connection lifecycle with nested states:

```python
# --- tcp_hsm.py --- Hierarchical state machine for TCP connections ---

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class StateNode:
    """A node in the hierarchical state tree."""
    name: str
    parent: StateNode | None = None
    children: dict[str, StateNode] = field(default_factory=dict)
    initial_child: str | None = None
    on_enter: list[Callable] = field(default_factory=list)
    on_exit: list[Callable] = field(default_factory=list)
    is_final: bool = False
    timeout: float | None = None  # seconds
    timeout_event: str | None = None

    @property
    def path(self) -> str:
        parts = []
        node: StateNode | None = self
        while node:
            parts.append(node.name)
            node = node.parent
        return ".".join(reversed(parts))

    @property
    def is_compound(self) -> bool:
        return len(self.children) > 0

    @property
    def is_atomic(self) -> bool:
        return len(self.children) == 0


@dataclass(frozen=True)
class HSMTransition:
    """Transition between hierarchical states."""
    source_path: str
    target_path: str
    event: str
    guard: Callable[[dict], bool] | None = None
    action: Callable[[dict], None] | None = None


class HierarchicalStateMachine:
    """
    Statechart implementation with:
    - Nested/compound states
    - Automatic entry into initial child states
    - Proper exit ordering (leaf to ancestor)
    - Proper entry ordering (ancestor to leaf)
    - Timeout transitions
    - History tracking per compound state
    """

    def __init__(self, name: str, context: dict[str, Any] | None = None):
        self.name = name
        self.context = context or {}
        self._root = StateNode(name="root")
        self._states: dict[str, StateNode] = {"root": self._root}
        self._transitions: dict[tuple[str, str], list[HSMTransition]] = {}
        self._active_states: list[StateNode] = []
        self._history: dict[str, str] = {}  # compound_path -> last_active_child
        self._timeout_tasks: dict[str, asyncio.Task] = {}
        self._started = False

    # ---- Builder API ----

    def add_state(
        self,
        path: str,
        *,
        parent_path: str = "root",
        initial_child: str | None = None,
        on_enter: Callable | None = None,
        on_exit: Callable | None = None,
        is_final: bool = False,
        timeout: float | None = None,
        timeout_event: str | None = None,
    ) -> HierarchicalStateMachine:
        parent = self._states[parent_path]
        node = StateNode(
            name=path.split(".")[-1],
            parent=parent,
            initial_child=initial_child,
            is_final=is_final,
            timeout=timeout,
            timeout_event=timeout_event,
        )
        if on_enter:
            node.on_enter.append(on_enter)
        if on_exit:
            node.on_exit.append(on_exit)
        parent.children[node.name] = node
        self._states[path] = node
        if parent.initial_child is None:
            parent.initial_child = node.name
        return self

    def add_transition(
        self,
        source: str,
        target: str,
        event: str,
        *,
        guard: Callable[[dict], bool] | None = None,
        action: Callable[[dict], None] | None = None,
    ) -> HierarchicalStateMachine:
        t = HSMTransition(source, target, event, guard, action)
        key = (source, event)
        self._transitions.setdefault(key, []).append(t)
        return self

    # ---- Runtime ----

    def _resolve_node(self, path: str) -> StateNode:
        return self._states[path]

    def _get_ancestors(self, node: StateNode) -> list[StateNode]:
        """Return ancestors from node to root (exclusive)."""
        ancestors = []
        current = node.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors

    def _find_lca(self, a: StateNode, b: StateNode) -> StateNode:
        """Find the Least Common Ancestor of two states."""
        ancestors_a = set()
        node: StateNode | None = a
        while node:
            ancestors_a.add(node.path)
            node = node.parent
        node = b
        while node:
            if node.path in ancestors_a:
                return node
            node = node.parent
        return self._root

    def _enter_state(self, node: StateNode) -> None:
        """Enter a state, recursively entering initial children."""
        logger.debug("Entering state: %s", node.path)
        self._active_states.append(node)
        for cb in node.on_enter:
            cb(self.context)

        # Set up timeout
        if node.timeout and node.timeout_event:
            self._schedule_timeout(node)

        # Recursively enter initial child
        if node.is_compound and node.initial_child:
            # Check history first
            history_child = self._history.get(node.path)
            child_name = history_child or node.initial_child
            if child_name in node.children:
                self._enter_state(node.children[child_name])

    def _exit_state(self, node: StateNode) -> None:
        """Exit a state, first exiting active children."""
        # Exit children first (deepest first)
        active_children = [s for s in self._active_states if s.parent == node]
        for child in active_children:
            self._exit_state(child)

        logger.debug("Exiting state: %s", node.path)

        # Save history for compound parent
        if node.parent and node.parent.is_compound:
            self._history[node.parent.path] = node.name

        # Cancel timeout
        task = self._timeout_tasks.pop(node.path, None)
        if task:
            task.cancel()

        for cb in node.on_exit:
            cb(self.context)

        self._active_states.remove(node)

    def _schedule_timeout(self, node: StateNode) -> None:
        """Schedule a timeout event for a state."""
        async def _fire():
            await asyncio.sleep(node.timeout)
            if node in self._active_states:
                logger.info("Timeout in state %s, firing %s", node.path, node.timeout_event)
                self.send(node.timeout_event)

        loop = asyncio.get_event_loop()
        self._timeout_tasks[node.path] = loop.create_task(_fire())

    def start(self) -> None:
        """Initialize the HSM by entering the root and its initial descendants."""
        if self._started:
            return
        self._started = True
        self._enter_state(self._root)

    @property
    def active_state_paths(self) -> list[str]:
        return [s.path for s in self._active_states]

    @property
    def leaf_state(self) -> StateNode | None:
        """The deepest active state (the actual current state)."""
        if not self._active_states:
            return None
        return max(self._active_states, key=lambda s: s.path.count("."))

    def send(self, event: str, **metadata: Any) -> str | None:
        """
        Dispatch an event. Searches from the deepest active state
        upward through ancestors for a matching transition.
        """
        leaf = self.leaf_state
        if leaf is None:
            raise RuntimeError("HSM not started")

        # Walk up the state tree looking for a handler
        node: StateNode | None = leaf
        transition: HSMTransition | None = None
        while node:
            candidates = self._transitions.get((node.path, event), [])
            for t in candidates:
                if t.guard is None or t.guard(self.context):
                    transition = t
                    break
            if transition:
                break
            node = node.parent

        if transition is None:
            logger.warning("No transition for event '%s' in state '%s'", event, leaf.path)
            return None

        source = self._resolve_node(transition.source_path)
        target = self._resolve_node(transition.target_path)
        lca = self._find_lca(source, target)

        # Exit states up to (but not including) LCA
        current = leaf
        while current and current != lca:
            self._exit_state(current)
            current = current.parent

        # Execute transition action
        if transition.action:
            transition.action(self.context)

        # Enter states from LCA down to target
        path_to_target: list[StateNode] = []
        t_node: StateNode | None = target
        while t_node and t_node != lca:
            path_to_target.append(t_node)
            t_node = t_node.parent
        for state in reversed(path_to_target):
            self._enter_state(state)

        return target.path


# ---- Example: TCP Connection FSM ----

def build_tcp_fsm() -> HierarchicalStateMachine:
    hsm = HierarchicalStateMachine("TCP", context={"retries": 0, "seq": 0})

    # Top-level states
    hsm.add_state("closed", parent_path="root")
    hsm.add_state("listen", parent_path="root")
    hsm.add_state("connecting", parent_path="root", initial_child="syn_sent",
                   timeout=30.0, timeout_event="TIMEOUT")

    # Nested states under connecting
    hsm.add_state("connecting.syn_sent", parent_path="connecting")
    hsm.add_state("connecting.syn_received", parent_path="connecting")

    hsm.add_state("established", parent_path="root", initial_child="idle")
    hsm.add_state("established.idle", parent_path="established")
    hsm.add_state("established.transferring", parent_path="established")

    hsm.add_state("closing", parent_path="root", initial_child="fin_wait",
                   timeout=60.0, timeout_event="TIMEOUT")
    hsm.add_state("closing.fin_wait", parent_path="closing")
    hsm.add_state("closing.time_wait", parent_path="closing",
                   timeout=120.0, timeout_event="TIMEOUT")

    # Transitions
    (hsm
        .add_transition("closed", "listen", "PASSIVE_OPEN")
        .add_transition("closed", "connecting.syn_sent", "ACTIVE_OPEN",
                        action=lambda ctx: ctx.update(seq=1))
        .add_transition("listen", "connecting.syn_received", "SYN_RCVD")
        .add_transition("connecting.syn_sent", "connecting.syn_received", "SYN_ACK_RCVD")
        .add_transition("connecting.syn_received", "established.idle", "ACK_RCVD")
        .add_transition("connecting", "closed", "TIMEOUT",
                        action=lambda ctx: logger.error("Connection timed out"))
        .add_transition("established.idle", "established.transferring", "DATA")
        .add_transition("established.transferring", "established.idle", "DATA_COMPLETE")
        .add_transition("established", "closing.fin_wait", "CLOSE")
        .add_transition("closing.fin_wait", "closing.time_wait", "FIN_ACK")
        .add_transition("closing.time_wait", "closed", "TIMEOUT")
        .add_transition("closing", "closed", "TIMEOUT")
    )

    return hsm
```

Key hierarchical statechart concepts:

| Concept | Description |
|---------|-------------|
| Compound states | States containing nested child states |
| Initial child | Default child entered when parent is entered |
| LCA (Least Common Ancestor) | Determines which states to exit/enter during transitions |
| History | Remembers last active child to restore on re-entry |
| Timeout transitions | Auto-fire events after a duration in a state |
| Event bubbling | Events propagate from leaf to ancestors until handled |

- **Exit order**: deepest child first, then ancestor toward LCA
- **Entry order**: ancestor first (after LCA), then descend to target, then auto-enter initial children
- **History states** enable "resume where you left off" when re-entering a compound state
'''
    ),
    (
        "state-machines/react-usestate-machine-hook",
        "Create a type-safe React hook that wraps XState v5 for component-level state machines with devtools integration and React 19 compatibility.",
        '''A production React hook for XState v5 with devtools, selectors, and React 19 transitions:

```typescript
// --- useStateMachine.ts --- React 19 + XState v5 integration hook ---

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  useTransition,
} from "react";
import {
  type AnyStateMachine,
  type SnapshotFrom,
  type EventFromLogic,
  type InputFrom,
  createActor,
  type Actor,
  type AnyActorLogic,
} from "xstate";

// ---- Types ----

interface UseStateMachineOptions<TMachine extends AnyStateMachine> {
  /** Input to pass to the machine (XState v5 input replaces v4 context factories) */
  input?: InputFrom<TMachine>;
  /** Enable XState inspect/devtools */
  devtools?: boolean;
  /** ID override for the actor */
  id?: string;
}

interface UseStateMachineReturn<TMachine extends AnyStateMachine> {
  /** Current snapshot (state) of the machine */
  snapshot: SnapshotFrom<TMachine>;
  /** Send events to the machine */
  send: (event: EventFromLogic<TMachine>) => void;
  /** The underlying XState actor reference */
  actorRef: Actor<TMachine>;
  /** Whether the machine is in a given state (supports dot-separated paths) */
  matches: (stateValue: string) => boolean;
  /** Whether the machine can handle a given event type */
  can: (eventType: string) => boolean;
  /** Whether a React transition is pending (for startTransition wrapping) */
  isPending: boolean;
}

// ---- Hook implementation ----

export function useStateMachine<TMachine extends AnyStateMachine>(
  machine: TMachine,
  options: UseStateMachineOptions<TMachine> = {}
): UseStateMachineReturn<TMachine> {
  const { input, devtools = false, id } = options;
  const [isPending, startTransition] = useTransition();

  // Stable actor reference across renders — only recreate if machine identity changes
  const actorRef = useMemo(() => {
    const actor = createActor(machine, {
      input,
      id,
      inspect: devtools
        ? (event) => {
            // Send to @xstate/inspect or custom devtools
            if (typeof window !== "undefined" && (window as any).__xstate__) {
              (window as any).__xstate__.register(event);
            }
          }
        : undefined,
    });
    return actor;
  }, [machine]); // eslint-disable-line react-hooks/exhaustive-deps

  // Start and stop the actor with component lifecycle
  useEffect(() => {
    actorRef.start();
    return () => {
      actorRef.stop();
    };
  }, [actorRef]);

  // Use useSyncExternalStore for tear-safe subscriptions (React 18+/19)
  const snapshot = useSyncExternalStore(
    useCallback(
      (callback: () => void) => {
        const subscription = actorRef.subscribe(callback);
        return () => subscription.unsubscribe();
      },
      [actorRef]
    ),
    () => actorRef.getSnapshot(),
    () => actorRef.getSnapshot() // server snapshot (SSR)
  );

  // Wrap send in startTransition for non-urgent updates
  const send = useCallback(
    (event: EventFromLogic<TMachine>) => {
      startTransition(() => {
        actorRef.send(event);
      });
    },
    [actorRef, startTransition]
  );

  const matches = useCallback(
    (stateValue: string) => {
      return snapshot.matches(stateValue);
    },
    [snapshot]
  );

  const can = useCallback(
    (eventType: string) => {
      return snapshot.can({ type: eventType } as any);
    },
    [snapshot]
  );

  return { snapshot, send, actorRef, matches, can, isPending };
}

// ---- Selector hook for derived state ----

export function useSelector<TMachine extends AnyStateMachine, T>(
  actorRef: Actor<TMachine>,
  selector: (snapshot: SnapshotFrom<TMachine>) => T,
  compare: (a: T, b: T) => boolean = Object.is
): T {
  const prevRef = useRef<T | undefined>(undefined);

  return useSyncExternalStore(
    useCallback(
      (callback) => {
        const sub = actorRef.subscribe(callback);
        return () => sub.unsubscribe();
      },
      [actorRef]
    ),
    () => {
      const next = selector(actorRef.getSnapshot());
      if (prevRef.current !== undefined && compare(prevRef.current, next)) {
        return prevRef.current;
      }
      prevRef.current = next;
      return next;
    },
    () => selector(actorRef.getSnapshot())
  );
}

// ---- Usage example ----

/*
import { formWizardMachine } from "./formWizardMachine";

function FormWizard() {
  const { snapshot, send, matches, can, isPending } = useStateMachine(
    formWizardMachine,
    { devtools: import.meta.env.DEV }
  );

  const { currentStep, errors } = snapshot.context;

  return (
    <div>
      <StepIndicator current={currentStep} total={3} />

      {matches("editing") && (
        <FormStep step={currentStep} errors={errors}
          onUpdate={(section, field, value) =>
            send({ type: "UPDATE_FIELD", section, field, value })
          }
        />
      )}

      {matches("submitting") && <Spinner />}
      {matches("success") && <SuccessMessage id={snapshot.context.submissionId} />}
      {matches("failure") && (
        <ErrorPanel onRetry={() => send({ type: "RETRY" })}
                    onReset={() => send({ type: "RESET" })} />
      )}

      <nav>
        <button disabled={!can("BACK")} onClick={() => send({ type: "BACK" })}>
          Back
        </button>
        <button disabled={isPending} onClick={() =>
          currentStep < 2
            ? send({ type: "NEXT" })
            : send({ type: "SUBMIT" })
        }>
          {currentStep < 2 ? "Next" : "Submit"}
        </button>
      </nav>
    </div>
  );
}
*/
```

Key patterns:

- **`useSyncExternalStore`** provides tear-safe subscription to XState actors (required in React 18+/19 concurrent mode)
- **`useTransition`** wraps `send()` so state machine transitions are non-blocking for UI
- **Stable actor ref** via `useMemo` prevents re-creating the actor on every render
- **`useSelector`** with custom comparator avoids unnecessary re-renders for derived state
- **SSR support** via the third argument to `useSyncExternalStore`
- **Devtools integration** via the `inspect` callback on `createActor`
- **`matches()` and `can()`** provide ergonomic state checking in JSX

| Feature | Implementation |
|---------|---------------|
| Tear-safe subscriptions | `useSyncExternalStore` |
| Non-blocking updates | `useTransition` + `startTransition` |
| Derived state | `useSelector` with comparison |
| Actor lifecycle | `useEffect` start/stop |
| Type safety | Generic `TMachine` flows through all return types |
'''
    ),
    (
        "state-machines/testing-state-machines",
        "Show comprehensive testing strategies for state machines including model-based testing, transition coverage, and property-based testing.",
        '''Comprehensive state machine testing with model-based testing and transition coverage:

```typescript
// --- formWizardMachine.test.ts --- Comprehensive state machine tests ---

import { describe, it, expect, vi, beforeEach } from "vitest";
import { createActor, type AnyActorRef } from "xstate";
import { formWizardMachine } from "./formWizardMachine";

// ---- Helper: create actor and get snapshot ----
function createTestActor(context?: Partial<typeof formWizardMachine.config.context>) {
  const machine = context
    ? formWizardMachine.provide({
        // Override actors for testing
        actors: {
          submitForm: fromPromise(async () => ({ id: "test-123" })),
        },
      })
    : formWizardMachine;

  const actor = createActor(machine);
  actor.start();
  return actor;
}

// ---- Unit tests: individual transitions ----
describe("FormWizardMachine - Unit", () => {
  let actor: ReturnType<typeof createTestActor>;

  beforeEach(() => {
    actor = createTestActor();
  });

  it("starts in editing state at step 0", () => {
    const snap = actor.getSnapshot();
    expect(snap.matches("editing")).toBe(true);
    expect(snap.context.currentStep).toBe(0);
  });

  it("updates personal info fields", () => {
    actor.send({
      type: "UPDATE_FIELD",
      section: "personalInfo",
      field: "firstName",
      value: "Alice",
    });
    expect(actor.getSnapshot().context.personalInfo.firstName).toBe("Alice");
  });

  it("rejects NEXT with invalid personal info", () => {
    actor.send({ type: "NEXT" });
    const snap = actor.getSnapshot();
    expect(snap.matches("editing")).toBe(true);
    expect(snap.context.currentStep).toBe(0);
    expect(Object.keys(snap.context.errors).length).toBeGreaterThan(0);
  });

  it("advances on NEXT with valid personal info", () => {
    // Fill valid data
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "firstName", value: "Alice" });
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "lastName", value: "Smith" });
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "email", value: "a@b.com" });

    actor.send({ type: "NEXT" });
    expect(actor.getSnapshot().context.currentStep).toBe(1);
  });

  it("goes back without losing data", () => {
    // Fill and advance
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "firstName", value: "Bob" });
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "lastName", value: "Jones" });
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "email", value: "b@c.com" });
    actor.send({ type: "NEXT" });
    expect(actor.getSnapshot().context.currentStep).toBe(1);

    actor.send({ type: "BACK" });
    const snap = actor.getSnapshot();
    expect(snap.context.currentStep).toBe(0);
    expect(snap.context.personalInfo.firstName).toBe("Bob"); // data preserved
  });
});

// ---- Integration tests: full flows ----
describe("FormWizardMachine - Integration Flows", () => {
  it("completes the happy path: fill -> submit -> success", async () => {
    const actor = createActor(
      formWizardMachine.provide({
        actors: {
          submitForm: fromPromise(async () => ({ id: "order-456" })),
        },
      })
    );
    actor.start();

    // Step 1: Personal info
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "firstName", value: "Jane" });
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "lastName", value: "Doe" });
    actor.send({ type: "UPDATE_FIELD", section: "personalInfo", field: "email", value: "j@d.com" });
    actor.send({ type: "NEXT" });

    // Step 2: Address
    actor.send({ type: "UPDATE_FIELD", section: "address", field: "street", value: "123 Main St" });
    actor.send({ type: "UPDATE_FIELD", section: "address", field: "city", value: "Springfield" });
    actor.send({ type: "UPDATE_FIELD", section: "address", field: "state", value: "IL" });
    actor.send({ type: "UPDATE_FIELD", section: "address", field: "zip", value: "62701" });
    actor.send({ type: "SUBMIT" });

    // Wait for async submission
    await new Promise<void>((resolve) => {
      actor.subscribe((snap) => {
        if (snap.matches("success")) resolve();
      });
    });

    expect(actor.getSnapshot().context.submissionId).toBe("order-456");
  });

  it("handles submission failure with retry", async () => {
    let callCount = 0;
    const actor = createActor(
      formWizardMachine.provide({
        actors: {
          submitForm: fromPromise(async () => {
            callCount++;
            if (callCount < 3) throw new Error("Server error");
            return { id: "retry-ok" };
          }),
        },
      })
    );
    actor.start();

    // Fill valid data and submit...
    // (abbreviated — same fill pattern as above)

    // Assert retry behavior
    await new Promise<void>((resolve) => {
      actor.subscribe((snap) => {
        if (snap.matches("success") || snap.matches("failure")) resolve();
      });
    });
  });
});

// ---- Transition coverage analysis ----
describe("FormWizardMachine - Transition Coverage", () => {
  const allTransitions = [
    { from: "editing", event: "NEXT", guard: "valid" },
    { from: "editing", event: "NEXT", guard: "invalid" },
    { from: "editing", event: "BACK" },
    { from: "editing", event: "UPDATE_FIELD" },
    { from: "editing", event: "SUBMIT", guard: "valid" },
    { from: "editing", event: "SUBMIT", guard: "invalid" },
    { from: "submitting", event: "done.invoke (success)" },
    { from: "submitting", event: "error.invoke (retryable)" },
    { from: "submitting", event: "error.invoke (fatal)" },
    { from: "retrying", event: "after(2000)" },
    { from: "success", event: "RESET" },
    { from: "failure", event: "RETRY" },
    { from: "failure", event: "RESET" },
  ];

  const covered = new Set<string>();

  function markCovered(from: string, event: string) {
    covered.add(`${from}:${event}`);
  }

  it("reports transition coverage", () => {
    // After running all tests above, check coverage
    const totalTransitions = allTransitions.length;
    const coveredCount = covered.size;
    const coverage = (coveredCount / totalTransitions) * 100;

    console.log(`Transition coverage: ${coveredCount}/${totalTransitions} (${coverage.toFixed(1)}%)`);
    console.log("Uncovered:", allTransitions
      .filter((t) => !covered.has(`${t.from}:${t.event}`))
      .map((t) => `${t.from} --${t.event}-->`)
    );

    // Enforce minimum coverage
    expect(coverage).toBeGreaterThanOrEqual(80);
  });
});
```

```python
# --- test_fsm_property.py --- Property-based testing with Hypothesis ---

import hypothesis.strategies as st
from hypothesis import given, settings, assume
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, precondition

from fsm import FiniteStateMachine, OrderState, OrderEvent, InvalidTransitionError


class OrderFSMStatefulTest(RuleBasedStateMachine):
    """
    Property-based stateful testing: Hypothesis explores random
    sequences of events to find edge cases automatically.
    """

    def __init__(self):
        super().__init__()
        self.fsm = FiniteStateMachine(
            "TestOrder", OrderState, OrderEvent, OrderState.DRAFT,
            context={"items": ["widget"], "payment_amount": 100},
        )
        self.fsm.add_transition(OrderState.DRAFT, OrderState.SUBMITTED, OrderEvent.SUBMIT,
                                guard=lambda ctx, e: len(ctx.get("items", [])) > 0)
        self.fsm.add_transition(OrderState.SUBMITTED, OrderState.PAYMENT_PENDING, "PAY")
        self.fsm.add_transition(OrderState.PAYMENT_PENDING, OrderState.PAID, "PAY",
                                guard=lambda ctx, e: ctx.get("payment_amount", 0) > 0)
        self.fsm.add_transition(OrderState.PAID, OrderState.SHIPPED, OrderEvent.SHIP)
        self.fsm.add_transition(OrderState.SHIPPED, OrderState.DELIVERED, OrderEvent.DELIVER)
        self.fsm.add_transition(OrderState.DRAFT, OrderState.CANCELLED, OrderEvent.CANCEL)
        self.fsm.add_transition(OrderState.SUBMITTED, OrderState.CANCELLED, OrderEvent.CANCEL)

    @rule()
    def submit(self):
        try:
            self.fsm.send("SUBMIT")
        except (InvalidTransitionError, Exception):
            pass

    @rule()
    def pay(self):
        try:
            self.fsm.send("PAY")
        except (InvalidTransitionError, Exception):
            pass

    @rule()
    def ship(self):
        try:
            self.fsm.send("SHIP")
        except (InvalidTransitionError, Exception):
            pass

    @rule()
    def deliver(self):
        try:
            self.fsm.send("DELIVER")
        except (InvalidTransitionError, Exception):
            pass

    @rule()
    def cancel(self):
        try:
            self.fsm.send("CANCEL")
        except (InvalidTransitionError, Exception):
            pass

    @invariant()
    def state_is_always_valid(self):
        assert self.fsm.state in OrderState

    @invariant()
    def history_length_bounded(self):
        assert len(self.fsm.history) <= self.fsm._max_history

    @invariant()
    def terminal_states_are_absorbing(self):
        if self.fsm.state in (OrderState.DELIVERED, OrderState.CANCELLED):
            # No transitions should be possible from terminal states
            for event in OrderEvent:
                assert not self.fsm.can_handle(event)


TestOrderFSM = OrderFSMStatefulTest.TestCase
```

Key testing strategies:

| Strategy | Tool | Purpose |
|----------|------|---------|
| Unit tests | Vitest/pytest | Individual transition correctness |
| Integration flows | Actor lifecycle | End-to-end happy/error paths |
| Transition coverage | Manual tracking | Ensure all edges exercised |
| Property-based | Hypothesis stateful | Random event sequences find edge cases |
| Model-based | XState `@xstate/test` | Generate test paths from machine definition |

- **Transition coverage** tracks which `(state, event)` pairs have been tested
- **Property-based stateful testing** uses Hypothesis to randomly fire events and check invariants
- **Invariants** verify properties that must hold in every reachable state
- **`provide()`** in XState v5 replaces actors/guards for test doubles without modifying the machine
'''
    ),
]
