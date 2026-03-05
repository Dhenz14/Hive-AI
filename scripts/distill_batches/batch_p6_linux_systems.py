"""
Batch P6 — Linux Systems Programming
Covers: epoll and io_uring, namespaces and cgroups, memory management,
process management, filesystem internals.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Linux epoll and io_uring ---
    (
        "linux/epoll-io_uring-event-driven-io",
        "Explain Linux event-driven I/O in depth including the evolution from select to poll to epoll, how epoll's red-black tree and ready list achieve O(1) event notification, the io_uring submission and completion queue architecture with memory-mapped ring buffers, how Python asyncio integrates with epoll under the hood, and provide C and Python code examples demonstrating high-performance I/O patterns.",
        r"""# Linux epoll and io_uring: Mastering Event-Driven I/O

## The Evolution of I/O Multiplexing

Linux provides multiple mechanisms for monitoring file descriptors, and understanding their evolution is critical for building high-performance servers. The progression from **select** to **poll** to **epoll** to **io_uring** represents decades of kernel engineering driven by the need to handle millions of concurrent connections.

### select: The Original (and Its Limitations)

The `select()` system call dates back to 4.2BSD (1983). It takes three bitmasks — read, write, exception — each representing a set of file descriptors. The kernel scans **every** file descriptor in the set on every call, making it **O(n)** where n is the highest fd number. The `FD_SETSIZE` limit (typically 1024) caps the maximum number of monitored descriptors.

**Common mistake**: Assuming `select()` is O(n) in the number of *active* fds. It is actually O(n) in the *highest fd value*, because the kernel must scan the entire bitmask up to `nfds`. If you have fd 1000 and fd 5, the kernel scans all 1001 bits.

### poll: Removing the FD Limit

`poll()` replaces bitmasks with an array of `struct pollfd`, removing the `FD_SETSIZE` limit. However, it is still **O(n)** because the kernel must iterate through the entire array on every call, and the entire array is copied between user-space and kernel-space each time. Therefore, `poll()` does not solve the scalability problem for servers handling tens of thousands of connections.

### epoll: O(1) Event Notification

**epoll** was introduced in Linux 2.5.44 and is the foundation of modern event-driven servers (nginx, Node.js, Redis). It solves the O(n) problem with a fundamentally different architecture.

## epoll Internal Architecture

epoll uses two key data structures inside the kernel:

1. **Red-black tree** — stores all monitored file descriptors. Adding or removing an fd is **O(log n)**, and the tree enables efficient lookup when events arrive.
2. **Ready list** (a linked list) — when an fd becomes ready (data available, socket writable, etc.), the kernel adds it to this list via a **callback** registered on the fd's wait queue. When `epoll_wait()` is called, it simply drains the ready list — **O(k)** where k is the number of ready fds, not the total monitored count.

This is the key insight: **epoll does not scan all fds**. Instead, the kernel pushes ready fds onto the ready list asynchronously, and `epoll_wait()` only touches fds that actually have events. For a server with 100,000 connections where 50 are active at any moment, epoll does O(50) work per call, not O(100,000).

### Edge-Triggered vs Level-Triggered

epoll supports two notification modes:

- **Level-triggered (LT)**: The default. `epoll_wait()` returns an fd as ready as long as the condition persists (e.g., there is data in the buffer). Safe but can cause redundant wake-ups.
- **Edge-triggered (ET)**: `epoll_wait()` returns an fd only when its state *changes* (e.g., new data arrives). More efficient but requires the application to drain the entire buffer on each notification, otherwise data will be missed.

**Pitfall**: Using edge-triggered mode without non-blocking I/O and full buffer drainage is the most common epoll bug. If you read only part of the data and no new data arrives, you will never be notified about the remaining data.

## C Implementation: epoll Echo Server

```c
// High-performance epoll echo server with edge-triggered mode
// Compile: gcc -O2 -o epoll_server epoll_server.c
#include <sys/epoll.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_EVENTS 1024
#define BUFFER_SIZE 4096
#define PORT 8080

// Set file descriptor to non-blocking mode
// Required for edge-triggered epoll to avoid blocking on partial reads
static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags == -1) return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

// Add fd to epoll with edge-triggered read monitoring
static int epoll_add(int epfd, int fd, uint32_t events) {
    struct epoll_event ev;
    ev.events = events;
    ev.data.fd = fd;
    return epoll_ctl(epfd, EPOLL_CTL_ADD, fd, &ev);
}

int main(void) {
    int server_fd, epfd, nfds;
    struct epoll_event events[MAX_EVENTS];
    struct sockaddr_in addr;
    char buffer[BUFFER_SIZE];

    // Create listening socket
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);
    bind(server_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, SOMAXCONN);
    set_nonblocking(server_fd);

    // Create epoll instance -- this allocates the red-black tree
    // and ready list in kernel space
    epfd = epoll_create1(0);
    // Monitor server socket for incoming connections (level-triggered is OK here)
    epoll_add(epfd, server_fd, EPOLLIN);

    printf("epoll echo server listening on port %d\n", PORT);

    while (1) {
        // Block until at least one fd is ready -- O(k) where k = ready fds
        nfds = epoll_wait(epfd, events, MAX_EVENTS, -1);

        for (int i = 0; i < nfds; i++) {
            if (events[i].data.fd == server_fd) {
                // Accept all pending connections (edge-triggered drain)
                while (1) {
                    int client_fd = accept(server_fd, NULL, NULL);
                    if (client_fd == -1) {
                        if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                        perror("accept");
                        break;
                    }
                    set_nonblocking(client_fd);
                    // Add client with EPOLLET (edge-triggered) + EPOLLIN
                    epoll_add(epfd, client_fd, EPOLLIN | EPOLLET);
                }
            } else {
                // Client fd ready -- drain ALL data (edge-triggered requirement)
                int fd = events[i].data.fd;
                while (1) {
                    ssize_t n = read(fd, buffer, BUFFER_SIZE);
                    if (n <= 0) {
                        if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK)) {
                            close(fd);  // epoll auto-removes closed fds
                        }
                        break;
                    }
                    // Echo back
                    write(fd, buffer, n);
                }
            }
        }
    }
    close(epfd);
    close(server_fd);
    return 0;
}
```

## io_uring: The Future of Linux I/O

io_uring was introduced by Jens Axboe in Linux 5.1 (2019) and represents a **paradigm shift** in how applications interact with the kernel for I/O. While epoll tells you *when* an fd is ready and you still make system calls to perform the I/O, io_uring lets you submit I/O operations to the kernel and receive completions **without any system calls in the hot path**.

### Submission and Completion Queue Architecture

io_uring uses two **memory-mapped ring buffers** shared between user-space and the kernel:

1. **Submission Queue (SQ)**: The application writes Submission Queue Entries (SQEs) describing I/O operations (read, write, accept, connect, etc.) into this ring buffer. The kernel consumes them.
2. **Completion Queue (CQ)**: The kernel writes Completion Queue Entries (CQEs) with the results of completed operations into this ring buffer. The application consumes them.

**Best practice**: Size the CQ at least 2x the SQ depth because a single submission can generate multiple completions (e.g., multi-shot accept). The kernel will back-pressure if the CQ overflows.

Because both queues are in shared memory, the application and kernel communicate via **memory barriers** rather than system calls. The `io_uring_enter()` syscall is only needed to wake the kernel when new submissions are available (and even that can be eliminated with `IORING_SETUP_SQPOLL`, which creates a kernel thread that polls the SQ).

```c
// io_uring echo server using liburing
// Compile: gcc -O2 -o uring_server uring_server.c -luring
#include <liburing.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#define QUEUE_DEPTH 256
#define BUFFER_SIZE 4096
#define PORT 8080

// Event types to distinguish completions
enum event_type { EVENT_ACCEPT, EVENT_READ, EVENT_WRITE };

struct conn_info {
    int fd;
    enum event_type type;
    char buffer[BUFFER_SIZE];
};

// Submit an accept operation to the submission queue
static void submit_accept(struct io_uring *ring, int server_fd,
                          struct sockaddr_in *addr, socklen_t *addrlen) {
    struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
    io_uring_prep_accept(sqe, server_fd, (struct sockaddr*)addr, addrlen, 0);
    struct conn_info *info = malloc(sizeof(struct conn_info));
    info->fd = server_fd;
    info->type = EVENT_ACCEPT;
    io_uring_sqe_set_data(sqe, info);
}

// Submit a read operation
static void submit_read(struct io_uring *ring, struct conn_info *info) {
    struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
    io_uring_prep_recv(sqe, info->fd, info->buffer, BUFFER_SIZE, 0);
    info->type = EVENT_READ;
    io_uring_sqe_set_data(sqe, info);
}

// Submit a write operation
static void submit_write(struct io_uring *ring, struct conn_info *info, int len) {
    struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
    io_uring_prep_send(sqe, info->fd, info->buffer, len, 0);
    info->type = EVENT_WRITE;
    io_uring_sqe_set_data(sqe, info);
}

int main(void) {
    struct io_uring ring;
    struct sockaddr_in addr, client_addr;
    socklen_t addrlen = sizeof(client_addr);

    // Initialize io_uring with specified queue depth
    // This sets up the SQ and CQ ring buffers in shared memory
    io_uring_queue_init(QUEUE_DEPTH, &ring, 0);

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);
    bind(server_fd, (struct sockaddr*)&addr, sizeof(addr));
    listen(server_fd, SOMAXCONN);

    printf("io_uring echo server on port %d\n", PORT);

    // Prime the submission queue with an accept
    submit_accept(&ring, server_fd, &client_addr, &addrlen);
    io_uring_submit(&ring);

    while (1) {
        struct io_uring_cqe *cqe;
        // Wait for a completion -- no busy polling needed
        io_uring_wait_cqe(&ring, &cqe);

        struct conn_info *info = io_uring_cqe_get_data(cqe);
        int res = cqe->res;

        if (info->type == EVENT_ACCEPT) {
            if (res >= 0) {
                // New connection: start reading from it
                struct conn_info *client = malloc(sizeof(struct conn_info));
                client->fd = res;
                submit_read(&ring, client);
                // Re-arm accept for next connection
                submit_accept(&ring, server_fd, &client_addr, &addrlen);
            }
        } else if (info->type == EVENT_READ) {
            if (res <= 0) {
                close(info->fd);
                free(info);
            } else {
                // Echo data back
                submit_write(&ring, info, res);
            }
        } else if (info->type == EVENT_WRITE) {
            // Write done, read more
            submit_read(&ring, info);
        }

        io_uring_cqe_seen(&ring, cqe);
        io_uring_submit(&ring);
    }

    io_uring_queue_exit(&ring);
    close(server_fd);
    return 0;
}
```

## Python asyncio and epoll Integration

Python's `asyncio` uses epoll as its default event loop on Linux. The `SelectorEventLoop` wraps `selectors.EpollSelector`, which in turn wraps the `epoll_create1`, `epoll_ctl`, and `epoll_wait` system calls. Understanding this relationship is essential for diagnosing performance issues in async Python applications.

```python
# Demonstrating the epoll underpinnings of Python asyncio
# and building a custom event loop with raw epoll access
import asyncio
import selectors
import socket
import select
from typing import Dict, Callable, Optional, Tuple, List
from dataclasses import dataclass, field

# --- Low-level epoll wrapper for educational purposes ---

@dataclass
class EpollReactor:
    # A minimal event reactor built directly on epoll
    # This is essentially what asyncio.SelectorEventLoop does internally

    _epfd: int = field(init=False)
    _handlers: Dict[int, Callable] = field(default_factory=dict)
    _fd_to_socket: Dict[int, socket.socket] = field(default_factory=dict)
    _running: bool = False

    def __post_init__(self) -> None:
        # epoll_create1(0) -- allocates the kernel red-black tree
        self._epfd = select.epoll().fileno()
        self._epoll = select.epoll()

    def register(self, sock: socket.socket, callback: Callable) -> None:
        # Add socket to the epoll interest set
        fd = sock.fileno()
        self._epoll.register(fd, select.EPOLLIN | select.EPOLLET)
        self._handlers[fd] = callback
        self._fd_to_socket[fd] = sock

    def unregister(self, sock: socket.socket) -> None:
        fd = sock.fileno()
        self._epoll.unregister(fd)
        del self._handlers[fd]
        del self._fd_to_socket[fd]

    def run_forever(self, timeout: float = 1.0) -> None:
        # Main event loop -- mirrors asyncio._run_once()
        self._running = True
        while self._running:
            # This calls epoll_wait() -- O(k) where k = ready fds
            events = self._epoll.poll(timeout)
            for fd, event_mask in events:
                handler = self._handlers.get(fd)
                if handler is not None:
                    handler(fd, event_mask)

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self._epoll.close()


# --- asyncio-based high-performance server ---

class AsyncEchoServer:
    # Production-grade async echo server using asyncio (which uses epoll)

    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        self.host = host
        self.port = port
        self._connections: Dict[str, asyncio.StreamWriter] = {}

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        client_id = f"{addr[0]}:{addr[1]}"
        self._connections[client_id] = writer

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                # Echo back -- asyncio handles epoll registration internally
                writer.write(data)
                await writer.drain()
        except ConnectionResetError:
            pass
        finally:
            del self._connections[client_id]
            writer.close()
            await writer.wait_closed()

    async def start(self) -> None:
        server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        # Inspect the underlying selector to prove it is epoll
        loop = asyncio.get_running_loop()
        selector = getattr(loop, "_selector", None)
        if selector is not None:
            print(f"Event loop selector: {type(selector).__name__}")
            # Output: EpollSelector on Linux
        async with server:
            await server.serve_forever()


async def demonstrate_epoll_asyncio() -> None:
    # Show that asyncio is built on epoll
    loop = asyncio.get_running_loop()
    print(f"Loop implementation: {type(loop).__name__}")
    print(f"Uses epoll: {hasattr(select, 'epoll')}")

    server = AsyncEchoServer(port=9090)
    await server.start()
```

## Performance Comparison: select vs poll vs epoll vs io_uring

| Feature | select | poll | epoll | io_uring |
|---|---|---|---|---|
| **FD limit** | FD_SETSIZE (1024) | Unlimited | Unlimited | Unlimited |
| **Complexity per call** | O(n) | O(n) | O(k) ready fds | O(0) with SQPOLL |
| **Kernel copy per call** | Full bitmask | Full array | None (shared state) | None (shared rings) |
| **Syscalls for I/O** | Separate read/write | Separate read/write | Separate read/write | **Zero** (batched) |
| **Kernel thread polling** | No | No | No | Yes (SQPOLL mode) |

## Pitfalls and Best Practices

- **Pitfall**: Using `EPOLLONESHOT` without re-arming. With `EPOLLONESHOT`, the fd is disabled after one event and must be re-enabled with `epoll_ctl(EPOLL_CTL_MOD)`. Forgetting this silently drops events
- **Best practice**: For io_uring, use `IORING_SETUP_SQPOLL` only when latency is more important than CPU usage — the kernel polling thread consumes a full CPU core
- **Trade-off**: Edge-triggered epoll has higher throughput because it avoids redundant wake-ups, however it requires more careful programming (non-blocking I/O, full buffer drainage). Level-triggered is safer for most applications
- **Common mistake**: Not checking `io_uring_get_sqe()` return value. If the SQ is full, it returns NULL and you must submit pending entries before adding more

## Summary and Key Takeaways

1. **select and poll are O(n) per call** because the kernel must scan all monitored file descriptors, making them unsuitable for servers handling more than a few hundred connections
2. **epoll achieves O(1) notification** through a kernel-side red-black tree and callback-driven ready list, which is why it powers nginx, Redis, and Node.js
3. **Edge-triggered epoll** eliminates redundant wake-ups but requires non-blocking I/O and full buffer drainage — level-triggered is the safer default for most applications
4. **io_uring eliminates system calls** from the I/O hot path by using shared memory ring buffers between user-space and kernel, achieving the lowest possible latency for high-throughput workloads
5. **Python asyncio uses epoll internally** via `selectors.EpollSelector`, and understanding this layer is essential for diagnosing performance bottlenecks in async Python applications
"""
    ),

    # --- 2. Linux Namespaces and cgroups ---
    (
        "linux/namespaces-cgroups-container-foundations",
        "Explain the Linux kernel foundations of containers including all namespace types (PID, network, mount, UTS, IPC, user, cgroup), cgroup v2 unified hierarchy with resource controllers for CPU memory and I/O, and provide a complete Python implementation of a minimal container runtime that uses these primitives to isolate a process.",
        r"""# Linux Namespaces and cgroups: Building Containers from Scratch

## Why Containers Are Not Virtual Machines

Containers are often described as "lightweight VMs," but this is a **fundamental misconception**. Virtual machines emulate hardware and run a complete OS kernel. Containers, by contrast, are just **regular Linux processes** with two kernel features applied: **namespaces** for isolation and **cgroups** for resource limits. There is no hypervisor, no guest kernel — the containerized process runs on the **same kernel** as the host.

Understanding namespaces and cgroups is therefore essential for anyone who uses Docker, Kubernetes, or any container technology, because these are the actual mechanisms providing the isolation guarantees you depend on.

## Linux Namespaces: Isolation Primitives

A namespace wraps a global system resource in an abstraction that makes it appear to processes within the namespace that they have their own isolated instance of that resource. Linux provides **eight** namespace types:

### PID Namespace

The PID namespace isolates the process ID number space. The first process in a new PID namespace gets PID 1 and acts as the `init` process for that namespace. Processes inside cannot see or signal processes outside their namespace. **However**, processes on the host can see all processes in all namespaces — the isolation is one-directional.

**Pitfall**: If PID 1 in a PID namespace exits, all other processes in that namespace are killed. This is why container init processes (like `tini` or `dumb-init`) are critical — they reap zombie processes and handle signals correctly.

### Network Namespace

Each network namespace has its own network stack: interfaces, routing tables, iptables rules, and sockets. A process in a new network namespace starts with only a loopback interface. To provide connectivity, you create a **veth pair** — a virtual ethernet cable with one end in the host namespace and one end in the container namespace.

### Mount Namespace

The mount namespace isolates the filesystem mount table. Combined with `pivot_root` or `chroot`, this gives each container its own filesystem view. **Best practice**: Use `pivot_root` instead of `chroot` because `chroot` can be escaped by a process with `CAP_SYS_CHROOT`.

### UTS Namespace

Isolates the hostname and NIS domain name, allowing each container to have its own hostname.

### IPC Namespace

Isolates System V IPC objects (message queues, semaphores, shared memory segments) and POSIX message queues.

### User Namespace

Maps UIDs/GIDs inside the namespace to different UIDs/GIDs outside. This enables **rootless containers** — a process can be root (UID 0) inside the namespace while being an unprivileged user on the host. This is the **most important security namespace** because it limits the blast radius of container escapes.

### Cgroup Namespace

Virtualizes the cgroup filesystem view so that a process sees its own cgroup as the root of the hierarchy, preventing it from discovering the host's cgroup structure.

## cgroup v2: Unified Resource Control

cgroup v2 (unified hierarchy) replaced the fragmented cgroup v1 with a single hierarchy where all controllers are managed together. The key controllers are:

- **cpu** — CPU bandwidth and scheduling weight
- **memory** — Memory usage limits and OOM control
- **io** — Block I/O bandwidth limits (replacing blkio from v1)
- **pids** — Maximum number of processes
- **cpuset** — CPU and memory node pinning

### cgroup v2 Interface

All control is done through the **cgroupfs** pseudo-filesystem, typically mounted at `/sys/fs/cgroup`. Each cgroup is a directory, and resource limits are set by writing to files in that directory.

```bash
# Create a cgroup for a container
# The unified hierarchy means one directory controls all resources
mkdir /sys/fs/cgroup/my_container

# Enable controllers (must be done from parent)
echo "+cpu +memory +io +pids" > /sys/fs/cgroup/cgroup.subtree_control

# Set memory limit to 256MB with 512MB swap
echo 268435456 > /sys/fs/cgroup/my_container/memory.max
echo 536870912 > /sys/fs/cgroup/my_container/memory.swap.max

# Set CPU limit to 50% of one core (50ms every 100ms period)
echo "50000 100000" > /sys/fs/cgroup/my_container/cpu.max

# Set CPU weight (relative scheduling priority, default 100)
echo 50 > /sys/fs/cgroup/my_container/cpu.weight

# Limit to 20 processes maximum
echo 20 > /sys/fs/cgroup/my_container/pids.max

# Set I/O weight (1-10000, default 100)
echo "default 50" > /sys/fs/cgroup/my_container/io.weight

# Move a process into this cgroup
echo $PID > /sys/fs/cgroup/my_container/cgroup.procs
```

## Python Minimal Container Implementation

The following Python implementation creates a container from scratch using the `ctypes` library to call Linux system calls directly. This is essentially what Docker's `runc` does, but in Python for educational purposes.

```python
# Minimal container runtime in Python
# Demonstrates namespace creation, cgroup setup, and filesystem isolation
# Must be run as root: sudo python3 mini_container.py
import ctypes
import ctypes.util
import os
import sys
import socket
import struct
from pathlib import Path
from typing import Optional, List, Callable
from dataclasses import dataclass, field

# --- Linux system call constants ---
CLONE_NEWPID = 0x20000000
CLONE_NEWNS = 0x00020000     # Mount namespace
CLONE_NEWNET = 0x40000000
CLONE_NEWUTS = 0x04000000
CLONE_NEWIPC = 0x08000000
CLONE_NEWUSER = 0x10000000
CLONE_NEWCGROUP = 0x02000000

MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_RDONLY = 1

STACK_SIZE = 1024 * 1024  # 1 MB stack for cloned child

# Load libc for direct syscall access
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# --- clone() wrapper ---
# Python's os.fork() cannot create namespaces, so we need clone() directly
clone_fn_type = ctypes.CFUNCTYPE(ctypes.c_int)

def _call_clone(flags: int, child_fn: Callable[[], int]) -> int:
    # Allocate stack for the child process
    child_stack = ctypes.create_string_buffer(STACK_SIZE)
    # Stack grows downward on x86_64 -- pass top of stack
    stack_top = ctypes.cast(
        ctypes.addressof(child_stack) + STACK_SIZE,
        ctypes.c_void_p
    )
    # Wrap the Python function for C calling convention
    @clone_fn_type
    def _child_wrapper():
        try:
            return child_fn()
        except Exception as e:
            print(f"Child error: {e}", file=sys.stderr)
            return 1

    pid = libc.clone(
        _child_wrapper,
        stack_top,
        ctypes.c_int(flags | 0x00000011),  # SIGCHLD
    )
    if pid == -1:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return pid


@dataclass
class CgroupConfig:
    # cgroup v2 resource limits for the container
    memory_max_bytes: int = 256 * 1024 * 1024  # 256 MB
    memory_swap_max_bytes: int = 0               # No swap
    cpu_max_usec: int = 50000                    # 50ms per 100ms period
    cpu_period_usec: int = 100000
    pids_max: int = 64
    # cgroup v2 base path
    cgroup_base: str = "/sys/fs/cgroup"

    @property
    def cpu_max_str(self) -> str:
        return f"{self.cpu_max_usec} {self.cpu_period_usec}"


@dataclass
class ContainerConfig:
    # Full container configuration
    rootfs: str                          # Path to container root filesystem
    command: List[str]                   # Command to execute inside container
    hostname: str = "container"
    uid_map: str = "0 1000 1"           # Map container root to host UID 1000
    gid_map: str = "0 1000 1"
    cgroup: CgroupConfig = field(default_factory=CgroupConfig)


class MiniContainer:
    # A minimal container runtime demonstrating Linux primitives
    # This implements the core of what runc/containerd does

    def __init__(self, config: ContainerConfig) -> None:
        self.config = config
        self._cgroup_path: Optional[Path] = None

    def _setup_cgroup(self, pid: int) -> None:
        # Create cgroup v2 directory and set resource limits
        cgroup_name = f"minicontainer_{pid}"
        self._cgroup_path = Path(self.config.cgroup.cgroup_base) / cgroup_name

        self._cgroup_path.mkdir(exist_ok=True)

        # Set memory limit
        (self._cgroup_path / "memory.max").write_text(
            str(self.config.cgroup.memory_max_bytes)
        )
        (self._cgroup_path / "memory.swap.max").write_text(
            str(self.config.cgroup.memory_swap_max_bytes)
        )

        # Set CPU limit
        (self._cgroup_path / "cpu.max").write_text(
            self.config.cgroup.cpu_max_str
        )

        # Set PID limit
        (self._cgroup_path / "pids.max").write_text(
            str(self.config.cgroup.pids_max)
        )

        # Move the container process into this cgroup
        (self._cgroup_path / "cgroup.procs").write_text(str(pid))

    def _setup_mount_namespace(self) -> None:
        # Isolate the filesystem: pivot_root to the container rootfs
        rootfs = self.config.rootfs

        # Make all mounts private so changes do not propagate to host
        libc.mount(b"none", b"/", None, MS_REC | MS_PRIVATE, None)

        # Bind-mount rootfs onto itself (required for pivot_root)
        rootfs_b = rootfs.encode()
        libc.mount(rootfs_b, rootfs_b, None, MS_BIND | MS_REC, None)

        # Create put_old directory for pivot_root
        old_root = os.path.join(rootfs, ".old_root")
        os.makedirs(old_root, exist_ok=True)

        # pivot_root swaps the root filesystem
        # After this, rootfs becomes / and old root is at /.old_root
        libc.syscall(155, rootfs_b, old_root.encode())  # SYS_pivot_root
        os.chdir("/")

        # Mount /proc for process visibility within the namespace
        os.makedirs("/proc", exist_ok=True)
        libc.mount(b"proc", b"/proc", b"proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, None)

        # Mount /dev/pts for PTY support
        os.makedirs("/dev/pts", exist_ok=True)
        libc.mount(b"devpts", b"/dev/pts", b"devpts", 0, None)

        # Unmount the old root to complete isolation
        libc.umount2(b"/.old_root", 2)  # MNT_DETACH
        os.rmdir("/.old_root")

    def _child_process(self) -> int:
        # This runs inside the new namespaces
        # Set hostname in the UTS namespace
        socket.sethostname(self.config.hostname)

        # Setup filesystem isolation
        self._setup_mount_namespace()

        # Execute the target command
        os.execvp(self.config.command[0], self.config.command)
        return 1  # Only reached if exec fails

    def run(self) -> int:
        # Create the container with all namespaces
        clone_flags = (
            CLONE_NEWPID | CLONE_NEWNS | CLONE_NEWUTS |
            CLONE_NEWNET | CLONE_NEWIPC | CLONE_NEWCGROUP
        )

        pid = _call_clone(clone_flags, self._child_process)
        print(f"Container started with PID {pid}")

        # Setup cgroup limits from the host side
        self._setup_cgroup(pid)

        # Wait for the container to exit
        _, status = os.waitpid(pid, 0)
        exit_code = os.WEXITSTATUS(status)

        # Cleanup cgroup
        if self._cgroup_path and self._cgroup_path.exists():
            self._cgroup_path.rmdir()

        return exit_code


def main() -> None:
    if os.getuid() != 0:
        print("Error: must run as root", file=sys.stderr)
        sys.exit(1)

    config = ContainerConfig(
        rootfs="/var/lib/minicontainer/rootfs",
        command=["/bin/sh"],
        hostname="mini-container",
        cgroup=CgroupConfig(
            memory_max_bytes=128 * 1024 * 1024,
            cpu_max_usec=25000,
            pids_max=32,
        ),
    )

    container = MiniContainer(config)
    sys.exit(container.run())


if __name__ == "__main__":
    main()
```

```python
# Monitoring cgroup v2 resource usage from Python
# Useful for container observability and autoscaling decisions
import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class CgroupStats:
    # Parsed cgroup v2 statistics for a container
    memory_current: int = 0
    memory_max: int = 0
    memory_swap_current: int = 0
    cpu_usage_usec: int = 0
    cpu_system_usec: int = 0
    cpu_user_usec: int = 0
    nr_periods: int = 0
    nr_throttled: int = 0
    throttled_usec: int = 0
    pids_current: int = 0
    pids_max: int = 0
    io_read_bytes: int = 0
    io_write_bytes: int = 0

class CgroupMonitor:
    # Real-time cgroup v2 monitor with rate calculation
    # because container resource usage is only meaningful as rates

    def __init__(self, cgroup_path: str) -> None:
        self._path = Path(cgroup_path)
        self._prev_stats: Optional[CgroupStats] = None
        self._prev_time: float = 0

    def _read_file(self, name: str) -> str:
        try:
            return (self._path / name).read_text().strip()
        except (FileNotFoundError, PermissionError):
            return "0"

    def _parse_key_value(self, content: str) -> Dict[str, int]:
        # Parse cgroup stat files with "key value" format
        result: Dict[str, int] = {}
        for line in content.splitlines():
            parts = line.split()
            if len(parts) == 2:
                try:
                    result[parts[0]] = int(parts[1])
                except ValueError:
                    pass
        return result

    def read_stats(self) -> CgroupStats:
        stats = CgroupStats()

        # Memory stats
        stats.memory_current = int(self._read_file("memory.current"))
        mem_max = self._read_file("memory.max")
        stats.memory_max = int(mem_max) if mem_max != "max" else 0
        stats.memory_swap_current = int(self._read_file("memory.swap.current"))

        # CPU stats (from cpu.stat)
        cpu_stat = self._parse_key_value(self._read_file("cpu.stat"))
        stats.cpu_usage_usec = cpu_stat.get("usage_usec", 0)
        stats.cpu_system_usec = cpu_stat.get("system_usec", 0)
        stats.cpu_user_usec = cpu_stat.get("user_usec", 0)
        stats.nr_throttled = cpu_stat.get("nr_throttled", 0)
        stats.throttled_usec = cpu_stat.get("throttled_usec", 0)

        # PID stats
        stats.pids_current = int(self._read_file("pids.current"))
        pids_max = self._read_file("pids.max")
        stats.pids_max = int(pids_max) if pids_max != "max" else 0

        return stats

    def get_cpu_percent(self, current: CgroupStats) -> float:
        # Calculate CPU usage as a percentage since last sample
        # because raw usage_usec is monotonically increasing
        now = time.monotonic()
        if self._prev_stats is None:
            self._prev_stats = current
            self._prev_time = now
            return 0.0

        delta_usec = current.cpu_usage_usec - self._prev_stats.cpu_usage_usec
        delta_time = now - self._prev_time
        self._prev_stats = current
        self._prev_time = now

        if delta_time <= 0:
            return 0.0
        # Convert microseconds to percentage of wall clock
        return (delta_usec / (delta_time * 1_000_000)) * 100.0

    def print_stats(self) -> None:
        stats = self.read_stats()
        cpu_pct = self.get_cpu_percent(stats)
        mem_mb = stats.memory_current / (1024 * 1024)
        mem_max_mb = stats.memory_max / (1024 * 1024) if stats.memory_max else float("inf")
        print(f"CPU: {cpu_pct:.1f}%  "
              f"Memory: {mem_mb:.1f}/{mem_max_mb:.0f} MB  "
              f"PIDs: {stats.pids_current}/{stats.pids_max}  "
              f"Throttled: {stats.nr_throttled}")


def monitor_container(cgroup_path: str, interval: float = 1.0) -> None:
    monitor = CgroupMonitor(cgroup_path)
    print(f"Monitoring cgroup: {cgroup_path}")
    while True:
        monitor.print_stats()
        time.sleep(interval)


if __name__ == "__main__":
    # Example: monitor a Docker container's cgroup
    # Docker containers are under /sys/fs/cgroup/system.slice/docker-<id>.scope
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/sys/fs/cgroup/my_container"
    monitor_container(path)
```

## Security Implications and Best Practices

- **Best practice**: Always use user namespaces in production containers. Without them, root inside the container is root on the host — a single container escape gives full host access
- **Pitfall**: Forgetting to set the `no_new_privs` bit via `prctl(PR_SET_NO_NEW_PRIVS, 1)`. Without this, a process in a container can gain privileges through setuid binaries
- **Trade-off**: User namespaces add complexity (UID mapping, file ownership issues with bind mounts) but provide the strongest isolation boundary. The trade-off is overwhelmingly worth it for multi-tenant environments
- **Common mistake**: Setting cgroup memory limits without considering the OOM killer behavior. When a cgroup hits its memory limit, the kernel's OOM killer selects a process within that cgroup to terminate. If you do not handle this gracefully, your application will be killed without warning

## Summary and Key Takeaways

1. **Containers are not VMs** — they are regular Linux processes with namespace isolation and cgroup resource limits applied, which means they share the host kernel and have fundamentally different security properties than virtual machines
2. **Namespaces provide isolation** across eight dimensions (PID, network, mount, UTS, IPC, user, cgroup, time), and each namespace type isolates a specific global resource to give the process its own view of the system
3. **cgroup v2 unified hierarchy** replaces the fragmented v1 system with a single tree where CPU, memory, I/O, and PID controllers are managed together, providing coherent resource accounting
4. **User namespaces are the most important security feature** because they allow root inside the container to map to an unprivileged user on the host, drastically reducing the impact of container escapes
5. **Building a container from scratch** requires only ~200 lines of Python using `clone()` with namespace flags, `pivot_root` for filesystem isolation, and cgroup v2 files for resource limits — demonstrating that containers are a kernel feature, not a platform
"""
    ),

    # --- 3. Linux Memory Management ---
    (
        "linux/memory-management-virtual-memory-mmap",
        "Explain Linux memory management in depth including virtual memory and page table structure on x86_64, how mmap works for file-backed and anonymous mappings, transparent huge pages versus explicit hugetlbfs, the OOM killer scoring algorithm and how to tune it, and provide Python ctypes examples demonstrating mmap operations and memory-mapped I/O for high-performance data processing.",
        r"""# Linux Memory Management: Virtual Memory, mmap, and the OOM Killer

## Virtual Memory Architecture on x86_64

Every process on Linux operates in its own **virtual address space** — a 48-bit (256 TB) address space on standard x86_64, or 57-bit (128 PB) with 5-level paging. The process never accesses physical memory directly. Instead, the **Memory Management Unit (MMU)** in the CPU translates virtual addresses to physical addresses using **page tables**, with the kernel managing the mappings.

This abstraction provides three critical guarantees: **isolation** (processes cannot access each other's memory), **overcommit** (the kernel can promise more memory than physically exists), and **flexibility** (memory can be backed by files, swap, or nothing at all).

### Page Table Structure

x86_64 uses a **4-level page table** hierarchy (5-level with LA57):

1. **PGD** (Page Global Directory) — 512 entries, indexed by bits 47:39
2. **PUD** (Page Upper Directory) — 512 entries, indexed by bits 38:30
3. **PMD** (Page Middle Directory) — 512 entries, indexed by bits 29:21
4. **PTE** (Page Table Entry) — 512 entries, indexed by bits 20:12
5. **Page offset** — bits 11:0 (4 KB page)

Each level contains 512 entries of 8 bytes each, fitting exactly in one 4 KB page. The **CR3 register** points to the PGD of the current process. On context switch, the kernel loads the new process's CR3, which instantly switches the entire address space.

**Common mistake**: Assuming page table walks are expensive. The CPU caches page table entries in the **TLB** (Translation Lookaside Buffer). A TLB hit resolves a virtual address in ~1 cycle. A TLB miss requires walking all 4 levels (~200 cycles on modern hardware). Therefore, TLB efficiency is critical for performance.

### Process Virtual Address Space Layout

```
High addresses (0x7FFF_FFFF_FFFF)
+---------------------------+
|         Stack             |  Grows downward, RLIMIT_STACK (default 8 MB)
+---------------------------+
|           |               |
|           v               |
|                           |
|           ^               |
|           |               |
+---------------------------+
|    Memory-mapped files    |  mmap() region, grows downward
+---------------------------+
|                           |
+---------------------------+
|         Heap              |  brk()/sbrk(), grows upward
+---------------------------+
|         BSS               |  Uninitialized globals (zero-filled on demand)
+---------------------------+
|         Data              |  Initialized globals
+---------------------------+
|         Text              |  Program code (read-only, executable)
+---------------------------+
Low addresses (0x0000_0000_0000)
```

## mmap: The Swiss Army Knife of Memory

The `mmap()` system call creates a new mapping in the virtual address space of the calling process. It is the **single most important memory API** in Linux because it serves multiple purposes:

- **File-backed mapping**: Maps a file into memory for zero-copy access
- **Anonymous mapping**: Allocates memory without a file backing (this is how `malloc()` works for large allocations)
- **Shared mapping**: Multiple processes see the same physical pages (IPC mechanism)
- **Private mapping**: Copy-on-write — reads share physical pages, writes create private copies

### How mmap Actually Works

When you call `mmap()`, the kernel does **not** allocate physical memory. It only creates a **Virtual Memory Area (VMA)** entry in the process's `mm_struct`. Physical pages are allocated **on demand** when the process first accesses the mapped region, triggering a **page fault**. This lazy allocation is why you can `mmap()` a 1 TB file on a machine with 16 GB of RAM — only the pages you actually access consume physical memory.

**Best practice**: For sequential file access, call `madvise(MADV_SEQUENTIAL)` after mmap to tell the kernel to read ahead aggressively and drop pages behind the access point. For random access, use `madvise(MADV_RANDOM)` to disable read-ahead.

```python
# High-performance file processing with mmap and ctypes
# Demonstrating zero-copy file access, memory-mapped I/O,
# and direct page table interaction
import ctypes
import ctypes.util
import mmap
import os
import struct
import time
from pathlib import Path
from typing import Optional, Iterator, Tuple, List
from dataclasses import dataclass

# Load libc for madvise and other memory syscalls
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# madvise constants
MADV_NORMAL = 0
MADV_RANDOM = 1
MADV_SEQUENTIAL = 2
MADV_WILLNEED = 3
MADV_DONTNEED = 4
MADV_HUGEPAGE = 14     # Enable THP for this region
MADV_NOHUGEPAGE = 15   # Disable THP for this region

# mmap protection and flags
PROT_READ = 0x1
PROT_WRITE = 0x2
MAP_SHARED = 0x01
MAP_PRIVATE = 0x02
MAP_ANONYMOUS = 0x20
MAP_HUGETLB = 0x40000
MAP_POPULATE = 0x08000  # Pre-fault pages


@dataclass
class MmapRegion:
    # Represents a memory-mapped region with metadata
    address: int
    length: int
    fd: int
    offset: int
    is_file_backed: bool
    access_pattern: str = "sequential"


class HighPerformanceMmap:
    # Production-grade mmap wrapper with madvise hints and huge page support
    # because the default mmap() behavior is rarely optimal

    def __init__(self, path: str, readonly: bool = True) -> None:
        self.path = path
        self.readonly = readonly
        self._fd: Optional[int] = None
        self._mm: Optional[mmap.mmap] = None
        self._size: int = 0

    def __enter__(self) -> "HighPerformanceMmap":
        flags = os.O_RDONLY if self.readonly else os.O_RDWR
        self._fd = os.open(self.path, flags)
        self._size = os.fstat(self._fd).st_size

        access = mmap.ACCESS_READ if self.readonly else mmap.ACCESS_WRITE
        self._mm = mmap.mmap(self._fd, 0, access=access)
        return self

    def __exit__(self, *args) -> None:
        if self._mm is not None:
            self._mm.close()
        if self._fd is not None:
            os.close(self._fd)

    def advise_sequential(self) -> None:
        # Tell kernel to read-ahead aggressively
        # This dramatically improves sequential scan performance
        if self._mm is not None:
            self._mm.madvise(mmap.MADV_SEQUENTIAL)

    def advise_random(self) -> None:
        # Disable read-ahead for random access patterns
        if self._mm is not None:
            self._mm.madvise(mmap.MADV_RANDOM)

    def advise_willneed(self, offset: int, length: int) -> None:
        # Pre-fault pages into memory (async read-ahead)
        # Useful for prefetching regions you know you will access soon
        if self._mm is not None:
            self._mm.madvise(mmap.MADV_WILLNEED, offset, length)

    def scan_lines(self, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        # Zero-copy line iterator over a memory-mapped file
        # because this avoids the read() buffer copy entirely
        if self._mm is None:
            raise RuntimeError("Not opened")

        self.advise_sequential()
        start = 0
        while start < self._size:
            end = self._mm.find(b"\n", start)
            if end == -1:
                yield self._mm[start:]
                break
            yield self._mm[start:end]
            start = end + 1

    def read_struct_at(self, offset: int, fmt: str) -> Tuple:
        # Read a binary struct at a specific offset -- zero-copy
        if self._mm is None:
            raise RuntimeError("Not opened")
        size = struct.calcsize(fmt)
        data = self._mm[offset:offset + size]
        return struct.unpack(fmt, data)

    @property
    def size(self) -> int:
        return self._size


def benchmark_mmap_vs_read(filepath: str) -> None:
    # Compare mmap vs traditional read() for sequential file scanning
    file_size = os.path.getsize(filepath)
    print(f"File: {filepath} ({file_size / 1024 / 1024:.1f} MB)")

    # Traditional read()
    start = time.perf_counter()
    total = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            total += len(chunk)
    read_time = time.perf_counter() - start
    print(f"read():  {read_time:.3f}s ({file_size / read_time / 1e6:.0f} MB/s)")

    # mmap with sequential advice
    start = time.perf_counter()
    with HighPerformanceMmap(filepath) as mm:
        mm.advise_sequential()
        total = 0
        for line in mm.scan_lines():
            total += len(line)
    mmap_time = time.perf_counter() - start
    print(f"mmap():  {mmap_time:.3f}s ({file_size / mmap_time / 1e6:.0f} MB/s)")
    print(f"Speedup: {read_time / mmap_time:.2f}x")
```

## Transparent Huge Pages vs Explicit Huge Pages

Standard 4 KB pages require one PTE per page. A 1 GB dataset needs 262,144 PTEs, consuming TLB entries and causing frequent TLB misses. **Huge pages** use 2 MB or 1 GB pages, reducing TLB pressure by 512x or 262,144x respectively.

### Transparent Huge Pages (THP)

The kernel automatically promotes contiguous 4 KB pages to 2 MB huge pages via the `khugepaged` kernel thread. THP is enabled by default on most Linux distributions.

**Pitfall**: THP can cause **latency spikes** because the kernel's page compaction (defragmentation) to create contiguous 2 MB regions runs synchronously on allocation. For latency-sensitive applications (databases, trading systems), **disable THP** and use explicit huge pages instead. Redis documentation explicitly recommends disabling THP for this reason.

### Explicit Huge Pages (hugetlbfs)

Explicit huge pages are pre-allocated at boot time or via `sysctl` and are guaranteed to be available. They require more setup but provide **deterministic performance** with no compaction latency.

```python
# Working with huge pages from Python using ctypes
# Demonstrates both THP control and explicit hugetlbfs allocation
import ctypes
import ctypes.util
import os
import mmap
from typing import Optional

libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# Huge page constants
MAP_HUGETLB = 0x40000
MAP_HUGE_2MB = 21 << 26  # MAP_HUGE_SHIFT = 26
MAP_HUGE_1GB = 30 << 26
MADV_HUGEPAGE = 14
MADV_NOHUGEPAGE = 15

class HugePageAllocator:
    # Allocate memory backed by huge pages for TLB-sensitive workloads

    def __init__(self, size_bytes: int, use_1gb: bool = False) -> None:
        self.size = size_bytes
        self._use_1gb = use_1gb
        self._addr: Optional[int] = None
        self._mm: Optional[mmap.mmap] = None

    def allocate_explicit(self) -> memoryview:
        # Allocate from the hugetlbfs pool (must be pre-configured)
        # Requires: echo 512 > /proc/sys/vm/nr_hugepages
        huge_flag = MAP_HUGE_1GB if self._use_1gb else MAP_HUGE_2MB

        # Use anonymous mmap with MAP_HUGETLB
        fd = -1  # Anonymous mapping
        self._mm = mmap.mmap(
            fd, self.size,
            flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS | MAP_HUGETLB | huge_flag,
            prot=mmap.PROT_READ | mmap.PROT_WRITE,
        )
        return memoryview(self._mm)

    def allocate_thp(self) -> memoryview:
        # Allocate with Transparent Huge Pages advisory
        # The kernel will attempt to back this with 2MB pages
        fd = -1
        self._mm = mmap.mmap(
            fd, self.size,
            flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
            prot=mmap.PROT_READ | mmap.PROT_WRITE,
        )
        # Advise the kernel to use THP for this region
        self._mm.madvise(MADV_HUGEPAGE)
        return memoryview(self._mm)

    def release(self) -> None:
        if self._mm is not None:
            self._mm.close()
            self._mm = None


def check_thp_status() -> None:
    # Read THP configuration from sysfs
    thp_enabled_path = "/sys/kernel/mm/transparent_hugepage/enabled"
    if os.path.exists(thp_enabled_path):
        with open(thp_enabled_path) as f:
            print(f"THP status: {f.read().strip()}")

    defrag_path = "/sys/kernel/mm/transparent_hugepage/defrag"
    if os.path.exists(defrag_path):
        with open(defrag_path) as f:
            print(f"THP defrag: {f.read().strip()}")

    # Check available huge pages
    meminfo_path = "/proc/meminfo"
    with open(meminfo_path) as f:
        for line in f:
            if "Huge" in line:
                print(line.strip())
```

## The OOM Killer: Linux's Last Resort

When the system runs out of memory and cannot reclaim enough through normal means (page cache eviction, swap), the kernel invokes the **Out-Of-Memory (OOM) killer** to terminate processes and free memory. Understanding its scoring algorithm is essential for production systems.

### OOM Score Calculation

Each process has an OOM score in `/proc/<pid>/oom_score` (range 0-1000). The kernel selects the process with the **highest score** to kill. The score is calculated based on:

1. **RSS (Resident Set Size)** — how much physical memory the process uses. Higher RSS = higher score
2. **oom_score_adj** — a tunable value in `/proc/<pid>/oom_score_adj` (range -1000 to +1000). Set to -1000 to make a process completely immune to the OOM killer (dangerous)
3. **Child processes** — the score includes memory of child processes
4. **Root processes** — get a 3% discount (bonus) because they are more likely to be system-critical

**Trade-off**: Setting `oom_score_adj = -1000` on critical processes means *other* processes will be killed first, potentially causing cascading failures. A **better approach** is to set memory cgroup limits so that the OOM killer acts within a cgroup scope rather than system-wide.

```python
# OOM killer management and monitoring
# Demonstrates reading OOM scores, adjusting priorities,
# and monitoring for OOM events
import os
import signal
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict

@dataclass
class ProcessOOMInfo:
    # OOM-related information for a single process
    pid: int
    name: str
    oom_score: int
    oom_score_adj: int
    rss_kb: int
    vm_size_kb: int

class OOMManager:
    # Monitor and manage OOM killer behavior
    # Best practice: use this proactively rather than reacting to OOM kills

    @staticmethod
    def get_process_oom_info(pid: int) -> Optional[ProcessOOMInfo]:
        # Read OOM-related data from /proc/<pid>/
        proc = Path(f"/proc/{pid}")
        try:
            name = (proc / "comm").read_text().strip()
            oom_score = int((proc / "oom_score").read_text().strip())
            oom_score_adj = int((proc / "oom_score_adj").read_text().strip())

            # Parse RSS from /proc/<pid>/status
            status = (proc / "status").read_text()
            rss_kb = 0
            vm_size_kb = 0
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                elif line.startswith("VmSize:"):
                    vm_size_kb = int(line.split()[1])

            return ProcessOOMInfo(
                pid=pid, name=name, oom_score=oom_score,
                oom_score_adj=oom_score_adj,
                rss_kb=rss_kb, vm_size_kb=vm_size_kb,
            )
        except (FileNotFoundError, PermissionError, ValueError):
            return None

    @staticmethod
    def set_oom_score_adj(pid: int, value: int) -> None:
        # Adjust OOM priority (-1000 to +1000)
        # -1000 = never kill (dangerous), +1000 = kill first
        if not -1000 <= value <= 1000:
            raise ValueError(f"oom_score_adj must be -1000..+1000, got {value}")
        Path(f"/proc/{pid}/oom_score_adj").write_text(str(value))

    def get_top_oom_candidates(self, limit: int = 10) -> List[ProcessOOMInfo]:
        # Return processes most likely to be OOM-killed, sorted by score
        candidates: List[ProcessOOMInfo] = []
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                info = self.get_process_oom_info(int(entry.name))
                if info is not None and info.oom_score > 0:
                    candidates.append(info)

        candidates.sort(key=lambda p: p.oom_score, reverse=True)
        return candidates[:limit]

    def protect_critical_process(self, pid: int) -> None:
        # Reduce OOM score for a critical process
        # However, do not use -1000 -- use -900 to leave room
        # because -1000 can cause system-wide OOM if all critical
        # processes are protected and the system truly runs out
        self.set_oom_score_adj(pid, -900)

    def print_oom_report(self) -> None:
        print(f"{'PID':>7} {'OOM':>5} {'ADJ':>5} {'RSS_MB':>8} {'Name':<20}")
        print("-" * 50)
        for info in self.get_top_oom_candidates(15):
            rss_mb = info.rss_kb / 1024
            print(f"{info.pid:>7} {info.oom_score:>5} {info.oom_score_adj:>5} "
                  f"{rss_mb:>8.1f} {info.name:<20}")


if __name__ == "__main__":
    manager = OOMManager()
    manager.print_oom_report()
```

## Memory Overcommit and Its Implications

Linux overcommits memory by default (`/proc/sys/vm/overcommit_memory = 0`). This means `malloc()` and `mmap()` almost never fail — the kernel promises memory it may not have. Physical pages are only allocated on first access (page fault). If the system cannot fulfill a page fault because all physical memory and swap are exhausted, the OOM killer is invoked.

**Best practice**: For production databases and other memory-critical applications, set `overcommit_memory = 2` (strict accounting) and `overcommit_ratio` appropriately. This causes `malloc()` to fail with `ENOMEM` when the system is overcommitted, allowing the application to handle the error gracefully instead of being OOM-killed.

## Summary and Key Takeaways

1. **Virtual memory on x86_64 uses 4-level page tables** where each level contains 512 entries, and the TLB caches translations to avoid the ~200 cycle penalty of a full page table walk — making TLB efficiency critical for performance-sensitive applications
2. **mmap creates VMAs without allocating physical memory** — pages are faulted in on demand, which is why you can map files larger than RAM and why `madvise()` hints are essential for optimal I/O patterns
3. **Transparent Huge Pages reduce TLB pressure by 512x** but can cause latency spikes from synchronous compaction — latency-sensitive applications should use explicit hugetlbfs with pre-allocated pages instead
4. **The OOM killer scores processes primarily by RSS** and can be tuned via `oom_score_adj`, however protecting critical processes with -1000 is dangerous because it shifts OOM kills to other processes and can cause cascading failures
5. **Memory overcommit is the default** on Linux, meaning malloc rarely fails but the OOM killer may terminate your process at any time — strict overcommit mode (`overcommit_memory=2`) gives applications the ability to handle memory exhaustion gracefully
"""
    ),

    # --- 4. Linux Process Management ---
    (
        "linux/process-management-fork-exec-signals-daemons",
        "Explain Linux process management comprehensively including the fork and exec model with copy-on-write optimization, process groups and sessions for job control, the complete signal handling mechanism including real-time signals, zombie process prevention with proper wait patterns, daemon process design following the double-fork method, and Python multiprocessing patterns with shared memory and process pools.",
        r"""# Linux Process Management: fork/exec, Signals, and Daemon Design

## The fork/exec Model

Unix process creation is fundamentally different from Windows's `CreateProcess`. Instead of a single call that creates a process and loads a program, Unix separates these into two steps:

1. **fork()** — creates an exact copy of the calling process (the child). Both parent and child continue executing from the same point, distinguished only by the return value of `fork()` (0 in the child, child's PID in the parent).
2. **exec()** — replaces the current process's memory image with a new program. The PID stays the same, but the code, data, and stack are entirely replaced.

This separation is **not** an accident — it enables powerful patterns like I/O redirection between `fork()` and `exec()`. The shell, for example, forks, sets up pipes and redirections, and then execs the target program.

### Copy-on-Write Optimization

A naive `fork()` would duplicate the entire address space, which would be extremely expensive for large processes. Modern Linux uses **Copy-on-Write (COW)**: after `fork()`, parent and child share the same physical pages, which are marked **read-only** in both page tables. When either process writes to a page, a **page fault** triggers the kernel to allocate a new physical page, copy the contents, and update the page table. This means a `fork()` of a 4 GB process is nearly instantaneous because only the page tables are copied, not the data.

**Common mistake**: Assuming `fork()` is expensive. On modern Linux, `fork()` costs roughly 100-300 microseconds regardless of process size, because COW defers the actual copying. However, calling `fork()` in a multi-threaded process is dangerous because only the calling thread is duplicated — all other threads vanish, potentially leaving mutexes locked and data structures inconsistent.

**Pitfall**: Redis's `BGSAVE` uses `fork()` to create a snapshot. If your Redis instance has 32 GB of data and the workload is write-heavy, COW will eventually copy most pages anyway, doubling memory usage temporarily. This is a well-known production issue.

## Process Groups and Sessions

Linux organizes processes into **process groups** and **sessions** for job control:

- **Process group**: A collection of related processes (e.g., all processes in a pipeline `cat file | grep pattern | sort`). Each group has a **PGID** (Process Group ID) equal to the PID of the group leader.
- **Session**: A collection of process groups, typically associated with a terminal. The session leader is usually the login shell. Each session has at most one **foreground process group** that receives terminal input and signals.

When you press Ctrl+C, the terminal sends `SIGINT` to every process in the **foreground process group**, not just the shell. When you press Ctrl+Z, `SIGTSTP` is sent to the foreground group. This is why `kill -9 %1` kills an entire job.

```c
// Demonstrating process groups, sessions, and job control
// Compile: gcc -o process_groups process_groups.c
#include <unistd.h>
#include <sys/wait.h>
#include <sys/types.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

// Signal handler that prints which signal was received
static void signal_handler(int sig) {
    // Using write() because printf is not async-signal-safe
    const char *msg;
    switch (sig) {
        case SIGINT:  msg = "Caught SIGINT\n"; break;
        case SIGTERM: msg = "Caught SIGTERM\n"; break;
        case SIGCHLD: msg = "Caught SIGCHLD\n"; break;
        case SIGHUP:  msg = "Caught SIGHUP\n"; break;
        default:      msg = "Caught signal\n"; break;
    }
    write(STDOUT_FILENO, msg, strlen(msg));
}

// Create a process group with parent and children
void demonstrate_process_groups(void) {
    pid_t pid1, pid2;

    // Install signal handlers
    struct sigaction sa;
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_RESTART;
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGCHLD, &sa, NULL);

    pid1 = fork();
    if (pid1 == 0) {
        // Child 1: create a new process group
        setpgid(0, 0);  // PGID = own PID
        printf("Child1 PID=%d, PGID=%d, SID=%d\n",
               getpid(), getpgrp(), getsid(0));

        // Fork a grandchild in the same group
        pid2 = fork();
        if (pid2 == 0) {
            printf("Grandchild PID=%d, PGID=%d\n", getpid(), getpgrp());
            pause();  // Wait for signal
            _exit(0);
        }
        pause();
        _exit(0);
    }

    printf("Parent PID=%d, Child1 PID=%d\n", getpid(), pid1);

    // Send SIGTERM to the entire process group
    sleep(1);
    printf("Sending SIGTERM to process group %d\n", pid1);
    kill(-pid1, SIGTERM);  // Negative PID = send to entire group

    // Reap children
    int status;
    while (waitpid(-1, &status, 0) > 0) {
        // Loop until no more children
    }
}

int main(void) {
    demonstrate_process_groups();
    return 0;
}
```

## Signal Handling: The Complete Picture

Signals are the primary **asynchronous notification mechanism** in Unix. There are two categories:

### Standard Signals (1-31)

These are the classic Unix signals. Key behaviors:

- **SIGKILL (9)** and **SIGSTOP (19)** cannot be caught, blocked, or ignored
- **SIGCHLD (17)** is sent to the parent when a child exits — essential for preventing zombies
- **SIGHUP (1)** is sent when the terminal disconnects — daemons traditionally use it to reload configuration
- **SIGPIPE (13)** is sent when writing to a broken pipe — **best practice** is to ignore it and handle `EPIPE` errors from `write()` instead

### Real-Time Signals (SIGRTMIN to SIGRTMAX)

Real-time signals (typically 34-64) have two advantages over standard signals: they are **queued** (multiple instances are not collapsed) and they are delivered in **order** (lowest signal number first). Standard signals are not queued — if `SIGUSR1` is sent three times while blocked, only one delivery occurs.

**Pitfall**: Signal handlers run in an interrupted context. Only **async-signal-safe** functions may be called — `printf()`, `malloc()`, and `mutex_lock()` are NOT safe. The safe approach is to set a `volatile sig_atomic_t` flag in the handler and check it in the main loop, or use `signalfd()` to receive signals as file descriptor events.

## Zombie Processes: Prevention and Cleanup

A **zombie** is a process that has exited but whose parent has not called `wait()` to retrieve its exit status. The kernel keeps the process table entry alive so the parent can read the status. If the parent never calls `wait()`, the zombie persists until the parent itself exits, at which point `init` (PID 1) inherits and reaps it.

```python
# Comprehensive process management in Python
# Covering fork/exec, signal handling, zombie prevention, and daemon design
import os
import sys
import signal
import time
import errno
import multiprocessing as mp
from multiprocessing import shared_memory
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field
import struct
import logging
import atexit

logger = logging.getLogger("procmgr")

# --- Zombie Prevention Patterns ---

class ZombieFreeProcessManager:
    # Prevents zombie processes using multiple strategies
    # because zombies waste process table entries (default limit ~32768)

    def __init__(self) -> None:
        self._children: Dict[int, str] = {}  # pid -> description
        # Install SIGCHLD handler to reap children asynchronously
        signal.signal(signal.SIGCHLD, self._sigchld_handler)

    def _sigchld_handler(self, signum: int, frame: Any) -> None:
        # Reap all finished children without blocking
        # Must use WNOHANG because multiple children may have exited
        # but only one SIGCHLD is delivered (signals are not queued)
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break  # No more finished children
                exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                desc = self._children.pop(pid, "unknown")
                logger.info(f"Reaped child {pid} ({desc}), exit={exit_code}")
            except ChildProcessError:
                break  # No children at all

    def spawn(self, description: str, target: Callable[[], None]) -> int:
        pid = os.fork()
        if pid == 0:
            # Child process
            try:
                target()
            except Exception as e:
                logger.error(f"Child error: {e}")
                os._exit(1)
            os._exit(0)
        else:
            self._children[pid] = description
            logger.info(f"Spawned child {pid} ({description})")
            return pid

    def wait_all(self, timeout: float = 30.0) -> None:
        # Wait for all children with timeout
        deadline = time.monotonic() + timeout
        while self._children and time.monotonic() < deadline:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid > 0:
                    self._children.pop(pid, None)
                else:
                    time.sleep(0.1)
            except ChildProcessError:
                break

        # Force-kill remaining children
        for pid in list(self._children.keys()):
            logger.warning(f"Force-killing child {pid}")
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except ProcessLookupError:
                pass
            self._children.pop(pid, None)


# --- Classic Double-Fork Daemon ---

def daemonize(
    pidfile: str = "/var/run/mydaemon.pid",
    stdin: str = "/dev/null",
    stdout: str = "/dev/null",
    stderr: str = "/dev/null",
) -> None:
    # Classic double-fork daemon pattern
    # First fork: detach from parent
    # Second fork: prevent acquiring a controlling terminal

    # First fork -- parent exits, child continues
    pid = os.fork()
    if pid > 0:
        sys.exit(0)  # Parent exits

    # Create new session -- child becomes session leader
    os.setsid()

    # Second fork -- session leader exits
    # This prevents the daemon from ever acquiring a controlling terminal
    # because only session leaders can acquire a controlling terminal
    pid = os.fork()
    if pid > 0:
        sys.exit(0)  # First child exits

    # Now running as grandchild (daemon)
    # Set working directory to / to avoid holding mount points
    os.chdir("/")
    # Reset file creation mask
    os.umask(0o022)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    with open(stdin, "r") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(stdout, "a+") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open(stderr, "a+") as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

    # Write PID file
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))

    # Register cleanup
    atexit.register(lambda: os.unlink(pidfile))
```

```python
# Python multiprocessing patterns: shared memory, process pools,
# and inter-process communication
import multiprocessing as mp
from multiprocessing import shared_memory, Queue, Event
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import os
import signal
import time
from typing import List, Tuple, Optional
from dataclasses import dataclass

# --- Shared Memory for Zero-Copy IPC ---

@dataclass
class SharedArrayConfig:
    # Configuration for a shared memory numpy array
    name: str
    shape: Tuple[int, ...]
    dtype: str = "float64"

class SharedMemoryArray:
    # Zero-copy shared numpy array between processes
    # because multiprocessing.Queue serializes data (copies it)

    def __init__(self, config: SharedArrayConfig, create: bool = True) -> None:
        self.config = config
        dtype = np.dtype(config.dtype)
        nbytes = int(np.prod(config.shape)) * dtype.itemsize

        if create:
            self._shm = shared_memory.SharedMemory(
                name=config.name, create=True, size=nbytes
            )
        else:
            self._shm = shared_memory.SharedMemory(
                name=config.name, create=False
            )

        self.array = np.ndarray(
            config.shape, dtype=config.dtype, buffer=self._shm.buf
        )

    def close(self) -> None:
        self._shm.close()

    def unlink(self) -> None:
        self._shm.unlink()


def worker_process(
    array_config: SharedArrayConfig,
    start_row: int,
    end_row: int,
    worker_id: int,
) -> Tuple[int, float]:
    # Worker that operates on a slice of shared memory
    # No data is copied -- all workers access the same physical pages
    shm_array = SharedMemoryArray(array_config, create=False)
    try:
        # Compute something on our slice
        chunk = shm_array.array[start_row:end_row]
        result = float(np.sum(chunk ** 2))
        # Write results back to shared memory (in-place)
        shm_array.array[start_row:end_row] = chunk * 2.0
        return worker_id, result
    finally:
        shm_array.close()


def parallel_processing_demo() -> None:
    # Demonstrate shared memory multiprocessing
    rows, cols = 10000, 1000
    config = SharedArrayConfig(
        name="demo_array", shape=(rows, cols), dtype="float64"
    )

    # Create shared array in parent
    shm_array = SharedMemoryArray(config, create=True)
    shm_array.array[:] = np.random.randn(rows, cols)

    num_workers = mp.cpu_count()
    chunk_size = rows // num_workers

    # Launch workers with ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for i in range(num_workers):
            start = i * chunk_size
            end = start + chunk_size if i < num_workers - 1 else rows
            future = executor.submit(
                worker_process, config, start, end, i
            )
            futures.append(future)

        total = 0.0
        for future in as_completed(futures):
            worker_id, partial_sum = future.result()
            total += partial_sum
            print(f"Worker {worker_id}: partial_sum={partial_sum:.2f}")

    print(f"Total sum of squares: {total:.2f}")
    # Verify shared memory was modified by workers
    print(f"Array mean after workers: {shm_array.array.mean():.4f}")

    shm_array.close()
    shm_array.unlink()


# --- Graceful Process Pool with Signal Handling ---

class GracefulProcessPool:
    # Process pool that handles SIGTERM/SIGINT gracefully
    # because the default Pool behavior on signals is to leave workers orphaned

    def __init__(self, num_workers: int = 0) -> None:
        self.num_workers = num_workers or mp.cpu_count()
        self._shutdown_event = Event()
        self._workers: List[mp.Process] = []

    def _install_signal_handlers(self) -> None:
        def shutdown_handler(signum: int, frame) -> None:
            print(f"\nReceived signal {signum}, initiating graceful shutdown")
            self._shutdown_event.set()

        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)

    def start(self, target: mp.Process, args: tuple = ()) -> None:
        self._install_signal_handlers()
        for i in range(self.num_workers):
            p = mp.Process(target=target, args=(self._shutdown_event, i, *args))
            p.daemon = True
            p.start()
            self._workers.append(p)

    def join(self, timeout: float = 30.0) -> None:
        # Wait for graceful shutdown, then force-kill stragglers
        for w in self._workers:
            w.join(timeout=timeout / len(self._workers))
        for w in self._workers:
            if w.is_alive():
                w.terminate()
                w.join(timeout=5)
            if w.is_alive():
                w.kill()


if __name__ == "__main__":
    parallel_processing_demo()
```

```python
# Modern daemon design using systemd socket activation
# because the double-fork pattern is largely obsolete on modern systems
import os
import sys
import socket
import signal
import logging
from typing import Optional, List

logger = logging.getLogger("modern_daemon")

class SystemdDaemon:
    # Modern daemon that integrates with systemd
    # No double-fork needed -- systemd manages the lifecycle
    # Uses sd_notify for readiness signaling

    def __init__(self, name: str) -> None:
        self.name = name
        self._running = True
        self._notify_socket: Optional[str] = os.environ.get("NOTIFY_SOCKET")

    def _sd_notify(self, state: str) -> None:
        # Send notification to systemd via NOTIFY_SOCKET
        if self._notify_socket is None:
            return
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            if self._notify_socket.startswith("@"):
                # Abstract socket
                addr = "\0" + self._notify_socket[1:]
            else:
                addr = self._notify_socket
            sock.connect(addr)
            sock.sendall(state.encode())
        finally:
            sock.close()

    def notify_ready(self) -> None:
        # Tell systemd we are ready to serve
        self._sd_notify("READY=1")

    def notify_stopping(self) -> None:
        self._sd_notify("STOPPING=1")

    def notify_status(self, status: str) -> None:
        self._sd_notify(f"STATUS={status}")

    def notify_watchdog(self) -> None:
        # Respond to systemd watchdog
        self._sd_notify("WATCHDOG=1")

    def get_listen_fds(self) -> List[int]:
        # Get socket-activated file descriptors from systemd
        # systemd passes FDs starting at 3 via LISTEN_FDS env var
        listen_pid = os.environ.get("LISTEN_PID")
        listen_fds = os.environ.get("LISTEN_FDS")

        if listen_pid is None or listen_fds is None:
            return []
        if int(listen_pid) != os.getpid():
            return []

        num_fds = int(listen_fds)
        # FDs start at SD_LISTEN_FDS_START = 3
        return list(range(3, 3 + num_fds))

    def run(self) -> None:
        # Install signal handlers for graceful shutdown
        def handle_term(signum, frame):
            logger.info("Received SIGTERM, shutting down gracefully")
            self._running = False

        signal.signal(signal.SIGTERM, handle_term)
        signal.signal(signal.SIGINT, handle_term)

        # Check for socket activation
        fds = self.get_listen_fds()
        if fds:
            logger.info(f"Socket-activated with {len(fds)} fds")
        else:
            logger.info("No socket activation, creating own socket")

        self.notify_ready()
        self.notify_status("Running")

        while self._running:
            # Main service loop
            self.notify_watchdog()
            time.sleep(1)

        self.notify_stopping()
        logger.info("Daemon stopped cleanly")
```

## Best Practices and Common Pitfalls

- **Best practice**: Use `os.waitpid(-1, os.WNOHANG)` in a loop inside your `SIGCHLD` handler because multiple children can exit between signal deliveries (standard signals are not queued)
- **Pitfall**: Calling `fork()` in a multi-threaded process. Only the calling thread survives in the child — all other threads vanish, potentially leaving locked mutexes and corrupted state. Use `posix_spawn()` or `subprocess.Popen()` instead
- **Trade-off**: The double-fork daemon pattern provides maximum portability but is **obsolete on systemd systems**. Modern daemons should run in the foreground and let systemd manage daemonization, PID files, logging, and socket activation
- **Common mistake**: Ignoring `SIGPIPE`. The default action for `SIGPIPE` is process termination, which means a broken network connection can kill your server. Always `signal(SIGPIPE, SIG_IGN)` and handle `EPIPE` from `write()` instead

## Summary and Key Takeaways

1. **fork() is nearly free due to Copy-on-Write** — only page tables are copied, and physical pages are shared until modified, making process creation a ~200 microsecond operation regardless of process size
2. **Process groups and sessions** enable job control by grouping related processes so that signals like SIGINT (Ctrl+C) are delivered to all processes in the foreground group simultaneously
3. **Signal handlers must only call async-signal-safe functions** — using printf, malloc, or mutex operations in signal handlers causes undefined behavior. The safest pattern is setting a flag or using signalfd()
4. **Zombie prevention requires calling wait()** in a SIGCHLD handler with WNOHANG in a loop, because standard signals are not queued and multiple children may exit before the handler runs
5. **Modern daemons should use systemd integration** (sd_notify, socket activation, watchdog) rather than the classic double-fork pattern, which is now an unnecessary complication on systems with a service manager
"""
    ),

    # --- 5. Linux Filesystem Internals ---
    (
        "linux/filesystem-internals-vfs-inodes-journaling",
        "Explain Linux filesystem internals comprehensively including the Virtual Filesystem Switch layer and its abstraction of filesystem operations, inode structure and how hard links and soft links work at the inode level, journaling strategies in ext4 versus XFS versus btrfs with their trade-offs, file descriptor tables and the three-level indirection from process to inode, and provide Python examples of low-level file I/O using os module functions and direct file descriptor manipulation.",
        r"""# Linux Filesystem Internals: VFS, Inodes, Journaling, and File Descriptors

## The Virtual Filesystem Switch (VFS)

The VFS is one of the most elegant abstractions in the Linux kernel. It provides a **uniform interface** for all filesystem operations, allowing user-space programs to use the same system calls (`open`, `read`, `write`, `stat`) regardless of whether the underlying storage is ext4, XFS, btrfs, NFS, procfs, or even FUSE. The VFS defines a set of **function pointer tables** (similar to vtables in C++) that each filesystem implements.

### VFS Core Objects

The VFS manages four primary objects:

1. **Superblock** (`struct super_block`) — represents a mounted filesystem. Contains metadata like block size, total/free blocks, and a pointer to the filesystem-specific operations table (`super_operations`).

2. **Inode** (`struct inode`) — represents a file on disk. Contains metadata (permissions, timestamps, size, block pointers) but **not** the filename. The inode number uniquely identifies a file within a filesystem.

3. **Dentry** (`struct dentry`) — represents a directory entry, mapping a name to an inode. Dentries are cached in the **dentry cache (dcache)** for fast pathname lookup. The dcache is one of the most performance-critical caches in the kernel.

4. **File** (`struct file`) — represents an open file. Contains the current file offset, access mode, and a pointer to the `file_operations` table. Multiple file objects can point to the same dentry/inode (e.g., when a file is opened by multiple processes).

### How a File Open Works Through VFS

When a process calls `open("/home/user/data.txt", O_RDONLY)`:

1. The VFS performs **pathname lookup** by walking the dentry cache: `/` -> `home` -> `user` -> `data.txt`. Each component lookup calls the parent inode's `lookup` operation.
2. If a dentry is not in the cache, the VFS calls the filesystem's `lookup` method to read the directory from disk and populate the dentry.
3. Once the final inode is found, the VFS allocates a `struct file`, sets up the `file_operations` pointer to the filesystem's read/write implementations, and returns a **file descriptor** (an integer index into the process's fd table).

**Best practice**: Minimize path lookups by opening files once and reusing the fd. Each `open()` call triggers a dentry lookup, which is fast for cached paths but expensive for deep directory trees on slow storage.

## Inode Structure and Links

### Inode Contents

An inode stores everything about a file **except its name**:

- **File type** (regular file, directory, symlink, device, socket, pipe, FIFO)
- **Permissions** (rwxrwxrwx + setuid/setgid/sticky bits)
- **Ownership** (UID, GID)
- **Timestamps** (atime, mtime, ctime, and on ext4, crtime for creation time)
- **Size** in bytes
- **Link count** — number of hard links
- **Block pointers** — how to find the file's data on disk

### Hard Links vs Symbolic Links

**Hard links** are additional directory entries (dentries) pointing to the same inode. Because they share the inode, they share all metadata and data. The inode's **link count** tracks how many hard links exist. The file's data is only freed when the link count reaches zero AND no process has the file open.

**Symbolic links (symlinks)** are separate inodes that contain a pathname string. They are indirection — the kernel follows the symlink to resolve the target path. Symlinks can cross filesystem boundaries (because they reference paths, not inodes), while hard links cannot (because inode numbers are filesystem-local).

**Pitfall**: Deleting the target of a symbolic link creates a **dangling symlink** that points to nothing. Hard links never dangle because they reference the inode directly.

```c
// Demonstrating inode operations: hard links, symlinks, and stat
// Compile: gcc -o inode_demo inode_demo.c
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <stdio.h>
#include <fcntl.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>

// Print inode information for a path
static void print_inode_info(const char *path) {
    struct stat st;
    if (lstat(path, &st) == -1) {
        printf("  %s: %s\n", path, strerror(errno));
        return;
    }
    printf("  %s:\n", path);
    printf("    inode:   %lu\n", (unsigned long)st.st_ino);
    printf("    links:   %lu\n", (unsigned long)st.st_nlink);
    printf("    size:    %ld bytes\n", (long)st.st_size);
    printf("    blocks:  %ld (512-byte)\n", (long)st.st_blocks);
    printf("    type:    ");
    if (S_ISREG(st.st_mode))       printf("regular file\n");
    else if (S_ISDIR(st.st_mode))  printf("directory\n");
    else if (S_ISLNK(st.st_mode))  printf("symbolic link\n");
    else                            printf("other\n");
}

int main(void) {
    // Create a file
    int fd = open("/tmp/inode_demo.txt", O_CREAT | O_WRONLY | O_TRUNC, 0644);
    write(fd, "Hello, inodes!\n", 15);
    close(fd);

    printf("After creation:\n");
    print_inode_info("/tmp/inode_demo.txt");

    // Create a hard link -- same inode, link count increases
    link("/tmp/inode_demo.txt", "/tmp/inode_hardlink.txt");
    printf("\nAfter hard link:\n");
    print_inode_info("/tmp/inode_demo.txt");
    print_inode_info("/tmp/inode_hardlink.txt");
    // Both show the SAME inode number and link count = 2

    // Create a symbolic link -- different inode
    symlink("/tmp/inode_demo.txt", "/tmp/inode_symlink.txt");
    printf("\nAfter symlink:\n");
    print_inode_info("/tmp/inode_demo.txt");
    print_inode_info("/tmp/inode_symlink.txt");
    // Different inode number, symlink size = length of target path

    // Delete original -- hard link survives, symlink dangles
    unlink("/tmp/inode_demo.txt");
    printf("\nAfter deleting original:\n");
    print_inode_info("/tmp/inode_hardlink.txt");  // Still works, link count = 1
    print_inode_info("/tmp/inode_symlink.txt");   // Dangling: No such file

    // Cleanup
    unlink("/tmp/inode_hardlink.txt");
    unlink("/tmp/inode_symlink.txt");
    return 0;
}
```

## Journaling: ext4 vs XFS vs btrfs

Journaling protects filesystem **metadata consistency** (and optionally data) in case of a crash. Without journaling, a crash during a multi-step operation (e.g., creating a file requires updating the directory, allocating an inode, and allocating data blocks) can leave the filesystem in an inconsistent state requiring a full `fsck`.

### ext4 Journaling

ext4 uses the **JBD2 (Journaling Block Device 2)** layer with three modes:

- **journal**: All data and metadata are written to the journal before being committed to the filesystem. Safest but slowest (~50% write throughput penalty).
- **ordered** (default): Only metadata is journaled, but data blocks are written **before** the metadata journal commit. This guarantees that if metadata says a file has been extended, the data is already on disk. A **trade-off** between safety and performance.
- **writeback**: Only metadata is journaled, and data may be written after metadata. Fastest but can expose stale data after a crash (a newly extended file might contain old disk contents).

### XFS

XFS uses a **write-ahead log (WAL)** for metadata journaling. It is designed for large filesystems and excels at parallel I/O because of its **allocation group** architecture — the filesystem is divided into independent allocation groups, each with its own inode allocator, free space index, and journal. This allows concurrent operations in different parts of the filesystem without lock contention.

**Best practice**: Use XFS for large-file workloads (databases, media) because it uses **extent-based allocation** natively (a single extent can describe up to 2^21 contiguous blocks, reducing metadata overhead for large files).

### btrfs (B-tree Filesystem)

btrfs takes a fundamentally different approach: **Copy-on-Write (COW)** for both data and metadata. Instead of updating in place, btrfs writes new data to free space and then atomically updates the pointer. This enables:

- **Snapshots**: Nearly instantaneous because they just copy the root pointer
- **Built-in RAID**: Supports RAID 0, 1, 10, 5, 6 at the filesystem level
- **Checksumming**: Every data and metadata block is checksummed (CRC32C by default), detecting silent data corruption
- **Send/receive**: Efficient incremental backup via `btrfs send`

**However**, btrfs has a well-known **write amplification** problem for random writes because COW means every small write creates a new copy of the affected block. This is particularly harmful for databases that perform many small random writes.

| Feature | ext4 | XFS | btrfs |
|---|---|---|---|
| **Journal type** | JBD2 (ordered) | WAL (metadata) | COW (no journal needed) |
| **Max file size** | 16 TB | 8 EB | 16 EB |
| **Snapshots** | No | No | Yes (instant COW) |
| **Checksums** | Metadata only | Metadata only | Data + metadata |
| **RAID** | External (mdadm) | External | Built-in |
| **Best for** | General purpose | Large files, DBs | Snapshots, integrity |

## File Descriptor Tables: Three-Level Indirection

When a process opens a file, three kernel data structures are involved:

1. **Per-process fd table** (`struct fdtable` in `struct files_struct`) — an array indexed by the fd integer. Each entry points to a `struct file`.
2. **Open file table** (`struct file`) — contains the file offset, access mode, and a pointer to the dentry. This is shared when a process `fork()`s or uses `dup()`.
3. **Inode table** — the VFS inode, shared across all opens of the same file.

**Common mistake**: Assuming that closing fd 3 in a forked child closes it in the parent. After `fork()`, parent and child have separate fd tables but the `struct file` entries are **shared** (reference counted). Closing an fd in one process only decrements the reference count — the other process's fd remains valid.

```python
# Low-level file I/O in Python using os module
# Demonstrating file descriptors, dup, fstat, and direct I/O
import os
import sys
import stat
import fcntl
import struct
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class FdInfo:
    # Information about an open file descriptor
    fd: int
    path: str
    mode: int
    flags: int
    offset: int
    inode: int
    link_count: int
    size: int
    is_regular: bool
    is_socket: bool
    is_pipe: bool

class FileDescriptorInspector:
    # Inspect and manipulate file descriptors at the OS level
    # because understanding fd tables is essential for debugging
    # resource leaks and I/O issues

    @staticmethod
    def inspect_fd(fd: int) -> Optional[FdInfo]:
        try:
            st = os.fstat(fd)
            # Read the symlink target in /proc/self/fd/<n>
            try:
                path = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                path = "<unknown>"

            flags = fcntl.fcntl(fd, fcntl.F_GETFL)

            return FdInfo(
                fd=fd,
                path=path,
                mode=st.st_mode,
                flags=flags,
                offset=os.lseek(fd, 0, os.SEEK_CUR) if stat.S_ISREG(st.st_mode) else 0,
                inode=st.st_ino,
                link_count=st.st_nlink,
                size=st.st_size,
                is_regular=stat.S_ISREG(st.st_mode),
                is_socket=stat.S_ISSOCK(st.st_mode),
                is_pipe=stat.S_ISFIFO(st.st_mode),
            )
        except OSError:
            return None

    def list_open_fds(self) -> List[FdInfo]:
        # List all open file descriptors for the current process
        fds: List[FdInfo] = []
        fd_dir = Path("/proc/self/fd")
        if not fd_dir.exists():
            return fds
        for entry in fd_dir.iterdir():
            try:
                fd = int(entry.name)
                info = self.inspect_fd(fd)
                if info is not None:
                    fds.append(info)
            except (ValueError, OSError):
                pass
        return sorted(fds, key=lambda f: f.fd)

    def detect_fd_leaks(self, baseline: int = 10) -> List[FdInfo]:
        # Find potentially leaked file descriptors
        # Heuristic: any fd > baseline that is not stdin/stdout/stderr
        # and is not the /proc/self/fd directory itself
        fds = self.list_open_fds()
        return [f for f in fds if f.fd > baseline]


class LowLevelFileOps:
    # Direct file descriptor operations bypassing Python's file objects
    # Useful for atomic operations, advisory locking, and direct I/O

    @staticmethod
    def atomic_write(path: str, data: bytes, mode: int = 0o644) -> None:
        # Atomic file write using rename
        # Write to a temp file, fsync, then rename
        # because rename() is atomic on POSIX filesystems
        tmp_path = path + ".tmp"
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            os.write(fd, data)
            os.fsync(fd)  # Ensure data is on disk
        finally:
            os.close(fd)
        # Atomic rename -- this is the commit point
        os.rename(tmp_path, path)
        # Also fsync the directory to ensure the rename is persisted
        dir_fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    @staticmethod
    def advisory_lock(fd: int, exclusive: bool = True, block: bool = True) -> bool:
        # POSIX advisory file locking via fcntl
        # Advisory locks are only enforced for cooperating processes
        lock_type = fcntl.F_WRLCK if exclusive else fcntl.F_RDLCK
        cmd = fcntl.F_SETLKW if block else fcntl.F_SETLK

        # struct flock: type, whence, start, len, pid
        lock_data = struct.pack("hhqqi", lock_type, 0, 0, 0, 0)
        try:
            fcntl.fcntl(fd, cmd, lock_data)
            return True
        except OSError:
            return False

    @staticmethod
    def release_lock(fd: int) -> None:
        lock_data = struct.pack("hhqqi", fcntl.F_UNLCK, 0, 0, 0, 0)
        fcntl.fcntl(fd, fcntl.F_SETLK, lock_data)

    @staticmethod
    def dup_redirect(old_fd: int, new_fd: int) -> None:
        # Duplicate old_fd onto new_fd (closing new_fd first)
        # This is how shell I/O redirection works:
        # dup2(pipe_fd, STDOUT_FILENO) redirects stdout to the pipe
        os.dup2(old_fd, new_fd)

    @staticmethod
    def get_file_flags(fd: int) -> Dict[str, bool]:
        # Read file status flags
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        return {
            "O_RDONLY": (flags & os.O_RDONLY) == os.O_RDONLY,
            "O_WRONLY": (flags & os.O_WRONLY) == os.O_WRONLY,
            "O_RDWR": (flags & os.O_RDWR) == os.O_RDWR,
            "O_NONBLOCK": bool(flags & os.O_NONBLOCK),
            "O_APPEND": bool(flags & os.O_APPEND),
            "O_SYNC": bool(flags & os.O_SYNC),
        }


def demonstrate_fd_operations() -> None:
    inspector = FileDescriptorInspector()
    ops = LowLevelFileOps()

    # Show all open file descriptors
    print("Open file descriptors:")
    for info in inspector.list_open_fds():
        print(f"  fd={info.fd:>3}  inode={info.inode:<12}  "
              f"links={info.link_count}  {info.path}")

    # Demonstrate atomic write
    test_path = "/tmp/atomic_test.txt"
    ops.atomic_write(test_path, b"atomically written data\n")

    # Open and inspect
    fd = os.open(test_path, os.O_RDONLY)
    info = inspector.inspect_fd(fd)
    if info:
        print(f"\nOpened {test_path}:")
        print(f"  fd={info.fd}, inode={info.inode}, size={info.size}")
        print(f"  flags: {ops.get_file_flags(fd)}")

    # Demonstrate dup2 -- duplicate fd onto a new number
    new_fd = os.dup(fd)
    print(f"\n  Duplicated fd {fd} -> {new_fd}")
    new_info = inspector.inspect_fd(new_fd)
    if new_info:
        print(f"  Both point to same inode: {info.inode == new_info.inode}")

    os.close(fd)
    os.close(new_fd)

    # Demonstrate advisory locking
    fd = os.open(test_path, os.O_RDWR)
    locked = ops.advisory_lock(fd, exclusive=True, block=False)
    print(f"\nAdvisory lock acquired: {locked}")
    ops.release_lock(fd)
    os.close(fd)
    os.unlink(test_path)


if __name__ == "__main__":
    demonstrate_fd_operations()
```

```python
# File I/O performance patterns: buffered vs direct, fsync strategies,
# and the write-ahead log pattern used by databases
import os
import time
import struct
import hashlib
from typing import BinaryIO, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# O_DIRECT requires aligned buffers and aligned offsets
# Not all filesystems support it (btrfs does, NFS may not)
O_DIRECT = 0o40000  # 16384

@dataclass
class WALEntry:
    # Write-ahead log entry for crash-consistent writes
    sequence: int
    operation: str  # "write", "delete", "truncate"
    offset: int
    length: int
    checksum: bytes
    data: bytes

class WriteAheadLog:
    # Simplified WAL implementation demonstrating the pattern
    # used by databases (PostgreSQL, SQLite) for crash consistency
    # because fsync alone is not enough for multi-step operations

    HEADER_FORMAT = "!QcQQ32s"  # seq, op, offset, length, checksum
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(self, wal_path: str, data_path: str) -> None:
        self.wal_path = wal_path
        self.data_path = data_path
        self._sequence: int = 0
        self._wal_fd: Optional[int] = None
        self._data_fd: Optional[int] = None

    def open(self) -> None:
        self._wal_fd = os.open(
            self.wal_path,
            os.O_CREAT | os.O_RDWR | os.O_APPEND,
            0o644,
        )
        self._data_fd = os.open(
            self.data_path,
            os.O_CREAT | os.O_RDWR,
            0o644,
        )

    def close(self) -> None:
        if self._wal_fd is not None:
            os.close(self._wal_fd)
        if self._data_fd is not None:
            os.close(self._data_fd)

    def append(self, offset: int, data: bytes) -> int:
        # Write to WAL first, then to data file
        # This ensures crash consistency: on recovery, replay the WAL
        if self._wal_fd is None or self._data_fd is None:
            raise RuntimeError("WAL not opened")

        self._sequence += 1
        checksum = hashlib.sha256(data).digest()

        # Write WAL entry: header + data
        header = struct.pack(
            self.HEADER_FORMAT,
            self._sequence,
            b"w",  # write operation
            offset,
            len(data),
            checksum,
        )
        os.write(self._wal_fd, header + data)
        # fsync the WAL -- this is the commit point
        # After this fsync, the write is guaranteed to be recoverable
        os.fsync(self._wal_fd)

        # Now apply to the data file
        os.lseek(self._data_fd, offset, os.SEEK_SET)
        os.write(self._data_fd, data)
        # fsync data file (can be deferred for better throughput)
        os.fsync(self._data_fd)

        return self._sequence

    def recover(self) -> int:
        # Replay WAL entries to recover from a crash
        if self._wal_fd is None or self._data_fd is None:
            raise RuntimeError("WAL not opened")

        os.lseek(self._wal_fd, 0, os.SEEK_SET)
        replayed = 0

        while True:
            header_data = os.read(self._wal_fd, self.HEADER_SIZE)
            if len(header_data) < self.HEADER_SIZE:
                break

            seq, op, offset, length, checksum = struct.unpack(
                self.HEADER_FORMAT, header_data
            )
            data = os.read(self._wal_fd, length)

            # Verify checksum
            if hashlib.sha256(data).digest() != checksum:
                print(f"Corrupt WAL entry at seq {seq}, stopping recovery")
                break

            # Apply to data file
            os.lseek(self._data_fd, offset, os.SEEK_SET)
            os.write(self._data_fd, data)
            replayed += 1

        os.fsync(self._data_fd)
        return replayed


def benchmark_sync_strategies(filepath: str, num_writes: int = 1000) -> None:
    # Compare different fsync strategies for write performance
    data = b"x" * 4096  # 4 KB writes

    # Strategy 1: fsync after every write (safest, slowest)
    fd = os.open(filepath, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    start = time.perf_counter()
    for _ in range(num_writes):
        os.write(fd, data)
        os.fsync(fd)
    sync_every = time.perf_counter() - start
    os.close(fd)

    # Strategy 2: fsync after all writes (fastest, no crash safety)
    fd = os.open(filepath, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    start = time.perf_counter()
    for _ in range(num_writes):
        os.write(fd, data)
    os.fsync(fd)
    sync_once = time.perf_counter() - start
    os.close(fd)

    # Strategy 3: fdatasync (skips metadata update, good trade-off)
    fd = os.open(filepath, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    start = time.perf_counter()
    for _ in range(num_writes):
        os.write(fd, data)
        os.fdatasync(fd)
    dsync_every = time.perf_counter() - start
    os.close(fd)

    total_mb = (num_writes * len(data)) / (1024 * 1024)
    print(f"Write benchmark: {num_writes} x {len(data)} bytes = {total_mb:.1f} MB")
    print(f"  fsync every write:    {sync_every:.3f}s "
          f"({total_mb/sync_every:.0f} MB/s)")
    print(f"  fsync once at end:    {sync_once:.3f}s "
          f"({total_mb/sync_once:.0f} MB/s)")
    print(f"  fdatasync every write: {dsync_every:.3f}s "
          f"({total_mb/dsync_every:.0f} MB/s)")

    os.unlink(filepath)


if __name__ == "__main__":
    benchmark_sync_strategies("/tmp/sync_bench.dat")
```

## fsync and Data Durability Gotchas

- **Pitfall**: Calling `fsync()` on the file but not on the **directory**. On ext4, a new file's directory entry is not guaranteed to be persisted until the directory inode is also fsynced. If the system crashes after writing the file but before the directory entry is persisted, the file vanishes
- **Common mistake**: Assuming `close()` flushes data to disk. It does NOT. `close()` only releases the fd and flushes the kernel buffer cache write-back timer. Use `fsync()` or `fdatasync()` for durability guarantees
- **Best practice**: Use `fdatasync()` instead of `fsync()` when you only need data durability (not metadata like timestamps). `fdatasync()` skips the metadata journal flush, which can be **2-10x faster** on journaled filesystems
- **Trade-off**: `O_DIRECT` bypasses the page cache for direct disk access, reducing memory pressure but requiring the application to manage its own buffering. Databases like PostgreSQL use `O_DIRECT` because they have their own buffer pool, however most applications should use the page cache

## Summary and Key Takeaways

1. **The VFS layer abstracts filesystem differences** through function pointer tables (superblock_operations, inode_operations, file_operations), allowing any filesystem to be accessed through the same syscall interface — this is why `cat` works identically on ext4, XFS, NFS, and procfs
2. **Inodes store all file metadata except the name** — hard links are multiple directory entries pointing to the same inode (same data, shared link count), while symlinks are separate inodes containing a target path string that can dangle if the target is deleted
3. **ext4 uses JBD2 ordered journaling by default** (metadata journaled, data written first), XFS excels at parallel I/O with allocation groups, and btrfs provides COW snapshots and data checksumming at the cost of write amplification for random workloads
4. **File descriptors involve three-level indirection** — the per-process fd table points to a shared open file description (with offset and flags), which points to the inode — and fork() shares file descriptions while dup() creates a new fd pointing to the same description
5. **Data durability requires explicit fsync/fdatasync** — close() does not guarantee persistence, new files require directory fsync, and fdatasync is significantly faster than fsync when metadata durability is not needed
"""
    ),
]
