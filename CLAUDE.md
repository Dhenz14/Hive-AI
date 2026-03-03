# HiveAI Project Rules

## Disk Hygiene (CRITICAL)

### Never use Downloads folder
- **NEVER** reference `C:\Users\theyc\Downloads` or `/mnt/c/Users/theyc/Downloads` in any source file, config, or script
- Downloads is for temporary files and installers — NOT project data
- All project data lives under `c:\Users\theyc\HiveAi\Hive-AI\` or WSL `/opt/hiveai/project/`

### Model file management
- **Windows**: Only keep `models/qwen3.5-35b-a3b/Qwen3.5-35B-A3B-Q4_K_M.gguf` (the active GGUF for llama-server)
- **WSL**: Only keep `qwen3.5-35b-a3b` (original) and the current best rebuild in `/opt/hiveai/project/models/`
- **Delete failed experiments immediately** — do not leave broken/superseded model directories lying around
- Never save duplicate GGUFs (BF16, -fixed, -clean variants). One working GGUF per quant type is enough
- Never keep the raw HF safetensors on Windows (`hf/` subdirectory) — originals live in WSL

### WSL2 vhdx management
- WSL2 ext4.vhdx **only grows, never shrinks automatically**
- After deleting large files in WSL, ALWAYS compact: `wsl --shutdown && diskpart /s scripts/compact_wsl.txt`
- Run `python scripts/disk_hygiene.py` periodically to check for bloat

### Caches to clear periodically
- `~/.cache/huggingface/hub/` — re-downloadable model cache
- `~/AppData/Local/pip/cache/` — pip package cache
- `~/AppData/Local/Temp/wsl-crashes/` — WSL crash dumps from segfaults
