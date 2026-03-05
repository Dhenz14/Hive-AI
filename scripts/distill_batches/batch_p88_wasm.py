"""WebAssembly — Rust to WASM, JavaScript interop, and performance patterns."""

PAIRS = [
    (
        "wasm/rust-wasm",
        "Show Rust to WebAssembly patterns: wasm-bindgen, JavaScript interop, and memory management.",
        '''Rust to WebAssembly with wasm-bindgen:

```rust
// Cargo.toml
// [lib]
// crate-type = ["cdylib"]
//
// [dependencies]
// wasm-bindgen = "0.2"
// js-sys = "0.3"
// web-sys = { version = "0.3", features = ["console", "Document", "Element", "HtmlElement", "Window"] }
// serde = { version = "1", features = ["derive"] }
// serde-wasm-bindgen = "0.6"

use wasm_bindgen::prelude::*;
use serde::{Serialize, Deserialize};


// --- Export Rust function to JavaScript ---

#[wasm_bindgen]
pub fn fibonacci(n: u32) -> u64 {
    if n <= 1 { return n as u64; }
    let (mut a, mut b) = (0u64, 1u64);
    for _ in 2..=n {
        let tmp = a + b;
        a = b;
        b = tmp;
    }
    b
}


// --- Struct exposed to JS ---

#[wasm_bindgen]
pub struct ImageProcessor {
    width: u32,
    height: u32,
    pixels: Vec<u8>,
}

#[wasm_bindgen]
impl ImageProcessor {
    #[wasm_bindgen(constructor)]
    pub fn new(width: u32, height: u32) -> ImageProcessor {
        ImageProcessor {
            width,
            height,
            pixels: vec![0; (width * height * 4) as usize],
        }
    }

    /// Get raw pixel data pointer for zero-copy JS access
    pub fn pixels_ptr(&self) -> *const u8 {
        self.pixels.as_ptr()
    }

    pub fn pixels_len(&self) -> usize {
        self.pixels.len()
    }

    /// Apply grayscale filter (fast in WASM)
    pub fn grayscale(&mut self) {
        for chunk in self.pixels.chunks_exact_mut(4) {
            let gray = (0.299 * chunk[0] as f64
                      + 0.587 * chunk[1] as f64
                      + 0.114 * chunk[2] as f64) as u8;
            chunk[0] = gray;
            chunk[1] = gray;
            chunk[2] = gray;
            // chunk[3] is alpha, keep unchanged
        }
    }

    /// Apply brightness adjustment
    pub fn brightness(&mut self, factor: f64) {
        for chunk in self.pixels.chunks_exact_mut(4) {
            chunk[0] = (chunk[0] as f64 * factor).min(255.0) as u8;
            chunk[1] = (chunk[1] as f64 * factor).min(255.0) as u8;
            chunk[2] = (chunk[2] as f64 * factor).min(255.0) as u8;
        }
    }

    /// Set pixel data from JS
    pub fn set_pixels(&mut self, data: &[u8]) {
        self.pixels.copy_from_slice(data);
    }
}


// --- Passing complex data with serde ---

#[derive(Serialize, Deserialize)]
pub struct ProcessingResult {
    pub histogram: Vec<u32>,
    pub mean_brightness: f64,
    pub dominant_color: [u8; 3],
}

#[wasm_bindgen]
pub fn analyze_image(data: &[u8]) -> JsValue {
    let mut histogram = vec![0u32; 256];
    let mut total: u64 = 0;
    let pixel_count = data.len() / 4;

    for chunk in data.chunks_exact(4) {
        let brightness = ((chunk[0] as u32 + chunk[1] as u32 + chunk[2] as u32) / 3) as usize;
        histogram[brightness] += 1;
        total += brightness as u64;
    }

    let result = ProcessingResult {
        histogram,
        mean_brightness: total as f64 / pixel_count as f64,
        dominant_color: [128, 128, 128], // Simplified
    };

    serde_wasm_bindgen::to_value(&result).unwrap()
}


// --- Call JavaScript from Rust ---

#[wasm_bindgen]
extern "C" {
    #[wasm_bindgen(js_namespace = console)]
    fn log(s: &str);

    #[wasm_bindgen(js_namespace = console, js_name = log)]
    fn log_u32(a: u32);

    fn alert(s: &str);

    // Custom JS function
    #[wasm_bindgen(js_name = "fetchData")]
    async fn fetch_data(url: &str) -> JsValue;
}

#[wasm_bindgen]
pub fn greet(name: &str) {
    log(&format!("Hello, {}!", name));
}


// --- Panic hook for better error messages ---

#[wasm_bindgen(start)]
pub fn init() {
    console_error_panic_hook::set_once();
}
```

```javascript
// JavaScript usage
import init, { fibonacci, ImageProcessor, analyze_image } from './pkg/my_wasm.js';

async function main() {
  await init(); // Initialize WASM module

  // Call Rust function
  console.log(fibonacci(50)); // Fast even for large N

  // Use Rust struct
  const processor = new ImageProcessor(800, 600);

  // Share memory (zero-copy)
  const canvas = document.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, 800, 600);

  // Copy image data to WASM memory
  processor.set_pixels(imageData.data);

  // Process in WASM (10-100x faster than JS for pixel ops)
  processor.grayscale();

  // Read back from WASM memory
  const wasmMemory = new Uint8Array(
    processor.pixels_ptr(),
    processor.pixels_len()
  );
  imageData.data.set(wasmMemory);
  ctx.putImageData(imageData, 0, 0);

  // Complex data via serde
  const analysis = analyze_image(imageData.data);
  console.log('Mean brightness:', analysis.mean_brightness);

  // Clean up (free WASM memory)
  processor.free();
}
```

WASM patterns:
1. **`#[wasm_bindgen]`** — auto-generate JS bindings for Rust functions/structs
2. **Zero-copy memory** — share pixel buffers between JS and WASM via pointers
3. **`serde_wasm_bindgen`** — serialize complex Rust structs to JS objects
4. **`console_error_panic_hook`** — readable panic messages in browser console
5. **`.free()`** — explicit memory cleanup for WASM-allocated objects'''
    ),
    (
        "wasm/wasm-workers",
        "Show WebAssembly with Web Workers: off-main-thread computation and SharedArrayBuffer patterns.",
        '''WASM with Web Workers for parallel processing:

```javascript
// --- Worker pool for WASM tasks ---

class WasmWorkerPool {
  constructor(workerUrl, poolSize = navigator.hardwareConcurrency || 4) {
    this.workers = [];
    this.taskQueue = [];
    this.freeWorkers = [];

    for (let i = 0; i < poolSize; i++) {
      const worker = new Worker(workerUrl, { type: 'module' });
      worker.id = i;
      worker.onmessage = (e) => this._onMessage(worker, e);
      this.workers.push(worker);
      this.freeWorkers.push(worker);
    }
  }

  // Submit task, returns Promise
  run(taskType, data, transferables = []) {
    return new Promise((resolve, reject) => {
      const task = { taskType, data, resolve, reject, transferables };

      const worker = this.freeWorkers.pop();
      if (worker) {
        this._dispatch(worker, task);
      } else {
        this.taskQueue.push(task);
      }
    });
  }

  _dispatch(worker, task) {
    worker._currentTask = task;
    worker.postMessage(
      { type: task.taskType, data: task.data },
      task.transferables,
    );
  }

  _onMessage(worker, event) {
    const task = worker._currentTask;
    worker._currentTask = null;

    if (event.data.error) {
      task.reject(new Error(event.data.error));
    } else {
      task.resolve(event.data.result);
    }

    // Pick up next task if queued
    const next = this.taskQueue.shift();
    if (next) {
      this._dispatch(worker, next);
    } else {
      this.freeWorkers.push(worker);
    }
  }

  terminate() {
    this.workers.forEach(w => w.terminate());
  }
}


// --- Worker script (wasm-worker.js) ---

import init, { process_chunk, fibonacci } from './pkg/my_wasm.js';

let initialized = false;

self.onmessage = async (event) => {
  if (!initialized) {
    await init();
    initialized = true;
  }

  const { type, data } = event.data;

  try {
    let result;
    switch (type) {
      case 'fibonacci':
        result = fibonacci(data.n);
        break;

      case 'process_image_chunk':
        // Process image chunk in WASM
        result = process_chunk(
          new Uint8Array(data.buffer),
          data.width,
          data.height,
        );
        break;

      default:
        throw new Error(`Unknown task: ${type}`);
    }

    self.postMessage({ result });
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};


// --- Main thread: parallel image processing ---

async function processImageParallel(imageData, chunkCount = 4) {
  const pool = new WasmWorkerPool('./wasm-worker.js', chunkCount);
  const { width, height, data } = imageData;
  const rowsPerChunk = Math.ceil(height / chunkCount);

  // Split image into horizontal strips
  const tasks = [];
  for (let i = 0; i < chunkCount; i++) {
    const startRow = i * rowsPerChunk;
    const endRow = Math.min(startRow + rowsPerChunk, height);
    const startByte = startRow * width * 4;
    const endByte = endRow * width * 4;

    // Copy chunk to transferable buffer
    const chunk = data.slice(startByte, endByte).buffer;

    tasks.push(pool.run('process_image_chunk', {
      buffer: chunk,
      width,
      height: endRow - startRow,
    }, [chunk]));
  }

  // Wait for all chunks to complete
  const results = await Promise.all(tasks);

  // Reassemble processed image
  const output = new Uint8ClampedArray(data.length);
  let offset = 0;
  for (const result of results) {
    const chunk = new Uint8Array(result);
    output.set(chunk, offset);
    offset += chunk.length;
  }

  pool.terminate();
  return new ImageData(output, width, height);
}


// --- SharedArrayBuffer for zero-copy parallel access ---

async function sharedMemoryExample() {
  // Requires: Cross-Origin-Opener-Policy: same-origin
  //           Cross-Origin-Embedder-Policy: require-corp

  const shared = new SharedArrayBuffer(1024 * 1024); // 1MB shared
  const view = new Int32Array(shared);

  // Multiple workers can read/write same buffer
  const worker1 = new Worker('worker.js');
  const worker2 = new Worker('worker.js');

  worker1.postMessage({ shared, offset: 0, length: 512 });
  worker2.postMessage({ shared, offset: 512, length: 512 });

  // Use Atomics for synchronization
  Atomics.store(view, 0, 42);       // Atomic write
  const val = Atomics.load(view, 0); // Atomic read
  Atomics.add(view, 1, 1);           // Atomic increment
  Atomics.wait(view, 2, 0);          // Block until value changes
  Atomics.notify(view, 2, 1);        // Wake one waiting thread
}
```

WASM + Workers patterns:
1. **Worker pool** — reuse workers, queue tasks, resolve promises
2. **Transferable buffers** — zero-copy transfer between main thread and workers
3. **Chunk parallelism** — split image/data into strips, process in parallel
4. **SharedArrayBuffer** — multiple workers access same memory
5. **Atomics** — thread-safe synchronization primitives for shared memory'''
    ),
]
"""
