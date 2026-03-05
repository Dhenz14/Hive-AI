"""WebRTC and media streaming — peer connections, signaling, and media handling."""

PAIRS = [
    (
        "frontend/webrtc-basics",
        "Show WebRTC patterns: peer connection setup, signaling, ICE candidates, and media streams in JavaScript.",
        '''WebRTC peer connection patterns:

```javascript
// --- Signaling server (simple WebSocket) ---

class SignalingClient {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.handlers = new Map();

    this.ws.onmessage = (event) => {
      const { type, payload, from } = JSON.parse(event.data);
      const handler = this.handlers.get(type);
      handler?.(payload, from);
    };
  }

  on(type, handler) {
    this.handlers.set(type, handler);
  }

  send(type, payload, to) {
    this.ws.send(JSON.stringify({ type, payload, to }));
  }

  async waitForOpen() {
    if (this.ws.readyState === WebSocket.OPEN) return;
    return new Promise((resolve) => {
      this.ws.addEventListener("open", resolve, { once: true });
    });
  }
}


// --- Peer connection manager ---

class PeerConnection {
  constructor(signaling, peerId) {
    this.signaling = signaling;
    this.peerId = peerId;
    this.streams = new Map();

    // STUN/TURN servers for NAT traversal
    this.pc = new RTCPeerConnection({
      iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        {
          urls: "turn:turn.example.com:3478",
          username: "user",
          credential: "pass",
        },
      ],
      iceCandidatePoolSize: 10,
    });

    this._setupHandlers();
  }

  _setupHandlers() {
    // Send ICE candidates to peer
    this.pc.onicecandidate = ({ candidate }) => {
      if (candidate) {
        this.signaling.send("ice-candidate", candidate, this.peerId);
      }
    };

    // Handle incoming tracks
    this.pc.ontrack = (event) => {
      const [stream] = event.streams;
      this.streams.set(stream.id, stream);
      this.onRemoteStream?.(stream);
    };

    // Connection state monitoring
    this.pc.onconnectionstatechange = () => {
      console.log("Connection state:", this.pc.connectionState);
      if (this.pc.connectionState === "failed") {
        this.pc.restartIce();
      }
    };

    // Handle signaling messages from peer
    this.signaling.on("offer", async (offer) => {
      await this.pc.setRemoteDescription(offer);
      const answer = await this.pc.createAnswer();
      await this.pc.setLocalDescription(answer);
      this.signaling.send("answer", answer, this.peerId);
    });

    this.signaling.on("answer", async (answer) => {
      await this.pc.setRemoteDescription(answer);
    });

    this.signaling.on("ice-candidate", async (candidate) => {
      await this.pc.addIceCandidate(candidate);
    });
  }

  // Add local media stream
  async addLocalStream(constraints = { video: true, audio: true }) {
    const stream = await navigator.mediaDevices.getUserMedia(constraints);

    for (const track of stream.getTracks()) {
      this.pc.addTrack(track, stream);
    }

    return stream;
  }

  // Add screen sharing
  async addScreenShare() {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: "always" },
      audio: false,
    });

    const [track] = stream.getVideoTracks();
    const sender = this.pc.addTrack(track, stream);

    // Handle user stopping share via browser UI
    track.onended = () => {
      this.pc.removeTrack(sender);
      this.onScreenShareEnded?.();
    };

    return stream;
  }

  // Create and send offer
  async createOffer() {
    const offer = await this.pc.createOffer({
      offerToReceiveAudio: true,
      offerToReceiveVideo: true,
    });
    await this.pc.setLocalDescription(offer);
    this.signaling.send("offer", offer, this.peerId);
  }

  // Data channel for non-media data
  createDataChannel(label, options = {}) {
    const channel = this.pc.createDataChannel(label, {
      ordered: true,
      ...options,
    });

    channel.onopen = () => console.log(`Channel "${label}" open`);
    channel.onclose = () => console.log(`Channel "${label}" closed`);

    return channel;
  }

  // Cleanup
  close() {
    this.pc.getSenders().forEach((sender) => {
      sender.track?.stop();
    });
    this.pc.close();
  }
}


// --- Media controls ---

function toggleTrack(stream, kind) {
  const track = stream.getTracks().find((t) => t.kind === kind);
  if (track) {
    track.enabled = !track.enabled;
    return track.enabled;
  }
  return false;
}

// toggleTrack(localStream, "audio");  // Mute/unmute
// toggleTrack(localStream, "video");  // Camera on/off


// --- Bandwidth adaptation ---

async function setMaxBitrate(pc, maxBitrate) {
  const sender = pc.getSenders().find((s) => s.track?.kind === "video");
  if (!sender) return;

  const params = sender.getParameters();
  if (!params.encodings?.length) {
    params.encodings = [{}];
  }
  params.encodings[0].maxBitrate = maxBitrate;
  await sender.setParameters(params);
}

// setMaxBitrate(pc, 500_000);  // 500 kbps for poor connections


// --- Connection quality stats ---

async function getConnectionStats(pc) {
  const stats = await pc.getStats();
  const result = {};

  stats.forEach((report) => {
    if (report.type === "inbound-rtp" && report.kind === "video") {
      result.framesPerSecond = report.framesPerSecond;
      result.packetsLost = report.packetsLost;
      result.bytesReceived = report.bytesReceived;
    }
    if (report.type === "candidate-pair" && report.state === "succeeded") {
      result.roundTripTime = report.currentRoundTripTime;
      result.availableBandwidth = report.availableOutgoingBitrate;
    }
  });

  return result;
}
```

WebRTC patterns:
1. **Signaling server** — WebSocket relay for offer/answer/ICE exchange (not part of WebRTC spec)
2. **ICE candidates** — NAT traversal via STUN (discover public IP) and TURN (relay fallback)
3. **`ontrack` event** — receive remote media streams for rendering in `<video>` elements
4. **Data channels** — low-latency peer-to-peer data (chat, file transfer, game state)
5. **`getStats()`** — monitor connection quality (RTT, packet loss, bandwidth)'''
    ),
    (
        "backend/video-streaming",
        "Show video streaming patterns: HLS/DASH adaptive streaming, FFmpeg transcoding, and chunked delivery.",
        '''Video streaming patterns:

```python
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
import asyncio
from typing import AsyncIterator


# --- FFmpeg transcoding to HLS ---

def transcode_to_hls(
    input_path: str,
    output_dir: str,
    variants: list[dict] | None = None,
) -> str:
    """Transcode video to HLS with adaptive bitrate variants."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if variants is None:
        variants = [
            {"name": "360p",  "height": 360,  "bitrate": "800k",  "audio": "96k"},
            {"name": "480p",  "height": 480,  "bitrate": "1400k", "audio": "128k"},
            {"name": "720p",  "height": 720,  "bitrate": "2800k", "audio": "128k"},
            {"name": "1080p", "height": 1080, "bitrate": "5000k", "audio": "192k"},
        ]

    # Generate each variant
    stream_maps = []
    filter_args = []
    output_args = []

    for i, v in enumerate(variants):
        filter_args.extend([
            "-map", "0:v:0", "-map", "0:a:0",
        ])
        output_args.extend([
            f"-c:v:{i}", "libx264",
            f"-b:v:{i}", v["bitrate"],
            f"-vf:{i}", f"scale=-2:{v['height']}",
            f"-c:a:{i}", "aac",
            f"-b:a:{i}", v["audio"],
        ])
        stream_maps.append(f"v:{i},a:{i},name:{v['name']}")

    cmd = [
        "ffmpeg", "-i", input_path,
        *filter_args,
        *output_args,
        "-preset", "fast",
        "-sc_threshold", "0",       # Consistent keyframes
        "-g", "48",                  # GOP size (2s at 24fps)
        "-keyint_min", "48",
        "-hls_time", "4",           # 4-second segments
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(output / "%v/segment_%03d.ts"),
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", " ".join(stream_maps),
        str(output / "%v/playlist.m3u8"),
    ]

    subprocess.run(cmd, check=True)
    return str(output / "master.m3u8")


# --- HLS master playlist format ---

"""
#EXTM3U
#EXT-X-VERSION:3

#EXT-X-STREAM-INF:BANDWIDTH=896000,RESOLUTION=640x360,NAME="360p"
360p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=1528000,RESOLUTION=854x480,NAME="480p"
480p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=2928000,RESOLUTION=1280x720,NAME="720p"
720p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=5192000,RESOLUTION=1920x1080,NAME="1080p"
1080p/playlist.m3u8
"""


# --- Streaming endpoint (range requests) ---

app = FastAPI()

@app.get("/stream/{video_id}/{path:path}")
async def stream_video(video_id: str, path: str, request: Request):
    """Serve HLS segments with range request support."""
    file_path = Path(f"/data/videos/{video_id}/{path}")

    if not file_path.exists():
        raise HTTPException(404, "Segment not found")

    # For .m3u8 playlists
    if path.endswith(".m3u8"):
        return FileResponse(
            file_path,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache"},
        )

    # For .ts segments — support range requests
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        start, end = parse_range(range_header, file_size)
        content_length = end - start + 1

        async def iter_file():
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = await f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp2t",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=31536000",
            },
        )

    return FileResponse(
        file_path,
        media_type="video/mp2t",
        headers={"Cache-Control": "public, max-age=31536000"},
    )


def parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse HTTP Range header."""
    _, range_spec = range_header.split("=")
    start_str, end_str = range_spec.split("-")
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    return start, min(end, file_size - 1)


# --- Thumbnail generation ---

def generate_thumbnails(
    video_path: str,
    output_dir: str,
    interval: int = 10,
) -> list[str]:
    """Generate thumbnails every N seconds."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval},scale=320:-1",
        "-q:v", "5",
        str(output / "thumb_%04d.jpg"),
    ]
    subprocess.run(cmd, check=True)

    return sorted(str(p) for p in output.glob("thumb_*.jpg"))
```

Video streaming patterns:
1. **HLS adaptive bitrate** — multiple quality variants with automatic switching
2. **FFmpeg transcoding** — consistent GOP size and keyframes for clean segment boundaries
3. **Range requests** — `206 Partial Content` for seeking without downloading entire file
4. **Segment caching** — `.ts` segments are immutable, cache forever; `.m3u8` playlists are `no-cache`
5. **Thumbnail sprites** — FFmpeg `fps=1/N` filter generates preview images at intervals'''
    ),
]
"""
