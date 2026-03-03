#!/bin/bash
df -h /opt/hiveai/project/models/
echo "---TRANSFORMERS---"
python3 -c "import transformers; print('transformers:', transformers.__version__)"
echo "---SHARDS---"
ls /opt/hiveai/project/models/qwen3.5-35b-a3b/*.safetensors 2>/dev/null | head -5
echo "COUNT:"
ls /opt/hiveai/project/models/qwen3.5-35b-a3b/*.safetensors 2>/dev/null | wc -l
echo "---SIZE---"
du -sh /opt/hiveai/project/models/qwen3.5-35b-a3b/
echo "---DISKFREE---"
df -h /opt/hiveai/project/ | tail -1
