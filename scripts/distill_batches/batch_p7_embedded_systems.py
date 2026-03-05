"""
Batch P7 — Embedded Systems Programming
Covers: bare-metal Rust, RTOS scheduling, communication protocols (SPI/I2C/CAN),
memory management in constrained environments, embedded testing and debugging.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "embedded/bare-metal-rust",
        "Explain bare-metal embedded Rust programming with no_std, HAL, PAC, and the RTIC real-time framework, including GPIO driver implementation, UART communication, and interrupt handling on STM32 microcontrollers with ownership model benefits for hardware safety",
        r"""# Bare-Metal Embedded Rust: Safe Hardware Programming Without an OS

## Why Rust for Embedded Systems

Rust has become a **first-class language for embedded development** because it solves the fundamental tension in systems programming: you need zero-cost abstractions and direct hardware access, but you also need memory safety guarantees. C gives you the performance but leaves you vulnerable to buffer overflows, use-after-free, and data races in interrupt handlers. Rust eliminates these entire classes of bugs **at compile time** with zero runtime overhead.

The key insight is that Rust's **ownership model** maps naturally onto hardware resources. A UART peripheral is a singleton — there's exactly one UART1 on your chip. Rust's type system can enforce that only one piece of code owns the UART at any time, preventing the classic embedded bug where two interrupt handlers accidentally stomp on each other's register writes. This is not an abstract benefit — it catches real bugs that would otherwise require hours of oscilloscope debugging.

### The no_std Ecosystem

When you write `#![no_std]` at the top of your crate, you opt out of Rust's standard library (which requires an OS with heap allocation, threads, and I/O). Instead, you get `core` — the subset of Rust that works on bare metal: iterators, `Option`, `Result`, slices, and all the zero-cost abstractions, but no `Vec`, no `String`, no `println!`. This is the foundation of embedded Rust.

The embedded Rust ecosystem is built in layers:

- **PAC (Peripheral Access Crate)**: Auto-generated from SVD files, provides raw register access with type safety
- **HAL (Hardware Abstraction Layer)**: Implements `embedded-hal` traits on top of PAC, giving you portable GPIO, SPI, I2C, UART abstractions
- **BSP (Board Support Package)**: Maps HAL peripherals to specific board pins and features
- **RTIC**: A real-time interrupt-driven concurrency framework that uses Rust's type system to guarantee deadlock-free execution

## Implementing a GPIO Driver on STM32

Let's build from the ground up. First, here's how you configure GPIO pins using the STM32F4 HAL, **because** the HAL provides type-state programming that prevents you from reading an output pin or writing to an input pin at compile time:

```rust
#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use stm32f4xx_hal::{
    gpio::{Output, PushPull, Input, PullUp, Edge, ExtiPin},
    pac,
    prelude::*,
};

# Type-state GPIO: the compiler tracks pin configuration
# Pin<'A', 5, Output<PushPull>> is a DIFFERENT TYPE than Pin<'A', 5, Input<PullUp>>
# Therefore you cannot accidentally read an output-only pin

#[entry]
fn main() -> ! {
    let dp = pac::Peripherals::take().unwrap();
    let rcc = dp.RCC.constrain();
    let clocks = rcc.cfgr.sysclk(168.MHz()).freeze();

    let gpioa = dp.GPIOA.split();
    let gpioc = dp.GPIOC.split();

    # Configure PA5 as push-pull output (onboard LED on Nucleo boards)
    # The into_push_pull_output() consumes the pin and returns a new type
    let mut led = gpioa.pa5.into_push_pull_output();

    # Configure PC13 as input with pull-up (user button)
    let button = gpioc.pc13.into_pull_up_input();

    # Type safety in action: this would NOT compile:
    # button.set_high();  // Error: Input pins don't implement OutputPin
    # led.is_high();      // Error: Output pins don't implement InputPin

    let mut delay = dp.TIM2.delay_ms(&clocks);

    loop {
        if button.is_low() {
            # Button pressed (active low with pull-up)
            led.set_high();
        } else {
            led.set_low();
        }
        delay.delay_ms(10u32);  # Debounce delay
    }
}
```

The **best practice** here is to use type-state programming extensively. Notice how `into_push_pull_output()` consumes the unconfigured pin and returns a pin typed as `Output<PushPull>`. This means pin misconfiguration is a **compile-time error**, not a runtime bug. This is a **zero-cost abstraction** — the type information exists only at compile time and generates the same machine code as raw register writes.

## UART Communication with Interrupts

UART is the workhorse of embedded debugging and inter-device communication. Here's a complete UART implementation with interrupt-driven reception, **because** polling-based UART wastes CPU cycles and can miss bytes at high baud rates:

```rust
#![no_std]
#![no_main]

use core::cell::RefCell;
use core::fmt::Write;
use cortex_m::interrupt::Mutex;
use cortex_m_rt::entry;
use panic_halt as _;
use stm32f4xx_hal::{
    gpio::{Alternate, Pin},
    pac::{self, interrupt, USART2},
    prelude::*,
    serial::{config::Config, Event, Serial, Rx, Tx},
};

# Global state protected by a Mutex (critical-section based)
# The Mutex<RefCell<Option<T>>> pattern is the standard way to share
# peripherals between main code and interrupt handlers in embedded Rust
static SERIAL_RX: Mutex<RefCell<Option<Rx<USART2>>>> = Mutex::new(RefCell::new(None));
static RX_BUFFER: Mutex<RefCell<[u8; 256]>> = Mutex::new(RefCell::new([0u8; 256]));
static RX_HEAD: Mutex<RefCell<usize>> = Mutex::new(RefCell::new(0));

#[entry]
fn main() -> ! {
    let dp = pac::Peripherals::take().unwrap();
    let rcc = dp.RCC.constrain();
    let clocks = rcc.cfgr.sysclk(168.MHz()).freeze();

    let gpioa = dp.GPIOA.split();

    # Configure UART pins — PA2 = TX, PA3 = RX
    let tx_pin = gpioa.pa2.into_alternate::<7>();
    let rx_pin = gpioa.pa3.into_alternate::<7>();

    # Configure UART: 115200 baud, 8N1
    let mut serial = Serial::new(
        dp.USART2,
        (tx_pin, rx_pin),
        Config::default().baudrate(115_200.bps()),
        &clocks,
    ).unwrap();

    # Enable RXNE interrupt (Receive Not Empty)
    serial.listen(Event::Rxne);

    let (tx, rx) = serial.split();

    # Move RX into the global so the interrupt handler can access it
    cortex_m::interrupt::free(|cs| {
        SERIAL_RX.borrow(cs).replace(Some(rx));
    });

    # Enable USART2 interrupt in the NVIC
    unsafe {
        cortex_m::peripheral::NVIC::unmask(pac::Interrupt::USART2);
    }

    let mut tx = tx;
    writeln!(tx, "System initialized. Waiting for data...").unwrap();

    loop {
        cortex_m::asm::wfi();  # Sleep until interrupt
    }
}

# Interrupt handler for USART2
# This fires every time a byte is received
#[interrupt]
fn USART2() {
    cortex_m::interrupt::free(|cs| {
        if let Some(ref mut rx) = SERIAL_RX.borrow(cs).borrow_mut().as_mut() {
            if let Ok(byte) = rx.read() {
                let mut buf = RX_BUFFER.borrow(cs).borrow_mut();
                let mut head = RX_HEAD.borrow(cs).borrow_mut();
                buf[*head] = byte;
                *head = (*head + 1) % buf.len();  # Ring buffer wrap
            }
        }
    });
}
```

A **common mistake** in embedded Rust is trying to share peripherals between `main()` and interrupt handlers without proper synchronization. The `Mutex<RefCell<Option<T>>>` pattern shown above is verbose but correct — the `cortex_m::interrupt::free` function disables interrupts for the duration of the closure, ensuring exclusive access. However, this approach has a **pitfall**: if you hold the critical section too long, you'll increase interrupt latency and potentially miss time-critical events.

## RTIC: Zero-Cost Concurrency

RTIC (Real-Time Interrupt-driven Concurrency) solves the ergonomics problem of the `Mutex<RefCell<Option<T>>>` pattern. It uses Rust's type system and procedural macros to **statically guarantee** deadlock freedom and provide **priority-based preemptive scheduling** with zero runtime overhead:

```rust
#![no_std]
#![no_main]

use panic_halt as _;
use rtic::app;
use stm32f4xx_hal::{
    gpio::{Output, PushPull, Pin},
    pac,
    prelude::*,
    serial::{config::Config, Event, Serial, Rx, Tx},
    timer::{CounterMs, Event as TimerEvent},
};

#[app(device = stm32f4xx_hal::pac, peripherals = true, dispatchers = [SPI1])]
mod app {
    use super::*;

    # Shared resources — RTIC generates the locking code automatically
    # Resources with the same ceiling priority share a lock
    #[shared]
    struct Shared {
        rx_count: u32,
        # RTIC ensures this is only accessed with proper locking
        serial_tx: Tx<pac::USART2>,
    }

    # Local resources — owned by exactly one task, no locking needed
    #[local]
    struct Local {
        led: Pin<'A', 5, Output<PushPull>>,
        serial_rx: Rx<pac::USART2>,
        timer: CounterMs<pac::TIM2>,
    }

    #[init]
    fn init(ctx: init::Context) -> (Shared, Local) {
        let dp = ctx.device;
        let rcc = dp.RCC.constrain();
        let clocks = rcc.cfgr.sysclk(168.MHz()).freeze();

        let gpioa = dp.GPIOA.split();
        let led = gpioa.pa5.into_push_pull_output();
        let tx_pin = gpioa.pa2.into_alternate::<7>();
        let rx_pin = gpioa.pa3.into_alternate::<7>();

        let mut serial = Serial::new(
            dp.USART2,
            (tx_pin, rx_pin),
            Config::default().baudrate(115_200.bps()),
            &clocks,
        ).unwrap();
        serial.listen(Event::Rxne);
        let (tx, rx) = serial.split();

        # Configure 1-second timer for status reports
        let mut timer = dp.TIM2.counter_ms(&clocks);
        timer.start(1000.millis()).unwrap();
        timer.listen(TimerEvent::Update);

        (
            Shared { rx_count: 0, serial_tx: tx },
            Local { led, serial_rx: rx, timer },
        )
    }

    # Hardware task: UART receive interrupt (high priority)
    #[task(binds = USART2, local = [serial_rx], shared = [rx_count], priority = 2)]
    fn uart_rx(mut ctx: uart_rx::Context) {
        if let Ok(_byte) = ctx.local.serial_rx.read() {
            ctx.shared.rx_count.lock(|count| {
                *count += 1;
            });
            # Spawn a lower-priority task to process the data
            process_byte::spawn().ok();
        }
    }

    # Hardware task: timer interrupt (medium priority)
    #[task(binds = TIM2, local = [led, timer], shared = [rx_count, serial_tx], priority = 1)]
    fn timer_tick(mut ctx: timer_tick::Context) {
        ctx.local.timer.clear_interrupt(TimerEvent::Update);
        ctx.local.led.toggle();

        let count = ctx.shared.rx_count.lock(|c| *c);
        ctx.shared.serial_tx.lock(|tx| {
            use core::fmt::Write;
            writeln!(tx, "Bytes received: {}", count).ok();
        });
    }

    # Software task: deferred processing (lowest priority)
    #[task(priority = 0)]
    async fn process_byte(_ctx: process_byte::Context) {
        # Process received byte without blocking the UART interrupt
        # This runs at the lowest priority, so it won't delay
        # time-critical UART reception
    }
}
```

The **trade-off** with RTIC is that it requires you to declare all resources and their access patterns upfront. This feels restrictive compared to FreeRTOS's dynamic approach, **however** RTIC's static analysis catches race conditions, priority inversions, and deadlocks at compile time. The generated code uses the hardware's priority ceiling protocol — no runtime scheduler, no heap allocation, no tick interrupt. The **best practice** is to use RTIC for any project with more than two interrupt handlers, because the complexity of manual locking scales poorly.

### Ownership Model Benefits for Hardware Safety

The single most important benefit of Rust for embedded programming is the **ownership model applied to hardware peripherals**. Consider these guarantees:

1. **Singleton enforcement**: `Peripherals::take()` returns `Option<Peripherals>` — you can only call it once. This prevents the classic C bug of two modules both configuring the same peripheral differently.

2. **Move semantics for pins**: When you call `gpioa.pa5.into_push_pull_output()`, the original pin value is **consumed**. You cannot accidentally use the unconfigured pin afterward.

3. **Borrow checker for DMA**: If you start a DMA transfer from a buffer, the borrow checker prevents you from modifying that buffer until the transfer completes. In C, this is a race condition waiting to happen.

4. **Type-state for protocols**: SPI chip select management, UART flow control, and I2C bus states can all be encoded in the type system, making protocol violations impossible.

A **common mistake** when coming from C is trying to use `unsafe` everywhere to bypass these restrictions. The Rust embedded community's guideline is: if you need `unsafe` outside of PAC register access and interrupt handler setup, you're probably doing something wrong. The HAL should encapsulate all unsafety.

## Key Takeaways

- Rust's **ownership model** maps naturally to hardware singletons — the compiler enforces that each peripheral has exactly one owner, preventing register stomping and race conditions that plague C firmware
- The **PAC -> HAL -> BSP** layering gives you type-safe register access at the bottom and portable driver interfaces at the top, all with **zero-cost abstractions** that compile to the same code as hand-written C
- **RTIC** provides priority-based preemptive scheduling with static deadlock-freedom guarantees — no runtime scheduler overhead, no heap, no tick interrupt — because it uses compile-time analysis of resource access patterns
- The `Mutex<RefCell<Option<T>>>` pattern is the manual approach to sharing peripherals between main and interrupt handlers, but RTIC automates this with better ergonomics and stronger guarantees
- **Type-state programming** (e.g., `Pin<Output<PushPull>>` vs `Pin<Input<PullUp>>`) catches pin misconfiguration, protocol violations, and mode errors at compile time — these are bugs that would require oscilloscope debugging in C
- The **trade-off** is a steeper learning curve and longer compile times, however the payoff is firmware that is correct by construction — no buffer overflows, no data races, no use-after-free in interrupt handlers
"""
    ),
    (
        "embedded/rtos-scheduling",
        "Describe Real-Time Operating Systems including FreeRTOS task scheduling with preemptive priority scheduling, priority inversion and inheritance mutexes, semaphores, message queues, inter-task communication, and worst-case execution time analysis with rate monotonic scheduling",
        r"""# Real-Time Operating Systems: FreeRTOS Task Scheduling and Synchronization

## What Makes an OS "Real-Time"

A **Real-Time Operating System (RTOS)** is fundamentally different from a general-purpose OS like Linux. The defining property is not speed — it's **determinism**. A real-time system must guarantee that tasks complete within their deadlines. Missing a deadline in a braking system or a pacemaker isn't just a performance issue — it's a safety failure. Therefore, an RTOS provides **bounded worst-case execution times** for all kernel operations (context switch, mutex acquisition, interrupt latency).

There are two categories of real-time guarantees:

- **Hard real-time**: Missing a deadline is a system failure. Examples: airbag deployment, flight control, medical devices.
- **Soft real-time**: Missing occasional deadlines degrades quality but isn't catastrophic. Examples: audio processing, video streaming, sensor logging.

FreeRTOS is the most widely deployed RTOS, running on over 40 billion devices. It provides **preemptive priority-based scheduling**, synchronization primitives (mutexes, semaphores, queues), and a minimal footprint (6-12 KB ROM, depending on configuration). Understanding its internals is essential for any serious embedded engineer.

## Preemptive Priority Scheduling

FreeRTOS uses a **fixed-priority preemptive scheduler**. Each task has a priority (0 = lowest, `configMAX_PRIORITIES - 1` = highest). The scheduler always runs the highest-priority ready task. When a higher-priority task becomes ready (e.g., unblocked by an interrupt), it **immediately preempts** the running task — there's no waiting for a time slice.

```c
#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"
#include "queue.h"

// Task priorities — higher number = higher priority
// Best practice: define symbolic names, not magic numbers
#define PRIORITY_SENSOR_READ    (tskIDLE_PRIORITY + 3)  // Highest
#define PRIORITY_DATA_PROCESS   (tskIDLE_PRIORITY + 2)
#define PRIORITY_DISPLAY_UPDATE (tskIDLE_PRIORITY + 1)  // Lowest

// Sensor reading task — highest priority because hardware has timing requirements
// This task must complete within 1ms of its trigger, therefore it gets the
// highest priority to preempt any lower-priority work
void vSensorReadTask(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(10);  // 100 Hz sampling

    // Statically allocated buffer — no malloc in real-time code
    // Common mistake: using dynamic allocation in periodic tasks,
    // which can cause unbounded latency due to heap fragmentation
    int16_t sensor_buffer[64];
    uint32_t sample_index = 0;

    for (;;) {
        // vTaskDelayUntil provides precise periodic execution
        // Unlike vTaskDelay, it compensates for execution time jitter
        // because it calculates the next wake time from the LAST wake
        // time, not the current time
        vTaskDelayUntil(&xLastWakeTime, xPeriod);

        // Read sensor via SPI (timing-critical)
        int16_t reading = read_accelerometer_spi();
        sensor_buffer[sample_index % 64] = reading;
        sample_index++;

        // Notify processing task when buffer is full
        if (sample_index % 64 == 0) {
            xTaskNotifyGive(xDataProcessHandle);
        }
    }
}

// Data processing task — medium priority
void vDataProcessTask(void *pvParameters) {
    for (;;) {
        // Block until sensor task signals us
        // This is more efficient than polling because the task
        // consumes zero CPU while waiting
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        // Process the 64-sample buffer
        float rms = compute_rms(sensor_buffer, 64);
        float peak = find_peak(sensor_buffer, 64);

        // Send results to display task via queue
        ProcessedData data = { .rms = rms, .peak = peak };
        xQueueSend(xDisplayQueue, &data, pdMS_TO_TICKS(100));
    }
}

// Display update task — lowest priority, runs only when nothing else needs the CPU
void vDisplayUpdateTask(void *pvParameters) {
    ProcessedData received;
    for (;;) {
        // Block waiting for data from the processing task
        if (xQueueReceive(xDisplayQueue, &received, portMAX_DELAY) == pdTRUE) {
            update_lcd_display(received.rms, received.peak);
        }
    }
}

// System initialization
int main(void) {
    hardware_init();

    // Create the message queue — holds up to 10 ProcessedData structs
    xDisplayQueue = xQueueCreate(10, sizeof(ProcessedData));
    configASSERT(xDisplayQueue != NULL);  // Fail fast if allocation fails

    // Create tasks with appropriate stack sizes
    // Pitfall: stack sizes are in WORDS (4 bytes on ARM), not bytes
    xTaskCreate(vSensorReadTask, "Sensor", 256, NULL, PRIORITY_SENSOR_READ, &xSensorHandle);
    xTaskCreate(vDataProcessTask, "Process", 512, NULL, PRIORITY_DATA_PROCESS, &xDataProcessHandle);
    xTaskCreate(vDisplayUpdateTask, "Display", 512, NULL, PRIORITY_DISPLAY_UPDATE, NULL);

    // Start the scheduler — this never returns
    vTaskStartScheduler();

    // Should never reach here
    for (;;) {}
}
```

### Understanding the Scheduler Internals

FreeRTOS maintains a **ready list** for each priority level. The scheduler selects the first task from the highest non-empty ready list. When tasks share the same priority, they **round-robin** with a configurable time slice (`configTICK_RATE_HZ`). The **trade-off** is between responsiveness and overhead: a higher tick rate gives finer scheduling granularity but increases context-switch overhead.

## Priority Inversion and Priority Inheritance

**Priority inversion** is the most dangerous scheduling pathology in real-time systems. It occurs when a high-priority task is blocked waiting for a resource held by a low-priority task, while a medium-priority task preempts the low-priority task — effectively making the high-priority task wait for the medium-priority task indefinitely. This exact bug caused the Mars Pathfinder reset anomaly in 1997.

The solution is **priority inheritance**: when a high-priority task blocks on a mutex held by a lower-priority task, the lower-priority task temporarily inherits the higher priority, **therefore** it cannot be preempted by medium-priority tasks and will release the mutex quickly.

```c
#include "FreeRTOS.h"
#include "semphr.h"

// Priority inheritance mutex — use this instead of binary semaphores
// for mutual exclusion. A common mistake is using binary semaphores
// for mutex purposes — they do NOT support priority inheritance.
SemaphoreHandle_t xSharedResourceMutex;

// Shared hardware resource (e.g., SPI bus shared between tasks)
typedef struct {
    SPI_HandleTypeDef *hspi;
    uint8_t tx_buffer[256];
    uint8_t rx_buffer[256];
} SharedSPIBus;

static SharedSPIBus spi_bus;

void system_init(void) {
    // Create a MUTEX, not a binary semaphore
    // xSemaphoreCreateMutex() enables priority inheritance
    // xSemaphoreCreateBinary() does NOT — this is a critical distinction
    xSharedResourceMutex = xSemaphoreCreateMutex();
    configASSERT(xSharedResourceMutex != NULL);
}

// High-priority task (priority 3) — reads temperature sensor via SPI
void vHighPriorityTask(void *pvParameters) {
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(100));

        // Attempt to take the mutex with a timeout
        // Best practice: ALWAYS use a timeout, never portMAX_DELAY for mutexes
        // because deadlock detection depends on timeouts
        if (xSemaphoreTake(xSharedResourceMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
            // We own the SPI bus — perform the transfer
            spi_bus.tx_buffer[0] = 0x80;  // Read temperature register
            HAL_SPI_TransmitReceive(spi_bus.hspi,
                spi_bus.tx_buffer, spi_bus.rx_buffer, 2, 10);

            int16_t temp = (spi_bus.rx_buffer[0] << 8) | spi_bus.rx_buffer[1];

            // Release the mutex — priority of the holder reverts to its base
            xSemaphoreGive(xSharedResourceMutex);

            process_temperature(temp);
        } else {
            // Mutex timeout — log error, the system may have a deadlock
            log_error("SPI mutex timeout in high-priority task");
        }
    }
}

// Low-priority task (priority 1) — reads accelerometer via same SPI bus
void vLowPriorityTask(void *pvParameters) {
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(500));

        if (xSemaphoreTake(xSharedResourceMutex, pdMS_TO_TICKS(200)) == pdTRUE) {
            // While this task holds the mutex, if the high-priority task
            // tries to take it, THIS task's priority is temporarily boosted
            // to priority 3 (the high-priority task's priority).
            // Therefore, medium-priority tasks (priority 2) cannot preempt us,
            // and we release the mutex quickly.

            spi_bus.tx_buffer[0] = 0x28;  // Accelerometer register
            HAL_SPI_TransmitReceive(spi_bus.hspi,
                spi_bus.tx_buffer, spi_bus.rx_buffer, 6, 50);

            xSemaphoreGive(xSharedResourceMutex);
        }
    }
}
```

## Message Queues and Inter-Task Communication

Queues are the **best practice** for passing data between tasks in FreeRTOS, because they provide both data transfer and synchronization in one primitive. Unlike shared global variables (which require explicit locking), queues handle all the synchronization internally.

```c
#include "FreeRTOS.h"
#include "queue.h"

// Define message types for a command/response pattern
typedef enum {
    CMD_SET_MOTOR_SPEED,
    CMD_SET_SERVO_ANGLE,
    CMD_EMERGENCY_STOP,
} CommandType;

typedef struct {
    CommandType type;
    int32_t value;
    TickType_t timestamp;
} MotorCommand;

// Queue handles
QueueHandle_t xCommandQueue;
QueueHandle_t xTelemetryQueue;

// Queue set — allows a task to block on multiple queues simultaneously
QueueSetHandle_t xQueueSet;

void init_communication(void) {
    // Command queue: holds 16 commands, each sizeof(MotorCommand)
    xCommandQueue = xQueueCreate(16, sizeof(MotorCommand));

    // Telemetry queue: holds 32 float values
    xTelemetryQueue = xQueueCreate(32, sizeof(float));

    // Queue set: allows blocking on both queues
    // The total size must be the sum of all queue lengths
    xQueueSet = xQueueCreateSet(16 + 32);
    xQueueAddToSet(xCommandQueue, xQueueSet);
    xQueueAddToSet(xTelemetryQueue, xQueueSet);
}

// Producer task: generates motor commands from user input
void vCommandProducerTask(void *pvParameters) {
    MotorCommand cmd;
    for (;;) {
        // Read joystick or communication interface
        int16_t joystick_x = read_adc_channel(0);

        cmd.type = CMD_SET_MOTOR_SPEED;
        cmd.value = map_joystick_to_speed(joystick_x);
        cmd.timestamp = xTaskGetTickCount();

        // Send to queue with timeout
        // Pitfall: using portMAX_DELAY here can cause the producer
        // to block indefinitely if the consumer is stuck
        if (xQueueSend(xCommandQueue, &cmd, pdMS_TO_TICKS(10)) != pdTRUE) {
            // Queue full — consumer isn't keeping up
            // Best practice: log this and consider if your design
            // has a throughput mismatch
            increment_overflow_counter();
        }

        vTaskDelay(pdMS_TO_TICKS(20));  // 50 Hz command rate
    }
}

// Consumer task: executes motor commands and reports telemetry
void vMotorControlTask(void *pvParameters) {
    for (;;) {
        // Block on the queue set — wakes when ANY queue has data
        QueueSetMemberHandle_t xActiveMember =
            xQueueSelectFromSet(xQueueSet, portMAX_DELAY);

        if (xActiveMember == xCommandQueue) {
            MotorCommand cmd;
            xQueueReceive(xCommandQueue, &cmd, 0);

            switch (cmd.type) {
                case CMD_EMERGENCY_STOP:
                    set_motor_pwm(0);
                    disable_motor_driver();
                    break;
                case CMD_SET_MOTOR_SPEED:
                    set_motor_pwm(cmd.value);
                    break;
                case CMD_SET_SERVO_ANGLE:
                    set_servo_position(cmd.value);
                    break;
            }

            // Report current speed as telemetry
            float current_speed = read_encoder_speed();
            xQueueSend(xTelemetryQueue, &current_speed, 0);
        }
    }
}
```

## Worst-Case Execution Time and Rate Monotonic Scheduling

**Rate Monotonic Scheduling (RMS)** is a mathematical framework for assigning priorities to periodic tasks. The rule is simple: **shorter period = higher priority**. RMS is **optimal** among fixed-priority schedulers — if any fixed-priority assignment can meet all deadlines, RMS can too.

The **schedulability test** for RMS with N tasks is:

**U = sum(Ci / Ti) <= N * (2^(1/N) - 1)**

Where Ci is the worst-case execution time and Ti is the period of task i. For large N, this bound converges to ln(2) = 0.693. **Therefore**, if your total CPU utilization is below 69.3%, RMS guarantees all deadlines are met.

However, this is a **sufficient but not necessary** condition. Many systems with utilization up to 80-90% still meet all deadlines under RMS — you just need to verify with exact analysis (response time analysis) rather than the utilization bound.

### Measuring Worst-Case Execution Time (WCET)

A **pitfall** in WCET measurement is only testing the average case. Caches, branch predictors, and pipeline stalls mean that worst-case execution can be 10-100x longer than average:

- **Cache miss storms**: First execution after a context switch may miss every cache line
- **Flash wait states**: Code running from flash with 0-wait-state caching can stall when the cache misses
- **Interrupt preemption**: Higher-priority interrupts steal cycles from your task

The **best practice** is to measure WCET empirically using GPIO toggling and an oscilloscope, combined with static WCET analysis tools (e.g., aiT, RapiTime) for safety-critical systems.

## Key Takeaways

- FreeRTOS uses **fixed-priority preemptive scheduling** — the highest-priority ready task always runs, preempting lower-priority tasks immediately, because real-time systems require deterministic response times
- **Priority inversion** occurs when a medium-priority task indirectly blocks a high-priority task; the solution is **priority inheritance mutexes** (not binary semaphores), which temporarily boost the mutex holder's priority
- Always use `xSemaphoreCreateMutex()` for mutual exclusion, not `xSemaphoreCreateBinary()` — the latter lacks priority inheritance and is a **common mistake** that can cause subtle scheduling failures
- **Message queues** are the preferred inter-task communication mechanism because they combine data transfer with synchronization and avoid shared-state concurrency bugs
- **Rate Monotonic Scheduling** assigns priorities by period (shorter period = higher priority) and guarantees deadline compliance when total utilization is below N * (2^(1/N) - 1), however many real systems exceed this bound and still meet deadlines
- The **trade-off** between tick rate and overhead must be carefully tuned: higher `configTICK_RATE_HZ` gives finer timing resolution but increases context-switch overhead, which eats into your WCET budget
"""
    ),
    (
        "embedded/communication-protocols",
        "Explain embedded communication protocols including SPI, I2C, UART, and CAN bus with practical driver implementations covering I2C master with START/STOP/ACK sequences, SPI chip select management, CAN message framing, bus arbitration, and protocol selection trade-offs",
        r"""# Embedded Communication Protocols: SPI, I2C, UART, and CAN Bus

## Overview of Serial Communication in Embedded Systems

Every embedded system needs to talk to peripherals — sensors, displays, memory chips, motor controllers, other microcontrollers. The four dominant protocols (**UART, SPI, I2C, CAN**) each make different **trade-offs** between speed, pin count, complexity, and reliability. Choosing the wrong protocol for your application can waste board space, limit throughput, or miss real-time deadlines. Understanding the internals of each protocol is essential **because** the HAL libraries abstract away details that matter when things go wrong — and things always go wrong on the bus.

### Quick Comparison

| Feature | UART | SPI | I2C | CAN |
|---------|------|-----|-----|-----|
| **Wires** | 2 (TX/RX) | 4+ (MOSI/MISO/SCK/CS) | 2 (SDA/SCL) | 2 (CANH/CANL) |
| **Speed** | Up to 3 Mbps | Up to 60+ MHz | 100/400/1000 kHz | 1 Mbps (classic) |
| **Topology** | Point-to-point | Star (1 master, N slaves) | Multi-master bus | Multi-master bus |
| **Distance** | Meters (with RS-485) | ~30 cm PCB traces | ~1 meter | ~40 meters (1 Mbps) |
| **Flow control** | Optional (RTS/CTS) | CS per device | ACK/NACK per byte | Built-in arbitration |

## I2C Master Driver: Bit-Level Implementation

I2C (Inter-Integrated Circuit) uses just two wires — **SDA** (data) and **SCL** (clock) — to communicate with up to 127 devices on the same bus. It's the **best practice** for connecting low-speed sensors, EEPROMs, and configuration interfaces where pin count matters more than throughput.

The protocol is based on **START conditions**, **STOP conditions**, **ACK/NACK**, and **7-bit addressing**. Here's a bit-banged I2C master implementation that reveals every step of the protocol, **because** understanding the waveform-level behavior is essential for debugging bus issues:

```c
#include <stdint.h>
#include <stdbool.h>

// GPIO abstraction — replace with your MCU's HAL
// SDA must be open-drain with external pull-up (typically 4.7k ohm)
// SCL must be open-drain with external pull-up
// Common mistake: using push-pull outputs for I2C — this creates
// bus contention and can damage peripherals

typedef struct {
    void (*set_sda)(bool high);   // Drive SDA low or release (high-Z)
    void (*set_scl)(bool high);   // Drive SCL low or release (high-Z)
    bool (*read_sda)(void);       // Read current SDA state
    bool (*read_scl)(void);       // Read current SCL state (for clock stretching)
    void (*delay_us)(uint32_t us); // Microsecond delay
} I2C_GPIO;

typedef enum {
    I2C_OK = 0,
    I2C_NACK,
    I2C_BUS_BUSY,
    I2C_TIMEOUT,
    I2C_ARBITRATION_LOST,
} I2C_Status;

// Clock stretching support: some slaves hold SCL low to slow the master
// Pitfall: not implementing clock stretching causes data corruption
// with slow devices like certain humidity sensors
static bool wait_scl_high(const I2C_GPIO *gpio, uint32_t timeout_us) {
    gpio->set_scl(true);  // Release SCL (pull-up pulls it high)
    uint32_t waited = 0;
    while (!gpio->read_scl()) {
        gpio->delay_us(1);
        waited++;
        if (waited >= timeout_us) {
            return false;  // Slave is holding SCL low — timeout
        }
    }
    return true;
}

// START condition: SDA falls while SCL is high
// This signals all devices on the bus that a transaction is beginning
static I2C_Status i2c_start(const I2C_GPIO *gpio) {
    // Ensure both lines are high (idle state)
    gpio->set_sda(true);
    if (!wait_scl_high(gpio, 1000)) return I2C_TIMEOUT;
    gpio->delay_us(5);

    // Check bus is free — SDA should be high
    if (!gpio->read_sda()) return I2C_BUS_BUSY;

    // Generate START: SDA goes LOW while SCL stays HIGH
    gpio->set_sda(false);
    gpio->delay_us(5);  // Setup time (t_SU;STA) >= 4.7us for standard mode
    gpio->set_scl(false);
    gpio->delay_us(5);

    return I2C_OK;
}

// STOP condition: SDA rises while SCL is high
static void i2c_stop(const I2C_GPIO *gpio) {
    gpio->set_sda(false);  // Ensure SDA is low
    gpio->delay_us(5);
    gpio->set_scl(true);   // Release SCL
    gpio->delay_us(5);     // Setup time (t_SU;STO) >= 4.0us
    gpio->set_sda(true);   // SDA goes HIGH while SCL is HIGH = STOP
    gpio->delay_us(5);     // Bus free time (t_BUF) >= 4.7us
}

// Send one byte, MSB first, return ACK status
static I2C_Status i2c_send_byte(const I2C_GPIO *gpio, uint8_t byte) {
    for (int i = 7; i >= 0; i--) {
        // Set SDA while SCL is low
        gpio->set_sda((byte >> i) & 1);
        gpio->delay_us(2);

        // Clock pulse: SCL high, hold, SCL low
        if (!wait_scl_high(gpio, 1000)) return I2C_TIMEOUT;
        gpio->delay_us(5);  // SCL high time >= 4.0us (standard mode)
        gpio->set_scl(false);
        gpio->delay_us(5);  // SCL low time >= 4.7us
    }

    // 9th clock: read ACK from slave
    gpio->set_sda(true);  // Release SDA so slave can drive it
    gpio->delay_us(2);
    if (!wait_scl_high(gpio, 1000)) return I2C_TIMEOUT;
    gpio->delay_us(3);

    bool nack = gpio->read_sda();  // LOW = ACK, HIGH = NACK

    gpio->set_scl(false);
    gpio->delay_us(5);

    return nack ? I2C_NACK : I2C_OK;
}

// Read one byte, send ACK or NACK
static uint8_t i2c_read_byte(const I2C_GPIO *gpio, bool send_ack) {
    uint8_t byte = 0;
    gpio->set_sda(true);  // Release SDA for slave to drive

    for (int i = 7; i >= 0; i--) {
        if (!wait_scl_high(gpio, 1000)) return 0xFF;
        gpio->delay_us(3);
        if (gpio->read_sda()) {
            byte |= (1 << i);
        }
        gpio->set_scl(false);
        gpio->delay_us(5);
    }

    // 9th clock: master sends ACK (low) or NACK (high)
    // Best practice: send NACK on the LAST byte of a read sequence
    // to tell the slave to release the bus
    gpio->set_sda(!send_ack);  // ACK = SDA low, NACK = SDA high
    gpio->delay_us(2);
    wait_scl_high(gpio, 1000);
    gpio->delay_us(5);
    gpio->set_scl(false);
    gpio->delay_us(5);
    gpio->set_sda(true);  // Release SDA

    return byte;
}

// High-level: read N bytes from a device register
I2C_Status i2c_read_register(const I2C_GPIO *gpio, uint8_t dev_addr,
                              uint8_t reg_addr, uint8_t *data, uint16_t len) {
    I2C_Status status;

    // Phase 1: Write the register address
    status = i2c_start(gpio);
    if (status != I2C_OK) return status;

    // Address byte: 7-bit address << 1 | write bit (0)
    status = i2c_send_byte(gpio, (dev_addr << 1) | 0);
    if (status != I2C_OK) { i2c_stop(gpio); return status; }

    status = i2c_send_byte(gpio, reg_addr);
    if (status != I2C_OK) { i2c_stop(gpio); return status; }

    // Phase 2: Repeated START + read
    // A repeated START avoids releasing the bus between write and read
    // This is critical because another master could steal the bus
    status = i2c_start(gpio);  // Repeated START
    if (status != I2C_OK) return status;

    // Address byte: 7-bit address << 1 | read bit (1)
    status = i2c_send_byte(gpio, (dev_addr << 1) | 1);
    if (status != I2C_OK) { i2c_stop(gpio); return status; }

    // Read data bytes, ACK all except the last one
    for (uint16_t i = 0; i < len; i++) {
        data[i] = i2c_read_byte(gpio, i < len - 1);  // NACK on last byte
    }

    i2c_stop(gpio);
    return I2C_OK;
}
```

## SPI with Chip Select Management

**SPI** (Serial Peripheral Interface) is faster than I2C (often 10-60 MHz) but requires more pins: **MOSI** (Master Out Slave In), **MISO** (Master In Slave Out), **SCK** (clock), and one **CS** (chip select) line per slave device. The **trade-off** is clear: SPI gives you speed, I2C gives you simplicity.

```c
#include <stdint.h>
#include <stdbool.h>

// SPI configuration — mode is defined by CPOL and CPHA
// Common mistake: using the wrong SPI mode for your device.
// Most sensors use Mode 0 (CPOL=0, CPHA=0), but some (like
// certain SD cards) use Mode 3 (CPOL=1, CPHA=1). Check the datasheet.
typedef enum {
    SPI_MODE_0 = 0,  // CPOL=0, CPHA=0: idle low, sample on rising edge
    SPI_MODE_1 = 1,  // CPOL=0, CPHA=1: idle low, sample on falling edge
    SPI_MODE_2 = 2,  // CPOL=1, CPHA=0: idle high, sample on falling edge
    SPI_MODE_3 = 3,  // CPOL=1, CPHA=1: idle high, sample on rising edge
} SPI_Mode;

typedef struct {
    SPI_HandleTypeDef *hspi;       // Hardware SPI peripheral
    GPIO_TypeDef *cs_port;         // Chip select GPIO port
    uint16_t cs_pin;               // Chip select GPIO pin
    SPI_Mode mode;                 // SPI clock mode
    uint32_t max_speed_hz;         // Maximum clock speed for this device
} SPI_Device;

// Chip select management with proper timing
// Best practice: manage CS in software, not hardware, because
// you need control over timing between CS assertion and first clock edge
void spi_select(const SPI_Device *dev) {
    HAL_GPIO_WritePin(dev->cs_port, dev->cs_pin, GPIO_PIN_RESET);  // CS active LOW
    // Many devices need a setup time after CS goes low
    // before the first clock edge. 100ns is typical.
    delay_ns(100);
}

void spi_deselect(const SPI_Device *dev) {
    // Ensure last clock edge has completed
    delay_ns(100);
    HAL_GPIO_WritePin(dev->cs_port, dev->cs_pin, GPIO_PIN_SET);    // CS inactive HIGH
    // Hold CS high for minimum deselect time (varies by device)
    delay_ns(50);
}

// Full-duplex transfer: sends and receives simultaneously
// This is the fundamental SPI operation — MOSI and MISO shift
// data at the same time on each clock edge
HAL_StatusTypeDef spi_transfer(const SPI_Device *dev,
                                const uint8_t *tx_data, uint8_t *rx_data,
                                uint16_t len) {
    spi_select(dev);

    HAL_StatusTypeDef status = HAL_SPI_TransmitReceive(
        dev->hspi, (uint8_t *)tx_data, rx_data, len, 100);

    spi_deselect(dev);
    return status;
}

// Example: reading a register from an SPI accelerometer (ADXL345)
int16_t spi_read_accel_axis(const SPI_Device *accel, uint8_t reg) {
    uint8_t tx[3] = {reg | 0x80 | 0x40, 0x00, 0x00};
    // Bit 7 = read flag, Bit 6 = multi-byte flag
    // Remaining bits = register address
    uint8_t rx[3] = {0};

    spi_transfer(accel, tx, rx, 3);

    // rx[0] is garbage (slave was receiving the command byte)
    // rx[1] = low byte, rx[2] = high byte (little-endian)
    return (int16_t)((rx[2] << 8) | rx[1]);
}
```

## CAN Bus Message Framing

**CAN** (Controller Area Network) is fundamentally different from SPI and I2C — it's a **multi-master broadcast bus** designed for noisy automotive and industrial environments. Every node can transmit, and **bus arbitration** is non-destructive: if two nodes transmit simultaneously, the one with the lower (higher priority) ID wins without any data corruption. This is **because** CAN uses a dominant/recessive bit scheme on a differential pair (CANH/CANL).

```c
#include <stdint.h>
#include <stdbool.h>

// CAN message structure — standard 11-bit identifier
// The ID serves double duty: it identifies the message type AND
// determines arbitration priority (lower ID = higher priority)
typedef struct {
    uint32_t id;           // 11-bit (standard) or 29-bit (extended) identifier
    bool     extended;     // true = 29-bit extended ID
    bool     rtr;          // Remote Transmission Request
    uint8_t  dlc;          // Data Length Code (0-8 bytes)
    uint8_t  data[8];      // Payload
} CAN_Message;

// CAN filter configuration — hardware filtering reduces CPU load
// by discarding irrelevant messages before they reach software
typedef struct {
    uint32_t id;
    uint32_t mask;         // 1 = must match, 0 = don't care
    bool     extended;
} CAN_Filter;

// Initialize CAN peripheral for 500 kbps
// Pitfall: bit timing calculation is the #1 source of CAN bus issues.
// The total number of time quanta per bit must be consistent across
// ALL nodes on the bus, otherwise you get intermittent errors.
void can_init(CAN_HandleTypeDef *hcan) {
    hcan->Init.Prescaler = 6;        // APB1 clock / prescaler = TQ frequency
    hcan->Init.Mode = CAN_MODE_NORMAL;
    hcan->Init.SyncJumpWidth = CAN_SJW_1TQ;
    hcan->Init.TimeSeg1 = CAN_BS1_11TQ;   // Propagation + Phase 1
    hcan->Init.TimeSeg2 = CAN_BS2_2TQ;    // Phase 2
    // Total = 1 (sync) + 11 (seg1) + 2 (seg2) = 14 TQ per bit
    // Sample point = (1 + 11) / 14 = 85.7% — ideal for automotive

    hcan->Init.TransmitFifoPriority = DISABLE;  // Use ID-based priority
    hcan->Init.AutoBusOff = ENABLE;  // Auto-recover from bus-off state
    hcan->Init.AutoWakeUp = ENABLE;
    hcan->Init.AutoRetransmission = ENABLE;  // Retry on arbitration loss

    HAL_CAN_Init(hcan);

    // Configure acceptance filter — only accept IDs 0x100-0x1FF
    CAN_FilterTypeDef filter;
    filter.FilterBank = 0;
    filter.FilterMode = CAN_FILTERMODE_IDMASK;
    filter.FilterScale = CAN_FILTERSCALE_32BIT;
    filter.FilterIdHigh = 0x100 << 5;     // ID in upper bits
    filter.FilterIdLow = 0x0000;
    filter.FilterMaskIdHigh = 0xF00 << 5; // Match upper nibble
    filter.FilterMaskIdLow = 0x0000;
    filter.FilterFIFOAssignment = CAN_RX_FIFO0;
    filter.FilterActivation = ENABLE;

    HAL_CAN_ConfigFilter(hcan, &filter);
    HAL_CAN_Start(hcan);
    HAL_CAN_ActivateNotification(hcan, CAN_IT_RX_FIFO0_MSG_PENDING);
}

// Send a CAN message — non-blocking, returns immediately
// The hardware handles arbitration, bit stuffing, and CRC automatically
CAN_Status can_send(CAN_HandleTypeDef *hcan, const CAN_Message *msg) {
    CAN_TxHeaderTypeDef header;
    header.StdId = msg->id;
    header.ExtId = 0;
    header.IDE = msg->extended ? CAN_ID_EXT : CAN_ID_STD;
    header.RTR = msg->rtr ? CAN_RTR_REMOTE : CAN_RTR_DATA;
    header.DLC = msg->dlc;
    header.TransmitGlobalTime = DISABLE;

    uint32_t mailbox;
    if (HAL_CAN_AddTxMessage(hcan, &header, (uint8_t *)msg->data, &mailbox) != HAL_OK) {
        return CAN_TX_FULL;  // All 3 TX mailboxes occupied
    }
    return CAN_OK;
}
```

### Bus Arbitration and Error Detection

CAN's arbitration mechanism is elegant: all transmitting nodes send their ID bits simultaneously. A logical '0' (dominant) overwrites a logical '1' (recessive) on the bus. Each node monitors the bus — if it sent a '1' but reads a '0', it lost arbitration and backs off without corrupting the winner's frame. **Therefore**, the message with the lowest ID always wins, providing deterministic, priority-based access without any bus master.

CAN also includes robust **error detection**: 15-bit CRC, bit stuffing violations, acknowledgment checking, and form error detection. The probability of an undetected error is less than 4.7 x 10^-11 per message — making CAN one of the most reliable serial protocols. **However**, this reliability comes at a cost: maximum 8 bytes of payload per frame (64 bytes with CAN FD), and the 1 Mbps speed limit restricts use to control networks, not high-bandwidth data transfer.

## Protocol Selection Trade-Offs

Choosing between these protocols depends on your specific constraints:

- **UART**: Use for debug consoles, GPS receivers, Bluetooth modules. Simple, point-to-point, no clock line needed. **Pitfall**: baud rate mismatch causes garbage data, and there's no error correction built in.
- **SPI**: Use for high-speed data transfer to displays, flash memory, ADCs. The **trade-off** is that each slave needs its own CS line, so pin count grows linearly with device count.
- **I2C**: Use when you need many low-speed devices on two wires — temperature sensors, EEPROMs, GPIO expanders. **However**, the shared bus means one stuck device can hang the entire bus (SCL held low).
- **CAN**: Use for distributed systems in noisy environments — automotive, industrial automation, robotics. Built-in arbitration and error handling justify the external transceiver cost.

## Key Takeaways

- **I2C** uses START/STOP conditions, ACK/NACK handshaking, and 7-bit addressing on just two wires, making it ideal for sensor networks — however, **clock stretching** and **stuck bus** conditions require timeout handling that many drivers omit
- **SPI** is the fastest option (up to 60+ MHz) with full-duplex data transfer, but the **trade-off** is one chip-select pin per slave device, and getting CPOL/CPHA mode wrong is the most **common mistake** in SPI development
- **CAN** provides deterministic, priority-based bus arbitration where lower IDs always win — this non-destructive arbitration is unique among embedded protocols and is why CAN dominates automotive and industrial applications
- Bit timing configuration is the **pitfall** that causes 90% of CAN bus failures — all nodes must agree on the number of time quanta per bit and the sample point position
- **Best practice**: use hardware peripherals instead of bit-banging in production (bit-banging is educational but wastes CPU and is jitter-sensitive), reserve UART for debug/logging, SPI for high-speed peripherals, I2C for configuration/sensor buses, and CAN for multi-node distributed control
- Protocol selection should be driven by **bandwidth requirements**, **pin budget**, **noise environment**, and **topology** — there is no universally best protocol, only the right one for your constraints
"""
    ),
    (
        "embedded/memory-management-constrained",
        "Explain memory management strategies for constrained embedded environments including static allocation, memory pool allocators, ring buffers for DMA transfers, stack watermarking, MPU configuration for memory protection, fragmentation avoidance techniques, and MISRA-C memory rules",
        r"""# Memory Management in Constrained Embedded Environments

## Why Dynamic Allocation Is Dangerous on Embedded Systems

On a desktop with 16 GB of RAM and virtual memory, `malloc()` feels free and safe. On a microcontroller with 64 KB of SRAM, it's a ticking time bomb. The problems are fundamental:

1. **Fragmentation**: After repeated alloc/free cycles, the heap becomes Swiss cheese — plenty of total free memory, but no contiguous block large enough for the next allocation. On a desktop, the OS can compact memory or swap to disk. On an MCU, you're dead.

2. **Non-deterministic timing**: `malloc()` walks a free list, which takes variable time depending on fragmentation. This violates real-time guarantees — you cannot predict the worst-case execution time of a function that calls `malloc()`.

3. **No safety net**: When `malloc()` returns NULL on a desktop, you can log an error and exit gracefully. When it happens in a flight controller at 30,000 feet, the consequence is catastrophic. **Therefore**, safety-critical standards like **MISRA-C** and **DO-178C** either prohibit or severely restrict dynamic allocation.

The **best practice** in embedded systems is: allocate everything at startup, never free, never allocate again. This is called **static allocation**, and it's the foundation of reliable embedded software.

## Fixed-Size Memory Pool Allocator

When you do need allocation-like behavior (e.g., network packet buffers, message passing), a **fixed-size pool allocator** provides O(1) allocation and deallocation with **zero fragmentation** — because all blocks are the same size, any free block can satisfy any request.

```c
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

// Fixed-size memory pool — zero fragmentation, O(1) alloc/free
// The pool is statically allocated, so no heap is needed.
// This is safe for interrupt contexts because operations are O(1)
// and can be made atomic with a single compare-and-swap.

#define POOL_BLOCK_SIZE  64    // Each block is 64 bytes
#define POOL_BLOCK_COUNT 32    // 32 blocks = 2 KB total

typedef struct MemPool {
    // The actual memory — statically allocated, aligned for any type
    __attribute__((aligned(4)))
    uint8_t memory[POOL_BLOCK_COUNT][POOL_BLOCK_SIZE];

    // Free list implemented as a singly-linked list through the blocks themselves
    // Each free block's first sizeof(void*) bytes store a pointer to the next free block
    // This is a classic trick: we reuse the block memory for bookkeeping
    void *free_list;

    // Statistics for monitoring
    uint32_t total_blocks;
    uint32_t free_blocks;
    uint32_t alloc_count;      // Total allocations since boot
    uint32_t free_count;       // Total frees since boot
    uint32_t high_water_mark;  // Maximum blocks ever in use simultaneously
} MemPool;

// Initialize the pool — call once at startup
void mempool_init(MemPool *pool) {
    pool->free_list = NULL;
    pool->total_blocks = POOL_BLOCK_COUNT;
    pool->free_blocks = POOL_BLOCK_COUNT;
    pool->alloc_count = 0;
    pool->free_count = 0;
    pool->high_water_mark = 0;

    // Chain all blocks into the free list
    // Each free block's first bytes point to the next free block
    for (int i = POOL_BLOCK_COUNT - 1; i >= 0; i--) {
        void **block = (void **)pool->memory[i];
        *block = pool->free_list;
        pool->free_list = block;
    }
}

// Allocate one block — O(1), returns NULL if pool is exhausted
// This is safe to call from an interrupt handler if you wrap it
// in a critical section (disable interrupts briefly)
void *mempool_alloc(MemPool *pool) {
    // Critical section start (platform-specific)
    uint32_t primask = __get_PRIMASK();
    __disable_irq();

    void *block = pool->free_list;
    if (block != NULL) {
        // Pop the first free block from the list
        pool->free_list = *(void **)block;
        pool->free_blocks--;
        pool->alloc_count++;

        // Update high water mark
        uint32_t in_use = pool->total_blocks - pool->free_blocks;
        if (in_use > pool->high_water_mark) {
            pool->high_water_mark = in_use;
        }

        // Zero the block before returning — best practice to prevent
        // information leakage between users of the pool
        memset(block, 0, POOL_BLOCK_SIZE);
    }

    // Critical section end
    __set_PRIMASK(primask);
    return block;
}

// Free one block — O(1), pushes it back onto the free list
void mempool_free(MemPool *pool, void *block) {
    if (block == NULL) return;

    // Validate that the block actually belongs to this pool
    // Common mistake: freeing a block that doesn't belong to the pool,
    // which corrupts the free list and causes hard-to-debug crashes
    uintptr_t addr = (uintptr_t)block;
    uintptr_t pool_start = (uintptr_t)pool->memory;
    uintptr_t pool_end = pool_start + sizeof(pool->memory);

    if (addr < pool_start || addr >= pool_end) {
        // Block doesn't belong to this pool — programming error
        fault_handler("mempool_free: invalid block address");
        return;
    }

    // Check alignment — block must be on a POOL_BLOCK_SIZE boundary
    if ((addr - pool_start) % POOL_BLOCK_SIZE != 0) {
        fault_handler("mempool_free: misaligned block");
        return;
    }

    uint32_t primask = __get_PRIMASK();
    __disable_irq();

    // Push block onto free list
    *(void **)block = pool->free_list;
    pool->free_list = block;
    pool->free_blocks++;
    pool->free_count++;

    __set_PRIMASK(primask);
}
```

## Ring Buffer for DMA Transfers

DMA (Direct Memory Access) transfers data between peripherals and memory without CPU intervention. A **ring buffer** (circular buffer) is the natural data structure for DMA reception, **because** DMA writes continuously while the application reads at its own pace. The ring buffer decouples the producer (DMA hardware) from the consumer (application code).

```c
#include <stdint.h>
#include <stdbool.h>

// Ring buffer for DMA UART reception
// The DMA controller writes into this buffer continuously in circular mode
// The application reads from it without disabling DMA — zero-copy, lock-free

#define RING_BUFFER_SIZE 512  // Must be power of 2 for efficient modulo

typedef struct {
    // Buffer must be in a DMA-accessible memory region
    // Pitfall on STM32H7: DMA cannot access DTCM RAM.
    // Use __attribute__((section(".dma_buffer"))) to place it correctly.
    __attribute__((aligned(4)))
    uint8_t buffer[RING_BUFFER_SIZE];

    volatile uint32_t read_index;  // Application's read position
    // Write index is derived from DMA's NDTR (Number of Data To Register)
    // Therefore we don't need an explicit write_index variable
    DMA_HandleTypeDef *hdma;       // DMA handle for querying position
} DMA_RingBuffer;

void dma_ring_init(DMA_RingBuffer *rb, UART_HandleTypeDef *huart,
                   DMA_HandleTypeDef *hdma) {
    rb->read_index = 0;
    rb->hdma = hdma;
    memset(rb->buffer, 0, RING_BUFFER_SIZE);

    // Start DMA reception in circular mode
    // The DMA will wrap around automatically when it reaches the end
    HAL_UART_Receive_DMA(huart, rb->buffer, RING_BUFFER_SIZE);
}

// Get the current DMA write position
// DMA counts DOWN from RING_BUFFER_SIZE to 0
static inline uint32_t dma_write_index(const DMA_RingBuffer *rb) {
    return RING_BUFFER_SIZE - __HAL_DMA_GET_COUNTER(rb->hdma);
}

// How many bytes are available to read?
uint32_t dma_ring_available(const DMA_RingBuffer *rb) {
    uint32_t write_idx = dma_write_index(rb);
    if (write_idx >= rb->read_index) {
        return write_idx - rb->read_index;
    } else {
        // Wrapped around
        return RING_BUFFER_SIZE - rb->read_index + write_idx;
    }
}

// Read up to 'len' bytes from the ring buffer
// Returns the number of bytes actually read
// This is lock-free because the DMA writes and we read from different positions
// However, if the DMA laps us (writes faster than we read), data is lost
uint32_t dma_ring_read(DMA_RingBuffer *rb, uint8_t *dest, uint32_t len) {
    uint32_t available = dma_ring_available(rb);
    if (len > available) {
        len = available;
    }
    if (len == 0) return 0;

    uint32_t read_idx = rb->read_index;

    // Check if the read wraps around the end of the buffer
    if (read_idx + len <= RING_BUFFER_SIZE) {
        // No wrap — single memcpy
        memcpy(dest, &rb->buffer[read_idx], len);
    } else {
        // Wrap — two memcpy operations
        uint32_t first_chunk = RING_BUFFER_SIZE - read_idx;
        memcpy(dest, &rb->buffer[read_idx], first_chunk);
        memcpy(dest + first_chunk, &rb->buffer[0], len - first_chunk);
    }

    rb->read_index = (read_idx + len) % RING_BUFFER_SIZE;
    return len;
}
```

## Stack Watermarking and Overflow Detection

Stack overflow is the **most common cause of random crashes** in embedded systems. Unlike desktops, MCUs don't have virtual memory to catch stack overflows — the stack just silently overwrites adjacent memory, corrupting global variables or other task stacks.

**Stack watermarking** (also called stack painting) fills the stack with a known pattern at startup and periodically checks how much of the pattern remains intact. This tells you the **high water mark** — the deepest the stack has ever grown.

```c
#include <stdint.h>

#define STACK_FILL_PATTERN 0xDEADBEEF

// Paint a task's stack with a known pattern
// Call this BEFORE the task starts executing
// FreeRTOS does this automatically if configCHECK_FOR_STACK_OVERFLOW >= 2
void stack_paint(uint32_t *stack_bottom, uint32_t stack_size_words) {
    for (uint32_t i = 0; i < stack_size_words; i++) {
        stack_bottom[i] = STACK_FILL_PATTERN;
    }
}

// Check how many words of stack are still painted (never used)
// The high water mark is (stack_size - unused_words) * sizeof(uint32_t)
uint32_t stack_unused_words(const uint32_t *stack_bottom, uint32_t stack_size_words) {
    uint32_t unused = 0;
    // ARM Cortex-M stacks grow downward, so the bottom of memory is
    // the deepest the stack can grow. Check from the bottom up.
    for (uint32_t i = 0; i < stack_size_words; i++) {
        if (stack_bottom[i] == STACK_FILL_PATTERN) {
            unused++;
        } else {
            break;  // Found used stack — stop counting
        }
    }
    return unused;
}

// Best practice: check stack usage periodically in an idle task
// and assert if any task has less than 10% stack remaining
void check_all_stacks(void) {
    TaskStatus_t task_status[16];
    UBaseType_t task_count = uxTaskGetSystemState(task_status, 16, NULL);

    for (UBaseType_t i = 0; i < task_count; i++) {
        // uxTaskGetStackHighWaterMark returns the MINIMUM free stack
        // ever observed, in words
        UBaseType_t free_words = uxTaskGetStackHighWaterMark(task_status[i].xHandle);

        if (free_words < 32) {  // Less than 128 bytes free
            // Danger zone — this task needs a bigger stack
            log_warning("Task '%s' stack critically low: %u words free",
                       task_status[i].pcTaskName, (unsigned)free_words);
        }
    }
}
```

## MPU (Memory Protection Unit) Configuration

The ARM Cortex-M MPU provides **hardware-enforced memory protection** — it can prevent tasks from accessing each other's memory, catch stack overflows instantly (not after corruption), and mark flash as read-only. This is essential for safety-critical systems **because** software bugs in one module cannot corrupt another module's data.

A **common mistake** is not using the MPU at all — many developers don't realize their Cortex-M3/M4/M7 has an MPU, or they consider it too complex to configure. However, even a minimal MPU setup (stack guard regions + null pointer protection) catches the majority of memory corruption bugs:

```c
#include "stm32f4xx.h"

// Configure MPU for basic memory protection
// This setup provides:
// 1. Null pointer dereference protection (region at 0x00000000)
// 2. Stack overflow detection (guard region below each task stack)
// 3. Peripheral access restriction (only privileged mode)
void mpu_configure(void) {
    // Disable MPU during configuration
    HAL_MPU_Disable();

    MPU_Region_InitTypeDef region;

    // Region 0: Null pointer protection
    // Make the first 256 bytes of memory inaccessible
    // This catches NULL pointer dereferences immediately
    region.Enable = MPU_REGION_ENABLE;
    region.Number = MPU_REGION_NUMBER0;
    region.BaseAddress = 0x00000000;
    region.Size = MPU_REGION_SIZE_256B;
    region.SubRegionDisable = 0;
    region.TypeExtField = MPU_TEX_LEVEL0;
    region.AccessPermission = MPU_REGION_NO_ACCESS;
    region.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    region.IsShareable = MPU_ACCESS_NOT_SHAREABLE;
    region.IsCacheable = MPU_ACCESS_NOT_CACHEABLE;
    region.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    HAL_MPU_ConfigRegion(&region);

    // Region 1: Flash — read-only, executable
    // Prevents code from accidentally modifying itself
    region.Number = MPU_REGION_NUMBER1;
    region.BaseAddress = 0x08000000;  // STM32 flash start
    region.Size = MPU_REGION_SIZE_1MB;
    region.AccessPermission = MPU_REGION_PRIV_RO_URO;  // Read-only for all
    region.DisableExec = MPU_INSTRUCTION_ACCESS_ENABLE;
    region.IsCacheable = MPU_ACCESS_CACHEABLE;
    HAL_MPU_ConfigRegion(&region);

    // Region 2: SRAM — read-write, no execute
    // Prevents code execution from RAM (buffer overflow exploit protection)
    region.Number = MPU_REGION_NUMBER2;
    region.BaseAddress = 0x20000000;  // STM32 SRAM start
    region.Size = MPU_REGION_SIZE_128KB;
    region.AccessPermission = MPU_REGION_FULL_ACCESS;
    region.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;  // No execute from RAM
    region.IsCacheable = MPU_ACCESS_CACHEABLE;
    region.IsBufferable = MPU_ACCESS_BUFFERABLE;
    HAL_MPU_ConfigRegion(&region);

    // Region 3: Peripheral region — privileged access only
    // Unprivileged tasks cannot directly access hardware registers
    region.Number = MPU_REGION_NUMBER3;
    region.BaseAddress = 0x40000000;  // STM32 peripheral base
    region.Size = MPU_REGION_SIZE_512MB;
    region.AccessPermission = MPU_REGION_PRIV_RW;  // Privileged only
    region.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    region.IsCacheable = MPU_ACCESS_NOT_CACHEABLE;
    region.IsBufferable = MPU_ACCESS_BUFFERABLE;
    HAL_MPU_ConfigRegion(&region);

    // Enable MPU with default memory map for privileged software
    // and MemManage fault handler enabled
    HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);
}
```

## MISRA-C Memory Rules

**MISRA-C** is the industry standard for safety-critical C programming. Its memory-related rules reflect decades of embedded system failures:

- **Rule 21.3**: `malloc`, `calloc`, `realloc`, and `free` shall not be used. Use static allocation or fixed-size pools instead.
- **Rule 18.1**: Array indexing shall be demonstrably within bounds. Use runtime bounds checking or static analysis.
- **Rule 18.6**: The address of an object with automatic storage shall not be assigned to a pointer that persists after the object ceases to exist (dangling pointer prevention).
- **Rule 11.3**: A cast shall not be performed between a pointer to object type and a different pointer to object type. This prevents type-punning bugs.

These rules exist **because** the failure modes they prevent have caused real-world safety incidents. The **trade-off** is development velocity — MISRA-compliant code is more verbose and restrictive — **however**, the cost of a field failure in automotive or medical devices dwarfs the cost of slower development.

## Key Takeaways

- **Never use `malloc()`/`free()` in embedded systems** — heap fragmentation is non-deterministic and eventually fatal on memory-constrained devices. Use static allocation at startup or fixed-size memory pools for runtime allocation needs
- **Fixed-size pool allocators** provide O(1) alloc/free with zero fragmentation, because all blocks are the same size — any free block satisfies any request. The **trade-off** is wasted space when most allocations are smaller than the block size
- **Ring buffers** for DMA transfers decouple hardware write speed from software read speed without locks or copies — the **pitfall** is that if the consumer falls behind, the DMA silently overwrites unread data
- **Stack watermarking** is a **best practice** that should be enabled in every embedded project — it's the only reliable way to detect stack overflow before it corrupts adjacent memory regions
- The **MPU** provides hardware-enforced memory protection (null pointer detection, stack guard regions, no-execute RAM) with zero performance cost, however most developers skip it because configuration is complex — this is a **common mistake** that leaves systems vulnerable to memory corruption
- **MISRA-C** prohibits dynamic allocation entirely in safety-critical code, therefore all memory must be accounted for at compile time — this discipline forces better architecture and eliminates an entire class of runtime failures
"""
    ),
    (
        "embedded/testing-debugging",
        "Describe embedded testing and debugging strategies including hardware-in-the-loop testing, mock HAL layers for unit testing, JTAG and SWD debugging, HardFault handler implementation with stack frame unwinding, watchdog timer recovery, code coverage on embedded targets, and static analysis integration",
        r"""# Embedded Testing and Debugging: From Unit Tests to Field Diagnostics

## The Testing Challenge in Embedded Systems

Testing embedded software is fundamentally harder than testing desktop applications **because** you're dealing with physical hardware, real-time constraints, and failure modes that don't exist in pure software. Your code runs on a microcontroller that's wired to sensors, actuators, and communication buses — you can't just spin up a Docker container and run your test suite. A motor controller bug might not manifest until the motor stalls under load at a specific temperature. A communication timeout might only occur when EMI from a nearby relay corrupts a CAN frame.

**Therefore**, embedded testing requires a layered strategy: unit tests with mock hardware (fast, run on your development machine), integration tests with real hardware (slower, catch hardware-specific issues), and hardware-in-the-loop (HIL) tests that simulate the complete physical environment.

## Mock HAL Layers for Unit Testing

The key to testable embedded code is **separating hardware access from business logic**. The HAL (Hardware Abstraction Layer) provides the seam where you inject mock implementations for testing. Here's a complete mock GPIO and UART framework that lets you unit-test firmware logic on your PC without any hardware:

```c
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>

// HAL interface — abstract function pointers
// Production code calls these through the interface, never directly
// Best practice: define the interface FIRST, then implement both
// the real HAL and mock HAL against it

typedef struct {
    void (*gpio_write)(uint16_t pin, bool state);
    bool (*gpio_read)(uint16_t pin);
    int  (*uart_send)(const uint8_t *data, uint16_t len, uint32_t timeout_ms);
    int  (*uart_recv)(uint8_t *data, uint16_t len, uint32_t timeout_ms);
    uint32_t (*get_tick_ms)(void);
    void (*delay_ms)(uint32_t ms);
} HAL_Interface;

// Global HAL pointer — set to real or mock at startup
extern HAL_Interface *hal;

// === MOCK IMPLEMENTATION FOR TESTING ===

#define MAX_GPIO_PINS 64
#define MOCK_UART_BUFFER_SIZE 1024

typedef struct {
    // GPIO state tracking
    bool pin_states[MAX_GPIO_PINS];
    uint32_t write_count[MAX_GPIO_PINS];  // How many times each pin was written

    // UART capture buffer — records everything sent via uart_send
    uint8_t uart_tx_buffer[MOCK_UART_BUFFER_SIZE];
    uint16_t uart_tx_index;

    // UART injection buffer — feeds data to uart_recv
    uint8_t uart_rx_buffer[MOCK_UART_BUFFER_SIZE];
    uint16_t uart_rx_len;
    uint16_t uart_rx_index;

    // Time simulation
    uint32_t current_tick_ms;

    // Error injection
    bool uart_send_should_fail;
    bool uart_recv_should_timeout;
} MockHAL_State;

static MockHAL_State mock_state;

// Mock implementations
static void mock_gpio_write(uint16_t pin, bool state) {
    assert(pin < MAX_GPIO_PINS);
    mock_state.pin_states[pin] = state;
    mock_state.write_count[pin]++;
}

static bool mock_gpio_read(uint16_t pin) {
    assert(pin < MAX_GPIO_PINS);
    return mock_state.pin_states[pin];
}

static int mock_uart_send(const uint8_t *data, uint16_t len, uint32_t timeout_ms) {
    if (mock_state.uart_send_should_fail) return -1;

    // Capture the transmitted data for verification
    uint16_t space = MOCK_UART_BUFFER_SIZE - mock_state.uart_tx_index;
    uint16_t copy_len = (len < space) ? len : space;
    memcpy(&mock_state.uart_tx_buffer[mock_state.uart_tx_index], data, copy_len);
    mock_state.uart_tx_index += copy_len;
    return copy_len;
}

static int mock_uart_recv(uint8_t *data, uint16_t len, uint32_t timeout_ms) {
    if (mock_state.uart_recv_should_timeout) return -1;

    uint16_t available = mock_state.uart_rx_len - mock_state.uart_rx_index;
    uint16_t copy_len = (len < available) ? len : available;
    memcpy(data, &mock_state.uart_rx_buffer[mock_state.uart_rx_index], copy_len);
    mock_state.uart_rx_index += copy_len;
    return copy_len;
}

static uint32_t mock_get_tick(void) {
    return mock_state.current_tick_ms;
}

static void mock_delay(uint32_t ms) {
    mock_state.current_tick_ms += ms;
}

// Mock HAL interface instance
static HAL_Interface mock_hal_interface = {
    .gpio_write = mock_gpio_write,
    .gpio_read = mock_gpio_read,
    .uart_send = mock_uart_send,
    .uart_recv = mock_uart_recv,
    .get_tick_ms = mock_get_tick,
    .delay_ms = mock_delay,
};

// Test helper functions
void mock_hal_reset(void) {
    memset(&mock_state, 0, sizeof(mock_state));
    hal = &mock_hal_interface;
}

void mock_hal_inject_uart_data(const uint8_t *data, uint16_t len) {
    memcpy(mock_state.uart_rx_buffer, data, len);
    mock_state.uart_rx_len = len;
    mock_state.uart_rx_index = 0;
}

// === EXAMPLE UNIT TESTS ===

// Test: LED blink function toggles the correct pin
void test_led_blink_toggles_pin(void) {
    mock_hal_reset();

    // The function under test — uses hal->gpio_write internally
    led_blink(PIN_LED_STATUS, 3);  // Blink 3 times

    // Verify: pin should have been written 6 times (on/off * 3)
    assert(mock_state.write_count[PIN_LED_STATUS] == 6);
    // Final state should be off
    assert(mock_state.pin_states[PIN_LED_STATUS] == false);
}

// Test: UART command parser handles malformed input
void test_uart_parser_rejects_bad_checksum(void) {
    mock_hal_reset();

    // Inject a packet with incorrect checksum
    uint8_t bad_packet[] = {0x02, 0x10, 0x00, 0x05, 0xFF};  // 0xFF != correct checksum
    mock_hal_inject_uart_data(bad_packet, sizeof(bad_packet));

    ParseResult result = parse_command_packet();
    assert(result == PARSE_CHECKSUM_ERROR);
}

// Test: motor controller handles UART timeout gracefully
void test_motor_stops_on_communication_loss(void) {
    mock_hal_reset();
    mock_state.uart_recv_should_timeout = true;

    // Start motor at 50% speed
    motor_set_speed(50);
    assert(get_motor_speed() == 50);

    // Process communication — should detect timeout and stop motor
    // Common mistake: not testing timeout paths, which are the most
    // likely failure mode in deployed systems
    communication_task_run();  // This calls uart_recv internally

    // Motor should be stopped as a safety measure
    assert(get_motor_speed() == 0);
}
```

## HardFault Handler with Stack Frame Unwinding

When an ARM Cortex-M encounters a serious error (invalid memory access, divide by zero, bus fault), it triggers a **HardFault exception**. The default handler is an infinite loop — useless for debugging. A proper HardFault handler captures the **stacked register values** (the CPU pushes R0-R3, R12, LR, PC, and xPSR onto the stack before entering the handler), giving you the exact instruction that caused the fault:

```c
#include <stdint.h>

// Fault status registers — these tell you WHY the fault occurred
// Reading these is essential for post-mortem analysis
typedef struct {
    uint32_t r0;
    uint32_t r1;
    uint32_t r2;
    uint32_t r3;
    uint32_t r12;
    uint32_t lr;      // Link register — return address
    uint32_t pc;      // Program counter — the faulting instruction
    uint32_t xpsr;    // Program status register
} StackFrame;

// Fault information structure — stored in a known RAM location
// that survives reset (use the .noinit section)
typedef struct __attribute__((section(".noinit"))) {
    uint32_t magic;           // 0xDEADFAUL if valid
    StackFrame frame;
    uint32_t cfsr;            // Configurable Fault Status Register
    uint32_t hfsr;            // HardFault Status Register
    uint32_t mmfar;           // MemManage Fault Address Register
    uint32_t bfar;            // Bus Fault Address Register
    uint32_t lr_exc_return;   // Exception return value (tells us which stack)
    uint32_t fault_count;     // Incremented on each fault (detects crash loops)
} FaultRecord;

static FaultRecord fault_record;

// The actual HardFault handler — called from assembly trampoline
// This function receives the stack pointer that was active when the
// fault occurred (MSP or PSP depending on context)
void HardFault_Handler_C(uint32_t *stack_ptr) {
    // Capture the stacked register frame
    fault_record.magic = 0xDEADFA01;  // Mark as valid fault record
    fault_record.frame.r0   = stack_ptr[0];
    fault_record.frame.r1   = stack_ptr[1];
    fault_record.frame.r2   = stack_ptr[2];
    fault_record.frame.r3   = stack_ptr[3];
    fault_record.frame.r12  = stack_ptr[4];
    fault_record.frame.lr   = stack_ptr[5];
    fault_record.frame.pc   = stack_ptr[6];  // THIS is the faulting instruction
    fault_record.frame.xpsr = stack_ptr[7];

    // Capture fault status registers
    fault_record.cfsr = SCB->CFSR;  // Shows usage fault, bus fault, or mem fault
    fault_record.hfsr = SCB->HFSR;  // Shows if fault escalated to HardFault
    fault_record.mmfar = SCB->MMFAR; // Address that caused MemManage fault
    fault_record.bfar = SCB->BFAR;   // Address that caused bus fault

    // Increment fault counter (survives reset because it's in .noinit)
    fault_record.fault_count++;

    // Decode the CFSR for human-readable analysis
    // Bit fields tell you exactly what went wrong:
    // CFSR[0]  = IACCVIOL  — instruction access violation
    // CFSR[1]  = DACCVIOL  — data access violation
    // CFSR[3]  = MUNSTKERR — MemManage on unstacking (corrupted stack)
    // CFSR[4]  = MSTKERR   — MemManage on stacking
    // CFSR[7]  = MMARVALID — MMFAR holds the faulting address
    // CFSR[8]  = IBUSERR   — instruction bus error
    // CFSR[9]  = PRECISERR — precise data bus error (BFAR valid)
    // CFSR[16] = UNDEFINSTR — undefined instruction
    // CFSR[17] = INVSTATE  — invalid state (e.g., Thumb bit cleared)
    // CFSR[18] = INVPC     — invalid PC load
    // CFSR[24] = UNALIGNED — unaligned access
    // CFSR[25] = DIVBYZERO — divide by zero

    // If we have a debugger attached, trigger a breakpoint
    // Otherwise, initiate a controlled system reset
    __asm volatile("BKPT #0");

    // If no debugger, reset the system
    NVIC_SystemReset();
}

// Assembly trampoline — determines which stack pointer was active
// This MUST be naked/pure assembly because we need to read the
// stack pointer before any C prologue code modifies it
void __attribute__((naked)) HardFault_Handler(void) {
    __asm volatile(
        "TST lr, #4          \n"  // Test bit 2 of LR (EXC_RETURN)
        "ITE EQ              \n"  // If bit 2 is 0, fault used MSP
        "MRSEQ r0, MSP       \n"  // Use Main Stack Pointer
        "MRSNE r0, PSP       \n"  // Use Process Stack Pointer (RTOS task)
        "B HardFault_Handler_C\n" // Branch to C handler with stack ptr in r0
    );
}

// Post-reset: check if we're recovering from a fault
void check_fault_record(void) {
    if (fault_record.magic == 0xDEADFA01) {
        // We just recovered from a HardFault
        // Log the fault information before clearing
        log_error("HardFault recovered! PC=0x%08X LR=0x%08X CFSR=0x%08X",
                  fault_record.frame.pc,
                  fault_record.frame.lr,
                  fault_record.cfsr);

        if (fault_record.fault_count > 3) {
            // Crash loop detected — enter safe mode
            // Best practice: have a degraded-but-safe operating mode
            enter_safe_mode();
        }

        fault_record.magic = 0;  // Clear the record
    }
}
```

## Watchdog Timer Recovery

A **watchdog timer** is your last line of defense against firmware lockups. If the software fails to "kick" (reset) the watchdog within a configured timeout, the hardware forces a system reset. **However**, a naive watchdog implementation that just kicks from the main loop can mask problems — if one task is stuck but the main loop still runs, the watchdog won't fire.

The **best practice** is a **task-level watchdog** where each critical task must check in, and a supervisor task kicks the hardware watchdog only if all tasks have checked in:

```c
#include <stdint.h>
#include <stdbool.h>

#define MAX_WATCHED_TASKS 8

typedef struct {
    const char *name;
    uint32_t timeout_ms;       // Maximum allowed silence period
    uint32_t last_checkin_ms;  // Timestamp of last check-in
    bool enabled;
    bool alive;                // Set true by task, cleared by supervisor
} WatchedTask;

typedef struct {
    WatchedTask tasks[MAX_WATCHED_TASKS];
    uint32_t task_count;
    uint32_t supervisor_period_ms;
} TaskWatchdog;

static TaskWatchdog watchdog;

// Register a task to be monitored
// Call during system initialization
int watchdog_register(const char *name, uint32_t timeout_ms) {
    if (watchdog.task_count >= MAX_WATCHED_TASKS) return -1;

    int id = watchdog.task_count++;
    watchdog.tasks[id].name = name;
    watchdog.tasks[id].timeout_ms = timeout_ms;
    watchdog.tasks[id].last_checkin_ms = hal->get_tick_ms();
    watchdog.tasks[id].enabled = true;
    watchdog.tasks[id].alive = true;
    return id;
}

// Called by each task periodically to signal it's alive
// Pitfall: checking in from inside a busy-wait loop defeats the
// purpose — only check in at natural task boundaries
void watchdog_checkin(int task_id) {
    if (task_id >= 0 && task_id < (int)watchdog.task_count) {
        watchdog.tasks[task_id].last_checkin_ms = hal->get_tick_ms();
        watchdog.tasks[task_id].alive = true;
    }
}

// Supervisor task — runs periodically, kicks hardware watchdog
// only if ALL registered tasks are healthy
void watchdog_supervisor_run(void) {
    uint32_t now = hal->get_tick_ms();
    bool all_healthy = true;

    for (uint32_t i = 0; i < watchdog.task_count; i++) {
        WatchedTask *t = &watchdog.tasks[i];
        if (!t->enabled) continue;

        uint32_t elapsed = now - t->last_checkin_ms;
        if (elapsed > t->timeout_ms) {
            // This task has not checked in within its timeout
            // Log the offending task before reset
            log_error("Watchdog: task '%s' unresponsive for %u ms (limit %u)",
                     t->name, elapsed, t->timeout_ms);
            all_healthy = false;
        }
    }

    if (all_healthy) {
        // All tasks alive — kick the hardware watchdog
        HAL_IWDG_Refresh(&hiwdg);
    }
    // If not all healthy, DON'T kick — let the hardware watchdog reset us
    // The fault_record from the HardFault handler (placed in .noinit RAM)
    // will tell us which task was stuck after we reboot
}
```

## Hardware-in-the-Loop (HIL) Testing

HIL testing bridges the gap between unit tests (fast but artificial) and field testing (realistic but expensive). A HIL setup replaces the physical plant (motor, sensors, environment) with a **real-time simulator** that responds to your firmware's outputs and feeds simulated inputs back. This lets you test edge cases that are dangerous or impossible to create in the real world: sensor failures, extreme temperatures, EMI spikes, and communication bus errors.

The **trade-off** is that HIL rigs are expensive and complex to build, **however** they pay for themselves by catching integration bugs before hardware prototypes exist and enabling automated regression testing.

## Code Coverage and Static Analysis

A **common mistake** is treating code coverage as a desktop-only practice. You can measure coverage on embedded targets using:

1. **Instrumented builds**: The compiler inserts counter increments at branch points. Run your test suite, read counters via JTAG/SWD, and generate coverage reports. The overhead is 10-30% code size and 5-15% runtime — acceptable for testing builds.

2. **JTAG trace**: Cortex-M trace ports (ETM/ITM) record executed instructions without modifying the binary. Zero overhead, but requires expensive debug hardware (Lauterbach, Segger J-Trace).

3. **Simulation**: Run the firmware in QEMU or Renode, which emulate the MCU and peripherals. Full coverage instrumentation with zero hardware needed.

**Static analysis** tools (PC-lint, Polyspace, Coverity, cppcheck) analyze source code without executing it, finding:
- Buffer overflows and array out-of-bounds
- Null pointer dereferences
- Uninitialized variable usage
- MISRA-C rule violations
- Dead code and unreachable paths
- Concurrency issues (data races between ISRs and tasks)

The **best practice** is to integrate static analysis into your CI pipeline so every commit is automatically checked. This catches bugs before they reach hardware testing, which is 10-100x cheaper than finding them in the field.

## Key Takeaways

- **Mock HAL layers** enable fast unit testing on your development PC by abstracting hardware behind function pointers — this separates business logic from hardware access and allows testing timeout paths, error conditions, and edge cases that are hard to reproduce on real hardware
- The **HardFault handler** is the most important debugging tool in Cortex-M development: it captures the exact faulting instruction (PC), call chain (LR), and fault type (CFSR) — without it, crashes are opaque and nearly impossible to diagnose in the field
- **Task-level watchdog monitoring** is a **best practice** over simple main-loop watchdog kicking, because it detects individual task lockups rather than just whole-system hangs — a **common mistake** is kicking the watchdog from the idle loop, which masks task-level failures
- The `.noinit` RAM section preserves fault records across resets, enabling **post-mortem debugging** and crash-loop detection — this is essential for devices deployed in the field where JTAG access is impossible
- **Hardware-in-the-loop testing** is expensive to set up but provides the only way to test firmware against realistic physical scenarios (sensor faults, communication errors, extreme conditions) without risking real hardware — the **trade-off** is setup cost versus the cost of field failures
- **Static analysis** in CI catches 30-70% of embedded bugs (buffer overflows, null pointers, MISRA violations) before code reaches hardware, however it produces false positives that require tuning — the investment in proper configuration pays for itself many times over in reduced debugging time
"""
    ),
]
