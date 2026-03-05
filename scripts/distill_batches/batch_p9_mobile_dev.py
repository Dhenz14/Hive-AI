PAIRS = [
    (
        "mobile/react-native-new-architecture-fabric-jsi-turbomodules",
        "Explain the React Native new architecture including Fabric renderer, JSI (JavaScript Interface), TurboModules, and Codegen with practical implementation of a native module bridge, platform-specific iOS and Android code, and a custom Fabric component",
        r"""# React Native New Architecture: Fabric, JSI, TurboModules, and Codegen

## Understanding the Architectural Shift

The React Native **new architecture** represents a fundamental rethinking of how JavaScript communicates with native platforms. The old architecture relied on an asynchronous **bridge** that serialized all communication as JSON messages over a message queue. This created inherent latency **because** every cross-boundary call required serialization, queuing, and deserialization — making synchronous operations impossible and creating the infamous "bridge bottleneck."

The new architecture replaces the bridge with three interconnected systems: **JSI** (JavaScript Interface) for direct native memory access, **Fabric** for synchronous UI rendering, and **TurboModules** for lazy-loaded native modules. **Codegen** ties everything together by generating type-safe bindings from JavaScript specs. **Therefore**, the new architecture delivers measurable performance improvements: up to 3x faster startup for TurboModules and near-synchronous UI updates through Fabric.

## JSI: The Foundation Layer

**JSI** (JavaScript Interface) is a lightweight C++ API that allows JavaScript to hold direct references to C++ host objects. Unlike the old bridge, JSI does not serialize data — it provides direct memory access. This is critical **because** it enables synchronous calls between JS and native code, eliminating the round-trip overhead that caused jank in complex interactions.

### Implementing a JSI Native Module

A **common mistake** is treating JSI modules like old-style bridge modules. JSI modules require C++ implementations that are shared across platforms, with thin platform-specific wrappers.

```cpp
// CryptoModule.h — JSI Host Object for cross-platform crypto operations
#pragma once

#include <jsi/jsi.h>
#include <string>
#include <vector>
#include <memory>
#include <openssl/sha.h>
#include <openssl/aes.h>

namespace facebook {
namespace react {

// Best practice: inherit from HostObject for garbage-collected C++ objects
// accessible from JavaScript with zero serialization overhead
class CryptoModule : public jsi::HostObject {
public:
    CryptoModule() = default;

    // get() is called when JS accesses a property on this host object
    jsi::Value get(jsi::Runtime& runtime, const jsi::PropNameID& name) override {
        auto methodName = name.utf8(runtime);

        if (methodName == "sha256") {
            // Return a native function callable from JS synchronously
            // Trade-off: synchronous calls block the JS thread,
            // so only use for fast operations (<1ms)
            return jsi::Function::createFromHostFunction(
                runtime,
                name,
                1, // argument count
                [](jsi::Runtime& rt,
                   const jsi::Value& thisVal,
                   const jsi::Value* args,
                   size_t count) -> jsi::Value {
                    if (count < 1 || !args[0].isString()) {
                        throw jsi::JSError(rt, "sha256 expects a string argument");
                    }
                    auto input = args[0].asString(rt).utf8(rt);

                    // Compute SHA-256 directly — no bridge serialization
                    unsigned char hash[SHA256_DIGEST_LENGTH];
                    SHA256(reinterpret_cast<const unsigned char*>(input.c_str()),
                           input.length(), hash);

                    // Convert to hex string
                    std::string hexStr;
                    hexStr.reserve(SHA256_DIGEST_LENGTH * 2);
                    for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
                        char buf[3];
                        snprintf(buf, sizeof(buf), "%02x", hash[i]);
                        hexStr += buf;
                    }

                    return jsi::String::createFromUtf8(rt, hexStr);
                }
            );
        }

        if (methodName == "generateKeyPair") {
            // Async operations should return Promises even in JSI
            // Pitfall: blocking the JS thread for key generation (>100ms)
            // causes visible frame drops
            return jsi::Function::createFromHostFunction(
                runtime, name, 1,
                [](jsi::Runtime& rt,
                   const jsi::Value& thisVal,
                   const jsi::Value* args,
                   size_t count) -> jsi::Value {
                    auto promiseCtor = rt.global()
                        .getPropertyAsFunction(rt, "Promise");
                    return promiseCtor.callAsConstructor(
                        rt,
                        jsi::Function::createFromHostFunction(
                            rt, jsi::PropNameID::forAscii(rt, "executor"), 2,
                            [](jsi::Runtime& rt2,
                               const jsi::Value&,
                               const jsi::Value* execArgs,
                               size_t) -> jsi::Value {
                                auto resolve = execArgs[0].asObject(rt2)
                                    .asFunction(rt2);
                                // In production, dispatch to background thread
                                auto result = jsi::Object(rt2);
                                result.setProperty(rt2, "publicKey",
                                    jsi::String::createFromUtf8(rt2, "pk_generated"));
                                result.setProperty(rt2, "privateKey",
                                    jsi::String::createFromUtf8(rt2, "sk_generated"));
                                resolve.call(rt2, result);
                                return jsi::Value::undefined();
                            }
                        )
                    );
                }
            );
        }
        return jsi::Value::undefined();
    }

    std::vector<jsi::PropNameID> getPropertyNames(jsi::Runtime& rt) override {
        std::vector<jsi::PropNameID> props;
        props.push_back(jsi::PropNameID::forAscii(rt, "sha256"));
        props.push_back(jsi::PropNameID::forAscii(rt, "generateKeyPair"));
        return props;
    }
};

// Registration function called during app initialization
void installCryptoModule(jsi::Runtime& runtime) {
    auto module = std::make_shared<CryptoModule>();
    auto obj = jsi::Object::createFromHostObject(runtime, module);
    runtime.global().setProperty(runtime, "CryptoNative", std::move(obj));
}

} // namespace react
} // namespace facebook
```

### Platform-Specific Registration

```java
// Android: CryptoPackage.java — register the JSI module during app init
package com.myapp.crypto;

import com.facebook.react.bridge.JSIModulePackage;
import com.facebook.react.bridge.JSIModuleSpec;
import com.facebook.react.bridge.JavaScriptContextHolder;
import com.facebook.react.bridge.ReactApplicationContext;
import java.util.Collections;
import java.util.List;

// Best practice: use JSIModulePackage for JSI registration on Android
// This ensures the module is installed before any JS execution
public class CryptoPackage implements JSIModulePackage {
    @Override
    public List<JSIModuleSpec> getJSIModules(
            ReactApplicationContext reactContext,
            JavaScriptContextHolder jsContext) {
        // Install native module into the JS runtime
        // The native method bridges to the C++ installCryptoModule function
        nativeInstall(jsContext.get());
        return Collections.emptyList();
    }

    // JNI bridge to C++ — loads from the shared library
    // Pitfall: forgetting to load the native library causes
    // UnsatisfiedLinkError at runtime
    static {
        System.loadLibrary("crypto_jsi");
    }

    private static native void nativeInstall(long jsiRuntimeRef);
}
```

## TurboModules and Codegen

**TurboModules** replace the old Native Modules system with lazy-loaded, type-safe modules. Unlike old native modules that were all initialized at startup, TurboModules are loaded on first access. This dramatically improves startup time **because** a typical app may register 50+ native modules but only use 10 in the first screen.

**Codegen** reads TypeScript or Flow type definitions and generates native interface code. This eliminates runtime type-checking overhead and catches type mismatches at build time rather than at runtime.

```typescript
// NativeCryptoSpec.ts — TurboModule spec processed by Codegen
// Best practice: keep specs in a dedicated specs/ directory
// Codegen generates Obj-C protocols and Java abstract classes from this
import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

// Codegen reads these TypeScript types and generates:
// 1. C++ JSI bindings with type validation
// 2. Obj-C protocol (NativeCryptoSpec.h)
// 3. Java abstract class (NativeCryptoSpec.java)
export interface Spec extends TurboModule {
  // Synchronous method — runs on JS thread, must be fast
  sha256(input: string): string;

  // Async method — returns Promise, can do heavy work
  generateKeyPair(algorithm: string): Promise<{
    publicKey: string;
    privateKey: string;
  }>;

  // However, avoid overloading a single TurboModule with too many methods
  // Trade-off: granular modules vs. initialization overhead
  encrypt(data: string, key: string): Promise<string>;
  decrypt(ciphertext: string, key: string): Promise<string>;

  // Constants are evaluated once at module load
  getConstants(): {
    supportedAlgorithms: string[];
    maxKeySize: number;
  };
}

// The string must match the native module registration name exactly
// Common mistake: mismatched names cause "TurboModule not found" errors
export default TurboModuleRegistry.getEnforcing<Spec>('CryptoModule');
```

## Fabric: Synchronous Rendering

**Fabric** replaces the old UI Manager with a C++ rendering pipeline that can perform layout calculations synchronously on any thread. This matters **because** the old architecture could not measure native views from JavaScript without an async round-trip, causing layout flickering in complex UIs.

### Key Takeaways

- **JSI** eliminates bridge serialization by giving JS direct access to C++ host objects, enabling synchronous native calls for latency-critical operations
- **TurboModules** provide lazy loading and type-safe native module access through Codegen-generated bindings, reducing startup time by 30-50% in typical apps
- **Fabric** enables synchronous UI rendering and measurement, eliminating the layout flickering caused by async bridge communication
- **Codegen** catches type mismatches at build time rather than runtime, and the **best practice** is to define specs in TypeScript for maximum type safety
- The **trade-off** with JSI synchronous calls is that they block the JS thread — reserve them for sub-millisecond operations and use Promises for anything slower
- **Pitfall**: mixing old architecture bridge modules with new architecture TurboModules causes subtle initialization ordering bugs; migrate incrementally but test each module in isolation
- Migration should be incremental: enable the new architecture in `react-native.config.js`, migrate one module at a time, and validate with the `RCT_NEW_ARCH_ENABLED` flag
"""
    ),
    (
        "mobile/flutter-internals-widget-element-render-trees-impeller",
        "Explain Flutter internals including the widget tree, element tree, render tree, Dart ahead-of-time compilation, platform channels, and Skia/Impeller rendering engine with implementation of a custom RenderObject, platform channel communication, and isolate-based background processing",
        r"""# Flutter Internals: Trees, Rendering, and Platform Communication

## The Three-Tree Architecture

Flutter's rendering pipeline is built on **three distinct tree structures** that work together to deliver 60fps (or 120fps) rendering. Understanding these trees is essential **because** they explain why Flutter can rebuild widgets cheaply while maintaining rendering performance that rivals native apps.

### Widget Tree: The Configuration Layer

The **widget tree** is what developers write in Dart code. Widgets are **immutable configuration objects** — they describe what the UI should look like but do not own any mutable state or rendering resources. When `setState()` is called, Flutter creates new widget instances and diffs them against the previous tree. This is fast **because** widgets are lightweight Dart objects with no platform resources attached.

### Element Tree: The Lifecycle Manager

The **element tree** is the persistent backbone of Flutter's UI. Elements are created from widgets and manage the lifecycle — mounting, updating, and unmounting. When a widget rebuild occurs, Flutter walks the element tree and calls `updateChild()` on each element. The element compares the old and new widget by `runtimeType` and `key`, and either updates in place or creates a new element.

A **common mistake** is neglecting `Key` usage in lists, which causes Flutter to reuse elements incorrectly. **Therefore**, always use `ValueKey` or `ObjectKey` for list items with stable identity.

### Render Tree: The Layout and Paint Engine

The **render tree** contains `RenderObject` instances that perform actual layout calculations and painting. Each `RenderObject` has a `performLayout()` method that computes its size and positions its children, and a `paint()` method that draws pixels to a canvas.

## Implementing a Custom RenderObject

Building a custom `RenderObject` gives you complete control over layout and painting. This is the **best practice** when built-in widgets cannot express your layout logic — for example, a radial menu or a custom chart.

```dart
// custom_radial_layout.dart
// A RenderObject that positions children in a radial (circular) pattern
// with configurable radius, start angle, and sweep

import 'dart:math' as math;
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

// The Widget layer — immutable configuration
class RadialLayout extends MultiChildRenderObjectWidget {
  final double radius;
  final double startAngle;
  final double sweepAngle;
  final Alignment center;

  const RadialLayout({
    super.key,
    required super.children,
    this.radius = 100.0,
    this.startAngle = 0.0,
    this.sweepAngle = 2 * math.pi,
    this.center = Alignment.center,
  });

  @override
  RenderRadialLayout createRenderObject(BuildContext context) {
    return RenderRadialLayout(
      layoutRadius: radius,
      layoutStartAngle: startAngle,
      layoutSweepAngle: sweepAngle,
      layoutCenter: center,
    );
  }

  @override
  void updateRenderObject(BuildContext context, RenderRadialLayout renderObject) {
    // Best practice: only mark needs-layout when values actually change
    // Trade-off: more boilerplate but prevents unnecessary layout passes
    renderObject
      ..layoutRadius = radius
      ..layoutStartAngle = startAngle
      ..layoutSweepAngle = sweepAngle
      ..layoutCenter = center;
  }
}

// ParentData stored on each child for radial positioning
class RadialParentData extends ContainerBoxParentData<RenderBox> {
  double angle = 0.0;
  double distanceFromCenter = 0.0;
}

// The RenderObject — mutable, performs actual layout and painting
class RenderRadialLayout extends RenderBox
    with
        ContainerRenderObjectMixin<RenderBox, RadialParentData>,
        RenderBoxContainerDefaultsMixin<RenderBox, RadialParentData> {

  double _layoutRadius;
  double _layoutStartAngle;
  double _layoutSweepAngle;
  Alignment _layoutCenter;

  RenderRadialLayout({
    required double layoutRadius,
    required double layoutStartAngle,
    required double layoutSweepAngle,
    required Alignment layoutCenter,
  })  : _layoutRadius = layoutRadius,
        _layoutStartAngle = layoutStartAngle,
        _layoutSweepAngle = layoutSweepAngle,
        _layoutCenter = layoutCenter;

  // Setters that trigger relayout only when values change
  set layoutRadius(double value) {
    if (_layoutRadius == value) return;
    _layoutRadius = value;
    markNeedsLayout();
  }

  set layoutStartAngle(double value) {
    if (_layoutStartAngle == value) return;
    _layoutStartAngle = value;
    markNeedsLayout();
  }

  set layoutSweepAngle(double value) {
    if (_layoutSweepAngle == value) return;
    _layoutSweepAngle = value;
    markNeedsLayout();
  }

  set layoutCenter(Alignment value) {
    if (_layoutCenter == value) return;
    _layoutCenter = value;
    markNeedsLayout();
  }

  @override
  void setupParentData(RenderBox child) {
    if (child.parentData is! RadialParentData) {
      child.parentData = RadialParentData();
    }
  }

  @override
  void performLayout() {
    // First pass: let each child determine its own size
    // Pitfall: using tight constraints here prevents children from sizing themselves
    final childConstraints = BoxConstraints.loose(constraints.biggest);
    int childCount = 0;
    RenderBox? child = firstChild;
    while (child != null) {
      child.layout(childConstraints, parentUsesSize: true);
      childCount++;
      child = childAfter(child);
    }

    // Second pass: position children in a radial pattern
    final centerX = size.width / 2 + _layoutCenter.x * size.width / 2;
    final centerY = size.height / 2 + _layoutCenter.y * size.height / 2;
    final angleStep = childCount > 1
        ? _layoutSweepAngle / (childCount - 1)
        : 0.0;

    int index = 0;
    child = firstChild;
    while (child != null) {
      final parentData = child.parentData as RadialParentData;
      final angle = _layoutStartAngle + angleStep * index;
      parentData.angle = angle;
      parentData.distanceFromCenter = _layoutRadius;

      // Position child centered on its radial point
      parentData.offset = Offset(
        centerX + _layoutRadius * math.cos(angle) - child.size.width / 2,
        centerY + _layoutRadius * math.sin(angle) - child.size.height / 2,
      );

      index++;
      child = childAfter(child);
    }

    // Size ourselves to fill available space
    size = constraints.biggest;
  }

  @override
  void paint(PaintingContext context, Offset offset) {
    // Paint connection lines from center to each child
    final canvas = context.canvas;
    final centerX = size.width / 2 + _layoutCenter.x * size.width / 2;
    final centerY = size.height / 2 + _layoutCenter.y * size.height / 2;
    final centerPoint = offset + Offset(centerX, centerY);

    final linePaint = Paint()
      ..color = const Color(0x40000000)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    RenderBox? child = firstChild;
    while (child != null) {
      final parentData = child.parentData as RadialParentData;
      final childCenter = offset + parentData.offset +
          Offset(child.size.width / 2, child.size.height / 2);
      canvas.drawLine(centerPoint, childCenter, linePaint);
      context.paintChild(child, offset + parentData.offset);
      child = childAfter(child);
    }
  }

  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) {
    return defaultHitTestChildren(result, position: position);
  }
}
```

## Platform Channels: Bridging Dart and Native

**Platform channels** enable communication between Dart and platform-specific code (Kotlin/Swift). **However**, they use asynchronous message passing, which introduces latency. The **trade-off** is straightforward: platform channels are simpler to implement than FFI but cannot support synchronous calls or high-frequency data streaming efficiently.

```dart
// platform_battery_service.dart
// Demonstrates MethodChannel and EventChannel for platform communication

import 'dart:async';
import 'package:flutter/services.dart';

class BatteryService {
  // MethodChannel for request-response communication
  static const _methodChannel = MethodChannel('com.myapp/battery');

  // EventChannel for continuous native-to-Dart streaming
  static const _eventChannel = EventChannel('com.myapp/battery_state');

  // One-shot queries use MethodChannel
  // Common mistake: not handling PlatformException for unsupported platforms
  Future<int> getBatteryLevel() async {
    try {
      final int level = await _methodChannel.invokeMethod('getBatteryLevel');
      return level;
    } on PlatformException catch (e) {
      throw BatteryException('Failed to get battery level: ${e.message}');
    }
  }

  // Continuous updates use EventChannel with broadcast streams
  // Best practice: expose as a broadcast stream so multiple listeners work
  Stream<BatteryState> get batteryStateStream {
    return _eventChannel.receiveBroadcastStream().map((event) {
      final Map<String, dynamic> data = Map<String, dynamic>.from(event);
      return BatteryState(
        level: data['level'] as int,
        isCharging: data['isCharging'] as bool,
        temperature: data['temperature'] as double,
      );
    });
  }
}

class BatteryState {
  final int level;
  final bool isCharging;
  final double temperature;
  const BatteryState({
    required this.level,
    required this.isCharging,
    required this.temperature,
  });
}

class BatteryException implements Exception {
  final String message;
  BatteryException(this.message);
}
```

## Isolate-Based Background Processing

Dart is single-threaded by default, but **isolates** provide true parallelism. Each isolate has its own memory heap, so communication happens via message passing. This is the **best practice** for CPU-intensive tasks **because** it prevents UI jank without sharing mutable state.

```dart
// image_processor_isolate.dart
// Heavy image processing in a background isolate

import 'dart:async';
import 'dart:isolate';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';

class ImageProcessor {
  // Use compute() for simple one-shot background tasks
  // However, for sustained processing, a long-lived isolate is more efficient
  // because compute() creates and destroys an isolate each time
  static Future<Uint8List> applyFilter(Uint8List imageData, String filter) {
    return compute(_applyFilterInIsolate, _FilterRequest(imageData, filter));
  }

  // Top-level or static function required for isolate entry point
  // Pitfall: closures capturing instance state cannot be sent to isolates
  static Uint8List _applyFilterInIsolate(_FilterRequest request) {
    final pixels = request.imageData;
    final result = Uint8List(pixels.length);

    for (int i = 0; i < pixels.length; i += 4) {
      final r = pixels[i];
      final g = pixels[i + 1];
      final b = pixels[i + 2];
      final a = pixels[i + 3];

      switch (request.filterName) {
        case 'grayscale':
          final gray = (0.299 * r + 0.587 * g + 0.114 * b).round();
          result[i] = gray;
          result[i + 1] = gray;
          result[i + 2] = gray;
          result[i + 3] = a;
          break;
        case 'sepia':
          result[i] = (r * 0.393 + g * 0.769 + b * 0.189).clamp(0, 255).round();
          result[i + 1] = (r * 0.349 + g * 0.686 + b * 0.168).clamp(0, 255).round();
          result[i + 2] = (r * 0.272 + g * 0.534 + b * 0.131).clamp(0, 255).round();
          result[i + 3] = a;
          break;
        default:
          result[i] = r;
          result[i + 1] = g;
          result[i + 2] = b;
          result[i + 3] = a;
      }
    }
    return result;
  }

  // Long-lived isolate for sustained processing pipelines
  // Trade-off: more setup code but reuses the isolate across requests
  static Future<LongLivedProcessor> createProcessor() async {
    final receivePort = ReceivePort();
    final isolate = await Isolate.spawn(
      _processorEntryPoint,
      receivePort.sendPort,
    );
    final sendPort = await receivePort.first as SendPort;
    return LongLivedProcessor(isolate, sendPort);
  }

  static void _processorEntryPoint(SendPort mainSendPort) {
    final receivePort = ReceivePort();
    mainSendPort.send(receivePort.sendPort);

    receivePort.listen((message) {
      if (message is _FilterRequest) {
        final result = _applyFilterInIsolate(message);
        mainSendPort.send(result);
      }
    });
  }
}

class _FilterRequest {
  final Uint8List imageData;
  final String filterName;
  _FilterRequest(this.imageData, this.filterName);
}

class LongLivedProcessor {
  final Isolate _isolate;
  final SendPort _sendPort;
  LongLivedProcessor(this._isolate, this._sendPort);

  void processImage(Uint8List data, String filter) {
    _sendPort.send(_FilterRequest(data, filter));
  }

  void dispose() {
    _isolate.kill(priority: Isolate.immediate);
  }
}
```

## Skia vs. Impeller Rendering

Flutter originally used **Skia** as its rendering backend. Skia compiles shaders at runtime, which caused **shader compilation jank** — first-time stutters when new visual effects appeared. **Impeller** is Flutter's replacement renderer that **pre-compiles all shaders** at build time. **Therefore**, Impeller eliminates first-run jank entirely, though the **trade-off** is slightly larger binary sizes due to bundled shader variants.

### Key Takeaways

- Flutter's **three-tree architecture** (widget, element, render) separates configuration from lifecycle from rendering, enabling cheap widget rebuilds without expensive re-rendering
- Custom **RenderObject** implementations give full control over layout and painting; use them when built-in widgets cannot express your design, but understand the **trade-off** of increased complexity and maintenance burden
- **Platform channels** use asynchronous message passing between Dart and native code; use `MethodChannel` for request-response and `EventChannel` for streams, and always handle `PlatformException`
- **Isolates** provide true parallelism with memory isolation; use `compute()` for one-shot tasks and long-lived isolates for sustained processing pipelines, but remember that **closures capturing instance state cannot cross isolate boundaries**
- **Impeller** eliminates shader compilation jank by pre-compiling all shaders at build time, replacing Skia's runtime compilation model — this is the **best practice** for production Flutter apps targeting smooth 60/120fps rendering
- **Pitfall**: overusing `setState()` at the root widget triggers full-tree rebuilds; scope state changes to the smallest possible subtree using `ValueNotifier` or `InheritedWidget`
"""
    ),
    (
        "mobile/performance-60fps-jank-detection-memory-optimization",
        "Explain mobile app performance optimization techniques including 60fps rendering targets, jank detection and frame timing analysis, memory pressure handling, image loading optimization, and list virtualization with implementation of a comprehensive performance monitoring framework",
        r"""# Mobile App Performance: Achieving 60fps and Beyond

## Understanding Frame Budgets and Jank

Mobile displays typically refresh at **60Hz** (16.67ms per frame) or **120Hz** (8.33ms per frame). Any frame that exceeds its budget causes **jank** — a visible stutter that users perceive as poor quality. This matters **because** studies show that users abandon apps with perceived performance issues at 2-3x the rate of smooth apps. A single 100ms jank during a scroll interaction feels broken, even if the app is otherwise fast.

**Jank** originates from three sources: **main thread overload** (too much work in the UI thread), **GPU overdraw** (too many layered transparent pixels), and **garbage collection pauses** (memory pressure forcing collection during animation frames). **Therefore**, a comprehensive performance strategy must address all three simultaneously.

### Frame Timing Analysis

The frame rendering pipeline on mobile follows a strict sequence: input handling, animation ticks, layout/measure, draw/paint, composite, and GPU render. A **common mistake** is optimizing only the draw phase while ignoring expensive layout recalculations that happen earlier in the pipeline. **However**, layout thrashing (repeatedly reading and writing layout properties) is often the largest contributor to jank.

## Implementing a Performance Monitoring Framework

The following framework captures frame timing, memory snapshots, and rendering statistics across both Android and iOS platforms.

```kotlin
// PerformanceMonitor.kt — Android frame timing and memory tracking
// Best practice: use Choreographer for accurate frame timing rather than
// System.currentTimeMillis() which lacks sub-frame precision

import android.os.Handler
import android.os.Looper
import android.view.Choreographer
import android.app.ActivityManager
import android.content.Context
import android.os.Debug
import android.os.Process
import java.util.concurrent.ConcurrentLinkedDeque
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.max

data class FrameMetrics(
    val frameNumber: Long,
    val timestampNanos: Long,
    val durationMs: Double,
    val isJank: Boolean,
    val droppedFrames: Int
)

data class MemorySnapshot(
    val timestampMs: Long,
    val heapUsedKb: Long,
    val heapTotalKb: Long,
    val nativeHeapKb: Long,
    val heapUtilization: Float,
    val gcCount: Long
)

data class PerformanceReport(
    val sessionDurationMs: Long,
    val totalFrames: Long,
    val jankFrames: Long,
    val jankPercentage: Double,
    val avgFrameTimeMs: Double,
    val p95FrameTimeMs: Double,
    val p99FrameTimeMs: Double,
    val maxFrameTimeMs: Double,
    val avgFps: Double,
    val memoryPeakKb: Long,
    val memoryAvgKb: Long,
    val gcPauses: Long
)

// Trade-off: monitoring itself has overhead (~0.1ms per frame)
// Therefore, use sampling in production (every Nth frame)
class PerformanceMonitor private constructor(
    private val context: Context,
    private val config: MonitorConfig
) {
    data class MonitorConfig(
        val jankThresholdMs: Double = 16.67,
        val maxHistorySize: Int = 3600,
        val memorySampleIntervalMs: Long = 1000,
        val enableInProduction: Boolean = false,
        val samplingRate: Int = 1 // 1 = every frame, 10 = every 10th
    )

    companion object {
        @Volatile
        private var instance: PerformanceMonitor? = null

        fun initialize(context: Context, config: MonitorConfig = MonitorConfig()): PerformanceMonitor {
            return instance ?: synchronized(this) {
                instance ?: PerformanceMonitor(context.applicationContext, config).also {
                    instance = it
                }
            }
        }

        fun getInstance(): PerformanceMonitor =
            instance ?: throw IllegalStateException("PerformanceMonitor not initialized")
    }

    private val isMonitoring = AtomicBoolean(false)
    private val frameHistory = ConcurrentLinkedDeque<FrameMetrics>()
    private val memoryHistory = ConcurrentLinkedDeque<MemorySnapshot>()
    private val frameCount = AtomicLong(0)
    private val jankCount = AtomicLong(0)
    private var startTimeMs = 0L
    private var lastFrameNanos = 0L

    private val mainHandler = Handler(Looper.getMainLooper())
    private val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE)
        as ActivityManager

    // Choreographer callback runs once per vsync — the most accurate
    // frame timing mechanism on Android
    // Pitfall: registering multiple Choreographer callbacks causes
    // duplicate frame counting
    private val frameCallback = object : Choreographer.FrameCallback {
        override fun doFrame(frameTimeNanos: Long) {
            if (!isMonitoring.get()) return

            val currentFrame = frameCount.incrementAndGet()

            if (lastFrameNanos > 0 && currentFrame % config.samplingRate == 0L) {
                val durationNanos = frameTimeNanos - lastFrameNanos
                val durationMs = durationNanos / 1_000_000.0
                val isJank = durationMs > config.jankThresholdMs
                val droppedFrames = max(0, (durationMs / config.jankThresholdMs).toInt() - 1)

                if (isJank) jankCount.incrementAndGet()

                val metrics = FrameMetrics(
                    frameNumber = currentFrame,
                    timestampNanos = frameTimeNanos,
                    durationMs = durationMs,
                    isJank = isJank,
                    droppedFrames = droppedFrames
                )

                frameHistory.addLast(metrics)
                while (frameHistory.size > config.maxHistorySize) {
                    frameHistory.pollFirst()
                }
            }

            lastFrameNanos = frameTimeNanos
            Choreographer.getInstance().postFrameCallback(this)
        }
    }

    fun startMonitoring() {
        if (isMonitoring.getAndSet(true)) return
        startTimeMs = System.currentTimeMillis()
        lastFrameNanos = 0
        frameCount.set(0)
        jankCount.set(0)
        Choreographer.getInstance().postFrameCallback(frameCallback)
        startMemorySampling()
    }

    fun stopMonitoring(): PerformanceReport {
        isMonitoring.set(false)
        return generateReport()
    }

    private fun startMemorySampling() {
        mainHandler.post(object : Runnable {
            override fun run() {
                if (!isMonitoring.get()) return
                captureMemorySnapshot()
                mainHandler.postDelayed(this, config.memorySampleIntervalMs)
            }
        })
    }

    private fun captureMemorySnapshot() {
        val runtime = Runtime.getRuntime()
        val memInfo = Debug.MemoryInfo()
        Debug.getMemoryInfo(memInfo)

        val snapshot = MemorySnapshot(
            timestampMs = System.currentTimeMillis(),
            heapUsedKb = (runtime.totalMemory() - runtime.freeMemory()) / 1024,
            heapTotalKb = runtime.totalMemory() / 1024,
            nativeHeapKb = Debug.getNativeHeapAllocatedSize() / 1024,
            heapUtilization = (runtime.totalMemory() - runtime.freeMemory()).toFloat()
                / runtime.maxMemory().toFloat(),
            gcCount = Debug.getRuntimeStat("art.gc.gc-count")?.toLongOrNull() ?: 0
        )

        memoryHistory.addLast(snapshot)
        while (memoryHistory.size > config.maxHistorySize) {
            memoryHistory.pollFirst()
        }
    }

    private fun generateReport(): PerformanceReport {
        val frames = frameHistory.toList()
        val durations = frames.map { it.durationMs }.sorted()
        val sessionDuration = System.currentTimeMillis() - startTimeMs

        return PerformanceReport(
            sessionDurationMs = sessionDuration,
            totalFrames = frameCount.get(),
            jankFrames = jankCount.get(),
            jankPercentage = if (frameCount.get() > 0)
                jankCount.get().toDouble() / frameCount.get() * 100 else 0.0,
            avgFrameTimeMs = durations.average(),
            p95FrameTimeMs = durations.getOrElse((durations.size * 0.95).toInt()) { 0.0 },
            p99FrameTimeMs = durations.getOrElse((durations.size * 0.99).toInt()) { 0.0 },
            maxFrameTimeMs = durations.maxOrNull() ?: 0.0,
            avgFps = if (durations.average() > 0) 1000.0 / durations.average() else 0.0,
            memoryPeakKb = memoryHistory.maxOfOrNull { it.heapUsedKb } ?: 0,
            memoryAvgKb = memoryHistory.map { it.heapUsedKb }.average().toLong(),
            gcPauses = memoryHistory.lastOrNull()?.gcCount ?: 0
        )
    }
}
```

## Image Loading Optimization

Images are the single largest source of memory consumption in mobile apps. A **common mistake** is loading full-resolution images into memory when only a thumbnail is displayed. A 4000x3000 JPEG occupies only 2MB on disk but **48MB in memory** as a decoded bitmap (4000 * 3000 * 4 bytes per pixel).

```kotlin
// ImageOptimizer.kt — memory-efficient image loading with progressive decoding
// Best practice: always decode to the target display size, never full resolution

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.widget.ImageView
import java.io.InputStream
import java.lang.ref.WeakReference
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.*

class ImageOptimizer(
    private val memoryCache: LruBitmapCache,
    private val scope: CoroutineScope
) {
    // Calculate optimal inSampleSize for target dimensions
    // Trade-off: inSampleSize must be power of 2, so you may
    // decode slightly larger than needed
    private fun calculateInSampleSize(
        options: BitmapFactory.Options,
        reqWidth: Int,
        reqHeight: Int
    ): Int {
        val (height, width) = options.outHeight to options.outWidth
        var inSampleSize = 1

        if (height > reqHeight || width > reqWidth) {
            val halfHeight = height / 2
            val halfWidth = width / 2
            // However, a non-power-of-2 inSampleSize works on modern Android
            // but is less efficient on GPU upload
            while (halfHeight / inSampleSize >= reqHeight
                && halfWidth / inSampleSize >= reqWidth) {
                inSampleSize *= 2
            }
        }
        return inSampleSize
    }

    // Load image at the exact size needed for display
    // Pitfall: forgetting to recycle old bitmaps causes OOM on older devices
    suspend fun loadOptimized(
        stream: InputStream,
        targetWidth: Int,
        targetHeight: Int
    ): Bitmap = withContext(Dispatchers.IO) {
        // First pass: decode bounds only (no memory allocation)
        val options = BitmapFactory.Options().apply {
            inJustDecodeBounds = true
        }
        BitmapFactory.decodeStream(stream, null, options)

        // Second pass: decode at target size
        stream.reset()
        options.apply {
            inJustDecodeBounds = false
            inSampleSize = calculateInSampleSize(this, targetWidth, targetHeight)
            inPreferredConfig = Bitmap.Config.RGB_565 // 2 bytes/pixel vs 4 for ARGB_8888
            inMutable = false // immutable bitmaps can share pixel data
        }

        BitmapFactory.decodeStream(stream, null, options)
            ?: throw IllegalStateException("Failed to decode image")
    }
}

// LRU cache that respects memory pressure
// Best practice: size cache as fraction of available heap
class LruBitmapCache(maxSizeBytes: Int) {
    private val cache = object : android.util.LruCache<String, Bitmap>(maxSizeBytes) {
        override fun sizeOf(key: String, bitmap: Bitmap): Int {
            return bitmap.allocationByteCount
        }

        override fun entryRemoved(
            evicted: Boolean, key: String,
            oldValue: Bitmap, newValue: Bitmap?
        ) {
            // Common mistake: recycling bitmaps that are still displayed
            // Therefore, only recycle on eviction, not on replacement
            if (evicted && !oldValue.isRecycled) {
                oldValue.recycle()
            }
        }
    }

    fun get(key: String): Bitmap? = cache.get(key)
    fun put(key: String, bitmap: Bitmap) = cache.put(key, bitmap)

    fun trimToSize(maxSize: Int) {
        cache.trimToSize(maxSize)
    }
}
```

## List Virtualization

List virtualization (also called **windowing**) renders only the visible items plus a small buffer. This is the most impactful optimization for long lists **because** it bounds memory usage to O(visible items) rather than O(total items), regardless of dataset size.

```kotlin
// VirtualizedListConfig.kt — configuration for optimal list recycling
// RecyclerView already virtualizes, but these settings prevent common jank sources

import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.LinearLayoutManager

// Best practice: pre-configure RecyclerView for maximum scroll smoothness
fun RecyclerView.optimizeForPerformance(
    prefetchDistance: Int = 5,
    cacheSize: Int = 10,
    hasFixedSize: Boolean = true
) {
    // setHasFixedSize avoids full layout pass on adapter changes
    setHasFixedSize(hasFixedSize)

    // Item view cache — recycled views skip onBindViewHolder
    // Trade-off: more memory for smoother reverse scrolling
    setItemViewCacheSize(cacheSize)

    // Enable prefetching — loads views during idle time
    // However, disable if items have expensive bind operations
    // that could extend into animation frames
    (layoutManager as? LinearLayoutManager)?.apply {
        initialPrefetchItemCount = prefetchDistance
        isItemPrefetchEnabled = true
    }

    // Disable change animations for frequently-updated lists
    // Pitfall: default change animations cause full alpha fade
    // on every notifyItemChanged, creating unnecessary GPU overdraw
    itemAnimator = null
}
```

### Key Takeaways

- Every frame has a **16.67ms budget** at 60Hz; exceeding it causes visible jank that users perceive as broken, so **therefore** all UI-thread work must be profiled against this budget
- Use **Choreographer.FrameCallback** on Android (or `CADisplayLink` on iOS) for accurate frame timing rather than wall-clock timers, which lack vsync synchronization
- Images are the primary memory consumer: always decode to display size using `inSampleSize`, use `RGB_565` for opaque images (50% memory savings), and size your bitmap cache as 1/8th of available heap as a **best practice**
- **List virtualization** bounds memory to visible items; RecyclerView provides this automatically, but **common mistakes** include disabling prefetch, using unbounded caches, or triggering layout passes inside `onBindViewHolder`
- Memory pressure monitoring should track both Java heap and native heap allocation, **because** native memory (Bitmaps, native libraries) is invisible to the Java GC but still triggers OOM kills
- **Trade-off** in monitoring granularity: per-frame metrics give maximum visibility but add ~0.1ms overhead; use sampling (every 10th frame) in production builds
"""
    ),
    (
        "mobile/offline-first-crdt-sync-engine-conflict-resolution",
        "Explain offline-first mobile architecture including local database strategies with SQLite and Realm, conflict resolution approaches, sync protocols, and optimistic UI updates with implementation of a CRDT-based sync engine featuring local storage, change tracking, and server reconciliation",
        r"""# Offline-First Architecture: CRDT-Based Sync Engines for Mobile

## Why Offline-First Matters

**Offline-first architecture** treats network connectivity as an enhancement rather than a requirement. This philosophy is critical for mobile apps **because** real-world network conditions include elevators, subways, rural areas, and congested conference WiFi where connectivity is intermittent or nonexistent. An app that shows a spinner or error when offline is fundamentally broken for mobile users.

The core principle is: **write locally first, sync when possible, resolve conflicts automatically**. This requires three components: a **local database** for persistence, a **change tracking system** to record mutations, and a **conflict resolution strategy** to reconcile divergent states.

## Local Storage Strategies

### SQLite vs. Realm vs. Drift

**SQLite** remains the most battle-tested embedded database. It handles concurrent reads efficiently, supports transactions, and has a tiny footprint (~600KB). **However**, SQLite requires manual schema management and migration scripts, which is a **common mistake** source — forgotten migrations cause crashes on app update.

**Realm** (now part of MongoDB Atlas Device Sync) provides an object-oriented API with automatic change notifications and built-in sync. The **trade-off** is vendor lock-in and larger binary size (~5MB). **Therefore**, choose SQLite when you need maximum control and portability, and Realm when developer velocity matters more.

## CRDT-Based Sync Engine

**CRDTs** (Conflict-free Replicated Data Types) are data structures that can be merged without conflicts by mathematical guarantee. Unlike operational transform (OT) which requires a central server to order operations, CRDTs converge to the same state regardless of merge order. This is the **best practice** for offline-first apps **because** it eliminates the need for complex server-side conflict resolution.

### Core CRDT Implementation

```python
# crdt_sync_engine.py
# A Last-Writer-Wins Register (LWW-Register) CRDT with
# hybrid logical clock for causal ordering

import uuid
import json
import time
import sqlite3
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Dict, List, Set, Tuple
from enum import Enum
from collections import defaultdict

class OperationType(Enum):
    SET = "set"
    DELETE = "delete"
    INCREMENT = "increment"  # Counter CRDT operation
    ADD_TO_SET = "add_to_set"  # G-Set operation

@dataclass
class HybridLogicalClock:
    # HLC combines wall clock with logical counter for causal ordering
    # Best practice: HLC provides globally unique, causally ordered timestamps
    # without requiring synchronized clocks across devices
    timestamp_ms: int
    counter: int
    node_id: str

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = uuid.uuid4().hex[:12]

    def tick(self) -> "HybridLogicalClock":
        now_ms = int(time.time() * 1000)
        if now_ms > self.timestamp_ms:
            return HybridLogicalClock(now_ms, 0, self.node_id)
        else:
            # Wall clock hasn't advanced — increment logical counter
            # This handles rapid successive writes within the same ms
            return HybridLogicalClock(self.timestamp_ms, self.counter + 1, self.node_id)

    def merge(self, other: "HybridLogicalClock") -> "HybridLogicalClock":
        now_ms = int(time.time() * 1000)
        max_ts = max(now_ms, self.timestamp_ms, other.timestamp_ms)

        if max_ts == self.timestamp_ms == other.timestamp_ms:
            counter = max(self.counter, other.counter) + 1
        elif max_ts == self.timestamp_ms:
            counter = self.counter + 1
        elif max_ts == other.timestamp_ms:
            counter = other.counter + 1
        else:
            counter = 0

        return HybridLogicalClock(max_ts, counter, self.node_id)

    def __gt__(self, other: "HybridLogicalClock") -> bool:
        if self.timestamp_ms != other.timestamp_ms:
            return self.timestamp_ms > other.timestamp_ms
        if self.counter != other.counter:
            return self.counter > other.counter
        return self.node_id > other.node_id  # Deterministic tiebreaker

    def to_string(self) -> str:
        return f"{self.timestamp_ms}:{self.counter}:{self.node_id}"

    @classmethod
    def from_string(cls, s: str) -> "HybridLogicalClock":
        parts = s.split(":")
        return cls(int(parts[0]), int(parts[1]), parts[2])


@dataclass
class CRDTOperation:
    # Each operation is immutable and globally unique
    operation_id: str
    entity_type: str
    entity_id: str
    field_name: str
    operation_type: OperationType
    value: Any
    hlc: HybridLogicalClock
    # Pitfall: forgetting to include the originating device ID
    # makes debugging sync issues nearly impossible
    device_id: str
    is_synced: bool = False

    def to_dict(self) -> Dict:
        return {
            "operation_id": self.operation_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "field_name": self.field_name,
            "operation_type": self.operation_type.value,
            "value": self.value,
            "hlc": self.hlc.to_string(),
            "device_id": self.device_id,
        }


class LocalStore:
    # SQLite-backed local storage with operation log
    # Best practice: separate the materialized view (current state)
    # from the operation log (history of changes)

    def __init__(self, db_path: str, device_id: str) -> None:
        self.db_path = db_path
        self.device_id = device_id
        self.clock = HybridLogicalClock(int(time.time() * 1000), 0, device_id[:12])
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Materialized view: current state of each entity field
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS entities ("
            "  entity_type TEXT NOT NULL,"
            "  entity_id TEXT NOT NULL,"
            "  field_name TEXT NOT NULL,"
            "  value TEXT,"
            "  hlc TEXT NOT NULL,"
            "  updated_by TEXT NOT NULL,"
            "  PRIMARY KEY (entity_type, entity_id, field_name))"
        )

        # Operation log: append-only log of all mutations
        # Trade-off: operation log grows unboundedly, needs periodic compaction
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS operations ("
            "  operation_id TEXT PRIMARY KEY,"
            "  entity_type TEXT NOT NULL,"
            "  entity_id TEXT NOT NULL,"
            "  field_name TEXT NOT NULL,"
            "  operation_type TEXT NOT NULL,"
            "  value TEXT,"
            "  hlc TEXT NOT NULL,"
            "  device_id TEXT NOT NULL,"
            "  is_synced INTEGER DEFAULT 0,"
            "  created_at REAL DEFAULT (julianday('now')))"
        )

        # Index for efficient sync queries
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_operations_unsynced "
            "ON operations (is_synced, created_at) "
            "WHERE is_synced = 0"
        )

        conn.commit()
        conn.close()

    def apply_operation(self, op: CRDTOperation) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check if this operation's HLC wins over the current value
            cursor.execute(
                "SELECT hlc FROM entities "
                "WHERE entity_type = ? AND entity_id = ? AND field_name = ?",
                (op.entity_type, op.entity_id, op.field_name)
            )

            row = cursor.fetchone()
            should_apply = True

            if row is not None:
                existing_hlc = HybridLogicalClock.from_string(row[0])
                # LWW: last writer wins based on HLC ordering
                # However, this means concurrent writes to the same field
                # will silently discard one value
                should_apply = op.hlc > existing_hlc

            if should_apply:
                if op.operation_type == OperationType.DELETE:
                    cursor.execute(
                        "DELETE FROM entities "
                        "WHERE entity_type = ? AND entity_id = ? AND field_name = ?",
                        (op.entity_type, op.entity_id, op.field_name)
                    )
                else:
                    cursor.execute(
                        "INSERT OR REPLACE INTO entities "
                        "(entity_type, entity_id, field_name, value, hlc, updated_by) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                        op.entity_type, op.entity_id, op.field_name,
                        json.dumps(op.value), op.hlc.to_string(), op.device_id
                    ))

            # Always record the operation in the log (idempotent via PK)
            cursor.execute(
                "INSERT OR IGNORE INTO operations "
                "(operation_id, entity_type, entity_id, field_name, "
                "operation_type, value, hlc, device_id, is_synced) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                op.operation_id, op.entity_type, op.entity_id, op.field_name,
                op.operation_type.value, json.dumps(op.value),
                op.hlc.to_string(), op.device_id, 1 if op.is_synced else 0
            ))

            conn.commit()
            return should_apply

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def write(self, entity_type: str, entity_id: str,
              field_name: str, value: Any) -> CRDTOperation:
        self.clock = self.clock.tick()
        op = CRDTOperation(
            operation_id=uuid.uuid4().hex,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            operation_type=OperationType.SET,
            value=value,
            hlc=self.clock,
            device_id=self.device_id,
            is_synced=False,
        )
        self.apply_operation(op)
        return op

    def read(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT field_name, value FROM entities "
            "WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id)
        )
        result = {}
        for row in cursor.fetchall():
            result[row[0]] = json.loads(row[1])
        conn.close()
        return result

    def get_unsynced_operations(self) -> List[CRDTOperation]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT operation_id, entity_type, entity_id, field_name, "
            "operation_type, value, hlc, device_id "
            "FROM operations WHERE is_synced = 0 "
            "ORDER BY hlc ASC"
        )
        ops = []
        for row in cursor.fetchall():
            ops.append(CRDTOperation(
                operation_id=row[0],
                entity_type=row[1],
                entity_id=row[2],
                field_name=row[3],
                operation_type=OperationType(row[4]),
                value=json.loads(row[5]),
                hlc=HybridLogicalClock.from_string(row[6]),
                device_id=row[7],
                is_synced=False,
            ))
        conn.close()
        return ops

    def mark_synced(self, operation_ids: List[str]) -> None:
        if not operation_ids:
            return
        conn = sqlite3.connect(self.db_path)
        placeholders = ",".join("?" * len(operation_ids))
        conn.execute(
            f"UPDATE operations SET is_synced = 1 "
            f"WHERE operation_id IN ({placeholders})",
            operation_ids
        )
        conn.commit()
        conn.close()
```

## Sync Protocol and Server Reconciliation

The sync protocol follows a **push-then-pull** pattern: first send local unsynced operations to the server, then receive and apply remote operations. This ordering prevents the device from receiving its own operations back.

```python
# sync_client.py
# Handles bidirectional sync between local CRDT store and remote server

import httpx
import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class SyncClient:
    # Best practice: implement exponential backoff for sync retries
    # Common mistake: retrying immediately on network errors floods
    # the server when it comes back online

    def __init__(self, store: LocalStore, server_url: str,
                 auth_token: str) -> None:
        self.store = store
        self.server_url = server_url
        self.auth_token = auth_token
        self._sync_lock = asyncio.Lock()
        self.max_retries = 5
        self.base_delay_seconds = 1.0

    async def sync(self) -> dict:
        # Prevent concurrent syncs — they cause operation ordering issues
        # Pitfall: allowing parallel syncs can duplicate operations
        async with self._sync_lock:
            pushed = await self._push_local_changes()
            pulled = await self._pull_remote_changes()
            return {"pushed": pushed, "pulled": pulled}

    async def _push_local_changes(self) -> int:
        unsynced = self.store.get_unsynced_operations()
        if not unsynced:
            return 0

        # Batch operations to reduce HTTP round-trips
        # Trade-off: larger batches are more efficient but risk
        # partial failures that are harder to retry
        batch_size = 100
        total_pushed = 0

        for i in range(0, len(unsynced), batch_size):
            batch = unsynced[i:i + batch_size]
            payload = [op.to_dict() for op in batch]

            for attempt in range(self.max_retries):
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{self.server_url}/api/sync/push",
                            json={"operations": payload},
                            headers={"Authorization": f"Bearer {self.auth_token}"},
                            timeout=30.0,
                        )
                        response.raise_for_status()
                        result = response.json()

                        # Mark successfully synced operations
                        synced_ids = result.get("accepted_ids", [])
                        self.store.mark_synced(synced_ids)
                        total_pushed += len(synced_ids)

                        # Update local clock from server response
                        if "server_hlc" in result:
                            server_hlc = HybridLogicalClock.from_string(
                                result["server_hlc"]
                            )
                            self.store.clock = self.store.clock.merge(server_hlc)
                        break

                except httpx.HTTPError as e:
                    delay = self.base_delay_seconds * (2 ** attempt)
                    logger.warning(
                        f"Push attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)

        return total_pushed

    async def _pull_remote_changes(self) -> int:
        # Therefore, pull uses the last-seen server timestamp
        # to request only new operations since the last sync
        last_sync_hlc = self.store.clock.to_string()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.server_url}/api/sync/pull",
                    params={
                        "since_hlc": last_sync_hlc,
                        "device_id": self.store.device_id,
                    },
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            remote_ops = data.get("operations", [])
            applied = 0

            for op_dict in remote_ops:
                op = CRDTOperation(
                    operation_id=op_dict["operation_id"],
                    entity_type=op_dict["entity_type"],
                    entity_id=op_dict["entity_id"],
                    field_name=op_dict["field_name"],
                    operation_type=OperationType(op_dict["operation_type"]),
                    value=op_dict["value"],
                    hlc=HybridLogicalClock.from_string(op_dict["hlc"]),
                    device_id=op_dict["device_id"],
                    is_synced=True,
                )
                if self.store.apply_operation(op):
                    applied += 1

            return applied

        except httpx.HTTPError as e:
            logger.error(f"Pull failed: {e}")
            return 0
```

## Optimistic UI Updates

**Optimistic UI** means applying changes to the local UI immediately without waiting for server confirmation. **However**, you must handle rollback gracefully when the server rejects an operation. The pattern involves three phases: apply locally and update UI, enqueue sync operation, and handle server response (confirm or rollback).

```python
# optimistic_ui.py
# Manages optimistic updates with rollback capability

from typing import Any, Callable, Optional
from dataclasses import dataclass

@dataclass
class PendingUpdate:
    entity_type: str
    entity_id: str
    field_name: str
    new_value: Any
    previous_value: Any
    operation: CRDTOperation
    on_confirm: Optional[Callable] = None
    on_rollback: Optional[Callable] = None

class OptimisticUpdateManager:
    # Best practice: track pending updates so you can rollback on server rejection
    # Pitfall: forgetting to store the previous value makes rollback impossible

    def __init__(self, store: LocalStore, sync_client: SyncClient) -> None:
        self.store = store
        self.sync_client = sync_client
        self.pending: dict[str, PendingUpdate] = {}

    def apply_optimistic(
        self, entity_type: str, entity_id: str,
        field_name: str, new_value: Any,
        on_confirm: Optional[Callable] = None,
        on_rollback: Optional[Callable] = None,
    ) -> str:
        # Read current value for potential rollback
        current = self.store.read(entity_type, entity_id)
        previous_value = current.get(field_name)

        # Write locally — UI sees immediate update
        # Therefore, the user perceives zero latency
        op = self.store.write(entity_type, entity_id, field_name, new_value)

        update = PendingUpdate(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            new_value=new_value,
            previous_value=previous_value,
            operation=op,
            on_confirm=on_confirm,
            on_rollback=on_rollback,
        )
        self.pending[op.operation_id] = update
        return op.operation_id

    def confirm(self, operation_id: str) -> None:
        update = self.pending.pop(operation_id, None)
        if update and update.on_confirm:
            update.on_confirm()

    def rollback(self, operation_id: str) -> None:
        # Common mistake: only rolling back state without updating the UI
        update = self.pending.pop(operation_id, None)
        if update:
            self.store.write(
                update.entity_type, update.entity_id,
                update.field_name, update.previous_value,
            )
            if update.on_rollback:
                update.on_rollback()
```

### Key Takeaways

- **Offline-first** treats network as an enhancement; write locally first, sync when possible, and resolve conflicts automatically using CRDTs that guarantee convergence without coordination
- **Hybrid Logical Clocks** provide causally ordered timestamps without requiring synchronized device clocks — a **best practice** over simple wall-clock timestamps that can go backwards during NTP adjustments
- **LWW-Register** is the simplest CRDT but silently drops concurrent writes; the **trade-off** is simplicity vs. data preservation — use merge-friendly CRDTs (G-Counter, OR-Set) when no data should be lost
- The **operation log** pattern separates mutation history from materialized state; this enables replay, audit trails, and time-travel debugging, but the **pitfall** is unbounded log growth requiring periodic compaction
- **Push-then-pull** sync ordering prevents a device from receiving its own operations back; always batch operations (100-500 per request) to reduce HTTP round-trips while keeping individual batches retryable
- **Common mistake**: implementing sync without idempotency — always use unique operation IDs and `INSERT OR IGNORE` semantics so replayed operations are harmless
"""
    ),
    (
        "mobile/security-certificate-pinning-secure-storage-tamper-detection",
        "Explain mobile security best practices including certificate pinning implementation, secure storage with Keychain and Keystore, biometric authentication, code obfuscation strategies, and root/jailbreak detection with implementation of a cross-platform security layer featuring encrypted storage and tamper detection",
        r"""# Mobile Security: Certificate Pinning, Secure Storage, and Tamper Detection

## The Mobile Threat Landscape

Mobile apps operate in a **hostile environment** where the device owner has full control over the hardware and operating system. Unlike server-side applications protected by controlled infrastructure, mobile apps can be decompiled, debugged, intercepted, and modified by anyone with basic tools. **Therefore**, mobile security is fundamentally about **defense in depth** — layering multiple protections so that compromising one layer does not give access to everything.

The primary threats are: **network interception** (MITM attacks on API traffic), **data extraction** (reading secrets from app storage), **binary analysis** (reverse-engineering the app to extract API keys or bypass logic), and **runtime manipulation** (hooking functions with Frida/Xposed to alter app behavior). Each requires a different defensive strategy.

## Certificate Pinning

**Certificate pinning** binds your app to specific TLS certificates or public keys, preventing man-in-the-middle attacks even when the attacker has installed a trusted CA certificate on the device. This is essential **because** corporate proxy devices, government surveillance systems, and malware all install custom root CAs that would otherwise be trusted by the OS.

### Implementation Approaches

There are three pinning strategies with different **trade-offs**:

1. **Certificate pinning**: Pin the exact leaf certificate. Most secure but requires app update when the certificate rotates (typically every 1-2 years).
2. **Public key pinning**: Pin the Subject Public Key Info (SPKI) hash. Survives certificate renewal as long as the same key pair is used. This is the **best practice** for most apps.
3. **CA pinning**: Pin the intermediate or root CA. Most resilient to rotation but weakest security — any certificate from that CA is trusted.

```swift
// NetworkSecurityManager.swift — iOS certificate pinning with URLSession
// Best practice: pin the SPKI hash (Subject Public Key Info) rather than
// the full certificate, because SPKI survives certificate renewal

import Foundation
import Security
import CryptoKit
import LocalAuthentication

class NetworkSecurityManager: NSObject, URLSessionDelegate {
    // Store SHA-256 hashes of the SPKI (Subject Public Key Info)
    // Include both current and backup pin to avoid lockout during rotation
    // Pitfall: pinning only one key means certificate rotation locks out
    // all existing app installations
    private let pinnedSPKIHashes: Set<String> = [
        "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=", // current key
        "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC=", // backup key
    ]

    // Pin expiration — force update if pins are too old
    // Common mistake: shipping pins that never expire means you cannot
    // rotate keys without breaking old app versions forever
    private let pinExpirationDate: Date = {
        var components = DateComponents()
        components.year = 2027
        components.month = 6
        components.day = 1
        return Calendar.current.date(from: components)!
    }()

    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.tlsMinimumSupportedProtocolVersion = .TLSv12
        config.tlsMaximumSupportedProtocolVersion = .TLSv13
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()

    // URLSessionDelegate method for TLS challenge
    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod ==
                NSURLAuthenticationMethodServerTrust,
              let serverTrust = challenge.protectionSpace.serverTrust else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        // Check pin expiration — if expired, fall back to standard validation
        // Trade-off: this creates a window of vulnerability but prevents
        // permanent lockout of users on old app versions
        if Date() > pinExpirationDate {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        // Validate the full certificate chain first
        var error: CFError?
        let isValid = SecTrustEvaluateWithError(serverTrust, &error)
        guard isValid else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        // Extract and verify SPKI hash from the leaf certificate
        guard let certificate = SecTrustCopyCertificateChain(serverTrust)
                as? [SecCertificate],
              let leafCert = certificate.first else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        let spkiHash = extractSPKIHash(from: leafCert)
        if pinnedSPKIHashes.contains(spkiHash) {
            let credential = URLCredential(trust: serverTrust)
            completionHandler(.useCredential, credential)
        } else {
            // Pin mismatch — possible MITM attack
            // However, also log this for monitoring — it could be a
            // legitimate certificate rotation you missed
            logPinningFailure(
                host: challenge.protectionSpace.host,
                actualHash: spkiHash
            )
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }

    private func extractSPKIHash(from certificate: SecCertificate) -> String {
        guard let publicKey = SecCertificateCopyKey(certificate) else {
            return ""
        }

        var error: Unmanaged<CFError>?
        guard let publicKeyData = SecKeyCopyExternalRepresentation(
            publicKey, &error
        ) as Data? else {
            return ""
        }

        // Hash the public key data with SHA-256
        let hash = SHA256.hash(data: publicKeyData)
        return Data(hash).base64EncodedString()
    }

    private func logPinningFailure(host: String, actualHash: String) {
        // Best practice: report pin failures to your security monitoring
        // so you can distinguish attacks from legitimate rotation
        print("PIN FAILURE: host=\(host) hash=\(actualHash)")
    }
}
```

## Secure Storage: Keychain and Keystore

Sensitive data (tokens, credentials, encryption keys) must be stored in the platform's **hardware-backed secure enclave** rather than in SharedPreferences, UserDefaults, or the filesystem. The Keychain (iOS) and Keystore (Android) provide hardware-level protection that survives device compromise.

```kotlin
// SecureStorageManager.kt — Android Keystore-backed encrypted storage
// Best practice: use AndroidX Security library for simplified Keystore access
// Pitfall: Keystore entries are wiped on factory reset and when the user
// changes their lock screen — handle KeyPermanentlyInvalidatedException

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.util.Base64
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureStorageManager(private val context: Context) {
    companion object {
        private const val KEYSTORE_PROVIDER = "AndroidKeyStore"
        private const val MASTER_KEY_ALIAS = "app_master_key"
        private const val AES_GCM_TAG_LENGTH = 128
        private const val PREFS_NAME = "secure_storage_encrypted"
    }

    private val keyStore: KeyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply {
        load(null)
    }

    // Generate or retrieve the master encryption key from hardware Keystore
    // The key never leaves the secure hardware — only encryption/decryption
    // operations are performed inside the TEE (Trusted Execution Environment)
    // Therefore, even root access cannot extract the raw key material
    private fun getOrCreateMasterKey(): SecretKey {
        keyStore.getEntry(MASTER_KEY_ALIAS, null)?.let { entry ->
            return (entry as KeyStore.SecretKeyEntry).secretKey
        }

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, KEYSTORE_PROVIDER
        )
        keyGenerator.init(
            KeyGenParameterSpec.Builder(
                MASTER_KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                // Trade-off: requiring user authentication means the key
                // is unavailable for background operations
                // However, it provides the strongest protection
                .setUserAuthenticationRequired(false)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return keyGenerator.generateKey()
    }

    fun encryptAndStore(key: String, plaintext: String) {
        try {
            val secretKey = getOrCreateMasterKey()
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, secretKey)

            val iv = cipher.iv
            val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))

            // Store IV + ciphertext together
            // Common mistake: storing IV separately and losing the association
            val combined = iv + ciphertext
            val encoded = Base64.encodeToString(combined, Base64.NO_WRAP)

            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(key, encoded)
                .apply()
        } catch (e: KeyPermanentlyInvalidatedException) {
            // Key was invalidated (user changed lock screen)
            // Must regenerate key and re-encrypt all data
            keyStore.deleteEntry(MASTER_KEY_ALIAS)
            throw SecurityException("Master key invalidated, re-authentication required", e)
        }
    }

    fun decryptAndRetrieve(key: String): String? {
        val encoded = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(key, null) ?: return null

        return try {
            val combined = Base64.decode(encoded, Base64.NO_WRAP)
            val iv = combined.sliceArray(0 until 12) // GCM IV is 12 bytes
            val ciphertext = combined.sliceArray(12 until combined.size)

            val secretKey = getOrCreateMasterKey()
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, secretKey, GCMParameterSpec(AES_GCM_TAG_LENGTH, iv))
            String(cipher.doFinal(ciphertext), Charsets.UTF_8)
        } catch (e: Exception) {
            null
        }
    }

    fun deleteSecureData(key: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(key)
            .apply()
    }
}
```

## Root/Jailbreak Detection and Tamper Detection

Root/jailbreak detection is a **defense-in-depth** measure. It cannot prevent a determined attacker but raises the bar significantly. A **common mistake** is using a single detection method — sophisticated attackers use tools like Magisk (Android) or Liberty Lite (iOS) that hide root indicators.

```kotlin
// TamperDetectionManager.kt — multi-signal root and tamper detection
// Best practice: combine multiple signals and score them rather than
// using a single binary check that can be easily bypassed

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import java.io.File
import java.io.BufferedReader
import java.io.InputStreamReader

data class SecurityAssessment(
    val isRooted: Boolean,
    val isEmulator: Boolean,
    val isDebuggerAttached: Boolean,
    val isAppTampered: Boolean,
    val riskScore: Float, // 0.0 = safe, 1.0 = compromised
    val detectedIndicators: List<String>
)

class TamperDetectionManager(private val context: Context) {
    // Expected signing certificate hash — computed at build time
    // Pitfall: hardcoding this in a decompilable string makes it easy
    // to patch. Consider computing it from multiple obfuscated fragments
    private val expectedSigningHash: String = "expected_sha256_hash_here"

    fun assess(): SecurityAssessment {
        val indicators = mutableListOf<String>()
        var riskScore = 0f

        // Signal 1: Check for root management apps
        val rootApps = listOf(
            "com.topjohnwu.magisk",
            "eu.chainfire.supersu",
            "com.koushikdutta.superuser",
            "com.noshufou.android.su",
            "com.thirdparty.superuser"
        )
        for (pkg in rootApps) {
            try {
                context.packageManager.getPackageInfo(pkg, 0)
                indicators.add("root_app_$pkg")
                riskScore += 0.3f
            } catch (_: PackageManager.NameNotFoundException) {
                // Expected — app not installed
            }
        }

        // Signal 2: Check for su binary in common paths
        // However, Magisk can hide the su binary from standard checks
        // Therefore, also check using shell execution
        val suPaths = listOf(
            "/system/bin/su", "/system/xbin/su", "/sbin/su",
            "/data/local/xbin/su", "/data/local/bin/su",
            "/system/sd/xbin/su", "/system/app/Superuser.apk"
        )
        for (path in suPaths) {
            if (File(path).exists()) {
                indicators.add("su_binary_$path")
                riskScore += 0.2f
            }
        }

        // Signal 3: Check for test-keys build (custom ROM)
        val buildTags = Build.TAGS ?: ""
        if (buildTags.contains("test-keys")) {
            indicators.add("test_keys_build")
            riskScore += 0.15f
        }

        // Signal 4: Emulator detection
        val isEmulator = detectEmulator()
        if (isEmulator) {
            indicators.add("emulator_detected")
            riskScore += 0.1f
        }

        // Signal 5: Debugger detection
        val isDebugging = android.os.Debug.isDebuggerConnected() ||
            android.os.Debug.waitingForDebugger()
        if (isDebugging) {
            indicators.add("debugger_attached")
            riskScore += 0.4f
        }

        // Signal 6: App signature verification
        // Best practice: verify at runtime that the APK was signed with
        // your release key — catches repackaged/patched APKs
        val isTampered = !verifyAppSignature()
        if (isTampered) {
            indicators.add("signature_mismatch")
            riskScore += 0.5f
        }

        // Signal 7: Check for hooking frameworks
        val hookingApps = listOf(
            "de.robv.android.xposed.installer",
            "com.saurik.substrate",
            "io.github.vvb2060.mahoshojo" // LSPosed
        )
        for (pkg in hookingApps) {
            try {
                context.packageManager.getPackageInfo(pkg, 0)
                indicators.add("hooking_framework_$pkg")
                riskScore += 0.4f
            } catch (_: PackageManager.NameNotFoundException) {
                // pass
            }
        }

        return SecurityAssessment(
            isRooted = indicators.any { it.startsWith("root_app") || it.startsWith("su_binary") },
            isEmulator = isEmulator,
            isDebuggerAttached = isDebugging,
            isAppTampered = isTampered,
            riskScore = riskScore.coerceIn(0f, 1f),
            detectedIndicators = indicators
        )
    }

    private fun detectEmulator(): Boolean {
        // Trade-off: aggressive emulator detection may flag legitimate
        // devices with unusual configurations
        return (Build.FINGERPRINT.contains("generic")
            || Build.FINGERPRINT.contains("unknown")
            || Build.MODEL.contains("google_sdk")
            || Build.MODEL.contains("Emulator")
            || Build.MODEL.contains("Android SDK built for x86")
            || Build.MANUFACTURER.contains("Genymotion")
            || Build.HARDWARE.contains("goldfish")
            || Build.HARDWARE.contains("ranchu")
            || Build.PRODUCT.contains("sdk")
            || Build.PRODUCT.contains("vbox86p")
            || Build.BOARD.contains("unknown"))
    }

    @Suppress("DEPRECATION")
    private fun verifyAppSignature(): Boolean {
        return try {
            val packageInfo = context.packageManager.getPackageInfo(
                context.packageName,
                PackageManager.GET_SIGNATURES
            )
            val signatures = packageInfo.signatures ?: return false
            for (signature in signatures) {
                val md = java.security.MessageDigest.getInstance("SHA-256")
                val hash = md.digest(signature.toByteArray())
                val hashStr = hash.joinToString("") { "%02x".format(it) }
                if (hashStr == expectedSigningHash) return true
            }
            false
        } catch (e: Exception) {
            false
        }
    }
}
```

## Biometric Authentication Integration

**Biometric authentication** (fingerprint, Face ID) provides a seamless user experience while maintaining strong security. The key insight is that biometric authentication on modern devices does not send biometric data to the app — it unlocks a **Keystore key** that was previously bound to biometric enrollment. **Therefore**, even if the app is compromised, the attacker cannot extract biometric templates.

### Key Takeaways

- **Certificate pinning** prevents MITM attacks even when the device trusts a malicious CA; pin SPKI hashes (not full certificates) and always include a backup pin to survive certificate rotation without app updates
- **Hardware-backed Keystore/Keychain** ensures encryption keys never leave the secure enclave; the **trade-off** is that keys are invalidated when the user changes their lock screen, requiring re-authentication flows
- **Root/jailbreak detection** should use **multi-signal scoring** rather than single binary checks; a **common mistake** is relying only on su binary detection, which Magisk hides trivially
- **App signature verification** at runtime catches repackaged APKs with modified code; combine with SafetyNet/Play Integrity API for server-side attestation as a **best practice**
- **Biometric authentication** unlocks Keystore-bound keys rather than transmitting biometric data to the app — **therefore**, it provides non-extractable proof of user presence without exposing biometric templates
- **Pitfall**: storing secrets in BuildConfig, strings.xml, or hardcoded constants is easily defeated by `apktool` decompilation; use the Keystore for runtime secrets and server-side configuration for API keys
- **Defense in depth** is the guiding principle: no single protection is unbreakable, but layering certificate pinning + encrypted storage + tamper detection + obfuscation raises the cost of attack to the point where most adversaries move to easier targets
"""
    ),
]
