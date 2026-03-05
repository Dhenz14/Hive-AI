"""Python web — middleware patterns, background tasks, and file uploads."""

PAIRS = [
    (
        "api/fastapi-middleware",
        "Show FastAPI middleware patterns: request ID tracking, timing, compression, and middleware ordering.",
        '''FastAPI middleware patterns:

```python
import uuid
import time
import gzip
import logging
from contextvars import ContextVar
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# ContextVar for request-scoped data
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

app = FastAPI()


# --- Request ID middleware ---

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to every request for tracing."""

    async def dispatch(self, request: Request, call_next):
        # Use existing header or generate new
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# --- Timing middleware ---

class TimingMiddleware(BaseHTTPMiddleware):
    """Add server timing header."""

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        response.headers["Server-Timing"] = f"total;dur={duration*1000:.1f}"
        response.headers["X-Response-Time"] = f"{duration*1000:.1f}ms"
        return response


# --- Request logging middleware ---

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        logger.info(
            "%s %s %d %.3fs [%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration,
            request_id_var.get(""),
        )
        return response


# --- CORS with more control than CORSMiddleware ---

class StrictCORSMiddleware(BaseHTTPMiddleware):
    """CORS with path-based origin rules."""

    RULES = {
        "/api/public/": {"origins": ["*"], "methods": ["GET"]},
        "/api/": {
            "origins": ["https://myapp.com", "https://admin.myapp.com"],
            "methods": ["GET", "POST", "PUT", "DELETE"],
        },
    }

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")
        path = request.url.path

        # Find matching rule
        rule = None
        for prefix, r in sorted(self.RULES.items(), key=lambda x: -len(x[0])):
            if path.startswith(prefix):
                rule = r
                break

        if not rule:
            return await call_next(request)

        # Check origin
        allowed = "*" in rule["origins"] or origin in rule["origins"]
        if not allowed:
            return await call_next(request)

        # Handle preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin if origin in rule["origins"] else "*",
                    "Access-Control-Allow-Methods": ", ".join(rule["methods"]),
                    "Access-Control-Allow-Headers": "Authorization, Content-Type",
                    "Access-Control-Max-Age": "3600",
                },
            )

        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = (
            origin if origin in rule["origins"] else "*"
        )
        return response


# --- Pure ASGI middleware (more performant) ---

class ASGITimingMiddleware:
    """Pure ASGI middleware — avoids BaseHTTPMiddleware overhead."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()

        async def send_with_timing(message):
            if message["type"] == "http.response.start":
                duration = time.monotonic() - start
                headers = list(message.get("headers", []))
                headers.append((
                    b"server-timing",
                    f"total;dur={duration*1000:.1f}".encode(),
                ))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_timing)


# --- Middleware ordering (outermost runs first) ---

# Order matters! Add in reverse order of execution:
app.add_middleware(LoggingMiddleware)       # 3rd: log after everything
app.add_middleware(TimingMiddleware)         # 2nd: time the request
app.add_middleware(RequestIDMiddleware)      # 1st: assign request ID
```

Middleware patterns:
1. **Request ID** — `X-Request-ID` header for distributed tracing correlation
2. **`ContextVar`** — thread-safe request-scoped data (available in loggers, handlers)
3. **`Server-Timing`** — standard header for DevTools performance analysis
4. **Pure ASGI** — `__call__(scope, receive, send)` avoids `BaseHTTPMiddleware` overhead
5. **Ordering** — add in reverse: last `add_middleware` call runs first'''
    ),
    (
        "api/file-uploads",
        "Show file upload patterns: streaming uploads, multipart handling, S3 storage, and image processing.",
        '''File upload patterns:

```python
import uuid
import hashlib
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import aiofiles
import boto3
from PIL import Image
from io import BytesIO

app = FastAPI()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


# --- Basic file upload with validation ---

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Validate content type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type {file.content_type} not allowed")

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024}MB)")

    # Generate safe filename
    ext = Path(file.filename or "file").suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"

    # Save to disk
    file_path = UPLOAD_DIR / safe_name
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Compute hash for dedup
    file_hash = hashlib.sha256(content).hexdigest()

    return {
        "filename": safe_name,
        "original_name": file.filename,
        "size": len(content),
        "content_type": file.content_type,
        "hash": file_hash,
    }


# --- Streaming upload (for large files) ---

@app.post("/upload/stream")
async def upload_stream(file: UploadFile = File(...)):
    safe_name = f"{uuid.uuid4().hex}{Path(file.filename or '').suffix}"
    file_path = UPLOAD_DIR / safe_name
    total_size = 0

    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(64 * 1024):  # 64KB chunks
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                await f.close()
                file_path.unlink()
                raise HTTPException(400, "File too large")
            await f.write(chunk)

    return {"filename": safe_name, "size": total_size}


# --- Upload to S3 ---

class S3Storage:
    def __init__(self, bucket: str, region: str = "us-east-1"):
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    async def upload(self, content: bytes, key: str, content_type: str) -> str:
        """Upload to S3 and return public URL."""
        import asyncio
        await asyncio.to_thread(
            self.s3.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate pre-signed URL for direct upload."""
        return self.s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def generate_download_url(self, key: str, expires_in: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


storage = S3Storage("my-uploads-bucket")


# --- Image processing on upload ---

class ImageProcessor:
    """Process uploaded images: resize, thumbnail, optimize."""

    SIZES = {
        "thumbnail": (150, 150),
        "small": (300, 300),
        "medium": (800, 800),
        "large": (1920, 1920),
    }

    @staticmethod
    def process(content: bytes, max_size: tuple[int, int] = (1920, 1920)) -> bytes:
        img = Image.open(BytesIO(content))

        # Convert RGBA to RGB (for JPEG)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg

        # Resize maintaining aspect ratio
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Auto-orient based on EXIF
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)

        output = BytesIO()
        img.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()

    @classmethod
    def generate_variants(cls, content: bytes) -> dict[str, bytes]:
        variants = {}
        for name, size in cls.SIZES.items():
            variants[name] = cls.process(content, max_size=size)
        return variants


@app.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Must be an image file")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large")

    base_name = uuid.uuid4().hex

    # Process main image
    processed = ImageProcessor.process(content)
    url = await storage.upload(processed, f"images/{base_name}.jpg", "image/jpeg")

    # Generate variants in background
    if background_tasks:
        background_tasks.add_task(
            generate_image_variants, content, base_name,
        )

    return {"url": url, "filename": f"{base_name}.jpg"}


async def generate_image_variants(content: bytes, base_name: str):
    variants = ImageProcessor.generate_variants(content)
    for variant_name, variant_bytes in variants.items():
        key = f"images/{base_name}_{variant_name}.jpg"
        await storage.upload(variant_bytes, key, "image/jpeg")
```

File upload patterns:
1. **Content-type validation** — whitelist allowed MIME types, check magic bytes
2. **Streaming upload** — `file.read(64KB)` chunks prevent loading entire file into memory
3. **UUID filenames** — never use user-provided names for storage (prevent path traversal)
4. **Pre-signed URLs** — S3 direct upload bypasses your server for large files
5. **Background image processing** — `BackgroundTasks` generates thumbnails after response'''
    ),
]
