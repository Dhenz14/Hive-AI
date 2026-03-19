import os
import multiprocessing
import logging

logger = logging.getLogger(__name__)

def detect_hardware():
    """Detect available hardware resources."""
    cpus = multiprocessing.cpu_count()
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
    except ImportError:
        ram_gb = 2.0
    return {"cpus": cpus, "ram_gb": round(ram_gb, 1)}


def detect_gpu() -> list[dict]:
    """Detect NVIDIA GPUs via nvidia-smi.

    Returns a list of dicts with keys: uuid, name, vram_gb, driver_version.
    Returns empty list if nvidia-smi is not available.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=gpu_uuid,name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpus.append({
                    "uuid": parts[0],              # e.g., "GPU-e57e219b-d0ad-..."
                    "name": parts[1],               # e.g., "NVIDIA GeForce RTX 4070 Ti SUPER"
                    "vram_gb": round(float(parts[2]) / 1024, 1),  # MiB → GB
                    "driver_version": parts[3],
                })
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as e:
        logger.debug(f"GPU detection failed: {e}")
        return []


def get_hardware_profile():
    """Get hardware profile: low, medium, high, or custom."""
    profile = os.environ.get("HARDWARE_PROFILE", "auto").lower()
    hw = detect_hardware()
    
    if profile == "auto":
        if hw["ram_gb"] >= 12 and hw["cpus"] >= 6:
            profile = "high"
        elif hw["ram_gb"] >= 6 and hw["cpus"] >= 3:
            profile = "medium"
        else:
            profile = "low"
    
    profiles = {
        "low": {
            "crawl_workers": 2,
            "llm_workers": 1,
            "embedding_batch_size": 8,
            "chunk_batch_size": 5,
            "max_crawl_pages": 5,
            "db_pool_size": 3,
        },
        "medium": {
            "crawl_workers": 4,
            "llm_workers": 2,
            "embedding_batch_size": 16,
            "chunk_batch_size": 10,
            "max_crawl_pages": 10,
            "db_pool_size": 5,
        },
        "high": {
            "crawl_workers": 8,
            "llm_workers": 4,
            "embedding_batch_size": 32,
            "chunk_batch_size": 20,
            "max_crawl_pages": 20,
            "db_pool_size": 8,
        },
    }
    
    settings = profiles.get(profile, profiles["medium"])
    
    settings["crawl_workers"] = int(os.environ.get("CRAWL_WORKERS", str(settings["crawl_workers"])))
    settings["llm_workers"] = int(os.environ.get("LLM_WORKERS", str(settings["llm_workers"])))
    settings["embedding_batch_size"] = int(os.environ.get("EMBEDDING_BATCH_SIZE", str(settings["embedding_batch_size"])))
    settings["max_crawl_pages"] = int(os.environ.get("MAX_CRAWL_PAGES", str(settings["max_crawl_pages"])))
    settings["db_pool_size"] = int(os.environ.get("DB_POOL_SIZE", str(settings["db_pool_size"])))
    
    settings["profile"] = profile
    settings["detected"] = hw
    
    logger.info(f"Hardware profile: {profile} (CPUs={hw['cpus']}, RAM={hw['ram_gb']}GB)")
    
    return settings
