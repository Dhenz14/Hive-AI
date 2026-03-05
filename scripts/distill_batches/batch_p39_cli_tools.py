"""CLI tools — building command-line applications with Python, argument parsing, and TUI patterns."""

PAIRS = [
    (
        "python/cli-development",
        "Show Python CLI development patterns: click/typer, rich output, progress bars, configuration, and packaging CLI tools.",
        '''Production CLI development with Typer and Rich:

```python
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.syntax import Syntax
from rich import print as rprint
from pathlib import Path
from typing import Optional, Annotated
from enum import Enum
import json
import sys

app = typer.Typer(
    name="myctl",
    help="My application CLI tool",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

# --- Subcommand groups ---

db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")

deploy_app = typer.Typer(help="Deployment operations")
app.add_typer(deploy_app, name="deploy")


# --- Output formatting ---

class OutputFormat(str, Enum):
    table = "table"
    json = "json"
    csv = "csv"


def format_output(data: list[dict], format: OutputFormat, title: str = ""):
    if format == OutputFormat.json:
        console.print_json(json.dumps(data, default=str))
    elif format == OutputFormat.csv:
        if data:
            print(",".join(data[0].keys()))
            for row in data:
                print(",".join(str(v) for v in row.values()))
    else:
        table = Table(title=title, show_header=True)
        if data:
            for key in data[0].keys():
                table.add_column(key, style="cyan")
            for row in data:
                table.add_row(*[str(v) for v in row.values()])
        console.print(table)


# --- Commands ---

@app.command()
def status(
    format: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.table,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
):
    """Show application status."""
    services = [
        {"name": "api", "status": "running", "version": "v1.2.0", "uptime": "3d 4h"},
        {"name": "worker", "status": "running", "version": "v1.2.0", "uptime": "3d 4h"},
        {"name": "scheduler", "status": "stopped", "version": "v1.1.0", "uptime": "-"},
    ]

    if format == OutputFormat.table:
        table = Table(title="Service Status")
        table.add_column("Service", style="cyan")
        table.add_column("Status")
        table.add_column("Version", style="dim")
        table.add_column("Uptime", style="dim")

        for s in services:
            status_style = "green" if s["status"] == "running" else "red"
            table.add_row(
                s["name"],
                f"[{status_style}]{s['status']}[/{status_style}]",
                s["version"],
                s["uptime"],
            )
        console.print(table)
    else:
        format_output(services, format)


@db_app.command("migrate")
def db_migrate(
    target: Annotated[Optional[str], typer.Argument()] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    """Run database migrations."""
    if dry_run:
        console.print("[yellow]Dry run mode — no changes will be applied[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running migrations...", total=None)

        migrations = ["001_create_users", "002_add_orders", "003_add_indexes"]
        for migration in migrations:
            progress.update(task, description=f"Applying {migration}...")
            import time; time.sleep(0.5)  # Simulated work

        progress.update(task, description="Migrations complete!")

    console.print(f"[green]Applied {len(migrations)} migrations[/green]")


@deploy_app.command("create")
def deploy_create(
    env: Annotated[str, typer.Argument(help="Target environment")],
    version: Annotated[str, typer.Option("--version", "-v")] = "latest",
    force: Annotated[bool, typer.Option("--force")] = False,
):
    """Create a new deployment."""
    if env == "production" and not force:
        confirm = typer.confirm(
            f"Deploy {version} to PRODUCTION?", abort=True
        )

    console.print(Panel(
        f"[bold]Deploying {version} to {env}[/bold]\\n\\n"
        f"Environment: {env}\\n"
        f"Version: {version}\\n"
        f"Strategy: rolling update",
        title="Deployment",
        border_style="blue",
    ))

    with Progress(console=console) as progress:
        build = progress.add_task("Building image...", total=100)
        push = progress.add_task("Pushing to registry...", total=100)
        deploy = progress.add_task("Deploying pods...", total=100)

        for i in range(100):
            import time; time.sleep(0.02)
            progress.update(build, advance=1)
        for i in range(100):
            import time; time.sleep(0.01)
            progress.update(push, advance=1)
        for i in range(100):
            import time; time.sleep(0.03)
            progress.update(deploy, advance=1)

    console.print("[green]Deployment successful![/green]")


@app.command()
def config(
    key: Annotated[Optional[str], typer.Argument()] = None,
    set_value: Annotated[Optional[str], typer.Option("--set")] = None,
    config_file: Annotated[Path, typer.Option("--config")] = Path("~/.myctl.json"),
):
    """View or set configuration."""
    config_path = config_file.expanduser()

    if config_path.exists():
        cfg = json.loads(config_path.read_text())
    else:
        cfg = {}

    if set_value and key:
        cfg[key] = set_value
        config_path.write_text(json.dumps(cfg, indent=2))
        console.print(f"Set {key} = {set_value}")
    elif key:
        value = cfg.get(key)
        if value is None:
            console.print(f"[red]Key not found: {key}[/red]")
            raise typer.Exit(1)
        console.print(f"{key} = {value}")
    else:
        console.print_json(json.dumps(cfg, indent=2))


# --- Error handling ---

@app.callback()
def main(
    debug: Annotated[bool, typer.Option("--debug")] = False,
):
    """My application management CLI."""
    if debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)


if __name__ == "__main__":
    app()
```

```toml
# pyproject.toml entry point
[project.scripts]
myctl = "myctl.cli:app"
```

CLI patterns:
1. **Typer** — type-hinted arguments auto-generate help and validation
2. **Rich output** — tables, progress bars, panels for readable output
3. **Subcommands** — `app.add_typer()` for organized command groups
4. **Output formats** — support table/JSON/CSV for human and machine consumers
5. **Confirmations** — prompt before destructive actions (especially production)'''
    ),
    (
        "python/file-processing",
        "Show Python file processing patterns: streaming large files, CSV/JSON processing, file watching, and atomic writes.",
        '''File processing patterns for production:

```python
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Iterator, Callable
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib

# --- Streaming large files (memory-efficient) ---

def stream_lines(filepath: Path, encoding: str = "utf-8") -> Iterator[str]:
    """Stream file line by line without loading into memory."""
    with open(filepath, "r", encoding=encoding) as f:
        for line in f:
            yield line.rstrip("\\n")

def stream_csv(filepath: Path, batch_size: int = 1000) -> Iterator[list[dict]]:
    """Stream CSV in batches."""
    batch = []
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            batch.append(row)
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch

def stream_jsonl(filepath: Path) -> Iterator[dict]:
    """Stream JSON Lines (one JSON object per line)."""
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {line_num}: {e}")

def count_lines(filepath: Path) -> int:
    """Efficiently count lines in large file."""
    count = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            count += chunk.count(b"\\n")
    return count


# --- Atomic file writes ---

@contextmanager
def atomic_write(filepath: Path, mode: str = "w", **kwargs):
    """Write to file atomically — prevents partial writes on crash."""
    filepath = Path(filepath)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=filepath.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, mode, **kwargs) as f:
            yield f
        # Atomic rename (on POSIX systems)
        os.replace(tmp_path, filepath)
    except Exception:
        os.unlink(tmp_path)
        raise

# Usage:
# with atomic_write(Path("output.json")) as f:
#     json.dump(data, f)
# If crash occurs during write, original file is untouched


# --- File transformation pipeline ---

@dataclass
class FileProcessor:
    """Composable file processing pipeline."""
    transforms: list[Callable] = None

    def __post_init__(self):
        self.transforms = self.transforms or []

    def pipe(self, fn: Callable) -> "FileProcessor":
        return FileProcessor(self.transforms + [fn])

    def process(self, input_path: Path, output_path: Path,
                batch_size: int = 1000):
        """Process file through pipeline in batches."""
        processed = 0

        with atomic_write(output_path) as out:
            for batch in stream_csv(input_path, batch_size):
                # Apply transforms
                for transform in self.transforms:
                    batch = transform(batch)

                # Write batch
                if processed == 0 and batch:
                    writer = csv.DictWriter(out, fieldnames=batch[0].keys())
                    writer.writeheader()

                for row in batch:
                    writer.writerow(row)
                    processed += 1

        return processed

# Usage:
# pipeline = (FileProcessor()
#     .pipe(lambda batch: [r for r in batch if r["status"] == "active"])
#     .pipe(lambda batch: [{**r, "email": r["email"].lower()} for r in batch])
#     .pipe(lambda batch: [{k: v for k, v in r.items() if k != "password"} for r in batch])
# )
# count = pipeline.process(Path("input.csv"), Path("output.csv"))


# --- File integrity ---

def file_checksum(filepath: Path, algorithm: str = "sha256") -> str:
    """Calculate file checksum without loading entire file."""
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def verify_checksum(filepath: Path, expected: str,
                    algorithm: str = "sha256") -> bool:
    return file_checksum(filepath, algorithm) == expected


# --- Write JSONL (for streaming output) ---

class JSONLWriter:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._file = None

    def __enter__(self):
        self._file = open(self.filepath, "w", encoding="utf-8")
        return self

    def __exit__(self, *args):
        self._file.close()

    def write(self, obj: dict):
        self._file.write(json.dumps(obj, default=str) + "\\n")

    def write_batch(self, objects: list[dict]):
        for obj in objects:
            self.write(obj)

# Usage:
# with JSONLWriter(Path("output.jsonl")) as writer:
#     for batch in stream_csv(Path("input.csv")):
#         for row in batch:
#             writer.write(transform(row))
```

Patterns:
1. **Streaming** — generator-based processing for files larger than memory
2. **Atomic writes** — temp file + rename prevents corruption
3. **Batch processing** — process in chunks for memory efficiency
4. **Pipeline composition** — chain transforms with `.pipe()`
5. **JSONL format** — one JSON per line for streamable structured data'''
    ),
    (
        "python/image-processing",
        "Show Python image processing patterns: Pillow operations, thumbnails, format conversion, watermarking, and EXIF handling.",
        '''Image processing with Pillow:

```python
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ExifTags
from pathlib import Path
from io import BytesIO
from typing import Optional
from dataclasses import dataclass

@dataclass
class ImageSize:
    width: int
    height: int

    def fits_within(self, max_width: int, max_height: int) -> bool:
        return self.width <= max_width and self.height <= max_height

    def scale_to_fit(self, max_width: int, max_height: int) -> "ImageSize":
        ratio = min(max_width / self.width, max_height / self.height)
        return ImageSize(
            width=int(self.width * ratio),
            height=int(self.height * ratio),
        )


class ImageProcessor:
    """Image processing with fluent API."""

    def __init__(self, image: Image.Image):
        self.image = image

    @classmethod
    def from_path(cls, path: Path) -> "ImageProcessor":
        return cls(Image.open(path))

    @classmethod
    def from_bytes(cls, data: bytes) -> "ImageProcessor":
        return cls(Image.open(BytesIO(data)))

    # --- Resize ---

    def thumbnail(self, max_width: int, max_height: int) -> "ImageProcessor":
        """Resize to fit within bounds, maintaining aspect ratio."""
        img = self.image.copy()
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        return ImageProcessor(img)

    def resize_exact(self, width: int, height: int) -> "ImageProcessor":
        """Resize to exact dimensions (may distort)."""
        return ImageProcessor(
            self.image.resize((width, height), Image.LANCZOS)
        )

    def crop_center(self, width: int, height: int) -> "ImageProcessor":
        """Crop from center to exact dimensions."""
        img = self.image
        left = (img.width - width) // 2
        top = (img.height - height) // 2
        return ImageProcessor(
            img.crop((left, top, left + width, top + height))
        )

    def cover(self, width: int, height: int) -> "ImageProcessor":
        """Resize to cover area, then crop center (like CSS object-fit: cover)."""
        img = self.image
        ratio = max(width / img.width, height / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        resized = img.resize(new_size, Image.LANCZOS)
        return ImageProcessor(resized).crop_center(width, height)

    # --- Transforms ---

    def rotate_by_exif(self) -> "ImageProcessor":
        """Auto-rotate based on EXIF orientation."""
        from PIL import ImageOps
        return ImageProcessor(ImageOps.exif_transpose(self.image))

    def grayscale(self) -> "ImageProcessor":
        return ImageProcessor(self.image.convert("L").convert("RGB"))

    def blur(self, radius: int = 5) -> "ImageProcessor":
        return ImageProcessor(
            self.image.filter(ImageFilter.GaussianBlur(radius))
        )

    def sharpen(self) -> "ImageProcessor":
        return ImageProcessor(
            self.image.filter(ImageFilter.SHARPEN)
        )

    # --- Watermark ---

    def watermark(self, text: str, opacity: int = 128,
                  font_size: int = 36) -> "ImageProcessor":
        """Add diagonal text watermark."""
        img = self.image.copy().convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        # Tile watermark diagonally
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        for y in range(0, img.height, text_h * 3):
            for x in range(0, img.width, text_w + 50):
                draw.text(
                    (x, y), text, fill=(255, 255, 255, opacity), font=font
                )

        watermarked = Image.alpha_composite(img, overlay)
        return ImageProcessor(watermarked.convert("RGB"))

    # --- EXIF metadata ---

    def get_exif(self) -> dict:
        """Extract EXIF metadata."""
        exif_data = self.image.getexif()
        if not exif_data:
            return {}

        result = {}
        for tag_id, value in exif_data.items():
            tag_name = ExifTags.TAGS.get(tag_id, tag_id)
            result[tag_name] = str(value)
        return result

    def strip_exif(self) -> "ImageProcessor":
        """Remove all EXIF data (privacy)."""
        data = BytesIO()
        self.image.save(data, format=self.image.format or "JPEG")
        data.seek(0)
        clean = Image.open(data)
        return ImageProcessor(clean)

    # --- Output ---

    def save(self, path: Path, quality: int = 85, optimize: bool = True):
        """Save with optimization."""
        fmt = path.suffix.lower().lstrip(".")
        fmt_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
        save_format = fmt_map.get(fmt, "JPEG")

        kwargs = {"optimize": optimize}
        if save_format in ("JPEG", "WEBP"):
            kwargs["quality"] = quality
        if save_format == "PNG":
            kwargs["compress_level"] = 6

        self.image.save(path, format=save_format, **kwargs)

    def to_bytes(self, format: str = "JPEG", quality: int = 85) -> bytes:
        buf = BytesIO()
        self.image.save(buf, format=format, quality=quality, optimize=True)
        return buf.getvalue()

    @property
    def size(self) -> ImageSize:
        return ImageSize(self.image.width, self.image.height)


# --- Generate responsive image set ---

def generate_responsive_images(
    source: Path, output_dir: Path, sizes: list[int] = None,
):
    """Generate multiple sizes for responsive <picture> element."""
    sizes = sizes or [320, 640, 960, 1280, 1920]
    output_dir.mkdir(parents=True, exist_ok=True)

    processor = ImageProcessor.from_path(source).rotate_by_exif()
    stem = source.stem
    results = []

    for width in sizes:
        if width > processor.size.width:
            continue

        ratio = width / processor.size.width
        height = int(processor.size.height * ratio)

        # Generate JPEG and WebP
        for fmt, ext in [("JPEG", "jpg"), ("WEBP", "webp")]:
            output = output_dir / f"{stem}-{width}w.{ext}"
            processor.thumbnail(width, height).save(output)
            results.append({"width": width, "format": fmt, "path": str(output)})

    return results
```

Patterns:
1. **Fluent API** — chain operations for readable pipelines
2. **EXIF handling** — auto-rotate, extract metadata, strip for privacy
3. **Cover resize** — resize + crop for exact dimensions (social media)
4. **Responsive images** — generate multiple sizes for `<picture>` element
5. **Format conversion** — always offer WebP alongside JPEG for smaller sizes'''
    ),
]
"""
