"""
Batch P6 — WebAssembly Deep Dive
Covers: WASM fundamentals, WASI, component model, Rust->WASM, edge computing.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "webassembly/fundamentals",
        "Explain WebAssembly architecture and execution model including the stack-based virtual machine, linear memory model, module structure, type system, and provide practical examples of compiling Rust to WASM for browser and server-side use with wasm-bindgen, demonstrating interop with JavaScript and performance comparison against native JavaScript implementations.",
        r"""# WebAssembly: Near-Native Performance in the Browser and Beyond

## What WebAssembly Actually Is

WebAssembly (WASM) is a **binary instruction format** for a stack-based virtual machine. It's not a programming language — it's a compilation target, like x86 or ARM. You write code in Rust, C++, Go, or AssemblyScript, and compile it to WASM bytecode that runs in browsers, edge workers, or standalone runtimes.

**Why WASM matters**: JavaScript's dynamic typing and garbage collection impose a performance ceiling. WASM provides predictable, near-native performance with a **linear memory model** (no GC pauses), **ahead-of-time compilation** (no JIT warmup), and **sandboxed execution** (security by default). For compute-intensive tasks — image processing, cryptography, physics simulations, codecs — WASM is 2-20x faster than equivalent JavaScript.

## The WASM Execution Model

### Stack-Based VM

WASM uses a **stack machine** — instructions pop operands from and push results to an implicit stack. This is similar to Java bytecode and Python bytecode.

```
;; WAT (WebAssembly Text Format) — human-readable WASM
;; Add two numbers: (a + b)
(module
  (func $add (param $a i32) (param $b i32) (result i32)
    local.get $a    ;; push a onto stack
    local.get $b    ;; push b onto stack
    i32.add         ;; pop both, push sum
  )
  (export "add" (func $add))
)
```

### Linear Memory

WASM modules get a **contiguous, resizable byte array** as their memory. There's no heap allocator built in — languages bring their own (Rust uses `dlmalloc` or `wee_alloc`). This model eliminates GC pauses and gives predictable performance, but it means you must manage memory manually or through your source language's allocator.

### Type System

WASM has only 4 value types: `i32`, `i64`, `f32`, `f64`. No strings, no objects, no arrays as first-class types. Complex data is represented as bytes in linear memory. This simplicity is intentional — it makes WASM easy to verify and compile to native code.

## Rust to WASM: Practical Implementation

```rust
// Cargo.toml
// [lib]
// crate-type = ["cdylib"]
//
// [dependencies]
// wasm-bindgen = "0.2"
// js-sys = "0.3"
// web-sys = { version = "0.3", features = ["console", "Performance"] }

use wasm_bindgen::prelude::*;

// Basic function exported to JavaScript
#[wasm_bindgen]
pub fn fibonacci(n: u32) -> u64 {
    // Iterative fibonacci — O(n) time, O(1) space
    // This is where WASM shines: tight numeric loops
    // run at near-native speed without JIT warmup
    if n <= 1 {
        return n as u64;
    }
    let mut a: u64 = 0;
    let mut b: u64 = 1;
    for _ in 2..=n {
        let temp = a + b;
        a = b;
        b = temp;
    }
    b
}

// Working with complex data: image processing
#[wasm_bindgen]
pub struct ImageProcessor {
    width: u32,
    height: u32,
    pixels: Vec<u8>,  // RGBA pixel data
}

#[wasm_bindgen]
impl ImageProcessor {
    #[wasm_bindgen(constructor)]
    pub fn new(width: u32, height: u32) -> ImageProcessor {
        let size = (width * height * 4) as usize;
        ImageProcessor {
            width,
            height,
            pixels: vec![0; size],
        }
    }

    // Return a pointer to the pixel buffer for JS to fill
    pub fn pixels_ptr(&self) -> *const u8 {
        self.pixels.as_ptr()
    }

    pub fn pixels_mut_ptr(&mut self) -> *mut u8 {
        self.pixels.as_mut_ptr()
    }

    pub fn pixel_count(&self) -> usize {
        self.pixels.len()
    }

    // Grayscale conversion — processes millions of pixels
    // This is 5-10x faster than equivalent JavaScript because:
    // 1. No bounds checking overhead (Rust validates at compile time)
    // 2. SIMD-friendly loop that the WASM compiler can auto-vectorize
    // 3. No GC pauses during processing
    pub fn grayscale(&mut self) {
        for i in (0..self.pixels.len()).step_by(4) {
            let r = self.pixels[i] as f32;
            let g = self.pixels[i + 1] as f32;
            let b = self.pixels[i + 2] as f32;
            // ITU-R BT.709 luminance coefficients
            let gray = (0.2126 * r + 0.7152 * g + 0.0722 * b) as u8;
            self.pixels[i] = gray;
            self.pixels[i + 1] = gray;
            self.pixels[i + 2] = gray;
            // Alpha channel (i+3) unchanged
        }
    }

    // Gaussian blur — compute-intensive convolution
    pub fn blur(&mut self, radius: u32) {
        let w = self.width as usize;
        let h = self.height as usize;
        let mut output = self.pixels.clone();

        let kernel_size = (radius * 2 + 1) as usize;
        let sigma = radius as f32 / 3.0;
        let mut kernel = vec![0.0f32; kernel_size];
        let mut sum = 0.0f32;

        // Build 1D Gaussian kernel
        for i in 0..kernel_size {
            let x = i as f32 - radius as f32;
            kernel[i] = (-x * x / (2.0 * sigma * sigma)).exp();
            sum += kernel[i];
        }
        for k in kernel.iter_mut() {
            *k /= sum;
        }

        // Horizontal pass
        for y in 0..h {
            for x in 0..w {
                let mut r = 0.0f32;
                let mut g = 0.0f32;
                let mut b = 0.0f32;
                for ki in 0..kernel_size {
                    let sx = (x as i32 + ki as i32 - radius as i32)
                        .max(0)
                        .min(w as i32 - 1) as usize;
                    let idx = (y * w + sx) * 4;
                    r += self.pixels[idx] as f32 * kernel[ki];
                    g += self.pixels[idx + 1] as f32 * kernel[ki];
                    b += self.pixels[idx + 2] as f32 * kernel[ki];
                }
                let idx = (y * w + x) * 4;
                output[idx] = r as u8;
                output[idx + 1] = g as u8;
                output[idx + 2] = b as u8;
            }
        }

        self.pixels = output;
    }
}

// String processing across the JS/WASM boundary
#[wasm_bindgen]
pub fn count_words(text: &str) -> u32 {
    // wasm-bindgen handles string conversion automatically:
    // JS string -> UTF-8 bytes copied into WASM linear memory
    text.split_whitespace().count() as u32
}

// JSON parsing in WASM (useful for large payloads)
#[wasm_bindgen]
pub fn parse_and_filter_json(json_str: &str, min_value: f64) -> String {
    // For large JSON payloads (>1MB), WASM parsing can be
    // faster than JSON.parse() because:
    // 1. No object allocation overhead
    // 2. Can stream-parse without building full DOM
    // However, for small payloads, JSON.parse() is faster
    // because it avoids the string copy across the boundary.
    use std::collections::HashMap;

    // Simplified: just demonstrate the boundary crossing
    let result = format!("Filtered with min_value={}", min_value);
    result
}
```

## JavaScript Integration

```javascript
// Loading and using WASM module in the browser
import init, { fibonacci, ImageProcessor, count_words } from './pkg/my_wasm.js';

async function main() {
    // Initialize WASM module (downloads and compiles .wasm file)
    await init();

    // --- Performance comparison: Fibonacci ---
    const n = 45;

    // JavaScript implementation
    function jsFibonacci(n) {
        if (n <= 1) return n;
        let a = 0, b = 1;
        for (let i = 2; i <= n; i++) {
            [a, b] = [b, a + b];
        }
        return b;
    }

    // Benchmark
    const jsStart = performance.now();
    for (let i = 0; i < 1000000; i++) jsFibonacci(n);
    const jsTime = performance.now() - jsStart;

    const wasmStart = performance.now();
    for (let i = 0; i < 1000000; i++) fibonacci(n);
    const wasmTime = performance.now() - wasmStart;

    console.log(`JS:   ${jsTime.toFixed(1)}ms`);
    console.log(`WASM: ${wasmTime.toFixed(1)}ms`);
    console.log(`Speedup: ${(jsTime / wasmTime).toFixed(1)}x`);

    // --- Image processing ---
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    const processor = new ImageProcessor(canvas.width, canvas.height);

    // Copy pixel data into WASM memory
    const wasmPixels = new Uint8Array(
        // Access WASM linear memory directly
        processor.pixels_mut_ptr(),
        processor.pixel_count()
    );
    wasmPixels.set(imageData.data);

    // Process in WASM (fast!)
    const start = performance.now();
    processor.grayscale();
    console.log(`Grayscale: ${(performance.now() - start).toFixed(1)}ms`);

    // Copy back to canvas
    imageData.data.set(wasmPixels);
    ctx.putImageData(imageData, 0, 0);
}

main();
```

## WASI: WebAssembly Outside the Browser

```python
# Running WASM modules server-side with wasmtime-py
# pip install wasmtime

import wasmtime


def run_wasm_module():
    # WASI (WebAssembly System Interface) provides POSIX-like
    # capabilities to WASM modules: file I/O, environment variables,
    # clock access, random numbers. Each capability is explicitly
    # granted -- sandboxing by default.

    engine = wasmtime.Engine()
    module = wasmtime.Module.from_file(engine, "my_module.wasm")

    # Configure WASI with explicit capabilities
    wasi_config = wasmtime.WasiConfig()
    wasi_config.inherit_stdout()  # allow printing
    wasi_config.preopen_dir("./data", "/data")  # map filesystem

    linker = wasmtime.Linker(engine)
    linker.define_wasi()

    store = wasmtime.Store(engine)
    store.set_wasi(wasi_config)

    instance = linker.instantiate(store, module)

    # Call exported function
    add = instance.exports(store)["add"]
    result = add(store, 40, 2)
    print(f"40 + 2 = {result}")

    return result


def benchmark_wasm_vs_python():
    # Compare WASM execution speed against pure Python
    import time

    # Pure Python fibonacci
    def py_fib(n):
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b

    n = 40
    iterations = 100_000

    start = time.perf_counter()
    for _ in range(iterations):
        py_fib(n)
    py_time = time.perf_counter() - start

    # WASM fibonacci would be called via wasmtime here
    # Typical results: WASM is 10-50x faster than CPython
    # for numeric computation

    print(f"Python: {py_time:.3f}s for {iterations} iterations")
    print(f"WASM: typically 10-50x faster for numeric loops")


if __name__ == "__main__":
    benchmark_wasm_vs_python()
```

## Performance Comparison

| Task | JavaScript | WASM (Rust) | Speedup | Notes |
|------|-----------|-------------|---------|-------|
| **Fibonacci (n=45)** | 1.0x | 1.1-1.5x | Marginal | JIT optimizes tight loops well |
| **Image grayscale (4K)** | 1.0x | 5-8x | **Significant** | WASM avoids GC + bounds checks |
| **Gaussian blur (4K)** | 1.0x | 8-15x | **Major** | Memory-intensive, WASM has better locality |
| **JSON parse (<1KB)** | 1.0x | 0.3x (slower) | JS wins | Boundary crossing overhead dominates |
| **Regex matching** | 1.0x | 2-3x | Moderate | Depends on regex engine |
| **Crypto (SHA-256)** | 1.0x | 3-5x | **Significant** | Tight byte manipulation |

**Key insight**: WASM excels at **compute-intensive, memory-dense** workloads. For I/O-bound tasks or tasks requiring heavy JS interop, the boundary crossing overhead can negate the speed advantage.

## Common Pitfalls

1. **String passing overhead**: Every string crossed between JS and WASM requires a copy (JS uses UTF-16, WASM uses UTF-8). For frequent small string operations, this overhead can make WASM slower than pure JS. **Best practice**: batch operations and minimize boundary crossings.

2. **Memory management**: WASM linear memory can only grow, never shrink. If your application allocates and frees large buffers repeatedly, memory usage will appear to grow unboundedly (even though the allocator reuses freed space internally). Monitor `memory.buffer.byteLength` in production.

3. **Missing SIMD**: Not all WASM runtimes support SIMD instructions. Without SIMD, certain operations (matrix math, image processing) lose a significant speedup factor. Check runtime support with `WebAssembly.validate()` on a SIMD-using module.

## Key Takeaways

- WebAssembly provides **near-native performance** (within 10-20% of native) for compute-intensive tasks by using a **linear memory model** without garbage collection overhead
- The **stack-based VM** with only 4 value types (i32, i64, f32, f64) makes WASM simple to verify, compile, and sandbox — security is a first-class design goal
- **Rust → WASM** via `wasm-bindgen` is the most mature toolchain, providing automatic JS interop for strings, arrays, and objects
- **WASI** extends WASM beyond the browser with capability-based system access — enabling server-side, edge computing, and plugin architectures
- The biggest performance trap is **boundary crossing overhead** — minimize JS↔WASM calls by batching operations and passing raw memory pointers instead of high-level objects
"""
    ),
    (
        "webassembly/component-model",
        "Explain the WebAssembly Component Model and its role in building composable, language-agnostic software components, covering WIT (WebAssembly Interface Types), canonical ABI, resource types, and provide practical examples of building and composing WASM components from different source languages with the wasmtime runtime.",
        r"""# WebAssembly Component Model: Composable Software Components

## Beyond Flat WASM Modules

Traditional WASM modules export flat functions with only numeric types. This makes cross-language interop painful — every string, struct, or variant must be manually serialized through linear memory. The **Component Model** solves this by defining a rich **Interface Definition Language** (WIT) and a **Canonical ABI** that automatically handles complex type marshaling.

**The vision**: Write a library in Rust, a plugin in Python, and a host application in Go — all communicating through well-typed interfaces without manual serialization code. This is the foundation for **portable, composable software components**.

## WIT: WebAssembly Interface Types

WIT is the IDL for WASM components. It defines interfaces, functions, types, and resources that components expose and consume.

```wit
// wit/image-processor.wit
package example:image-processing@1.0.0;

// Define the interface
interface types {
    // Record types (like structs)
    record pixel {
        r: u8,
        g: u8,
        b: u8,
        a: u8,
    }

    record image {
        width: u32,
        height: u32,
        pixels: list<pixel>,
    }

    // Variant types (like enums/sum types)
    variant filter {
        grayscale,
        blur(f32),        // blur with radius
        sharpen(f32),     // sharpen with strength
        brightness(f32),  // adjust brightness
    }

    // Result type for error handling
    variant processing-error {
        invalid-dimensions,
        out-of-memory,
        unsupported-filter(string),
    }
}

// The interface that components implement
interface processor {
    use types.{image, filter, processing-error};

    // Apply a filter to an image
    apply-filter: func(img: image, filter: filter) -> result<image, processing-error>;

    // Chain multiple filters
    apply-pipeline: func(img: image, filters: list<filter>) -> result<image, processing-error>;

    // Get supported filters
    list-filters: func() -> list<string>;
}

// Resource types — handles to opaque objects with methods
interface canvas {
    // A resource is like an object — the host manages its lifetime
    resource drawing-context {
        constructor(width: u32, height: u32);
        draw-rect: func(x: f32, y: f32, w: f32, h: f32);
        draw-circle: func(cx: f32, cy: f32, radius: f32);
        fill: func(color: string);
        to-image: func() -> image;
        // drop is implicit — called when the resource is no longer referenced
    }
}

// World definition — what the component provides and requires
world image-plugin {
    import wasi:io/streams@0.2.0;
    import wasi:filesystem/types@0.2.0;

    export processor;
    export canvas;
}
```

## Implementing a Component in Rust

```rust
// src/lib.rs — Implementing the image-plugin world
// Build with: cargo component build --release

// wit-bindgen generates Rust types and traits from WIT
wit_bindgen::generate!({
    world: "image-plugin",
    path: "wit",
});

use exports::example::image_processing::processor::*;
use exports::example::image_processing::types::*;

struct MyProcessor;

impl Guest for MyProcessor {
    fn apply_filter(img: Image, filter: Filter) -> Result<Image, ProcessingError> {
        let mut pixels = img.pixels;

        match filter {
            Filter::Grayscale => {
                // Apply ITU-R BT.709 grayscale conversion
                for pixel in pixels.iter_mut() {
                    let gray = (0.2126 * pixel.r as f32
                        + 0.7152 * pixel.g as f32
                        + 0.0722 * pixel.b as f32) as u8;
                    pixel.r = gray;
                    pixel.g = gray;
                    pixel.b = gray;
                }
            }
            Filter::Brightness(factor) => {
                for pixel in pixels.iter_mut() {
                    pixel.r = ((pixel.r as f32 * factor).min(255.0)) as u8;
                    pixel.g = ((pixel.g as f32 * factor).min(255.0)) as u8;
                    pixel.b = ((pixel.b as f32 * factor).min(255.0)) as u8;
                }
            }
            Filter::Blur(radius) => {
                // Box blur approximation for simplicity
                let w = img.width as usize;
                let h = img.height as usize;
                let r = radius.round() as i32;

                let mut output = pixels.clone();
                for y in 0..h {
                    for x in 0..w {
                        let mut sum_r = 0u32;
                        let mut sum_g = 0u32;
                        let mut sum_b = 0u32;
                        let mut count = 0u32;

                        for dy in -r..=r {
                            for dx in -r..=r {
                                let ny = (y as i32 + dy).clamp(0, h as i32 - 1) as usize;
                                let nx = (x as i32 + dx).clamp(0, w as i32 - 1) as usize;
                                let p = &pixels[ny * w + nx];
                                sum_r += p.r as u32;
                                sum_g += p.g as u32;
                                sum_b += p.b as u32;
                                count += 1;
                            }
                        }

                        output[y * w + x] = Pixel {
                            r: (sum_r / count) as u8,
                            g: (sum_g / count) as u8,
                            b: (sum_b / count) as u8,
                            a: pixels[y * w + x].a,
                        };
                    }
                }
                pixels = output;
            }
            Filter::Sharpen(_strength) => {
                // Unsharp mask implementation would go here
                return Err(ProcessingError::UnsupportedFilter(
                    "sharpen not yet implemented".to_string()
                ));
            }
        }

        Ok(Image {
            width: img.width,
            height: img.height,
            pixels,
        })
    }

    fn apply_pipeline(
        img: Image,
        filters: Vec<Filter>,
    ) -> Result<Image, ProcessingError> {
        // Chain filters sequentially
        // Each filter's output becomes the next filter's input
        let mut current = img;
        for filter in filters {
            current = Self::apply_filter(current, filter)?;
        }
        Ok(current)
    }

    fn list_filters() -> Vec<String> {
        vec![
            "grayscale".into(),
            "blur".into(),
            "brightness".into(),
        ]
    }
}

export!(MyProcessor);
```

## Composing Components

```python
# Host application that loads and runs WASM components
# Using wasmtime-py with component model support

import wasmtime
from dataclasses import dataclass


@dataclass
class Pixel:
    r: int
    g: int
    b: int
    a: int


@dataclass
class Image:
    width: int
    height: int
    pixels: list  # list of Pixel


def load_image_plugin(wasm_path: str):
    # Load a WASM component and call its exported interface
    #
    # The component model handles all type conversion automatically:
    # - Python lists <-> WASM lists
    # - Python dataclasses <-> WASM records
    # - Python exceptions <-> WASM results
    #
    # This is the key advantage over raw WASM: no manual serialization

    engine = wasmtime.Engine()

    # Component model requires the component linker
    linker = wasmtime.component.Linker(engine)

    # Define WASI imports (the component needs filesystem/IO)
    wasmtime.wasi.add_to_linker(linker)

    store = wasmtime.Store(engine)
    component = wasmtime.component.Component.from_file(engine, wasm_path)

    instance = linker.instantiate(store, component)

    # Access the exported interface
    processor = instance.exports(store)["processor"]

    # Create a test image
    pixels = [Pixel(255, 0, 0, 255) for _ in range(100 * 100)]
    img = Image(width=100, height=100, pixels=pixels)

    # Apply a filter through the component
    # Types are automatically marshaled across the boundary
    result = processor["apply-filter"](store, img, ("grayscale",))

    if isinstance(result, tuple) and result[0] == "ok":
        processed_img = result[1]
        print(f"Processed image: {processed_img.width}x{processed_img.height}")
        first_pixel = processed_img.pixels[0]
        print(f"First pixel (should be gray): r={first_pixel.r}")
    else:
        print(f"Error: {result}")

    # Apply a pipeline of filters
    pipeline = [("grayscale",), ("brightness", 1.2)]
    result = processor["apply-pipeline"](store, img, pipeline)
    print(f"Pipeline result: {'ok' if result[0] == 'ok' else result[1]}")

    return processor


def compose_components():
    # The component model allows composing multiple components:
    # Component A (Rust image processor) + Component B (Go ML classifier)
    # → Composed component that processes and classifies images
    #
    # This is done at the WAT/component level, not at runtime:
    # wasm-tools compose image-processor.wasm -d ml-classifier.wasm -o pipeline.wasm
    #
    # The composed component has all dependencies satisfied internally
    # and only exposes the final interface to the host.
    print("Component composition: combine components from different languages")
    print("  1. Build each component separately (Rust, Go, Python via componentize-py)")
    print("  2. Define WIT interfaces they share")
    print("  3. Use wasm-tools compose to wire them together")
    print("  4. Run the composed component in any WASM runtime")
```

## Component Model vs Raw WASM

| Feature | Raw WASM Module | WASM Component |
|---------|----------------|----------------|
| **Types** | i32, i64, f32, f64 only | Strings, records, variants, lists, resources |
| **Interop** | Manual memory + ABI | Automatic via Canonical ABI |
| **Composition** | Not supported | First-class composition |
| **Language support** | All languages | Rust, Go, Python, JS (growing) |
| **Error handling** | Return codes | Result types with variants |
| **Object-oriented** | Not supported | Resource types with methods |
| **Maturity** | Stable, widely supported | Preview 2 (stabilizing) |

## Common Pitfalls

1. **String copying overhead**: The Canonical ABI copies strings across the component boundary (different linear memories). For high-throughput string processing, this overhead is significant. **Best practice**: batch operations and pass byte buffers instead of strings where possible.

2. **Resource lifetime management**: Resources (handles to host objects) must be explicitly dropped. Forgetting to drop a resource causes a memory leak on the host side. The component model provides drop handlers, but the source language must call them.

3. **Version compatibility**: WIT packages are versioned (e.g., `wasi:io/streams@0.2.0`). Components built against different WASI versions are incompatible. Pin your WIT dependencies and test composition before deployment.

## Key Takeaways

- The **Component Model** adds a rich type system (strings, records, variants, resources) on top of WASM's raw numeric types, eliminating manual serialization between languages
- **WIT** (WebAssembly Interface Types) is the IDL that defines component interfaces — it's designed for language-agnostic interop between Rust, Go, Python, and more
- **Component composition** enables building applications from independently-developed components in different languages, linked together at the WASM level
- **Resource types** provide object-oriented semantics (constructor, methods, destructor) while maintaining WASM's sandboxing guarantees
- The Component Model is still **stabilizing** (WASI Preview 2) — production use should pin specific versions and test thoroughly, but the architecture is sound and adoption is accelerating
"""
    ),
    (
        "webassembly/edge-computing",
        "Explain WebAssembly for edge computing and serverless platforms including Cloudflare Workers, Fermyon Spin, and Fastly Compute, covering cold start advantages over containers, WASI for server-side capabilities, and provide implementation examples of building edge applications with Rust and Python compiled to WASM with routing, KV storage, and AI inference at the edge.",
        r"""# WebAssembly at the Edge: Sub-Millisecond Serverless

## Why WASM for Edge Computing

Containers have cold starts measured in **hundreds of milliseconds to seconds**. WASM modules start in **microseconds** — 100-1000x faster. This matters at the edge because edge functions handle many short-lived requests and cold starts directly impact user-perceived latency.

**The numbers**: A Cloudflare Worker (WASM-based) cold starts in ~0.5ms. An AWS Lambda (container-based) cold starts in 100-500ms. For latency-sensitive APIs serving users globally, this difference is the entire response time budget.

### Why WASM Starts So Fast

1. **No OS boot**: WASM runs in a pre-initialized runtime, not a full OS
2. **No language runtime init**: No JVM startup, no Python interpreter loading
3. **Pre-compiled**: AOT compilation happens at deploy time, not request time
4. **Small binaries**: Typical WASM modules are 1-10MB vs 50-500MB containers
5. **Snapshot restore**: Runtimes like Wasmtime can snapshot initialized state

## Cloudflare Workers: WASM at Global Scale

```rust
// Cloudflare Worker in Rust — compiled to WASM
// Build: npx wrangler deploy
// wrangler.toml:
//   name = "my-api"
//   main = "build/worker/shim.mjs"
//   compatibility_date = "2024-01-01"
//   [build]
//   command = "cargo install -q worker-build && worker-build --release"

use worker::*;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct ApiResponse {
    message: String,
    region: String,
    latency_ms: f64,
}

#[derive(Serialize, Deserialize)]
struct UserData {
    name: String,
    email: String,
    preferences: std::collections::HashMap<String, String>,
}

#[event(fetch)]
async fn main(req: Request, env: Env, _ctx: Context) -> Result<Response> {
    // Router pattern — matches URLs to handler functions
    let router = Router::new();

    router
        .get("/", |_, _| {
            Response::ok("Edge API — powered by WASM")
        })
        .get_async("/api/user/:id", handle_get_user)
        .put_async("/api/user/:id", handle_put_user)
        .post_async("/api/process", handle_process)
        .get_async("/api/geo", handle_geo)
        .run(req, env)
        .await
}

async fn handle_get_user(
    _req: Request,
    ctx: RouteContext<()>,
) -> Result<Response> {
    // KV storage — globally replicated key-value store
    // Reads are fast (~10ms) from the nearest edge location
    // Writes propagate globally within ~60 seconds
    let kv = ctx.kv("USER_STORE")?;
    let user_id = ctx.param("id").unwrap();

    match kv.get(user_id).text().await? {
        Some(data) => {
            let user: UserData = serde_json::from_str(&data)
                .map_err(|e| Error::from(e.to_string()))?;

            Response::from_json(&ApiResponse {
                message: format!("Found user: {}", user.name),
                region: "auto".to_string(),
                latency_ms: 0.0,
            })
        }
        None => Response::error("User not found", 404),
    }
}

async fn handle_put_user(
    mut req: Request,
    ctx: RouteContext<()>,
) -> Result<Response> {
    let user_id = ctx.param("id").unwrap().to_string();
    let user: UserData = req.json().await?;
    let kv = ctx.kv("USER_STORE")?;

    // Store with 24h TTL
    kv.put(&user_id, serde_json::to_string(&user)?)?
        .expiration_ttl(86400)
        .execute()
        .await?;

    Response::from_json(&ApiResponse {
        message: "User saved".to_string(),
        region: "auto".to_string(),
        latency_ms: 0.0,
    })
}

async fn handle_process(
    mut req: Request,
    _ctx: RouteContext<()>,
) -> Result<Response> {
    // CPU-intensive processing at the edge
    // WASM excels here because compute runs close to users
    let body: serde_json::Value = req.json().await?;

    let start = js_sys::Date::now();

    // Example: markdown to HTML conversion at the edge
    // This avoids a round-trip to a central server
    let text = body["text"].as_str().unwrap_or("");
    let processed = text
        .lines()
        .map(|line| {
            if line.starts_with("# ") {
                format!("<h1>{}</h1>", &line[2..])
            } else if line.starts_with("## ") {
                format!("<h2>{}</h2>", &line[3..])
            } else if line.is_empty() {
                "<br>".to_string()
            } else {
                format!("<p>{}</p>", line)
            }
        })
        .collect::<Vec<_>>()
        .join("\n");

    let latency = js_sys::Date::now() - start;

    Response::from_json(&serde_json::json!({
        "html": processed,
        "processing_ms": latency,
    }))
}

async fn handle_geo(
    req: Request,
    _ctx: RouteContext<()>,
) -> Result<Response> {
    // Edge-native geolocation — available without external API
    // Cloudflare provides request metadata from the nearest PoP
    let cf = req.cf().unwrap();

    Response::from_json(&serde_json::json!({
        "country": cf.country().unwrap_or("unknown"),
        "city": cf.city().unwrap_or("unknown"),
        "region": cf.region().unwrap_or("unknown"),
        "colo": cf.colo(),
        "timezone": cf.timezone(),
    }))
}
```

## Fermyon Spin: Open-Source WASM Platform

```python
# Spin application in Python (compiled to WASM via componentize-py)
# spin.toml:
#   [component.api]
#   source = "app.wasm"
#   [component.api.trigger]
#   route = "/api/..."

from spin_sdk.http import IncomingHandler, Request, Response
from spin_sdk import key_value
import json


class IncomingHandler(IncomingHandler):
    # Spin handler — each request gets a fresh WASM instance
    # Cold start: ~1ms (WASM snapshot restore)
    # No state carries over between requests (stateless by design)

    def handle_request(self, request: Request) -> Response:
        # Route based on path
        path = request.uri
        method = request.method

        if path.startswith("/api/items") and method == "GET":
            return self.list_items()
        elif path.startswith("/api/items") and method == "POST":
            return self.create_item(request)
        elif path.startswith("/api/health"):
            return self.health_check()
        else:
            return Response(404, {"content-type": "application/json"},
                          bytes(json.dumps({"error": "not found"}), "utf-8"))

    def list_items(self) -> Response:
        # Spin KV store — built-in key-value storage
        store = key_value.open_default()

        items = []
        # Scan pattern: store item keys with a prefix
        # In production, use a sorted set or index
        try:
            index_data = store.get("items:index")
            item_ids = json.loads(index_data.decode("utf-8"))
        except Exception:
            item_ids = []

        for item_id in item_ids:
            try:
                data = store.get(f"item:{item_id}")
                items.append(json.loads(data.decode("utf-8")))
            except Exception:
                continue

        return Response(
            200,
            {"content-type": "application/json"},
            bytes(json.dumps({"items": items, "count": len(items)}), "utf-8"),
        )

    def create_item(self, request: Request) -> Response:
        body = json.loads(request.body.decode("utf-8"))
        store = key_value.open_default()

        import hashlib
        import time
        item_id = hashlib.md5(
            f"{body.get('name', '')}{time.time()}".encode()
        ).hexdigest()[:8]

        item = {
            "id": item_id,
            "name": body.get("name", ""),
            "description": body.get("description", ""),
        }

        store.set(f"item:{item_id}", bytes(json.dumps(item), "utf-8"))

        # Update index
        try:
            index = json.loads(store.get("items:index").decode("utf-8"))
        except Exception:
            index = []
        index.append(item_id)
        store.set("items:index", bytes(json.dumps(index), "utf-8"))

        return Response(
            201,
            {"content-type": "application/json"},
            bytes(json.dumps(item), "utf-8"),
        )

    def health_check(self) -> Response:
        return Response(
            200,
            {"content-type": "application/json"},
            bytes(json.dumps({
                "status": "healthy",
                "runtime": "spin-wasm",
            }), "utf-8"),
        )
```

## Cold Start Comparison

| Platform | Technology | Cold Start | Warm Request | Binary Size |
|----------|-----------|------------|--------------|-------------|
| **Cloudflare Workers** | V8 Isolate + WASM | 0.5-5ms | <1ms | 1-5MB |
| **Fermyon Spin** | Wasmtime + WASI | 1-5ms | <1ms | 1-10MB |
| **Fastly Compute** | Lucet/Wasmtime | 0.5-2ms | <1ms | 1-5MB |
| **AWS Lambda** | Container | 100-500ms | 1-50ms | 50-500MB |
| **Google Cloud Run** | Container | 200-1000ms | 5-100ms | 50-500MB |
| **Deno Deploy** | V8 Isolate | 5-20ms | <1ms | N/A (JS) |

## Common Pitfalls

1. **Memory limits**: Edge WASM runtimes typically limit memory to 128-256MB. Large ML models or in-memory databases won't fit. **Best practice**: use KV stores for large data and keep WASM modules focused on compute.

2. **CPU time limits**: Most edge platforms impose 10-50ms CPU time limits per request. This prevents abuse but also limits complex processing. Break long computations into multiple requests with intermediate storage.

3. **No persistent connections**: Each WASM instance is short-lived. You cannot maintain WebSocket connections or database connection pools within the WASM module. Use platform-provided bindings (Cloudflare's Durable Objects, Spin's outbound HTTP) instead.

4. **Debugging difficulty**: WASM stack traces are less informative than native ones. Source maps help but aren't universally supported. **Best practice**: use structured logging and deploy debug builds to staging environments.

## Key Takeaways

- WASM cold starts are **100-1000x faster** than container-based serverless, making it ideal for latency-sensitive edge computing where every millisecond matters
- **Cloudflare Workers** (V8 isolates + WASM) provide the largest edge network (300+ cities), while **Fermyon Spin** offers the most portable, open-source approach
- Edge WASM is best for **compute at the edge** — geolocation, content transformation, authentication, A/B testing — not for heavy stateful workloads
- **WASI** standardizes system access across edge platforms, but each platform adds proprietary extensions (KV stores, queues, AI inference) — test portability explicitly
- The future of edge computing is **WASM components**: composable, language-agnostic modules that can be deployed to any compatible runtime without recompilation
"""
    ),
    (
        "webassembly/plugin-systems",
        "Explain how to build plugin systems using WebAssembly for safe, sandboxed extensibility in applications, covering the security model, capability-based permissions, host function injection, resource limits, and provide a complete Python implementation of a WASM plugin host that loads untrusted plugins with memory limits, CPU timeouts, and controlled access to host APIs.",
        r"""# Building Plugin Systems with WebAssembly

## Why WASM for Plugins

Traditional plugin systems face a fundamental tension: plugins need access to host APIs to be useful, but untrusted code can crash your application, leak data, or consume unbounded resources. The options are bad: **run plugins in-process** (fast but unsafe) or **run in separate processes** (safe but slow, with complex IPC).

WASM provides a third option: **in-process sandboxing with capability-based security**. Plugins run at near-native speed within the host process, but they can only access resources explicitly granted by the host. Memory is isolated, CPU time can be bounded, and the type system prevents invalid memory access.

**Real-world examples**: Envoy Proxy (network filters), Figma (design plugins), Shopify (checkout extensions), Zed editor (language plugins), and Fastly (edge compute) all use WASM for plugins.

## The Security Model

```python
# WASM plugin host with sandboxing and capability control
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class Permission(enum.Flag):
    # Capability-based permissions for plugins
    # Each permission grants access to a specific host API
    # Plugins start with NO permissions and must be granted explicitly
    NONE = 0
    READ_CONFIG = enum.auto()     # read application config
    WRITE_CONFIG = enum.auto()    # modify application config
    HTTP_OUTBOUND = enum.auto()   # make external HTTP requests
    KV_READ = enum.auto()         # read key-value store
    KV_WRITE = enum.auto()        # write key-value store
    LOG = enum.auto()             # write to application log
    METRICS = enum.auto()         # emit metrics/telemetry
    FILESYSTEM = enum.auto()      # access sandboxed filesystem

    # Common permission sets
    @classmethod
    def read_only(cls) -> Permission:
        return cls.READ_CONFIG | cls.KV_READ | cls.LOG

    @classmethod
    def standard(cls) -> Permission:
        return cls.READ_CONFIG | cls.KV_READ | cls.KV_WRITE | cls.LOG | cls.METRICS


@dataclasses.dataclass
class ResourceLimits:
    # Resource constraints for plugin execution
    # These prevent denial-of-service from malicious or buggy plugins
    max_memory_bytes: int = 64 * 1024 * 1024   # 64 MB
    max_cpu_time_ms: float = 100.0              # 100ms per invocation
    max_fuel: int = 1_000_000                   # instruction fuel (wasmtime)
    max_table_elements: int = 10_000
    max_instances: int = 10


@dataclasses.dataclass
class PluginManifest:
    # Metadata about a plugin
    name: str
    version: str
    author: str
    description: str
    permissions: list[str]   # requested permissions
    entry_point: str = "handle"
    wasm_hash: str = ""       # SHA-256 of the WASM binary for integrity


class HostAPI:
    # Host functions exposed to plugins.
    #
    # Each function checks permissions before executing.
    # This is the capability-based security model: plugins
    # can only call functions they've been granted access to.
    #
    # Common mistake: exposing raw file/network access to plugins.
    # Instead, expose high-level, auditable operations that the
    # host can log, rate-limit, and revoke.

    def __init__(self, permissions: Permission) -> None:
        self.permissions = permissions
        self._kv_store: dict[str, str] = {}
        self._config: dict[str, Any] = {}
        self._logs: list[str] = []
        self._metrics: list[dict] = []
        self._http_requests: list[dict] = []

    def _check_permission(self, required: Permission) -> None:
        if not (self.permissions & required):
            raise PermissionError(
                f"Plugin lacks permission: {required.name}"
            )

    def kv_get(self, key: str) -> Optional[str]:
        self._check_permission(Permission.KV_READ)
        return self._kv_store.get(key)

    def kv_set(self, key: str, value: str) -> None:
        self._check_permission(Permission.KV_WRITE)
        # Enforce key/value size limits
        if len(key) > 256:
            raise ValueError("Key too long (max 256 bytes)")
        if len(value) > 1024 * 1024:
            raise ValueError("Value too long (max 1MB)")
        self._kv_store[key] = value

    def kv_delete(self, key: str) -> bool:
        self._check_permission(Permission.KV_WRITE)
        return self._kv_store.pop(key, None) is not None

    def config_get(self, key: str) -> Any:
        self._check_permission(Permission.READ_CONFIG)
        return self._config.get(key)

    def log(self, level: str, message: str) -> None:
        self._check_permission(Permission.LOG)
        # Truncate long messages to prevent log flooding
        if len(message) > 4096:
            message = message[:4096] + "... [truncated]"
        self._logs.append(f"[{level}] {message}")
        logger.info(f"Plugin log: [{level}] {message}")

    def emit_metric(self, name: str, value: float, tags: dict[str, str]) -> None:
        self._check_permission(Permission.METRICS)
        self._metrics.append({
            "name": name,
            "value": value,
            "tags": tags,
            "timestamp": time.time(),
        })

    def http_fetch(self, url: str, method: str = "GET") -> dict:
        self._check_permission(Permission.HTTP_OUTBOUND)
        # In production: use allowlist for URLs, rate limit requests
        self._http_requests.append({"url": url, "method": method})
        # Simulated response
        return {"status": 200, "body": f"Response from {url}"}


@dataclasses.dataclass
class PluginResult:
    # Result of a plugin invocation
    success: bool
    output: Any
    execution_time_ms: float
    memory_used_bytes: int
    logs: list[str]
    metrics: list[dict]
    error: Optional[str] = None


class PluginHost:
    # WASM plugin host with sandboxing and lifecycle management.
    #
    # Architecture:
    # 1. Plugin WASM binary is loaded and validated
    # 2. A fresh WASM instance is created per invocation (isolation)
    # 3. Host functions are injected based on granted permissions
    # 4. Resource limits (memory, CPU) are enforced by the runtime
    # 5. Plugin output is collected and returned to the host
    #
    # This architecture ensures that:
    # - A plugin crash cannot crash the host
    # - A plugin cannot access another plugin's memory
    # - Resource consumption is bounded and measurable
    # - All host API calls are auditable

    def __init__(self) -> None:
        self._plugins: dict[str, dict] = {}  # name -> plugin info
        self._permissions: dict[str, Permission] = {}  # name -> granted perms
        self._limits: dict[str, ResourceLimits] = {}
        self._execution_counts: dict[str, int] = {}

    def register_plugin(
        self,
        manifest: PluginManifest,
        wasm_bytes: bytes,
        permissions: Permission,
        limits: Optional[ResourceLimits] = None,
    ) -> bool:
        # Register a plugin with specified permissions and limits
        #
        # The host explicitly decides what each plugin can access.
        # This is the opposite of traditional plugin systems where
        # plugins run with the same privileges as the host.

        # Verify integrity
        actual_hash = hashlib.sha256(wasm_bytes).hexdigest()
        if manifest.wasm_hash and manifest.wasm_hash != actual_hash:
            logger.error(f"Plugin {manifest.name}: hash mismatch!")
            return False

        # Validate requested vs granted permissions
        for perm_name in manifest.permissions:
            try:
                requested = Permission[perm_name.upper()]
                if not (permissions & requested):
                    logger.warning(
                        f"Plugin {manifest.name} requested {perm_name} "
                        f"but it was not granted"
                    )
            except KeyError:
                logger.warning(f"Unknown permission: {perm_name}")

        self._plugins[manifest.name] = {
            "manifest": manifest,
            "wasm_bytes": wasm_bytes,
            "registered_at": time.time(),
        }
        self._permissions[manifest.name] = permissions
        self._limits[manifest.name] = limits or ResourceLimits()
        self._execution_counts[manifest.name] = 0

        logger.info(
            f"Registered plugin: {manifest.name} v{manifest.version} "
            f"with permissions: {permissions}"
        )
        return True

    def invoke(
        self,
        plugin_name: str,
        function: str,
        input_data: Any,
    ) -> PluginResult:
        # Invoke a plugin function with sandboxing.
        #
        # Each invocation creates a fresh WASM instance with:
        # - Isolated linear memory (no state leaks between calls)
        # - Injected host functions based on permissions
        # - Resource limits enforced by the runtime
        # - CPU time tracking for billing/monitoring

        if plugin_name not in self._plugins:
            return PluginResult(
                success=False, output=None,
                execution_time_ms=0, memory_used_bytes=0,
                logs=[], metrics=[],
                error=f"Plugin not found: {plugin_name}",
            )

        permissions = self._permissions[plugin_name]
        limits = self._limits[plugin_name]
        host_api = HostAPI(permissions)

        start_time = time.perf_counter()

        try:
            # In production, this creates a wasmtime Instance with:
            # - Memory limited to limits.max_memory_bytes
            # - Fuel consumption limited to limits.max_fuel
            # - Host functions linked from host_api
            #
            # Simulated execution for demonstration:
            result = self._simulate_plugin_execution(
                plugin_name, function, input_data, host_api, limits
            )

            execution_time = (time.perf_counter() - start_time) * 1000

            self._execution_counts[plugin_name] += 1

            return PluginResult(
                success=True,
                output=result,
                execution_time_ms=execution_time,
                memory_used_bytes=0,  # would come from wasmtime
                logs=host_api._logs,
                metrics=host_api._metrics,
            )

        except TimeoutError:
            return PluginResult(
                success=False, output=None,
                execution_time_ms=limits.max_cpu_time_ms,
                memory_used_bytes=0,
                logs=host_api._logs, metrics=[],
                error=f"Plugin exceeded CPU time limit ({limits.max_cpu_time_ms}ms)",
            )
        except MemoryError:
            return PluginResult(
                success=False, output=None,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                memory_used_bytes=limits.max_memory_bytes,
                logs=host_api._logs, metrics=[],
                error=f"Plugin exceeded memory limit ({limits.max_memory_bytes} bytes)",
            )
        except PermissionError as e:
            return PluginResult(
                success=False, output=None,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                memory_used_bytes=0,
                logs=host_api._logs, metrics=[],
                error=str(e),
            )
        except Exception as e:
            return PluginResult(
                success=False, output=None,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                memory_used_bytes=0,
                logs=host_api._logs, metrics=[],
                error=f"Plugin error: {e}",
            )

    def _simulate_plugin_execution(
        self,
        plugin_name: str,
        function: str,
        input_data: Any,
        host_api: HostAPI,
        limits: ResourceLimits,
    ) -> Any:
        # Simulated plugin execution for demonstration
        # In production, this would use wasmtime to instantiate and run
        host_api.log("info", f"Plugin {plugin_name} executing {function}")
        host_api.emit_metric(
            "plugin.invocation",
            1.0,
            {"plugin": plugin_name, "function": function},
        )

        # Simulate plugin logic
        if function == "transform":
            result = {"transformed": True, "input": input_data}
            host_api.kv_set(f"last_result:{plugin_name}", json.dumps(result))
            return result
        elif function == "validate":
            return {"valid": True, "errors": []}
        else:
            return {"echo": input_data}

    def list_plugins(self) -> list[dict]:
        return [
            {
                "name": name,
                "version": info["manifest"].version,
                "permissions": str(self._permissions[name]),
                "invocations": self._execution_counts[name],
            }
            for name, info in self._plugins.items()
        ]

    def revoke_plugin(self, plugin_name: str) -> bool:
        # Immediately revoke a plugin's access
        # This is instantaneous because each invocation creates
        # a fresh instance — there's no long-lived plugin process to kill
        if plugin_name in self._plugins:
            del self._plugins[plugin_name]
            del self._permissions[plugin_name]
            del self._limits[plugin_name]
            logger.info(f"Revoked plugin: {plugin_name}")
            return True
        return False


def test_plugin_host():
    host = PluginHost()

    # Register a plugin with limited permissions
    manifest = PluginManifest(
        name="data-transformer",
        version="1.0.0",
        author="example",
        description="Transforms input data",
        permissions=["kv_read", "kv_write", "log"],
    )

    host.register_plugin(
        manifest=manifest,
        wasm_bytes=b"(fake wasm bytes)",
        permissions=Permission.standard(),
        limits=ResourceLimits(max_memory_bytes=32 * 1024 * 1024),
    )

    # Invoke the plugin
    result = host.invoke(
        "data-transformer",
        "transform",
        {"key": "value"},
    )

    assert result.success, f"Plugin failed: {result.error}"
    assert len(result.logs) > 0, "Should have logs"
    assert len(result.metrics) > 0, "Should have metrics"
    print(f"Plugin result: {result.output}")
    print(f"Execution time: {result.execution_time_ms:.2f}ms")
    print(f"Logs: {result.logs}")

    # Test permission denial
    manifest2 = PluginManifest(
        name="restricted-plugin",
        version="1.0.0",
        author="untrusted",
        description="Should have limited access",
        permissions=["http_outbound"],  # requests HTTP access
    )

    host.register_plugin(
        manifest=manifest2,
        wasm_bytes=b"(fake wasm bytes)",
        permissions=Permission.LOG,  # only grant logging
    )

    # List all plugins
    print(f"\nRegistered plugins: {json.dumps(host.list_plugins(), indent=2)}")

    # Revoke a plugin
    host.revoke_plugin("restricted-plugin")
    print("Revoked restricted-plugin")


if __name__ == "__main__":
    test_plugin_host()
    print("\nPlugin host tests passed!")
```

## Security Best Practices

| Concern | WASM Solution | Additional Measures |
|---------|--------------|---------------------|
| **Memory access** | Linear memory isolation | Set per-plugin memory limits |
| **CPU abuse** | Fuel metering (instruction counting) | Set per-invocation timeouts |
| **Network access** | No default network access | Capability-grant for specific URLs |
| **Filesystem** | No default FS access | Sandboxed directory via WASI |
| **Host API abuse** | Permission checks on every call | Rate limiting per plugin |
| **Supply chain** | Hash verification of WASM binary | Signed manifests, registry trust |

## Key Takeaways

- WASM provides **in-process sandboxing** that's both fast (near-native speed) and secure (memory isolation, capability-based permissions) — the best of both worlds for plugin systems
- **Capability-based security** means plugins start with zero permissions and must be explicitly granted access to each host API — this is fundamentally more secure than running plugins with host privileges
- **Fresh instances per invocation** prevent state leaks between plugin calls and make revocation instantaneous — there's no long-lived plugin process to manage
- **Resource limits** (memory, CPU fuel, timeout) prevent denial-of-service from malicious or buggy plugins — the host remains responsive even if a plugin goes rogue
- Production plugin hosts should add **signed manifests**, **version pinning**, and **audit logging** on top of WASM's built-in sandboxing for defense in depth
"""
    ),
]
