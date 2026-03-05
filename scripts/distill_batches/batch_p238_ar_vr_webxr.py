"""AR/VR and WebXR — immersive web, spatial computing, 3D on the web."""

PAIRS = [
    (
        "emerging/webxr-basics",
        "Show WebXR API usage: creating immersive VR/AR sessions, rendering 3D scenes, and handling spatial input in the browser.",
        '''WebXR immersive experiences:

```javascript
// WebXR session setup and render loop
class WebXRApp {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl2", { xrCompatible: true });
    this.xrSession = null;
    this.xrRefSpace = null;
    this.scene = new Scene3D();
  }

  async checkSupport() {
    if (!navigator.xr) return { vr: false, ar: false };
    const [vr, ar] = await Promise.all([
      navigator.xr.isSessionSupported("immersive-vr"),
      navigator.xr.isSessionSupported("immersive-ar"),
    ]);
    return { vr, ar };
  }

  async startVR() {
    this.xrSession = await navigator.xr.requestSession("immersive-vr", {
      requiredFeatures: ["local-floor"],
      optionalFeatures: ["hand-tracking", "bounded-floor"],
    });

    this.xrSession.addEventListener("end", () => { this.xrSession = null; });

    // Create WebGL layer for XR rendering
    const glLayer = new XRWebGLLayer(this.xrSession, this.gl);
    await this.xrSession.updateRenderState({ baseLayer: glLayer });

    // Reference space for tracking
    this.xrRefSpace = await this.xrSession.requestReferenceSpace("local-floor");

    // Start render loop
    this.xrSession.requestAnimationFrame(this.onXRFrame.bind(this));
  }

  async startAR() {
    this.xrSession = await navigator.xr.requestSession("immersive-ar", {
      requiredFeatures: ["hit-test", "local-floor"],
      optionalFeatures: ["plane-detection", "anchors", "light-estimation"],
    });

    const glLayer = new XRWebGLLayer(this.xrSession, this.gl);
    await this.xrSession.updateRenderState({ baseLayer: glLayer });
    this.xrRefSpace = await this.xrSession.requestReferenceSpace("local-floor");
    this.xrSession.requestAnimationFrame(this.onXRFrame.bind(this));
  }

  onXRFrame(time, frame) {
    const session = frame.session;
    session.requestAnimationFrame(this.onXRFrame.bind(this));

    const pose = frame.getViewerPose(this.xrRefSpace);
    if (!pose) return;

    const glLayer = session.renderState.baseLayer;
    this.gl.bindFramebuffer(this.gl.FRAMEBUFFER, glLayer.framebuffer);

    // Render each eye/view
    for (const view of pose.views) {
      const viewport = glLayer.getViewport(view);
      this.gl.viewport(viewport.x, viewport.y, viewport.width, viewport.height);

      const projMatrix = view.projectionMatrix;
      const viewMatrix = view.transform.inverse.matrix;
      this.scene.render(projMatrix, viewMatrix);
    }

    // Process input sources (controllers, hands)
    for (const source of session.inputSources) {
      if (source.gamepad) {
        this.handleController(source, frame);
      }
      if (source.hand) {
        this.handleHandTracking(source, frame);
      }
    }
  }

  handleController(source, frame) {
    const gripPose = frame.getPose(source.gripSpace, this.xrRefSpace);
    if (gripPose) {
      const pos = gripPose.transform.position;
      const trigger = source.gamepad.buttons[0];
      if (trigger.pressed) {
        this.scene.interact(pos.x, pos.y, pos.z);
      }
    }
  }

  handleHandTracking(source, frame) {
    const hand = source.hand;
    const indexTip = hand.get("index-finger-tip");
    if (indexTip) {
      const pose = frame.getJointPose(indexTip, this.xrRefSpace);
      if (pose) {
        this.scene.updatePointer(pose.transform.position);
      }
    }
  }
}

// AR hit testing — place objects on real surfaces
class ARPlacement {
  constructor(session, refSpace) {
    this.session = session;
    this.refSpace = refSpace;
    this.hitTestSource = null;
  }

  async enableHitTest() {
    const viewerSpace = await this.session.requestReferenceSpace("viewer");
    this.hitTestSource = await this.session.requestHitTestSource({
      space: viewerSpace,
    });
  }

  getHitPose(frame) {
    if (!this.hitTestSource) return null;
    const results = frame.getHitTestResults(this.hitTestSource);
    if (results.length > 0) {
      return results[0].getPose(this.refSpace);
    }
    return null;
  }
}
```

Key patterns:
1. **Session types** — immersive-vr (headset), immersive-ar (passthrough), inline (browser)
2. **Reference spaces** — local-floor for room-scale; viewer for head-relative
3. **Stereo rendering** — iterate pose.views; each view = one eye with its own projection matrix
4. **Hit testing** — AR ray from device camera hits real-world surfaces for object placement
5. **Input abstraction** — controllers via gamepad API, hand tracking via joint poses'''
    ),
    (
        "emerging/three-js-xr",
        "Show Three.js WebXR integration: VR scene setup, interactive 3D objects, physics, and spatial audio.",
        '''Three.js WebXR with interactions:

```javascript
import * as THREE from "three";
import { VRButton } from "three/addons/webxr/VRButton.js";
import { XRControllerModelFactory } from "three/addons/webxr/XRControllerModelFactory.js";

class VRScene {
  constructor() {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.xr.enabled = true;
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.raycaster = new THREE.Raycaster();
    this.interactables = [];

    document.body.appendChild(this.renderer.domElement);
    document.body.appendChild(VRButton.createButton(this.renderer));

    this.setupScene();
    this.setupControllers();
    this.renderer.setAnimationLoop(this.render.bind(this));
  }

  setupScene() {
    // Lighting
    this.scene.add(new THREE.AmbientLight(0x404040, 2));
    const dirLight = new THREE.DirectionalLight(0xffffff, 3);
    dirLight.position.set(5, 10, 5);
    dirLight.castShadow = true;
    this.scene.add(dirLight);

    // Floor
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 20),
      new THREE.MeshStandardMaterial({ color: 0x808080 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);

    // Interactive objects
    for (let i = 0; i < 5; i++) {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(0.3, 0.3, 0.3),
        new THREE.MeshStandardMaterial({
          color: new THREE.Color().setHSL(i * 0.2, 0.8, 0.5),
        })
      );
      mesh.position.set(i * 0.5 - 1, 1.2, -1.5);
      mesh.castShadow = true;
      mesh.userData.interactive = true;
      this.scene.add(mesh);
      this.interactables.push(mesh);
    }

    // Spatial audio
    const listener = new THREE.AudioListener();
    this.camera.add(listener);
    const sound = new THREE.PositionalAudio(listener);
    const audioLoader = new THREE.AudioLoader();
    audioLoader.load("/audio/ambient.mp3", (buffer) => {
      sound.setBuffer(buffer);
      sound.setRefDistance(1);
      sound.setLoop(true);
      sound.play();
    });
    this.interactables[0].add(sound);
  }

  setupControllers() {
    const factory = new XRControllerModelFactory();

    for (let i = 0; i < 2; i++) {
      const controller = this.renderer.xr.getController(i);
      controller.addEventListener("selectstart", (e) => this.onSelect(e, controller));
      controller.addEventListener("squeezestart", (e) => this.onSqueeze(e, controller));
      this.scene.add(controller);

      // Visual controller model
      const grip = this.renderer.xr.getControllerGrip(i);
      grip.add(factory.createControllerModel(grip));
      this.scene.add(grip);

      // Pointer ray
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0, 0),
          new THREE.Vector3(0, 0, -3),
        ]),
        new THREE.LineBasicMaterial({ color: 0x00ffff })
      );
      controller.add(line);
    }
  }

  onSelect(event, controller) {
    const tempMatrix = new THREE.Matrix4();
    tempMatrix.identity().extractRotation(controller.matrixWorld);
    this.raycaster.ray.origin.setFromMatrixPosition(controller.matrixWorld);
    this.raycaster.ray.direction.set(0, 0, -1).applyMatrix4(tempMatrix);

    const intersects = this.raycaster.intersectObjects(this.interactables);
    if (intersects.length > 0) {
      const obj = intersects[0].object;
      obj.material.emissive.setHex(0x444444);
      // Grab object
      controller.attach(obj);
      controller.userData.grabbed = obj;
    }
  }

  onSqueeze(event, controller) {
    if (controller.userData.grabbed) {
      this.scene.attach(controller.userData.grabbed);
      controller.userData.grabbed = null;
    }
  }

  render(time, frame) {
    this.renderer.render(this.scene, this.camera);
  }
}
```

Key patterns:
1. **VRButton** — Three.js helper handles XR session lifecycle and enter/exit VR
2. **Controller models** — XRControllerModelFactory renders actual controller geometry
3. **Raycasting** — point controller, cast ray, detect intersections for interaction
4. **Grab mechanics** — attach/detach objects from controller for manipulation
5. **Positional audio** — THREE.PositionalAudio for spatial sound that changes with head position'''
    ),
    (
        "emerging/spatial-computing",
        "Show spatial computing concepts: world understanding, scene anchors, shared AR experiences, and persistent content.",
        '''Spatial computing patterns:

```typescript
// Spatial anchor management for persistent AR content
interface SpatialAnchor {
  id: string;
  position: { x: number; y: number; z: number };
  orientation: { x: number; y: number; z: number; w: number };
  createdAt: number;
  contentId: string;
  confidence: number;
}

class SpatialAnchorManager {
  private anchors: Map<string, SpatialAnchor> = new Map();
  private xrSession: XRSession;

  constructor(session: XRSession) {
    this.xrSession = session;
  }

  async createAnchor(
    hitResult: XRHitTestResult,
    refSpace: XRReferenceSpace,
    contentId: string
  ): Promise<SpatialAnchor> {
    const pose = hitResult.getPose(refSpace);
    if (!pose) throw new Error("No pose from hit test");

    // Create persistent XR anchor
    const xrAnchor = await hitResult.createAnchor();
    const anchor: SpatialAnchor = {
      id: crypto.randomUUID(),
      position: {
        x: pose.transform.position.x,
        y: pose.transform.position.y,
        z: pose.transform.position.z,
      },
      orientation: {
        x: pose.transform.orientation.x,
        y: pose.transform.orientation.y,
        z: pose.transform.orientation.z,
        w: pose.transform.orientation.w,
      },
      createdAt: Date.now(),
      contentId,
      confidence: 1.0,
    };

    this.anchors.set(anchor.id, anchor);
    return anchor;
  }

  async persistAnchors(): Promise<void> {
    // Save anchors for cross-session persistence
    const serialized = Array.from(this.anchors.values());
    localStorage.setItem("spatial-anchors", JSON.stringify(serialized));
  }

  async restoreAnchors(): Promise<SpatialAnchor[]> {
    const stored = localStorage.getItem("spatial-anchors");
    if (!stored) return [];
    const anchors: SpatialAnchor[] = JSON.parse(stored);
    anchors.forEach((a) => this.anchors.set(a.id, a));
    return anchors;
  }
}

// Shared AR experience via WebRTC + spatial sync
class SharedARSession {
  private peers: Map<string, RTCPeerConnection> = new Map();
  private sharedAnchors: Map<string, SpatialAnchor> = new Map();
  private ws: WebSocket;

  constructor(roomId: string, signalingUrl: string) {
    this.ws = new WebSocket(`${signalingUrl}/room/${roomId}`);
    this.ws.onmessage = (e) => this.handleSignaling(JSON.parse(e.data));
  }

  broadcastAnchor(anchor: SpatialAnchor) {
    this.ws.send(JSON.stringify({
      type: "anchor",
      data: anchor,
    }));
  }

  broadcastPose(pose: { position: any; orientation: any }) {
    this.ws.send(JSON.stringify({
      type: "pose",
      data: pose,
    }));
  }

  private handleSignaling(msg: any) {
    switch (msg.type) {
      case "anchor":
        this.sharedAnchors.set(msg.data.id, msg.data);
        this.onAnchorReceived?.(msg.data);
        break;
      case "pose":
        this.onPeerPoseUpdated?.(msg.peerId, msg.data);
        break;
    }
  }

  onAnchorReceived?: (anchor: SpatialAnchor) => void;
  onPeerPoseUpdated?: (peerId: string, pose: any) => void;
}
```

Key patterns:
1. **Spatial anchors** — pin virtual content to real-world locations; persist across sessions
2. **Hit test placement** — detect real surfaces, create anchors at intersection points
3. **Cross-session persistence** — save/restore anchor positions for returning users
4. **Shared AR** — sync anchors and poses via WebSocket/WebRTC for multi-user AR
5. **World understanding** — plane detection + hit testing builds map of physical space'''
    ),
]
"""
