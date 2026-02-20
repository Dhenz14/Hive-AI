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
