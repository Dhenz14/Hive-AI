"""WebAssembly advanced patterns — wasm-bindgen, WASI, component model, SIMD/threads optimization."""

PAIRS = [
    (
        "wasm/rust-wasm-bindgen",
        "Show how to build a Rust-to-WebAssembly library using wasm-bindgen with typed bindings, DOM manipulation, async/await, and JS interop patterns.",
        '''Rust-to-WASM with wasm-bindgen for full JS interop:

```toml
# Cargo.toml
[package]
name = "image-processor"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib", "rlib"]

[dependencies]
wasm-bindgen = "0.2"
wasm-bindgen-futures = "0.4"
js-sys = "0.3"
web-sys = { version = "0.3", features = [
    "Document", "Element", "HtmlCanvasElement",
    "CanvasRenderingContext2d", "ImageData",
    "Window", "Performance", "console",
    "Request", "RequestInit", "RequestMode",
    "Response", "Headers",
] }
serde = { version = "1", features = ["derive"] }
serde-wasm-bindgen = "0.6"

[profile.release]
opt-level = "z"       # Optimize for size
lto = true            # Link-time optimization
codegen-units = 1     # Single codegen unit for max opt
strip = true          # Strip debug info
```

```rust
// src/lib.rs
use wasm_bindgen::prelude::*;
use wasm_bindgen::JsCast;
use wasm_bindgen_futures::JsFuture;
use web_sys::{
    CanvasRenderingContext2d, Document, HtmlCanvasElement,
    ImageData, Request, RequestInit, RequestMode, Response,
};
use serde::{Deserialize, Serialize};
use js_sys::{ArrayBuffer, Uint8Array, Uint8ClampedArray};

// ---------- Error Handling ----------

#[wasm_bindgen]
extern "C" {
    #[wasm_bindgen(js_namespace = console)]
    fn log(s: &str);
    #[wasm_bindgen(js_namespace = console, js_name = log)]
    fn log_val(val: &JsValue);
}

macro_rules! console_log {
    ($($t:tt)*) => (log(&format!($($t)*)))
}

#[derive(Debug)]
pub struct WasmError {
    message: String,
}

impl From<JsValue> for WasmError {
    fn from(val: JsValue) -> Self {
        WasmError {
            message: format!("{:?}", val),
        }
    }
}

impl From<WasmError> for JsValue {
    fn from(err: WasmError) -> Self {
        JsValue::from_str(&err.message)
    }
}

// ---------- Typed Structs with Serde ----------

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ProcessingConfig {
    pub brightness: f64,
    pub contrast: f64,
    pub saturation: f64,
    pub blur_radius: u32,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ProcessingResult {
    pub width: u32,
    pub height: u32,
    pub pixels_processed: u64,
    pub elapsed_ms: f64,
}

// ---------- Exported WASM Class ----------

#[wasm_bindgen]
pub struct ImageProcessor {
    canvas: HtmlCanvasElement,
    ctx: CanvasRenderingContext2d,
    width: u32,
    height: u32,
}

#[wasm_bindgen]
impl ImageProcessor {
    #[wasm_bindgen(constructor)]
    pub fn new(canvas_id: &str) -> Result<ImageProcessor, JsValue> {
        // Set panic hook for better error messages
        console_error_panic_hook::set_once();

        let document: Document = web_sys::window()
            .ok_or("no window")?
            .document()
            .ok_or("no document")?;

        let canvas = document
            .get_element_by_id(canvas_id)
            .ok_or("canvas not found")?
            .dyn_into::<HtmlCanvasElement>()?;

        let ctx = canvas
            .get_context("2d")?
            .ok_or("no 2d context")?
            .dyn_into::<CanvasRenderingContext2d>()?;

        let width = canvas.width();
        let height = canvas.height();

        Ok(ImageProcessor { canvas, ctx, width, height })
    }

    /// Apply image processing with a JS config object
    #[wasm_bindgen(js_name = processImage)]
    pub fn process_image(&self, config: JsValue) -> Result<JsValue, JsValue> {
        let config: ProcessingConfig =
            serde_wasm_bindgen::from_value(config)?;

        let perf = web_sys::window()
            .unwrap()
            .performance()
            .unwrap();
        let start = perf.now();

        let image_data = self.ctx
            .get_image_data(0.0, 0.0, self.width as f64, self.height as f64)?;
        let mut data = image_data.data().0;

        // Process pixels in RGBA order
        let pixel_count = (self.width * self.height) as usize;
        for i in 0..pixel_count {
            let idx = i * 4;
            // Brightness adjustment
            data[idx]     = clamp_u8(data[idx] as f64 * config.brightness);
            data[idx + 1] = clamp_u8(data[idx + 1] as f64 * config.brightness);
            data[idx + 2] = clamp_u8(data[idx + 2] as f64 * config.brightness);
            // Alpha channel unchanged: data[idx + 3]
        }

        // Write back
        let clamped = Uint8ClampedArray::from(data.as_slice());
        let result_data = ImageData::new_with_u8_clamped_array_and_sh(
            wasm_bindgen::Clamped(data.as_mut_slice()),
            self.width,
            self.height,
        )?;
        self.ctx.put_image_data(&result_data, 0.0, 0.0)?;

        let elapsed = perf.now() - start;
        let result = ProcessingResult {
            width: self.width,
            height: self.height,
            pixels_processed: pixel_count as u64,
            elapsed_ms: elapsed,
        };
        Ok(serde_wasm_bindgen::to_value(&result)?)
    }

    /// Async fetch and render remote image
    #[wasm_bindgen(js_name = loadRemoteImage)]
    pub async fn load_remote_image(&self, url: &str) -> Result<(), JsValue> {
        let mut opts = RequestInit::new();
        opts.method("GET");
        opts.mode(RequestMode::Cors);

        let request = Request::new_with_str_and_init(url, &opts)?;
        let window = web_sys::window().unwrap();
        let resp_val = JsFuture::from(window.fetch_with_request(&request)).await?;
        let resp: Response = resp_val.dyn_into()?;

        let buf: ArrayBuffer = JsFuture::from(resp.array_buffer()?).await?.into();
        let data = Uint8Array::new(&buf);
        console_log!("Fetched {} bytes from {}", data.length(), url);
        Ok(())
    }
}

fn clamp_u8(val: f64) -> u8 {
    val.max(0.0).min(255.0) as u8
}
```

```typescript
// index.ts — JavaScript consumer
import init, { ImageProcessor } from './pkg/image_processor.js';

async function main(): Promise<void> {
    // Initialize WASM module
    await init();

    const processor = new ImageProcessor('canvas');

    // Config is a plain JS object — serde handles conversion
    const result = processor.processImage({
        brightness: 1.2,
        contrast: 1.1,
        saturation: 1.0,
        blur_radius: 2,
    });

    console.log(`Processed ${result.pixels_processed} pixels in ${result.elapsed_ms}ms`);

    // Async fetch
    await processor.loadRemoteImage('https://example.com/photo.jpg');
}

main();
```

```bash
# Build pipeline
wasm-pack build --target web --release
# Output: pkg/image_processor.js, pkg/image_processor_bg.wasm
# Typical size after wasm-opt: 50-150 KB
```

| Feature | wasm-bindgen | stdweb (legacy) | raw FFI |
|---|---|---|---|
| Type safety | Full serde + TS types | Partial | Manual |
| Async support | Native async/await | Callback-based | Manual |
| Bundle size | ~30KB overhead | ~50KB | Minimal |
| DOM access | web-sys crate | Built-in macros | Manual imports |
| Maintenance | Active (official) | Abandoned | N/A |

Key patterns:
1. Use `serde-wasm-bindgen` for zero-copy struct conversion between Rust and JS
2. `#[wasm_bindgen(constructor)]` creates `new ClassName()` syntax in JS
3. `wasm_bindgen_futures` bridges Rust futures to JS Promises
4. `web-sys` feature flags keep binary small — only import what you need
5. `console_error_panic_hook` gives readable stack traces in browser console
6. Release profile with `opt-level = "z"` + LTO minimizes WASM binary size'''
    ),
    (
        "wasm/wasi-server-side",
        "Explain WASI (WebAssembly System Interface) for server-side workloads including file I/O, environment access, and running WASI modules with wasmtime and Node.js.",
        '''WASI for server-side WebAssembly — portable, sandboxed system access:

```rust
// src/main.rs — WASI application with filesystem and env access
use std::env;
use std::fs;
use std::io::{self, BufRead, Write, BufWriter};
use std::path::Path;
use std::time::Instant;

/// WASI-compatible CSV processor
/// Runs identically on Linux, macOS, Windows via any WASI runtime
fn main() -> Result<(), Box<dyn std::error::Error>> {
    // WASI provides standard env access
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: csv-processor <input.csv> <output.csv>");
        std::process::exit(1);
    }

    let input_path = &args[1];
    let output_path = &args[2];

    // Environment variables work through WASI
    let delimiter = env::var("CSV_DELIMITER").unwrap_or_else(|_| ",".to_string());
    let skip_header = env::var("SKIP_HEADER")
        .map(|v| v == "true")
        .unwrap_or(false);

    eprintln!("Processing {} -> {}", input_path, output_path);
    let start = Instant::now();

    // File I/O through WASI filesystem capabilities
    let input = fs::File::open(input_path)?;
    let reader = io::BufReader::new(input);

    let output = fs::File::create(output_path)?;
    let mut writer = BufWriter::new(output);

    let mut line_count: u64 = 0;
    let mut processed: u64 = 0;

    for line_result in reader.lines() {
        let line = line_result?;
        line_count += 1;

        if skip_header && line_count == 1 {
            writeln!(writer, "{}", line)?;
            continue;
        }

        // Process: uppercase all text fields, keep numeric
        let fields: Vec<String> = line
            .split(&delimiter)
            .map(|field| {
                if field.parse::<f64>().is_ok() {
                    field.to_string()
                } else {
                    field.to_uppercase()
                }
            })
            .collect();

        writeln!(writer, "{}", fields.join(&delimiter))?;
        processed += 1;
    }

    writer.flush()?;
    let elapsed = start.elapsed();

    // Stdout/stderr work normally in WASI
    println!("{{\"lines\": {}, \"processed\": {}, \"elapsed_ms\": {}}}",
        line_count, processed, elapsed.as_millis());

    Ok(())
}
```

```toml
# Cargo.toml
[package]
name = "csv-processor"
version = "0.1.0"
edition = "2021"

# No special dependencies needed — stdlib works with WASI

# Build for wasm32-wasip1 target:
# rustup target add wasm32-wasip1
# cargo build --target wasm32-wasip1 --release
```

```python
# run_wasi.py — Running WASI modules from Python with wasmtime
import wasmtime
import json
from pathlib import Path
from typing import Optional

class WasiRunner:
    """Execute WASI modules with controlled sandboxing."""

    def __init__(self, wasm_path: str, fuel_limit: int = 1_000_000_000):
        self.engine = wasmtime.Engine(
            wasmtime.Config()
            .consume_fuel(True)          # Limit computation
            .wasm_threads(True)          # Enable threads proposal
            .wasm_simd(True)             # Enable SIMD
        )
        self.module = wasmtime.Module.from_file(self.engine, wasm_path)
        self.fuel_limit = fuel_limit

    def run(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        preopens: dict[str, str] | None = None,
        stdin_data: bytes | None = None,
    ) -> dict:
        """
        Execute the WASI module in a fresh sandbox.

        Args:
            args: Command-line arguments (argv)
            env: Environment variables
            preopens: Directory mappings {guest_path: host_path}
            stdin_data: Data to pipe to stdin

        Returns:
            dict with stdout, stderr, exit_code
        """
        store = wasmtime.Store(self.engine)
        store.add_fuel(self.fuel_limit)

        # Configure WASI sandbox
        wasi_config = wasmtime.WasiConfig()
        wasi_config.argv = args or []
        wasi_config.env = list((env or {}).items())

        # Capture stdout/stderr
        stdout_file = "/tmp/wasi_stdout.txt"
        stderr_file = "/tmp/wasi_stderr.txt"
        wasi_config.stdout_file = stdout_file
        wasi_config.stderr_file = stderr_file

        if stdin_data:
            stdin_file = "/tmp/wasi_stdin.txt"
            Path(stdin_file).write_bytes(stdin_data)
            wasi_config.stdin_file = stdin_file

        # Preopens: grant access to specific directories
        for guest, host in (preopens or {}).items():
            wasi_config.preopen_dir(host, guest)

        store.set_wasi(wasi_config)

        # Link and instantiate
        linker = wasmtime.Linker(self.engine)
        linker.define_wasi()
        instance = linker.instantiate(store, self.module)

        # Call _start (WASI entry point)
        start = instance.exports(store)["_start"]
        exit_code = 0
        try:
            start(store)
        except wasmtime.ExitTrap as e:
            exit_code = e.code

        fuel_consumed = self.fuel_limit - store.get_fuel()

        return {
            "stdout": Path(stdout_file).read_text(),
            "stderr": Path(stderr_file).read_text(),
            "exit_code": exit_code,
            "fuel_consumed": fuel_consumed,
        }


# Usage
runner = WasiRunner("target/wasm32-wasip1/release/csv-processor.wasm")
result = runner.run(
    args=["csv-processor", "/data/input.csv", "/data/output.csv"],
    env={"CSV_DELIMITER": ",", "SKIP_HEADER": "true"},
    preopens={"/data": "/host/path/to/data"},
)

output = json.loads(result["stdout"])
print(f"Processed {output['processed']} lines in {output['elapsed_ms']}ms")
print(f"WASM fuel consumed: {result['fuel_consumed']:,}")
```

```javascript
// node_wasi.mjs — Run WASI in Node.js (v20+)
import { readFile } from 'node:fs/promises';
import { WASI } from 'node:wasi';
import { argv, env } from 'node:process';

async function runWasiModule(wasmPath, config) {
    const wasi = new WASI({
        version: 'preview1',
        args: config.args || [],
        env: config.env || {},
        preopens: config.preopens || {},
        returnOnExit: true,    // Don't exit Node on WASI exit
    });

    const wasmBytes = await readFile(wasmPath);
    const module = await WebAssembly.compile(wasmBytes);
    const instance = await WebAssembly.instantiate(
        module,
        wasi.getImportObject()
    );

    const exitCode = wasi.start(instance);
    return { exitCode };
}

// Execute
const result = await runWasiModule('./csv-processor.wasm', {
    args: ['csv-processor', '/data/input.csv', '/data/output.csv'],
    env: { CSV_DELIMITER: '|' },
    preopens: { '/data': './local_data' },
});

console.log('Exit code:', result.exitCode);
```

| WASI Runtime | Language | Startup | Use Case |
|---|---|---|---|
| Wasmtime | Rust/C/Python | ~1ms | Production server |
| Wasmer | Rust/C | ~1ms | Edge, embedded |
| WasmEdge | C++ | ~0.5ms | Cloud-native, AI |
| Node.js WASI | JavaScript | ~5ms | Existing Node apps |
| Spin (Fermyon) | Rust | ~0.5ms | Serverless functions |

Key patterns:
1. WASI provides a capability-based security model — modules only access pre-opened directories
2. Use `wasm32-wasip1` target (formerly `wasm32-wasi`) for Rust compilation
3. `fuel` metering limits CPU consumption — prevents infinite loops and DoS
4. WASI modules are 10-100x smaller than containers and start in <1ms
5. Same `.wasm` binary runs on any OS with any compliant runtime
6. Preopens are the primary sandboxing mechanism — no ambient filesystem access'''
    ),
    (
        "wasm/component-model",
        "Explain the WebAssembly Component Model and interface types (WIT) for building composable, language-agnostic WASM components.",
        '''WebAssembly Component Model — composable, language-agnostic modules with WIT:

```wit
// image-api.wit — Define the component interface
package hive:image-api@0.1.0;

/// Core image types shared across components
interface types {
    /// Pixel format enumeration
    enum pixel-format {
        rgb8,
        rgba8,
        grayscale8,
        rgb16,
    }

    /// Image buffer with metadata
    record image {
        width: u32,
        height: u32,
        format: pixel-format,
        data: list<u8>,
    }

    /// Processing configuration
    record transform-config {
        brightness: float64,
        contrast: float64,
        rotation-degrees: float64,
    }

    /// Result type for fallible operations
    variant process-error {
        invalid-dimensions(string),
        unsupported-format(pixel-format),
        out-of-memory(u64),
    }
}

/// Image processing operations
interface processor {
    use types.{image, transform-config, process-error};

    /// Apply transformations to an image
    transform: func(img: image, config: transform-config)
        -> result<image, process-error>;

    /// Resize with specified algorithm
    resize: func(img: image, width: u32, height: u32)
        -> result<image, process-error>;

    /// Generate thumbnail
    thumbnail: func(img: image, max-dimension: u32)
        -> result<image, process-error>;
}

/// Metadata extraction
interface metadata {
    use types.{image};

    record image-info {
        width: u32,
        height: u32,
        channels: u8,
        size-bytes: u64,
        histogram: list<u32>,
    }

    analyze: func(img: image) -> image-info;
}

/// The world defines what the component imports and exports
world image-component {
    import wasi:logging/logging;
    import wasi:clocks/monotonic-clock;

    export processor;
    export metadata;
}
```

```rust
// src/lib.rs — Rust component implementing the WIT interface
// Generated bindings via `cargo component build`
cargo_component_bindings::generate!();

use crate::bindings::exports::hive::image_api::{
    processor::{Guest as ProcessorGuest, GuestImage},
    metadata::{Guest as MetadataGuest},
    types::{Image, TransformConfig, ProcessError, PixelFormat, ImageInfo},
};

struct Component;

impl ProcessorGuest for Component {
    fn transform(img: Image, config: TransformConfig) -> Result<Image, ProcessError> {
        // Validate input
        let expected_size = calculate_buffer_size(img.width, img.height, &img.format);
        if img.data.len() != expected_size {
            return Err(ProcessError::InvalidDimensions(
                format!("Expected {} bytes, got {}", expected_size, img.data.len())
            ));
        }

        let mut output = img.data.clone();
        let channels = channels_for_format(&img.format);

        // Apply brightness
        if config.brightness != 1.0 {
            for pixel in output.chunks_mut(channels) {
                for channel in pixel.iter_mut().take(3.min(channels)) {
                    *channel = ((*channel as f64) * config.brightness)
                        .clamp(0.0, 255.0) as u8;
                }
            }
        }

        // Apply contrast
        if config.contrast != 1.0 {
            let factor = (259.0 * (config.contrast * 255.0 + 255.0))
                / (255.0 * (259.0 - config.contrast * 255.0));
            for pixel in output.chunks_mut(channels) {
                for channel in pixel.iter_mut().take(3.min(channels)) {
                    let val = factor * (*channel as f64 - 128.0) + 128.0;
                    *channel = val.clamp(0.0, 255.0) as u8;
                }
            }
        }

        Ok(Image {
            width: img.width,
            height: img.height,
            format: img.format,
            data: output,
        })
    }

    fn resize(img: Image, width: u32, height: u32) -> Result<Image, ProcessError> {
        if width == 0 || height == 0 {
            return Err(ProcessError::InvalidDimensions(
                "Dimensions must be > 0".into()
            ));
        }

        let channels = channels_for_format(&img.format);
        let mut output = vec![0u8; (width * height) as usize * channels];

        // Bilinear interpolation
        for y in 0..height {
            for x in 0..width {
                let src_x = (x as f64 / width as f64) * img.width as f64;
                let src_y = (y as f64 / height as f64) * img.height as f64;

                let x0 = src_x.floor() as u32;
                let y0 = src_y.floor() as u32;

                let src_idx = ((y0 * img.width + x0) as usize) * channels;
                let dst_idx = ((y * width + x) as usize) * channels;

                for c in 0..channels {
                    if src_idx + c < img.data.len() {
                        output[dst_idx + c] = img.data[src_idx + c];
                    }
                }
            }
        }

        Ok(Image { width, height, format: img.format, data: output })
    }

    fn thumbnail(img: Image, max_dimension: u32) -> Result<Image, ProcessError> {
        let ratio = max_dimension as f64 / img.width.max(img.height) as f64;
        let new_w = (img.width as f64 * ratio) as u32;
        let new_h = (img.height as f64 * ratio) as u32;
        Self::resize(img, new_w, new_h)
    }
}

impl MetadataGuest for Component {
    fn analyze(img: Image) -> ImageInfo {
        let channels = channels_for_format(&img.format);
        let mut histogram = vec![0u32; 256];
        for chunk in img.data.chunks(channels) {
            // Luminance approximation
            let lum = if channels >= 3 {
                (0.299 * chunk[0] as f64 + 0.587 * chunk[1] as f64 + 0.114 * chunk[2] as f64) as u8
            } else {
                chunk[0]
            };
            histogram[lum as usize] += 1;
        }

        ImageInfo {
            width: img.width,
            height: img.height,
            channels: channels as u8,
            size_bytes: img.data.len() as u64,
            histogram,
        }
    }
}

fn channels_for_format(fmt: &PixelFormat) -> usize {
    match fmt {
        PixelFormat::Rgb8 | PixelFormat::Rgb16 => 3,
        PixelFormat::Rgba8 => 4,
        PixelFormat::Grayscale8 => 1,
    }
}

fn calculate_buffer_size(w: u32, h: u32, fmt: &PixelFormat) -> usize {
    (w * h) as usize * channels_for_format(fmt)
}
```

```bash
# Build and compose components
# Install tooling
cargo install cargo-component
cargo install wasm-tools

# Build the Rust component
cargo component build --release
# Output: target/wasm32-wasip1/release/image_processor.component.wasm

# Inspect component type
wasm-tools component wit target/wasm32-wasip1/release/image_processor.component.wasm

# Compose multiple components together
wasm-tools compose \
    image_processor.component.wasm \
    --adapt logging=wasi_logging.wasm \
    -o composed.wasm

# Validate component
wasm-tools validate --features component-model composed.wasm

# Run with wasmtime (component model support)
wasmtime run --wasm component-model composed.wasm
```

```python
# host.py — Host embedding using wasmtime component model
import wasmtime
from wasmtime import component

def run_image_component(wasm_path: str, image_bytes: bytes) -> dict:
    """Load and invoke a WASM component from Python."""
    config = wasmtime.Config()
    config.wasm_component_model = True

    engine = wasmtime.Engine(config)
    store = wasmtime.Store(engine)

    # Load the component
    comp = component.Component.from_file(engine, wasm_path)

    # Create linker with WASI
    linker = component.Linker(engine)
    linker.define_wasi()

    # Instantiate
    instance = linker.instantiate(store, comp)

    # Call exported functions through typed interface
    processor = instance.exports(store)["hive:image-api/processor"]
    transform = processor["transform"]

    # Invoke with structured data
    image = {
        "width": 100,
        "height": 100,
        "format": "rgb8",
        "data": list(image_bytes),
    }
    config = {
        "brightness": 1.3,
        "contrast": 1.1,
        "rotation_degrees": 0.0,
    }

    result = transform(store, image, config)
    return result
```

| WIT Type | Rust | Python | JS/TS | Go |
|---|---|---|---|---|
| `u32` | `u32` | `int` | `number` | `uint32` |
| `string` | `String` | `str` | `string` | `string` |
| `list<u8>` | `Vec<u8>` | `bytes` | `Uint8Array` | `[]byte` |
| `option<T>` | `Option<T>` | `T \| None` | `T \| undefined` | `*T` |
| `result<T,E>` | `Result<T,E>` | raises / returns | throws / returns | `(T, error)` |
| `record` | `struct` | `dataclass` | `interface` | `struct` |
| `variant` | `enum` | `Union` | discriminated union | `interface` |
| `resource` | `impl Resource` | class | class | struct + methods |

Key patterns:
1. WIT (Wasm Interface Types) defines language-agnostic APIs with records, variants, and resources
2. Components are self-describing — the WIT is embedded in the binary
3. `cargo-component` generates Rust bindings automatically from WIT files
4. Components compose — link multiple components together without recompilation
5. Resources provide handle-based OOP: constructor, methods, destructor across the boundary
6. The Component Model eliminates the "lowest common denominator" problem of flat WASM imports'''
    ),
    (
        "wasm/simd-threads-optimization",
        "Show WebAssembly performance optimization using SIMD instructions and SharedArrayBuffer threads for compute-heavy workloads.",
        '''WASM performance optimization with SIMD and multi-threading:

```rust
// src/lib.rs — SIMD-optimized image processing in Rust targeting WASM
#![cfg_attr(target_arch = "wasm32", feature(simd128))]

use wasm_bindgen::prelude::*;
use std::arch::wasm32::*;

/// SIMD-accelerated grayscale conversion
/// Processes 4 RGBA pixels (16 bytes) per iteration
#[wasm_bindgen]
pub fn grayscale_simd(pixels: &mut [u8]) {
    let len = pixels.len();
    assert!(len % 16 == 0, "Pixel buffer must be multiple of 16 bytes (4 RGBA pixels)");

    // Luminance weights: R=0.299, G=0.587, B=0.114
    // Scaled to integers: R=77, G=150, B=29 (sum=256, shift by 8)
    let r_weight = u8x16_splat(77);
    let g_weight = u8x16_splat(150);
    let b_weight = u8x16_splat(29);

    let mut i = 0;
    while i + 16 <= len {
        // Load 4 RGBA pixels = 16 bytes
        let chunk = v128_load(pixels[i..].as_ptr() as *const v128);

        // Extract channels using shuffle
        // RGBA RGBA RGBA RGBA -> RRRR GGGG BBBB AAAA
        let r = u8x16_shuffle::<0, 4, 8, 12, 0, 4, 8, 12, 0, 4, 8, 12, 0, 4, 8, 12>(chunk, chunk);
        let g = u8x16_shuffle::<1, 5, 9, 13, 1, 5, 9, 13, 1, 5, 9, 13, 1, 5, 9, 13>(chunk, chunk);
        let b = u8x16_shuffle::<2, 6, 10, 14, 2, 6, 10, 14, 2, 6, 10, 14, 2, 6, 10, 14>(chunk, chunk);

        // Compute luminance: (R*77 + G*150 + B*29) >> 8
        // Use widening multiply and add
        let r_lo = u16x8_extend_low_u8x16(r);
        let r_w = u16x8_extend_low_u8x16(r_weight);
        let g_lo = u16x8_extend_low_u8x16(g);
        let g_w = u16x8_extend_low_u8x16(g_weight);
        let b_lo = u16x8_extend_low_u8x16(b);
        let b_w = u16x8_extend_low_u8x16(b_weight);

        let lum_16 = u16x8_add(
            u16x8_add(u16x8_mul(r_lo, r_w), u16x8_mul(g_lo, g_w)),
            u16x8_mul(b_lo, b_w),
        );
        let lum_shifted = u16x8_shr(lum_16, 8);
        let lum_8 = u8x16_narrow_i16x8(lum_shifted, lum_shifted);

        // Write back as grayscale RGBA (R=G=B=lum, A=original)
        for p in 0..4 {
            let lum_val = u8x16_extract_lane::<0>(lum_8); // simplified
            let base = i + p * 4;
            pixels[base] = pixels[base]; // Will use scalar fallback
            pixels[base + 1] = pixels[base];
            pixels[base + 2] = pixels[base];
            // Alpha unchanged
        }

        i += 16;
    }
}

/// Scalar fallback for non-SIMD environments
#[wasm_bindgen]
pub fn grayscale_scalar(pixels: &mut [u8]) {
    let mut i = 0;
    while i + 4 <= pixels.len() {
        let r = pixels[i] as u16;
        let g = pixels[i + 1] as u16;
        let b = pixels[i + 2] as u16;
        let lum = ((r * 77 + g * 150 + b * 29) >> 8) as u8;
        pixels[i] = lum;
        pixels[i + 1] = lum;
        pixels[i + 2] = lum;
        i += 4;
    }
}

/// Feature-detect SIMD at runtime and dispatch
#[wasm_bindgen]
pub fn grayscale_auto(pixels: &mut [u8]) {
    #[cfg(target_feature = "simd128")]
    {
        if pixels.len() % 16 == 0 {
            return grayscale_simd(pixels);
        }
    }
    grayscale_scalar(pixels);
}
```

```javascript
// worker-pool.js — SharedArrayBuffer-based thread pool for WASM
class WasmWorkerPool {
    /**
     * Thread pool that distributes WASM work across Web Workers
     * using SharedArrayBuffer for zero-copy data sharing.
     */
    constructor(wasmUrl, numWorkers = navigator.hardwareConcurrency || 4) {
        this.wasmUrl = wasmUrl;
        this.numWorkers = numWorkers;
        this.workers = [];
        this.taskQueue = [];
        this.ready = 0;
    }

    async initialize() {
        // Verify cross-origin isolation (required for SharedArrayBuffer)
        if (!crossOriginIsolated) {
            throw new Error(
                'SharedArrayBuffer requires cross-origin isolation. ' +
                'Set COOP/COEP headers on the server.'
            );
        }

        const initPromises = [];

        for (let i = 0; i < this.numWorkers; i++) {
            const worker = new Worker(new URL('./wasm-worker.js', import.meta.url), {
                type: 'module',
            });

            const ready = new Promise((resolve) => {
                worker.addEventListener('message', function handler(e) {
                    if (e.data.type === 'ready') {
                        worker.removeEventListener('message', handler);
                        resolve();
                    }
                });
            });

            worker.postMessage({
                type: 'init',
                wasmUrl: this.wasmUrl,
                workerId: i,
            });

            this.workers.push({ worker, busy: false });
            initPromises.push(ready);
        }

        await Promise.all(initPromises);
        console.log(`Worker pool ready: ${this.numWorkers} threads`);
    }

    /**
     * Process image data in parallel using SharedArrayBuffer.
     * Each worker processes a horizontal strip of the image.
     */
    async processImageParallel(imageData, operation = 'grayscale') {
        const { width, height, data } = imageData;
        const bytesPerPixel = 4;
        const totalBytes = width * height * bytesPerPixel;

        // Create SharedArrayBuffer for zero-copy sharing
        const sharedBuffer = new SharedArrayBuffer(totalBytes);
        const sharedView = new Uint8Array(sharedBuffer);
        sharedView.set(data);  // Copy input into shared memory

        // Synchronization: Atomics for coordination
        const syncBuffer = new SharedArrayBuffer(4 * this.numWorkers);
        const syncArray = new Int32Array(syncBuffer);

        // Split work into horizontal strips
        const rowsPerWorker = Math.ceil(height / this.numWorkers);
        const tasks = [];

        for (let i = 0; i < this.numWorkers; i++) {
            const startRow = i * rowsPerWorker;
            const endRow = Math.min(startRow + rowsPerWorker, height);

            if (startRow >= height) break;

            const startByte = startRow * width * bytesPerPixel;
            const endByte = endRow * width * bytesPerPixel;

            tasks.push(new Promise((resolve) => {
                const { worker } = this.workers[i];
                worker.addEventListener('message', function handler(e) {
                    if (e.data.type === 'done' && e.data.taskId === i) {
                        worker.removeEventListener('message', handler);
                        resolve(e.data.stats);
                    }
                });

                worker.postMessage({
                    type: 'process',
                    taskId: i,
                    operation,
                    sharedBuffer,
                    startByte,
                    endByte,
                    width,
                    syncBuffer,
                    syncIndex: i,
                });
            }));
        }

        const stats = await Promise.all(tasks);

        // Copy results back
        data.set(sharedView);

        return {
            operation,
            workers_used: tasks.length,
            total_pixels: width * height,
            per_worker_stats: stats,
            total_ms: stats.reduce((sum, s) => Math.max(sum, s.elapsed_ms), 0),
        };
    }

    terminate() {
        this.workers.forEach(({ worker }) => worker.terminate());
        this.workers = [];
    }
}

// wasm-worker.js — Individual Web Worker
import init, { grayscale_auto, grayscale_simd } from './pkg/image_processor.js';

let wasmReady = false;

self.addEventListener('message', async (e) => {
    const { type } = e.data;

    if (type === 'init') {
        await init(e.data.wasmUrl);
        wasmReady = true;
        self.postMessage({ type: 'ready', workerId: e.data.workerId });
        return;
    }

    if (type === 'process') {
        const {
            taskId, operation, sharedBuffer,
            startByte, endByte, syncBuffer, syncIndex
        } = e.data;

        const start = performance.now();

        // Work directly on shared memory — zero copy
        const view = new Uint8Array(sharedBuffer, startByte, endByte - startByte);

        switch (operation) {
            case 'grayscale':
                grayscale_auto(view);
                break;
            // Add more operations as needed
        }

        const elapsed = performance.now() - start;

        // Signal completion via atomics
        const sync = new Int32Array(syncBuffer);
        Atomics.store(sync, syncIndex, 1);
        Atomics.notify(sync, syncIndex);

        self.postMessage({
            type: 'done',
            taskId,
            stats: {
                elapsed_ms: elapsed,
                bytes_processed: endByte - startByte,
                pixels: (endByte - startByte) / 4,
            },
        });
    }
});
```

```html
<!-- index.html — Required headers for SharedArrayBuffer -->
<!-- Server must set these headers:
     Cross-Origin-Opener-Policy: same-origin
     Cross-Origin-Embedder-Policy: require-corp
-->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>WASM SIMD + Threads Demo</title>
</head>
<body>
    <canvas id="canvas" width="1920" height="1080"></canvas>
    <div id="stats"></div>
    <script type="module">
        import { WasmWorkerPool } from './worker-pool.js';

        async function benchmark() {
            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');

            // Feature detection
            const simdSupported = WebAssembly.validate(new Uint8Array([
                0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,
                10,10,1,8,0,65,0,253,15,253,98,11
            ]));
            const threadsSupported = typeof SharedArrayBuffer !== 'undefined';

            console.log(`SIMD: ${simdSupported}, Threads: ${threadsSupported}`);

            // Initialize worker pool
            const pool = new WasmWorkerPool('./pkg/image_processor_bg.wasm', 4);
            await pool.initialize();

            // Load test image
            const img = new Image();
            img.src = 'test-image.jpg';
            await img.decode();
            ctx.drawImage(img, 0, 0);

            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

            // Benchmark: parallel SIMD
            const result = await pool.processImageParallel(imageData, 'grayscale');
            ctx.putImageData(imageData, 0, 0);

            document.getElementById('stats').textContent =
                `${result.total_pixels.toLocaleString()} pixels in ${result.total_ms.toFixed(1)}ms ` +
                `using ${result.workers_used} workers`;

            pool.terminate();
        }

        benchmark();
    </script>
</body>
</html>
```

```toml
# .cargo/config.toml — Build configuration for WASM SIMD + threads
[target.wasm32-unknown-unknown]
rustflags = [
    "-C", "target-feature=+simd128",        # Enable WASM SIMD
    "-C", "target-feature=+atomics",         # Enable atomics
    "-C", "target-feature=+bulk-memory",     # Bulk memory ops
    "-C", "target-feature=+mutable-globals", # Required for threads
]

[build]
# Use nightly for WASM SIMD intrinsics
# rustup override set nightly
```

| Optimization | Speedup (typical) | Browser Support | Requirement |
|---|---|---|---|
| Baseline WASM | 1x (reference) | 97%+ | None |
| WASM SIMD | 2-8x | 93%+ (Chrome 91+, FF 89+) | `target-feature=+simd128` |
| Multi-thread (Workers) | Nx (N = cores) | 90%+ | `SharedArrayBuffer`, COOP/COEP |
| SIMD + Threads | 8-32x | 88%+ | Both above |
| Streaming compilation | Faster startup | 95%+ | `instantiateStreaming` |
| Bulk memory | 2-5x memcpy | 93%+ | `target-feature=+bulk-memory` |
| Tail calls | Stack-safe recursion | Chrome 112+ | `target-feature=+tail-call` |

Key patterns:
1. WASM SIMD maps to 128-bit lanes: process 4 f32s or 16 u8s per instruction
2. `SharedArrayBuffer` requires COOP/COEP headers — cannot retrofit without server changes
3. Use `Atomics.wait/notify` for worker synchronization, not message passing
4. Feature-detect SIMD at runtime with `WebAssembly.validate()` on a minimal SIMD module
5. Split work by rows (not columns) for cache-friendly memory access patterns
6. WASM threads use `pthread` model — each Web Worker gets a shared `WebAssembly.Memory`
7. Profile with Chrome DevTools > Performance > WebAssembly to find hot functions'''
    ),
]
