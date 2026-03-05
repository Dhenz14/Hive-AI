"""Game development patterns — ECS architecture, game loop, spatial partitioning, AI state machines, networking."""

PAIRS = [
    (
        "gamedev/entity-component-system",
        "Implement an Entity-Component-System (ECS) architecture in Python with sparse component storage, system iteration with component queries, entity archetypes, and event dispatch for a 2D game engine.",
        '''Entity-Component-System architecture with sparse storage, queries, and events:

```python
# ecs.py — Full ECS framework for 2D game development
from __future__ import annotations
import time
import logging
from typing import Any, TypeVar, Type, Iterator
from dataclasses import dataclass, field
from collections import defaultdict
from weakref import WeakSet

logger = logging.getLogger(__name__)

T = TypeVar("T")
Entity = int  # Entity is just an integer ID


# ---- Components: Pure data, no behavior ----

@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0

@dataclass
class Velocity:
    dx: float = 0.0
    dy: float = 0.0

@dataclass
class Sprite:
    texture: str = ""
    width: int = 32
    height: int = 32
    layer: int = 0

@dataclass
class Health:
    current: int = 100
    maximum: int = 100

    @property
    def ratio(self) -> float:
        return self.current / max(self.maximum, 1)

@dataclass
class Collider:
    radius: float = 16.0
    is_trigger: bool = False
    layer_mask: int = 0xFFFF

@dataclass
class AIController:
    state: str = "idle"
    target_entity: Entity | None = None
    detection_range: float = 200.0

@dataclass
class PlayerInput:
    move_x: float = 0.0
    move_y: float = 0.0
    fire: bool = False


# ---- Sparse Component Storage ----

class ComponentStore:
    """Sparse storage for a single component type using a dict (entity -> component).

    This is the sparse-set approach: memory-efficient when most entities
    do not have a given component, O(1) add/remove/lookup.
    """
    def __init__(self, component_type: type):
        self.component_type = component_type
        self._data: dict[Entity, Any] = {}

    def add(self, entity: Entity, component: Any) -> None:
        self._data[entity] = component

    def remove(self, entity: Entity) -> Any | None:
        return self._data.pop(entity, None)

    def get(self, entity: Entity) -> Any | None:
        return self._data.get(entity)

    def has(self, entity: Entity) -> bool:
        return entity in self._data

    def entities(self) -> set[Entity]:
        return set(self._data.keys())

    def items(self) -> Iterator[tuple[Entity, Any]]:
        return iter(self._data.items())

    def __len__(self) -> int:
        return len(self._data)


# ---- Event System ----

@dataclass
class Event:
    """Base event class. Subclass for specific events."""
    pass

@dataclass
class CollisionEvent(Event):
    entity_a: Entity
    entity_b: Entity
    overlap: float = 0.0

@dataclass
class DamageEvent(Event):
    target: Entity
    amount: int = 0
    source: Entity | None = None

@dataclass
class EntityDestroyedEvent(Event):
    entity: Entity

EventHandler = type[Event]

class EventBus:
    """Publish-subscribe event dispatcher for decoupled system communication."""

    def __init__(self):
        self._handlers: dict[type, list[callable]] = defaultdict(list)
        self._queue: list[Event] = []

    def subscribe(self, event_type: type[Event], handler: callable):
        self._handlers[event_type].append(handler)

    def publish(self, event: Event):
        """Queue event for deferred processing (avoids mutation during iteration)."""
        self._queue.append(event)

    def dispatch(self):
        """Process all queued events. Call once per frame after all systems run."""
        while self._queue:
            event = self._queue.pop(0)
            for handler in self._handlers.get(type(event), []):
                handler(event)


# ---- World: Manages entities, components, and systems ----

class World:
    """Central ECS world — owns all entities, component stores, and systems."""

    def __init__(self):
        self._next_entity: Entity = 1
        self._alive: set[Entity] = set()
        self._stores: dict[type, ComponentStore] = {}
        self._systems: list[System] = []
        self._destroy_queue: list[Entity] = []
        self.events = EventBus()
        self.dt: float = 0.0  # Delta time, set each frame

    def create_entity(self, *components: Any) -> Entity:
        """Create entity and attach components in one call."""
        eid = self._next_entity
        self._next_entity += 1
        self._alive.add(eid)
        for comp in components:
            self.add_component(eid, comp)
        return eid

    def destroy_entity(self, entity: Entity):
        """Queue entity for end-of-frame destruction."""
        self._destroy_queue.append(entity)

    def _flush_destroys(self):
        for entity in self._destroy_queue:
            if entity in self._alive:
                self._alive.discard(entity)
                for store in self._stores.values():
                    store.remove(entity)
                self.events.publish(EntityDestroyedEvent(entity=entity))
        self._destroy_queue.clear()

    def add_component(self, entity: Entity, component: Any):
        comp_type = type(component)
        if comp_type not in self._stores:
            self._stores[comp_type] = ComponentStore(comp_type)
        self._stores[comp_type].add(entity, component)

    def remove_component(self, entity: Entity, comp_type: type):
        store = self._stores.get(comp_type)
        if store:
            store.remove(entity)

    def get_component(self, entity: Entity, comp_type: Type[T]) -> T | None:
        store = self._stores.get(comp_type)
        return store.get(entity) if store else None

    def has_component(self, entity: Entity, comp_type: type) -> bool:
        store = self._stores.get(comp_type)
        return store.has(entity) if store else False

    def query(self, *comp_types: type) -> Iterator[tuple[Entity, ...]]:
        """Iterate entities that have ALL specified component types.

        Yields (entity, comp1, comp2, ...) tuples.

        Uses intersection of entity sets for efficient filtering.
        """
        if not comp_types:
            return

        stores = [self._stores.get(ct) for ct in comp_types]
        if any(s is None for s in stores):
            return

        # Start with smallest set for optimal intersection
        sorted_stores = sorted(stores, key=len)
        candidates = sorted_stores[0].entities()
        for store in sorted_stores[1:]:
            candidates = candidates & store.entities()

        for entity in candidates:
            components = tuple(store.get(entity) for store in stores)
            yield (entity, *components)

    def add_system(self, system: System):
        self._systems.append(system)
        self._systems.sort(key=lambda s: s.priority)
        system.world = self

    def update(self, dt: float):
        """Run all systems, dispatch events, flush destroys."""
        self.dt = dt
        for system in self._systems:
            if system.enabled:
                system.update(dt)
        self.events.dispatch()
        self._flush_destroys()


# ---- System base class ----

class System:
    """Base class for all ECS systems. Override update() with game logic."""
    priority: int = 0      # Lower runs first
    enabled: bool = True
    world: World = None    # Set when added to world

    def update(self, dt: float):
        raise NotImplementedError


# ---- Concrete Systems ----

class MovementSystem(System):
    """Applies velocity to position for all entities with both components."""
    priority = 10

    def update(self, dt: float):
        for entity, pos, vel in self.world.query(Position, Velocity):
            pos.x += vel.dx * dt
            pos.y += vel.dy * dt


class CollisionSystem(System):
    """Brute-force circle-circle collision detection."""
    priority = 20

    def update(self, dt: float):
        entities = list(self.world.query(Position, Collider))
        for i in range(len(entities)):
            e1, p1, c1 = entities[i]
            for j in range(i + 1, len(entities)):
                e2, p2, c2 = entities[j]
                dx = p1.x - p2.x
                dy = p1.y - p2.y
                dist_sq = dx * dx + dy * dy
                min_dist = c1.radius + c2.radius
                if dist_sq < min_dist * min_dist:
                    overlap = min_dist - dist_sq ** 0.5
                    self.world.events.publish(
                        CollisionEvent(entity_a=e1, entity_b=e2, overlap=overlap)
                    )


class HealthSystem(System):
    """Processes damage events and destroys dead entities."""
    priority = 50

    def __init__(self):
        super().__init__()
        self._initialized = False

    def update(self, dt: float):
        if not self._initialized:
            self.world.events.subscribe(DamageEvent, self._on_damage)
            self._initialized = True

        for entity, health in self.world.query(Health):
            if health.current <= 0:
                self.world.destroy_entity(entity)

    def _on_damage(self, event: DamageEvent):
        health = self.world.get_component(event.target, Health)
        if health:
            health.current = max(0, health.current - event.amount)


class PlayerInputSystem(System):
    """Translates player input into velocity."""
    priority = 5
    SPEED = 200.0

    def update(self, dt: float):
        for entity, inp, vel in self.world.query(PlayerInput, Velocity):
            vel.dx = inp.move_x * self.SPEED
            vel.dy = inp.move_y * self.SPEED


# ---- Entity Archetypes (prefabs) ----

class Archetypes:
    """Factory methods for common entity configurations."""

    @staticmethod
    def player(world: World, x: float, y: float) -> Entity:
        return world.create_entity(
            Position(x, y),
            Velocity(),
            Sprite(texture="player.png", layer=10),
            Health(current=100, maximum=100),
            Collider(radius=16),
            PlayerInput(),
        )

    @staticmethod
    def enemy(world: World, x: float, y: float) -> Entity:
        return world.create_entity(
            Position(x, y),
            Velocity(),
            Sprite(texture="enemy.png", layer=10),
            Health(current=50, maximum=50),
            Collider(radius=12),
            AIController(state="patrol", detection_range=150),
        )

    @staticmethod
    def bullet(world: World, x: float, y: float, dx: float, dy: float) -> Entity:
        return world.create_entity(
            Position(x, y),
            Velocity(dx, dy),
            Sprite(texture="bullet.png", width=8, height=8, layer=20),
            Collider(radius=4, is_trigger=True),
        )


# ---- Main game setup ----

def create_game() -> World:
    world = World()
    world.add_system(PlayerInputSystem())
    world.add_system(MovementSystem())
    world.add_system(CollisionSystem())
    world.add_system(HealthSystem())

    Archetypes.player(world, 400, 300)
    for i in range(10):
        Archetypes.enemy(world, 100 + i * 80, 100)

    return world
```

| ECS Approach | Storage | Query Speed | Memory | Best For |
|---|---|---|---|---|
| Sparse set (dict) | dict[Entity, Component] | O(N) intersect | Low when sparse | General purpose, Python |
| Dense array | Component[] + entity mapping | O(N) iterate | Lowest per entity | C++/Rust, cache-friendly |
| Archetype table | Components grouped by archetype | O(1) per archetype | Medium | Unity DOTS, Bevy |
| Bitset queries | Bitmask per entity for components | O(1) has-check | Fixed overhead | Many component types |

Key ECS patterns:
- Components are pure data with no methods (Position, Velocity, Health)
- Systems contain all logic, iterating entities that match component queries
- Entity destruction is deferred to end-of-frame to avoid iterator invalidation
- Event bus decouples systems (CollisionSystem publishes, HealthSystem subscribes)
- Archetypes are factory functions that create entities with preset components
- Query intersection starts with the smallest component set for efficiency
'''
    ),
    (
        "gamedev/game-loop",
        "Implement a fixed-timestep game loop with interpolation for smooth rendering, frame timing, performance monitoring, and graceful handling of spiral-of-death scenarios.",
        '''Fixed-timestep game loop with interpolation and performance monitoring:

```python
# game_loop.py — Production game loop with fixed physics and interpolated rendering
import time
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import Protocol

logger = logging.getLogger(__name__)


class GameState(Protocol):
    """Interface for the game state that the loop manages."""

    def fixed_update(self, dt: float) -> None:
        """Physics and game logic at fixed timestep."""
        ...

    def update(self, dt: float) -> None:
        """Variable-rate update (input, animation, audio)."""
        ...

    def render(self, alpha: float) -> None:
        """Render with interpolation factor (0.0 to 1.0)."""
        ...


@dataclass
class FrameStats:
    """Per-frame performance metrics."""
    frame_time_ms: float = 0.0
    update_time_ms: float = 0.0
    render_time_ms: float = 0.0
    physics_steps: int = 0
    fps: float = 0.0


@dataclass
class PerformanceMonitor:
    """Tracks frame timing statistics over a rolling window."""
    window_size: int = 120  # ~2 seconds at 60fps
    _frame_times: deque = field(default_factory=deque)
    _worst_frame: float = 0.0
    _total_frames: int = 0

    def record_frame(self, frame_time_ms: float):
        self._frame_times.append(frame_time_ms)
        if len(self._frame_times) > self.window_size:
            self._frame_times.popleft()
        self._worst_frame = max(self._worst_frame, frame_time_ms)
        self._total_frames += 1

    @property
    def avg_fps(self) -> float:
        if not self._frame_times:
            return 0.0
        avg_ms = sum(self._frame_times) / len(self._frame_times)
        return 1000.0 / max(avg_ms, 0.001)

    @property
    def avg_frame_ms(self) -> float:
        if not self._frame_times:
            return 0.0
        return sum(self._frame_times) / len(self._frame_times)

    @property
    def p99_frame_ms(self) -> float:
        if not self._frame_times:
            return 0.0
        sorted_times = sorted(self._frame_times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    @property
    def worst_frame_ms(self) -> float:
        return self._worst_frame

    def summary(self) -> str:
        return (
            f"FPS: {self.avg_fps:.1f} | "
            f"Avg: {self.avg_frame_ms:.2f}ms | "
            f"P99: {self.p99_frame_ms:.2f}ms | "
            f"Worst: {self._worst_frame:.2f}ms | "
            f"Frames: {self._total_frames}"
        )


class GameLoop:
    """Fixed-timestep game loop with rendering interpolation.

    Physics runs at a fixed rate (e.g., 60Hz) regardless of frame rate.
    Rendering uses interpolation between the last two physics states
    for smooth visuals even when the display rate differs from physics rate.

    Handles spiral-of-death by capping accumulated time per frame.
    """

    def __init__(
        self,
        fixed_dt: float = 1.0 / 60.0,     # Physics at 60Hz
        max_frame_time: float = 0.25,       # Cap at 250ms (4 FPS minimum)
        max_physics_steps: int = 5,          # Max physics steps per frame
        target_fps: float | None = None,     # None = uncapped
    ):
        self.fixed_dt = fixed_dt
        self.max_frame_time = max_frame_time
        self.max_physics_steps = max_physics_steps
        self.target_fps = target_fps
        self.min_frame_time = 1.0 / target_fps if target_fps else 0.0
        self.running = False
        self.monitor = PerformanceMonitor()

    def run(self, game: GameState):
        """Main game loop — blocks until stopped."""
        self.running = True

        current_time = time.perf_counter()
        accumulator = 0.0
        frame_count = 0

        logger.info(
            f"Game loop started: physics={1/self.fixed_dt:.0f}Hz, "
            f"target_fps={self.target_fps or 'uncapped'}"
        )

        while self.running:
            new_time = time.perf_counter()
            frame_time = new_time - current_time
            current_time = new_time

            # Spiral-of-death protection: cap accumulated time
            # Without this, a long frame causes more physics steps,
            # which causes an even longer frame, creating a death spiral.
            if frame_time > self.max_frame_time:
                logger.warning(
                    f"Frame took {frame_time*1000:.1f}ms, "
                    f"capping to {self.max_frame_time*1000:.1f}ms"
                )
                frame_time = self.max_frame_time

            accumulator += frame_time

            # --- Variable-rate update (input, animation) ---
            update_start = time.perf_counter()
            game.update(frame_time)

            # --- Fixed-timestep physics ---
            physics_steps = 0
            while accumulator >= self.fixed_dt and physics_steps < self.max_physics_steps:
                game.fixed_update(self.fixed_dt)
                accumulator -= self.fixed_dt
                physics_steps += 1

            update_end = time.perf_counter()

            # --- Render with interpolation ---
            # Alpha represents how far we are between the last two physics frames.
            # Renderer uses this to interpolate positions for smooth visuals.
            alpha = accumulator / self.fixed_dt

            render_start = time.perf_counter()
            game.render(alpha)
            render_end = time.perf_counter()

            # --- Frame timing ---
            total_frame_ms = (render_end - (new_time)) * 1000
            self.monitor.record_frame(total_frame_ms)

            # Frame rate limiting (if target_fps is set)
            if self.min_frame_time > 0:
                elapsed = time.perf_counter() - current_time + frame_time
                sleep_time = self.min_frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            frame_count += 1
            if frame_count % 300 == 0:
                logger.info(self.monitor.summary())

    def stop(self):
        self.running = False


# ---- Example usage with interpolated rendering ----

@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0

class InterpolatedTransform:
    """Stores previous and current position for render interpolation."""

    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.previous = Vec2(x, y)
        self.current = Vec2(x, y)

    def save_state(self):
        """Call before physics update to save current as previous."""
        self.previous.x = self.current.x
        self.previous.y = self.current.y

    def interpolated(self, alpha: float) -> Vec2:
        """Linearly interpolate between previous and current state."""
        return Vec2(
            x=self.previous.x + (self.current.x - self.previous.x) * alpha,
            y=self.previous.y + (self.current.y - self.previous.y) * alpha,
        )


class ExampleGame:
    """Minimal game demonstrating the fixed-timestep loop."""

    def __init__(self):
        self.player = InterpolatedTransform(400, 300)
        self.player_speed = 200.0  # pixels/sec
        self.move_dir = Vec2(1, 0)

    def update(self, dt: float):
        """Process input, animations (variable rate)."""
        pass  # Input polling would go here

    def fixed_update(self, dt: float):
        """Physics step at fixed rate."""
        self.player.save_state()
        self.player.current.x += self.move_dir.x * self.player_speed * dt
        self.player.current.y += self.move_dir.y * self.player_speed * dt

        # Bounce off screen edges
        if self.player.current.x > 800 or self.player.current.x < 0:
            self.move_dir.x *= -1
        if self.player.current.y > 600 or self.player.current.y < 0:
            self.move_dir.y *= -1

    def render(self, alpha: float):
        """Render using interpolated position."""
        pos = self.player.interpolated(alpha)
        # draw_sprite("player.png", pos.x, pos.y)  # <- actual rendering call


if __name__ == "__main__":
    loop = GameLoop(fixed_dt=1/60, target_fps=60)
    game = ExampleGame()
    loop.run(game)
```

| Timestep Model | Pros | Cons | Use Case |
|---|---|---|---|
| Variable dt | Simple, smooth visuals | Non-deterministic physics | Simple animations |
| Fixed dt (no interp) | Deterministic physics | Visual stuttering | Networked games |
| Fixed dt + interpolation | Deterministic + smooth | Slight complexity | Production games |
| Semi-fixed dt | Compromise | Neither fully smooth nor deterministic | Prototyping |

Critical game loop concepts:
- Fixed timestep ensures deterministic physics (same result on all hardware)
- Interpolation factor `alpha` smooths rendering between physics frames
- Spiral-of-death cap prevents exponential frame time growth
- Max physics steps per frame prevents freeze on very slow frames
- `time.perf_counter()` gives microsecond precision (not `time.time()`)
- Frame limiter prevents unnecessary CPU/GPU usage when above target FPS
'''
    ),
    (
        "gamedev/spatial-partitioning",
        "Implement spatial partitioning for collision detection: a spatial hash grid and a quadtree, with benchmarks showing when to use each, and integration with an ECS world.",
        '''Spatial partitioning: hash grid and quadtree for efficient collision detection:

```python
# spatial.py — Spatial hash grid and quadtree for broad-phase collision
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any

Entity = int


@dataclass
class AABB:
    """Axis-aligned bounding box."""
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float: return self.x + self.width / 2
    @property
    def center_y(self) -> float: return self.y + self.height / 2
    @property
    def right(self) -> float: return self.x + self.width
    @property
    def bottom(self) -> float: return self.y + self.height

    def intersects(self, other: AABB) -> bool:
        return (
            self.x < other.right and self.right > other.x and
            self.y < other.bottom and self.bottom > other.y
        )

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom


# ============================================================
# 1. SPATIAL HASH GRID — O(1) insert, O(1) query for uniform objects
# ============================================================

class SpatialHashGrid:
    """Fixed-cell spatial hash for fast broad-phase collision detection.

    Best when objects are roughly the same size and uniformly distributed.
    Cell size should be ~2x the largest object diameter.
    """

    def __init__(self, cell_size: float = 64.0):
        self.cell_size = cell_size
        self._inv_cell_size = 1.0 / cell_size
        self._cells: dict[tuple[int, int], set[Entity]] = {}
        self._entity_cells: dict[Entity, list[tuple[int, int]]] = {}

    def _cell_key(self, x: float, y: float) -> tuple[int, int]:
        return (int(math.floor(x * self._inv_cell_size)),
                int(math.floor(y * self._inv_cell_size)))

    def _covered_cells(self, aabb: AABB) -> list[tuple[int, int]]:
        """Get all grid cells that an AABB overlaps."""
        min_cx, min_cy = self._cell_key(aabb.x, aabb.y)
        max_cx, max_cy = self._cell_key(aabb.right - 0.001, aabb.bottom - 0.001)
        cells = []
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                cells.append((cx, cy))
        return cells

    def clear(self):
        self._cells.clear()
        self._entity_cells.clear()

    def insert(self, entity: Entity, aabb: AABB):
        cells = self._covered_cells(aabb)
        self._entity_cells[entity] = cells
        for cell in cells:
            if cell not in self._cells:
                self._cells[cell] = set()
            self._cells[cell].add(entity)

    def remove(self, entity: Entity):
        cells = self._entity_cells.pop(entity, [])
        for cell in cells:
            bucket = self._cells.get(cell)
            if bucket:
                bucket.discard(entity)
                if not bucket:
                    del self._cells[cell]

    def update(self, entity: Entity, aabb: AABB):
        """Reinsert entity with new position (move operation)."""
        self.remove(entity)
        self.insert(entity, aabb)

    def query_aabb(self, aabb: AABB) -> set[Entity]:
        """Find all entities whose cells overlap the query AABB."""
        result: set[Entity] = set()
        for cell in self._covered_cells(aabb):
            bucket = self._cells.get(cell)
            if bucket:
                result.update(bucket)
        return result

    def query_radius(self, cx: float, cy: float, radius: float) -> set[Entity]:
        """Find entities within radius using AABB approximation."""
        aabb = AABB(cx - radius, cy - radius, radius * 2, radius * 2)
        return self.query_aabb(aabb)

    def find_all_pairs(self) -> list[tuple[Entity, Entity]]:
        """Find all potentially colliding pairs across all cells."""
        pairs: set[tuple[Entity, Entity]] = set()
        for cell_entities in self._cells.values():
            entities = list(cell_entities)
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    a, b = entities[i], entities[j]
                    pair = (min(a, b), max(a, b))
                    pairs.add(pair)
        return list(pairs)


# ============================================================
# 2. QUADTREE — Adaptive subdivision for non-uniform distributions
# ============================================================

class QuadTree:
    """Recursive quadtree for broad-phase collision detection.

    Best when objects vary greatly in size or have non-uniform distribution.
    Subdivides regions that contain too many objects.
    """

    MAX_OBJECTS = 8    # Objects per node before split
    MAX_DEPTH = 8      # Maximum tree depth

    def __init__(self, bounds: AABB, depth: int = 0):
        self.bounds = bounds
        self.depth = depth
        self.objects: list[tuple[Entity, AABB]] = []
        self.children: list[QuadTree] | None = None

    def _subdivide(self):
        """Split into 4 quadrants: NW, NE, SW, SE."""
        x, y = self.bounds.x, self.bounds.y
        hw = self.bounds.width / 2
        hh = self.bounds.height / 2
        d = self.depth + 1

        self.children = [
            QuadTree(AABB(x, y, hw, hh), d),          # NW
            QuadTree(AABB(x + hw, y, hw, hh), d),     # NE
            QuadTree(AABB(x, y + hh, hw, hh), d),     # SW
            QuadTree(AABB(x + hw, y + hh, hw, hh), d), # SE
        ]

        # Redistribute existing objects
        for obj in self.objects:
            for child in self.children:
                if child.bounds.intersects(obj[1]):
                    child.objects.append(obj)
        self.objects = []

    def insert(self, entity: Entity, aabb: AABB) -> bool:
        if not self.bounds.intersects(aabb):
            return False

        if self.children is not None:
            for child in self.children:
                child.insert(entity, aabb)
            return True

        self.objects.append((entity, aabb))

        if len(self.objects) > self.MAX_OBJECTS and self.depth < self.MAX_DEPTH:
            self._subdivide()

        return True

    def query(self, area: AABB) -> list[Entity]:
        """Find all entities whose AABB intersects the query area."""
        result: list[Entity] = []
        if not self.bounds.intersects(area):
            return result

        for entity, aabb in self.objects:
            if aabb.intersects(area):
                result.append(entity)

        if self.children is not None:
            for child in self.children:
                result.extend(child.query(area))

        return result

    def find_all_pairs(self) -> list[tuple[Entity, Entity]]:
        """Find all potentially colliding pairs in the tree."""
        all_pairs: set[tuple[Entity, Entity]] = set()
        self._find_pairs_recursive(all_pairs)
        return list(all_pairs)

    def _find_pairs_recursive(self, pairs: set):
        # Check pairs within this node
        for i in range(len(self.objects)):
            for j in range(i + 1, len(self.objects)):
                ea, aa = self.objects[i]
                eb, ab = self.objects[j]
                if aa.intersects(ab):
                    pairs.add((min(ea, eb), max(ea, eb)))

        if self.children:
            for child in self.children:
                child._find_pairs_recursive(pairs)

    def clear(self):
        self.objects.clear()
        self.children = None


# ============================================================
# 3. ECS Integration — Spatial system using hash grid
# ============================================================

class SpatialSystem:
    """ECS system that maintains a spatial index for collision queries."""

    def __init__(self, cell_size: float = 64.0, world_bounds: AABB = None):
        self.grid = SpatialHashGrid(cell_size)
        self.world_bounds = world_bounds or AABB(0, 0, 4096, 4096)
        self.priority = 15  # Run after movement, before collision
        self.enabled = True
        self.world = None

    def update(self, dt: float):
        """Rebuild spatial index every frame (fast for moving objects)."""
        self.grid.clear()

        # Assumes Position and Collider components exist
        from ecs import Position, Collider
        for entity, pos, col in self.world.query(Position, Collider):
            aabb = AABB(
                pos.x - col.radius,
                pos.y - col.radius,
                col.radius * 2,
                col.radius * 2,
            )
            self.grid.insert(entity, aabb)

    def query_nearby(self, x: float, y: float, radius: float) -> set[int]:
        return self.grid.query_radius(x, y, radius)

    def get_collision_pairs(self) -> list[tuple[int, int]]:
        return self.grid.find_all_pairs()
```

Performance comparison:

| Structure | Insert | Query | Memory | Best For |
|---|---|---|---|---|
| Brute force | O(1) | O(N^2) | O(N) | < 50 objects |
| Spatial hash grid | O(1) | O(1) avg | O(N + cells) | Uniform size, ~1000+ objects |
| Quadtree | O(log N) | O(log N) | O(N log N) | Mixed sizes, non-uniform density |
| BVH tree | O(N log N) build | O(log N) | O(N) | Static geometry, raycasting |
| R-tree | O(log N) | O(log N) | O(N) | Database spatial queries |

When to use each:
- **Spatial hash**: Objects are similar size (bullets, particles) -- fastest for uniform distributions
- **Quadtree**: Objects vary in size (players vs. buildings) -- adapts to density
- **Rebuild per frame**: Simpler and often faster than incremental updates for moving objects
- Cell size = 2x largest object diameter gives best hash grid performance
'''
    ),
    (
        "gamedev/ai-state-machine",
        "Implement a hierarchical finite state machine (HFSM) for game AI with state transitions, substates, blackboard data sharing, and behavior examples for patrol/chase/attack enemy AI.",
        '''Hierarchical finite state machine (HFSM) for game enemy AI:

```python
# ai_fsm.py — Hierarchical FSM with blackboard for game AI behavior
from __future__ import annotations
import math
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class Blackboard:
    """Shared memory for AI decisions. Avoids tight coupling between states."""

    def __init__(self):
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data

    def clear(self):
        self._data.clear()


class StateResult(Enum):
    RUNNING = auto()
    SUCCESS = auto()
    FAILURE = auto()


class State:
    """Base state in the FSM. Override enter/execute/exit."""

    name: str = "BaseState"

    def enter(self, bb: Blackboard) -> None:
        """Called once when transitioning INTO this state."""
        pass

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        """Called every frame while in this state. Returns status."""
        return StateResult.RUNNING

    def exit(self, bb: Blackboard) -> None:
        """Called once when transitioning OUT of this state."""
        pass


class Transition:
    """Conditional transition between states."""

    def __init__(
        self,
        target_state: str,
        condition: Callable[[Blackboard], bool],
        priority: int = 0,
    ):
        self.target_state = target_state
        self.condition = condition
        self.priority = priority


class StateMachine:
    """Finite state machine with named states and conditional transitions."""

    def __init__(self, owner_id: str = ""):
        self.owner_id = owner_id
        self._states: dict[str, State] = {}
        self._transitions: dict[str, list[Transition]] = {}
        self._current_state: State | None = None
        self._current_name: str = ""
        self.blackboard = Blackboard()

    @property
    def current_state_name(self) -> str:
        return self._current_name

    def add_state(self, name: str, state: State) -> StateMachine:
        state.name = name
        self._states[name] = state
        self._transitions[name] = []
        return self

    def add_transition(
        self, from_state: str, to_state: str,
        condition: Callable[[Blackboard], bool],
        priority: int = 0,
    ) -> StateMachine:
        self._transitions[from_state].append(
            Transition(to_state, condition, priority)
        )
        # Sort by priority (higher = checked first)
        self._transitions[from_state].sort(key=lambda t: -t.priority)
        return self

    def set_initial_state(self, name: str):
        self._current_name = name
        self._current_state = self._states[name]
        self._current_state.enter(self.blackboard)

    def _change_state(self, new_name: str):
        if self._current_state:
            self._current_state.exit(self.blackboard)
            logger.debug(f"[{self.owner_id}] {self._current_name} -> {new_name}")
        self._current_name = new_name
        self._current_state = self._states[new_name]
        self._current_state.enter(self.blackboard)

    def update(self, dt: float):
        """Check transitions then execute current state."""
        if not self._current_state:
            return

        # Check transitions from current state
        for transition in self._transitions.get(self._current_name, []):
            if transition.condition(self.blackboard):
                self._change_state(transition.target_state)
                break

        # Execute current state
        self._current_state.execute(self.blackboard, dt)


class HierarchicalState(State):
    """A state that contains a sub-state machine (HFSM)."""

    def __init__(self):
        self.sub_fsm = StateMachine()

    def enter(self, bb: Blackboard):
        self.sub_fsm.blackboard = bb  # Share blackboard with parent
        # Reset sub-FSM to its initial state

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        self.sub_fsm.update(dt)
        return StateResult.RUNNING

    def exit(self, bb: Blackboard):
        pass


# ============================================================
# Concrete AI States for Enemy Behavior
# ============================================================

class IdleState(State):
    """Wait at position, periodically look around."""

    def __init__(self, idle_duration: float = 3.0):
        self.idle_duration = idle_duration
        self._timer = 0.0

    def enter(self, bb: Blackboard):
        self._timer = 0.0
        bb.set("idle_complete", False)

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        self._timer += dt
        if self._timer >= self.idle_duration:
            bb.set("idle_complete", True)
            return StateResult.SUCCESS
        return StateResult.RUNNING


class PatrolState(State):
    """Move between waypoints in sequence."""

    def __init__(self, waypoints: list[tuple[float, float]], speed: float = 80.0):
        self.waypoints = waypoints
        self.speed = speed
        self._current_wp = 0

    def enter(self, bb: Blackboard):
        pass

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        if not self.waypoints:
            return StateResult.FAILURE

        pos_x = bb.get("pos_x", 0.0)
        pos_y = bb.get("pos_y", 0.0)
        target = self.waypoints[self._current_wp]

        dx = target[0] - pos_x
        dy = target[1] - pos_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 5.0:
            # Reached waypoint, advance to next
            self._current_wp = (self._current_wp + 1) % len(self.waypoints)
            return StateResult.RUNNING

        # Move toward waypoint
        nx, ny = dx / dist, dy / dist
        bb.set("pos_x", pos_x + nx * self.speed * dt)
        bb.set("pos_y", pos_y + ny * self.speed * dt)
        bb.set("facing_x", nx)
        bb.set("facing_y", ny)

        return StateResult.RUNNING


class ChaseState(State):
    """Pursue a target entity."""

    def __init__(self, speed: float = 120.0, give_up_range: float = 300.0):
        self.speed = speed
        self.give_up_range = give_up_range

    def enter(self, bb: Blackboard):
        logger.debug("Enemy entering chase state")

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        pos_x = bb.get("pos_x", 0.0)
        pos_y = bb.get("pos_y", 0.0)
        target_x = bb.get("target_x", 0.0)
        target_y = bb.get("target_y", 0.0)

        dx = target_x - pos_x
        dy = target_y - pos_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > self.give_up_range:
            bb.set("target_lost", True)
            return StateResult.FAILURE

        if dist < 1.0:
            return StateResult.SUCCESS

        nx, ny = dx / dist, dy / dist
        bb.set("pos_x", pos_x + nx * self.speed * dt)
        bb.set("pos_y", pos_y + ny * self.speed * dt)
        bb.set("facing_x", nx)
        bb.set("facing_y", ny)
        bb.set("target_dist", dist)

        return StateResult.RUNNING


class AttackState(State):
    """Attack target with cooldown."""

    def __init__(self, damage: int = 10, cooldown: float = 1.0, range_: float = 30.0):
        self.damage = damage
        self.cooldown = cooldown
        self.range = range_
        self._timer = 0.0

    def enter(self, bb: Blackboard):
        self._timer = 0.0

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        target_dist = bb.get("target_dist", 999.0)
        if target_dist > self.range:
            return StateResult.FAILURE  # Target moved out of range

        self._timer += dt
        if self._timer >= self.cooldown:
            self._timer = 0.0
            bb.set("attack_triggered", True)
            bb.set("attack_damage", self.damage)
            logger.debug(f"Enemy attacks for {self.damage} damage!")

        return StateResult.RUNNING


class FleeState(State):
    """Run away from threat."""

    def __init__(self, speed: float = 150.0, safe_distance: float = 200.0):
        self.speed = speed
        self.safe_distance = safe_distance

    def execute(self, bb: Blackboard, dt: float) -> StateResult:
        pos_x, pos_y = bb.get("pos_x", 0.0), bb.get("pos_y", 0.0)
        threat_x, threat_y = bb.get("target_x", 0.0), bb.get("target_y", 0.0)

        dx, dy = pos_x - threat_x, pos_y - threat_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist >= self.safe_distance:
            bb.set("is_safe", True)
            return StateResult.SUCCESS

        if dist > 0:
            nx, ny = dx / dist, dy / dist
            bb.set("pos_x", pos_x + nx * self.speed * dt)
            bb.set("pos_y", pos_y + ny * self.speed * dt)

        return StateResult.RUNNING


# ============================================================
# Build complete enemy AI
# ============================================================

def create_enemy_ai(
    waypoints: list[tuple[float, float]],
    detection_range: float = 150.0,
    attack_range: float = 30.0,
    flee_health_pct: float = 0.2,
) -> StateMachine:
    """Create a complete HFSM enemy AI: Idle -> Patrol -> Chase -> Attack -> Flee."""

    fsm = StateMachine(owner_id="enemy")

    fsm.add_state("idle", IdleState(idle_duration=2.0))
    fsm.add_state("patrol", PatrolState(waypoints, speed=80))
    fsm.add_state("chase", ChaseState(speed=120, give_up_range=detection_range * 2))
    fsm.add_state("attack", AttackState(damage=10, cooldown=1.0, range_=attack_range))
    fsm.add_state("flee", FleeState(speed=150, safe_distance=200))

    def player_detected(bb: Blackboard) -> bool:
        dist = bb.get("target_dist", 999)
        return dist < detection_range

    def player_in_attack_range(bb: Blackboard) -> bool:
        return bb.get("target_dist", 999) < attack_range

    def player_out_of_range(bb: Blackboard) -> bool:
        return bb.get("target_dist", 999) > attack_range

    def low_health(bb: Blackboard) -> bool:
        return bb.get("health_pct", 1.0) < flee_health_pct

    def target_lost(bb: Blackboard) -> bool:
        return bb.get("target_lost", False)

    def idle_done(bb: Blackboard) -> bool:
        return bb.get("idle_complete", False)

    def is_safe(bb: Blackboard) -> bool:
        return bb.get("is_safe", False)

    # Transitions (priority determines check order)
    fsm.add_transition("idle", "patrol", idle_done)
    fsm.add_transition("patrol", "chase", player_detected, priority=10)
    fsm.add_transition("chase", "attack", player_in_attack_range, priority=10)
    fsm.add_transition("chase", "patrol", target_lost)
    fsm.add_transition("attack", "chase", player_out_of_range)
    fsm.add_transition("attack", "flee", low_health, priority=20)  # Flee takes priority
    fsm.add_transition("chase", "flee", low_health, priority=20)
    fsm.add_transition("flee", "patrol", is_safe)

    fsm.set_initial_state("idle")
    return fsm
```

State transition diagram:

```
                     idle_done
         [IDLE] ──────────────> [PATROL]
                                   |
                          player_detected
                                   v
        target_lost            [CHASE] <──── player_out_of_range
        ┌────────────────────── |    |                |
        v                       |    v                |
     [PATROL]          in_range |  [ATTACK] ──────────┘
                                |    |
                     low_health |    | low_health (priority=20)
                                v    v
                              [FLEE]
                                |
                             is_safe
                                v
                            [PATROL]
```

| AI Pattern | Complexity | Flexibility | Best For |
|---|---|---|---|
| Flat FSM | Low | Limited | Simple 2-3 state behaviors |
| Hierarchical FSM | Medium | Good | Most game enemy AI |
| Behavior Tree | High | Best | Complex multi-phase bosses |
| GOAP | Highest | Best for emergent | Open world NPC planning |
| Utility AI | High | Good for scoring | Action selection with preferences |

Key HFSM patterns:
- Blackboard decouples states from game world (testable in isolation)
- Priority-based transitions ensure critical behaviors (flee) override others
- Hierarchical states contain sub-FSMs for complex behaviors within a single state
- Enter/exit hooks handle setup/cleanup (play animations, reset timers)
- States return RUNNING/SUCCESS/FAILURE to help parent FSMs make decisions
'''
    ),
    (
        "gamedev/networking",
        "Implement client-side prediction with server reconciliation for a multiplayer game, including input buffering, snapshot interpolation, lag compensation, and handling network jitter.",
        '''Client-side prediction with server reconciliation for multiplayer networking:

```python
# netcode.py — Client prediction, server reconciliation, snapshot interpolation
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def lerp(self, target: Vec2, t: float) -> Vec2:
        return Vec2(
            self.x + (target.x - self.x) * t,
            self.y + (target.y - self.y) * t,
        )

    def distance_sq(self, other: Vec2) -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy

    def copy(self) -> Vec2:
        return Vec2(self.x, self.y)


@dataclass
class InputCommand:
    """Player input for a single tick, tagged with sequence number."""
    sequence: int
    tick: int
    move_x: float = 0.0     # -1 to 1
    move_y: float = 0.0     # -1 to 1
    fire: bool = False
    timestamp: float = 0.0


@dataclass
class PlayerState:
    """Authoritative player state from the server."""
    entity_id: int
    position: Vec2 = field(default_factory=Vec2)
    velocity: Vec2 = field(default_factory=Vec2)
    health: int = 100
    last_processed_input: int = 0  # Last InputCommand.sequence server processed
    tick: int = 0


@dataclass
class WorldSnapshot:
    """Complete world state at a point in time."""
    tick: int
    timestamp: float
    players: dict[int, PlayerState] = field(default_factory=dict)


# ============================================================
# Shared: Deterministic simulation step
# ============================================================

TICK_RATE = 60           # Server simulation rate (Hz)
TICK_DURATION = 1.0 / TICK_RATE
PLAYER_SPEED = 200.0     # pixels per second


def simulate_player(state: PlayerState, input_cmd: InputCommand, dt: float) -> PlayerState:
    """Deterministic physics step — same on client and server.

    CRITICAL: This function must produce IDENTICAL results on both sides.
    No random numbers, no floating-point-order-dependent operations.
    """
    new_state = PlayerState(
        entity_id=state.entity_id,
        position=state.position.copy(),
        velocity=Vec2(
            input_cmd.move_x * PLAYER_SPEED,
            input_cmd.move_y * PLAYER_SPEED,
        ),
        health=state.health,
        last_processed_input=input_cmd.sequence,
        tick=state.tick + 1,
    )
    new_state.position.x += new_state.velocity.x * dt
    new_state.position.y += new_state.velocity.y * dt

    # Clamp to world bounds
    new_state.position.x = max(0, min(1920, new_state.position.x))
    new_state.position.y = max(0, min(1080, new_state.position.y))

    return new_state


# ============================================================
# SERVER: Authoritative simulation
# ============================================================

class GameServer:
    """Authoritative game server processing client inputs."""

    def __init__(self):
        self.tick = 0
        self.players: dict[int, PlayerState] = {}
        self._input_queues: dict[int, deque[InputCommand]] = {}
        self._snapshot_history: deque[WorldSnapshot] = deque(maxlen=128)

    def add_player(self, entity_id: int, spawn: Vec2):
        self.players[entity_id] = PlayerState(
            entity_id=entity_id, position=spawn
        )
        self._input_queues[entity_id] = deque(maxlen=64)

    def receive_input(self, entity_id: int, cmd: InputCommand):
        """Buffer client input for processing on next tick."""
        queue = self._input_queues.get(entity_id)
        if queue is not None:
            queue.append(cmd)

    def tick_update(self):
        """Process one server tick: consume inputs, simulate, snapshot."""
        self.tick += 1

        for eid, state in self.players.items():
            queue = self._input_queues.get(eid, deque())
            if queue:
                cmd = queue.popleft()
                self.players[eid] = simulate_player(state, cmd, TICK_DURATION)
            else:
                # No input: apply empty input (player stands still)
                empty = InputCommand(sequence=state.last_processed_input, tick=self.tick)
                self.players[eid] = simulate_player(state, empty, TICK_DURATION)

        # Save snapshot for lag compensation
        snapshot = WorldSnapshot(
            tick=self.tick,
            timestamp=time.time(),
            players={eid: PlayerState(
                entity_id=s.entity_id,
                position=s.position.copy(),
                velocity=s.velocity.copy(),
                health=s.health,
                last_processed_input=s.last_processed_input,
                tick=s.tick,
            ) for eid, s in self.players.items()},
        )
        self._snapshot_history.append(snapshot)

    def get_snapshot(self) -> WorldSnapshot:
        """Returns current world state to broadcast to clients."""
        return self._snapshot_history[-1] if self._snapshot_history else WorldSnapshot(tick=0, timestamp=0)

    def get_snapshot_at_time(self, timestamp: float) -> WorldSnapshot | None:
        """Lag compensation: find world state at a past timestamp."""
        for snap in reversed(self._snapshot_history):
            if snap.timestamp <= timestamp:
                return snap
        return self._snapshot_history[0] if self._snapshot_history else None


# ============================================================
# CLIENT: Prediction + Reconciliation + Interpolation
# ============================================================

class GameClient:
    """Client with prediction, reconciliation, and entity interpolation."""

    def __init__(self, local_entity_id: int):
        self.local_id = local_entity_id
        self.sequence = 0

        # Local predicted state
        self.predicted_state: PlayerState | None = None

        # Input history for reconciliation (unacknowledged inputs)
        self._pending_inputs: deque[InputCommand] = deque(maxlen=256)

        # Snapshot buffer for interpolation of other players
        self._snapshot_buffer: deque[WorldSnapshot] = deque(maxlen=32)
        self._interpolation_delay = 0.1  # 100ms interpolation buffer (3 ticks at 30Hz send rate)

        # Visual smoothing for reconciliation corrections
        self._visual_position: Vec2 = Vec2()
        self._smoothing_factor = 0.1  # Blend speed for error correction

    def create_input(self, move_x: float, move_y: float, fire: bool = False) -> InputCommand:
        """Create timestamped input command."""
        self.sequence += 1
        return InputCommand(
            sequence=self.sequence,
            tick=0,
            move_x=move_x,
            move_y=move_y,
            fire=fire,
            timestamp=time.time(),
        )

    def apply_input(self, cmd: InputCommand):
        """Client-side prediction: apply input immediately without waiting for server."""
        if self.predicted_state is None:
            return

        # Predict locally
        self.predicted_state = simulate_player(
            self.predicted_state, cmd, TICK_DURATION
        )

        # Save for reconciliation
        self._pending_inputs.append(cmd)

    def receive_server_state(self, snapshot: WorldSnapshot):
        """Process authoritative server snapshot.

        For local player: reconcile prediction errors.
        For remote players: buffer for interpolation.
        """
        self._snapshot_buffer.append(snapshot)

        # --- Reconciliation for local player ---
        server_state = snapshot.players.get(self.local_id)
        if server_state is None:
            return

        # Remove inputs the server has already processed
        while (self._pending_inputs and
               self._pending_inputs[0].sequence <= server_state.last_processed_input):
            self._pending_inputs.popleft()

        # Start from server's authoritative state
        reconciled = PlayerState(
            entity_id=server_state.entity_id,
            position=server_state.position.copy(),
            velocity=server_state.velocity.copy(),
            health=server_state.health,
            last_processed_input=server_state.last_processed_input,
            tick=server_state.tick,
        )

        # Re-apply unacknowledged inputs on top of server state
        for cmd in self._pending_inputs:
            reconciled = simulate_player(reconciled, cmd, TICK_DURATION)

        # Check for prediction error
        if self.predicted_state:
            error = reconciled.position.distance_sq(self.predicted_state.position)
            if error > 0.01:  # Threshold to avoid micro-corrections
                logger.debug(
                    f"Reconciliation correction: error={error:.2f}px^2, "
                    f"replayed {len(self._pending_inputs)} inputs"
                )

        self.predicted_state = reconciled

    def get_interpolated_remote(self, entity_id: int) -> Vec2 | None:
        """Interpolate between two snapshots for smooth remote player rendering.

        Uses a fixed delay (render_time = current_time - interpolation_delay)
        to always have two snapshots to interpolate between.
        """
        render_time = time.time() - self._interpolation_delay

        # Find the two snapshots that bracket render_time
        before: WorldSnapshot | None = None
        after: WorldSnapshot | None = None

        for snap in self._snapshot_buffer:
            if snap.timestamp <= render_time:
                before = snap
            elif before is not None:
                after = snap
                break

        if before is None:
            return None

        player_before = before.players.get(entity_id)
        if player_before is None:
            return None

        if after is None:
            return player_before.position.copy()

        player_after = after.players.get(entity_id)
        if player_after is None:
            return player_before.position.copy()

        # Interpolation factor: how far between the two snapshots
        total = after.timestamp - before.timestamp
        if total <= 0:
            return player_before.position.copy()

        t = (render_time - before.timestamp) / total
        t = max(0.0, min(1.0, t))

        return player_before.position.lerp(player_after.position, t)

    def get_render_position(self) -> Vec2:
        """Get smoothed local player position for rendering."""
        if self.predicted_state is None:
            return self._visual_position

        # Smooth visual position toward predicted position
        self._visual_position = self._visual_position.lerp(
            self.predicted_state.position,
            1.0 - self._smoothing_factor,
        )
        return self._visual_position
```

Data flow:

```
CLIENT                          NETWORK              SERVER
  |                                                    |
  |  [1] Sample input            ----CMD---->         |
  |  [2] Predict locally                              |  [3] Buffer input
  |  [3] Render predicted                             |  [4] Simulate tick
  |       position                                    |  [5] Broadcast snapshot
  |                              <---SNAPSHOT----     |
  |  [4] Reconcile:                                   |
  |      - Remove acked inputs                        |
  |      - Rewind to server state                     |
  |      - Replay unacked inputs                      |
  |  [5] Smooth visual position                       |
  |  [6] Interpolate remote                           |
  |       players from snapshots                      |
```

| Technique | Purpose | Tradeoff |
|---|---|---|
| Client-side prediction | Immediate response to input | Can mispre dict (needs reconciliation) |
| Server reconciliation | Fix prediction errors | Replay cost on correction |
| Snapshot interpolation | Smooth remote players | Adds 100ms visual delay |
| Lag compensation | Fair hit detection | Server rewinds world state |
| Input buffering | Handle jitter | Adds ~1 tick of latency |

Key networking patterns:
- Deterministic simulation is CRITICAL: client and server must produce identical results
- Reconciliation replays only unacknowledged inputs (typically 3-10 at 60Hz with 50ms RTT)
- Interpolation delay should be ~2-3x the server send interval
- Visual smoothing prevents jarring "teleport" corrections on small errors
- Snapshot history on server enables lag compensation for hit detection
- Input sequence numbers ensure server processes inputs in order
'''
    ),
]
