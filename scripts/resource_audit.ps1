# HiveAI Resource Audit
Write-Host "============================================================"
Write-Host "  HiveAI Resource Audit"
Write-Host "============================================================"

Write-Host ""
Write-Host "=== GPU PROCESSES ==="
nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  No CUDA compute apps running"
}

Write-Host ""
Write-Host "=== GPU MEMORY ==="
nvidia-smi --query-gpu=memory.used,memory.free,memory.total,utilization.gpu --format=csv,noheader

Write-Host ""
Write-Host "=== TOP RAM CONSUMERS over 200MB ==="
Get-Process | Where-Object { $_.WorkingSet64 -gt 200MB } |
    Sort-Object WorkingSet64 -Descending |
    ForEach-Object {
        $ramMB = [math]::Round($_.WorkingSet64 / 1MB)
        $cpuS = [math]::Round($_.CPU, 1)
        Write-Host ("  {0,6} MB  {1,8} CPU_s  PID {2,6}  {3}" -f $ramMB, $cpuS, $_.Id, $_.ProcessName)
    }

Write-Host ""
Write-Host "=== PYTHON PROCESSES ==="
$pyProcs = Get-Process -Name python*, Python* -ErrorAction SilentlyContinue
if ($pyProcs) {
    foreach ($p in $pyProcs) {
        $ramMB = [math]::Round($p.WorkingSet64 / 1MB)
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($p.Id)" -ErrorAction SilentlyContinue).CommandLine
        if ($cmdline.Length -gt 120) { $cmdline = $cmdline.Substring(0, 120) + "..." }
        Write-Host "  PID $($p.Id): $ramMB MB - $cmdline"
    }
} else {
    Write-Host "  No Python processes running"
}

Write-Host ""
Write-Host "=== OLLAMA ==="
$ollama = Get-Process -Name ollama* -ErrorAction SilentlyContinue
if ($ollama) {
    foreach ($p in $ollama) {
        $ramMB = [math]::Round($p.WorkingSet64 / 1MB)
        Write-Host "  PID $($p.Id): $($p.ProcessName) - $ramMB MB RAM"
    }
} else {
    Write-Host "  Ollama not running"
}

Write-Host ""
Write-Host "=== LLAMA-SERVER ==="
$llama = Get-Process -Name llama-server*, llama_server* -ErrorAction SilentlyContinue
if ($llama) {
    foreach ($p in $llama) {
        $ramMB = [math]::Round($p.WorkingSet64 / 1MB)
        Write-Host "  PID $($p.Id): $($p.ProcessName) - $ramMB MB RAM"
    }
} else {
    Write-Host "  llama-server not running"
}

Write-Host ""
Write-Host "=== DOCKER ==="
$docker = Get-Process -Name Docker*, com.docker* -ErrorAction SilentlyContinue
if ($docker) {
    $totalMB = [math]::Round(($docker | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
    Write-Host "  $($docker.Count) Docker processes, $totalMB MB total RAM"
} else {
    Write-Host "  Docker not running"
}

Write-Host ""
Write-Host "=== WSL ==="
$wslProcs = Get-Process -Name wsl*, wslhost* -ErrorAction SilentlyContinue
if ($wslProcs) {
    $totalMB = [math]::Round(($wslProcs | Measure-Object WorkingSet64 -Sum).Sum / 1MB)
    Write-Host "  $($wslProcs.Count) WSL processes, $totalMB MB total RAM"
} else {
    Write-Host "  WSL not running"
}

Write-Host ""
Write-Host "=== NODE / FLASK ==="
$node = Get-Process -Name node* -ErrorAction SilentlyContinue
if ($node) {
    foreach ($p in $node) {
        $ramMB = [math]::Round($p.WorkingSet64 / 1MB)
        Write-Host "  PID $($p.Id): $($p.ProcessName) - $ramMB MB RAM"
    }
} else {
    Write-Host "  No Node.js processes"
}

Write-Host ""
Write-Host "=== SYSTEM SUMMARY ==="
$os = Get-CimInstance Win32_OperatingSystem
$totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
$usedGB = $totalGB - $freeGB
$pct = [math]::Round($usedGB / $totalGB * 100)
Write-Host "  RAM: $usedGB GB used / $totalGB GB total - ${pct}%"

$diskFree = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
Write-Host "  Disk: $diskFree GB free on C:"
Write-Host ""
