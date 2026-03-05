"""Concurrency patterns — actors, CSP, and parallel processing."""

PAIRS = [
    (
        "patterns/actor-model",
        "Show actor model patterns: message passing, supervision, and actor hierarchies in Python.",
        '''Actor model patterns:

```python
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# --- Message types ---

@dataclass(frozen=True)
class Message:
    type: str
    payload: Any = None
    reply_to: asyncio.Queue | None = None


# --- Actor base class ---

class Actor:
    """Lightweight actor with mailbox and message processing loop."""

    def __init__(self, name: str):
        self.name = name
        self.mailbox: asyncio.Queue[Message | None] = asyncio.Queue(maxsize=1000)
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        """Start the actor's message processing loop."""
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"actor-{self.name}")
        logger.info("Actor %s started", self.name)

    async def stop(self):
        """Gracefully stop the actor."""
        self._running = False
        await self.mailbox.put(None)  # Poison pill
        if self._task:
            await self._task

    async def send(self, message: Message):
        """Send a message to this actor."""
        await self.mailbox.put(message)

    async def ask(self, msg_type: str, payload: Any = None, timeout: float = 5.0) -> Any:
        """Send message and wait for reply."""
        reply_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        await self.send(Message(type=msg_type, payload=payload, reply_to=reply_queue))
        return await asyncio.wait_for(reply_queue.get(), timeout=timeout)

    async def _run(self):
        """Main message processing loop."""
        while self._running:
            try:
                msg = await self.mailbox.get()
                if msg is None:
                    break
                await self.handle(msg)
            except Exception as e:
                logger.error("Actor %s error handling %s: %s", self.name, msg, e)
                await self.on_error(e, msg)

    async def handle(self, msg: Message):
        """Override to handle messages. Dispatch by type."""
        raise NotImplementedError

    async def on_error(self, error: Exception, msg: Message):
        """Override for custom error handling."""
        pass


# --- Example: Bank Account Actor ---

class AccountActor(Actor):
    def __init__(self, account_id: str):
        super().__init__(f"account-{account_id}")
        self.balance = 0.0

    async def handle(self, msg: Message):
        match msg.type:
            case "deposit":
                self.balance += msg.payload["amount"]
                if msg.reply_to:
                    await msg.reply_to.put({"balance": self.balance})

            case "withdraw":
                amount = msg.payload["amount"]
                if amount > self.balance:
                    if msg.reply_to:
                        await msg.reply_to.put({"error": "insufficient funds"})
                    return
                self.balance -= amount
                if msg.reply_to:
                    await msg.reply_to.put({"balance": self.balance})

            case "get_balance":
                if msg.reply_to:
                    await msg.reply_to.put({"balance": self.balance})


# --- Supervisor (restart failed actors) ---

class SupervisorStrategy(Enum):
    ONE_FOR_ONE = "one_for_one"    # Restart only failed actor
    ALL_FOR_ONE = "all_for_one"    # Restart all if one fails


class Supervisor:
    """Manages and restarts child actors."""

    def __init__(self, strategy: SupervisorStrategy = SupervisorStrategy.ONE_FOR_ONE,
                 max_restarts: int = 3, restart_window: float = 60.0):
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.restart_window = restart_window
        self.children: dict[str, Actor] = {}
        self._factories: dict[str, Callable] = {}
        self._restart_counts: dict[str, list[float]] = {}

    async def add_child(self, name: str, factory: Callable[[], Actor]):
        """Register and start a child actor."""
        self._factories[name] = factory
        self._restart_counts[name] = []
        actor = factory()
        self.children[name] = actor
        await actor.start()

    async def restart_child(self, name: str):
        """Restart a failed child actor."""
        import time
        now = time.time()

        # Check restart rate
        restarts = self._restart_counts[name]
        restarts = [t for t in restarts if now - t < self.restart_window]
        self._restart_counts[name] = restarts

        if len(restarts) >= self.max_restarts:
            logger.error("Actor %s exceeded max restarts, giving up", name)
            return

        restarts.append(now)
        logger.info("Restarting actor %s (attempt %d)", name, len(restarts))

        if self.strategy == SupervisorStrategy.ALL_FOR_ONE:
            for child_name, child in self.children.items():
                await child.stop()
                new_actor = self._factories[child_name]()
                self.children[child_name] = new_actor
                await new_actor.start()
        else:
            old = self.children[name]
            await old.stop()
            new_actor = self._factories[name]()
            self.children[name] = new_actor
            await new_actor.start()


# --- Actor registry ---

class ActorSystem:
    """Central registry for finding actors by name."""

    def __init__(self):
        self._actors: dict[str, Actor] = {}

    def register(self, actor: Actor):
        self._actors[actor.name] = actor

    def lookup(self, name: str) -> Actor | None:
        return self._actors.get(name)

    async def broadcast(self, msg: Message):
        for actor in self._actors.values():
            await actor.send(msg)
```

Actor model patterns:
1. **Mailbox** — async queue isolates actor state from concurrent access
2. **`ask()`** — request-reply with reply_to queue and timeout
3. **Pattern matching** — dispatch messages by `msg.type` in handle()
4. **Supervisor** — automatically restart failed actors with rate limiting
5. **Actor registry** — find actors by name, broadcast to all'''
    ),
    (
        "patterns/csp-channels",
        "Show CSP (Communicating Sequential Processes) patterns: channels, select, pipelines, and fan-out/fan-in.",
        '''CSP channel patterns in Python:

```python
import asyncio
from dataclasses import dataclass
from typing import TypeVar, Generic, AsyncIterator

T = TypeVar("T")


# --- Typed channel ---

class Channel(Generic[T]):
    """Go-style buffered channel for async communication."""

    def __init__(self, capacity: int = 0):
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(
            maxsize=max(capacity, 1)
        )
        self._closed = False

    async def send(self, value: T):
        """Send value to channel. Blocks if full."""
        if self._closed:
            raise RuntimeError("Cannot send on closed channel")
        await self._queue.put(value)

    async def receive(self) -> T | None:
        """Receive value from channel. Returns None if closed."""
        value = await self._queue.get()
        if value is None:
            # Re-send None so other receivers also stop
            await self._queue.put(None)
            return None
        return value

    def close(self):
        """Close channel — receivers will get None."""
        self._closed = True
        self._queue.put_nowait(None)

    async def __aiter__(self) -> AsyncIterator[T]:
        """Iterate over channel values until closed."""
        while True:
            value = await self.receive()
            if value is None:
                break
            yield value


# --- Select (wait on multiple channels) ---

async def select(*channels: Channel) -> tuple[int, any]:
    """Wait on multiple channels, return (index, value) of first ready."""
    tasks = [
        asyncio.create_task(ch.receive())
        for ch in channels
    ]

    done, pending = await asyncio.wait(
        tasks, return_when=asyncio.FIRST_COMPLETED,
    )

    # Cancel remaining tasks
    for task in pending:
        task.cancel()

    # Return result from completed task
    for i, task in enumerate(tasks):
        if task in done:
            return i, task.result()

    raise RuntimeError("No task completed")


# --- Pipeline pattern ---

async def generate(nums: list[int]) -> Channel[int]:
    """Generate numbers into a channel."""
    ch = Channel[int](capacity=10)

    async def producer():
        for n in nums:
            await ch.send(n)
        ch.close()

    asyncio.create_task(producer())
    return ch


async def square(input_ch: Channel[int]) -> Channel[int]:
    """Square each number from input channel."""
    output = Channel[int](capacity=10)

    async def worker():
        async for n in input_ch:
            await output.send(n * n)
        output.close()

    asyncio.create_task(worker())
    return output


async def filter_even(input_ch: Channel[int]) -> Channel[int]:
    """Pass through only even numbers."""
    output = Channel[int](capacity=10)

    async def worker():
        async for n in input_ch:
            if n % 2 == 0:
                await output.send(n)
        output.close()

    asyncio.create_task(worker())
    return output


async def pipeline_example():
    # Chain: generate → square → filter_even → consume
    nums = await generate(list(range(1, 11)))
    squared = await square(nums)
    evens = await filter_even(squared)

    async for value in evens:
        print(value)  # 4, 16, 36, 64, 100


# --- Fan-out / Fan-in ---

async def fan_out(
    input_ch: Channel[T],
    num_workers: int,
    process: callable,
) -> Channel:
    """Distribute work across N workers, merge results."""
    output = Channel(capacity=100)
    done_count = 0

    async def worker(worker_id: int):
        nonlocal done_count
        async for item in input_ch:
            result = await process(item)
            await output.send(result)
        done_count += 1
        if done_count == num_workers:
            output.close()

    for i in range(num_workers):
        asyncio.create_task(worker(i))

    return output


# --- Ticker (periodic channel) ---

async def ticker(interval: float) -> Channel[float]:
    """Channel that emits timestamps at regular intervals."""
    ch = Channel[float](capacity=1)

    async def tick():
        import time
        while not ch._closed:
            await ch.send(time.time())
            await asyncio.sleep(interval)

    asyncio.create_task(tick())
    return ch


# --- Timeout channel ---

async def after(seconds: float) -> Channel[bool]:
    """Channel that sends True after timeout."""
    ch = Channel[bool](capacity=1)

    async def timer():
        await asyncio.sleep(seconds)
        await ch.send(True)
        ch.close()

    asyncio.create_task(timer())
    return ch
```

CSP patterns:
1. **Buffered channels** — bounded queue with back-pressure on full
2. **`async for`** — iterate over channel until closed (Go range-over-channel)
3. **Pipeline** — chain stages: generate → transform → filter → consume
4. **Fan-out/Fan-in** — distribute work to N workers, merge into one output
5. **Select** — wait on multiple channels, process first available'''
    ),
]
