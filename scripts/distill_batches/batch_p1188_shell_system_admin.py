"""
Shell/CLI training pairs - System admin: processes, disk, networking, cron, systemd.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''My server is running slow. How do I find which processes are consuming the most CPU and memory, and what's eating disk space?''',
        "output": r'''<think>
The user wants a quick triage of a slow server. I should cover:
1. CPU/memory -- top/htop, ps aux sorted by CPU and memory
2. Disk space -- df for filesystem usage, du for directory breakdown
3. Maybe also check load average and IO wait

I will give practical commands they can run immediately, not just theory. For disk, I should show du with a depth limit so it does not take forever on large filesystems.
</think>

Quick triage commands:

```bash
# System overview -- load average, uptime
uptime
# output: load average: 4.52, 3.21, 2.80 (1, 5, 15 min)
# If load > number of CPU cores, the system is overloaded

# Top 10 CPU consumers
ps aux --sort=-%cpu | head -11

# Top 10 memory consumers
ps aux --sort=-%mem | head -11

# Interactive view (press q to quit)
top -bn1 | head -20

# Check for IO wait (wa column -- high value means disk bottleneck)
iostat -x 1 3
```

Disk space investigation:

```bash
# Filesystem usage overview
df -h

# Find largest directories under root (depth 1)
du -h --max-depth=1 / 2>/dev/null | sort -rh | head -20

# Drill into the biggest directory
du -h --max-depth=1 /var | sort -rh | head -10

# Find files over 500MB
find / -type f -size +500M -exec ls -lh {} \; 2>/dev/null

# Check for deleted files still held open (common disk space leak)
lsof +L1 2>/dev/null | awk '{print $7, $1, $NF}' | sort -rn | head
```

Quick memory check:

```bash
# Free memory in human-readable format
free -h

# If swap is heavily used, the system is memory-starved
```'''
    },
    {
        "instruction": r'''How do I create a systemd service for a Python application that auto-restarts on failure?''',
        "output": r'''Create the service file:

```bash
sudo cat > /etc/systemd/system/myapp.service << 'EOF'
[Unit]
Description=My Python Application
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=appuser
Group=appuser
WorkingDirectory=/opt/myapp
ExecStart=/opt/myapp/venv/bin/python app.py
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Environment
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/opt/myapp/.env

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/myapp/data /var/log/myapp

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=myapp

[Install]
WantedBy=multi-user.target
EOF
```

Enable and manage:

```bash
# Reload systemd after creating/editing the file
sudo systemctl daemon-reload

# Enable (start on boot) and start
sudo systemctl enable --now myapp

# Check status
sudo systemctl status myapp

# View logs
sudo journalctl -u myapp -f        # follow live
sudo journalctl -u myapp --since "1 hour ago"

# Restart / stop
sudo systemctl restart myapp
sudo systemctl stop myapp
```

Key settings explained:
- `Restart=on-failure` -- only restart on non-zero exit (not on clean shutdown)
- `RestartSec=5` -- wait 5 seconds between restarts
- `StartLimitBurst=5` and `StartLimitIntervalSec=60` -- max 5 restarts per 60 seconds before giving up'''
    },
    {
        "instruction": r'''Show me how to set up a cron job that runs a backup script every night at 2 AM, logs output, and sends an email on failure.''',
        "output": r'''```bash
# Edit crontab for the current user
crontab -e

# Add this line (runs at 2:00 AM daily):
0 2 * * * /opt/scripts/backup.sh >> /var/log/backup.log 2>&1 || echo "Backup failed at $(date)" | mail -s "BACKUP FAILED" admin@example.com
```

A more robust approach with a wrapper script:

```bash
cat > /opt/scripts/run-backup.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

LOGFILE="/var/log/backup-$(date +\%Y\%m\%d).log"
MAILTO="admin@example.com"

echo "=== Backup started: $(date) ===" >> "$LOGFILE"

if /opt/scripts/backup.sh >> "$LOGFILE" 2>&1; then
    echo "=== Backup completed: $(date) ===" >> "$LOGFILE"
else
    EXIT_CODE=$?
    echo "=== Backup FAILED (exit $EXIT_CODE): $(date) ===" >> "$LOGFILE"
    tail -50 "$LOGFILE" | mail -s "BACKUP FAILED on $(hostname)" "$MAILTO"
fi

# Clean up logs older than 30 days
find /var/log -name 'backup-*.log' -mtime +30 -delete
SCRIPT

chmod +x /opt/scripts/run-backup.sh
```

Then the cron entry is simply:

```bash
0 2 * * * /opt/scripts/run-backup.sh
```

Cron format reminder:
```
# min hour day month weekday
# 0   2    *   *     *       = daily at 2:00 AM
# 0   */6  *   *     *       = every 6 hours
# 30  2    *   *     0       = Sundays at 2:30 AM
```

Verify your cron is registered:

```bash
crontab -l
```'''
    },
    {
        "instruction": r'''How do I check what's listening on which ports, and find which process is using a specific port?''',
        "output": r'''<think>
Multiple tools can do this: ss, netstat, lsof. ss is the modern replacement for netstat on Linux. I should show all approaches since the user might be on different systems.

Key commands:
- `ss -tlnp` -- TCP listeners with process info
- `lsof -i :PORT` -- find process on a specific port
- `netstat -tlnp` -- older equivalent of ss
</think>

```bash
# Show all listening TCP ports with process names
ss -tlnp
# t=TCP, l=listening, n=numeric ports, p=show process

# Show all listening ports (TCP + UDP)
ss -tulnp

# Find what's using port 8080
ss -tlnp | grep :8080
# Or more reliably:
ss -tlnp 'sport = :8080'

# Using lsof (works on Linux and macOS)
sudo lsof -i :8080
# Shows PID, user, and file descriptor

# Find all connections to a specific remote host
ss -tn dst 10.0.0.5

# Show established connections grouped by state
ss -s

# Check if a specific service is reachable
nc -zv hostname 443 -w 3
# -z = scan only, -v = verbose, -w 3 = 3 second timeout
```

On macOS (no ss):

```bash
# List listening ports
lsof -iTCP -sTCP:LISTEN -n -P

# Find process on a port
lsof -i :8080

# Using netstat
netstat -an | grep LISTEN
```

Kill a process on a port:

```bash
# Find PID, then kill it
kill $(lsof -t -i :8080)

# Force kill
kill -9 $(lsof -t -i :8080)
```'''
    },
    {
        "instruction": r'''How do I set up SSH key-based authentication and create an SSH config for managing multiple servers?''',
        "output": r'''Generate a key and copy it to the server:

```bash
# Generate ed25519 key (more secure and faster than RSA)
ssh-keygen -t ed25519 -C "your-email@example.com"
# Saves to ~/.ssh/id_ed25519 by default

# Copy public key to remote server
ssh-copy-id user@server.example.com

# Or manually if ssh-copy-id is unavailable
cat ~/.ssh/id_ed25519.pub | ssh user@server 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

Create an SSH config for easy access:

```bash
cat > ~/.ssh/config << 'EOF'
# Default settings for all hosts
Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
    AddKeysToAgent yes

Host prod
    HostName 10.0.1.50
    User deploy
    IdentityFile ~/.ssh/id_ed25519_work
    Port 2222

Host staging
    HostName staging.example.com
    User deploy
    IdentityFile ~/.ssh/id_ed25519_work

Host db-tunnel
    HostName 10.0.1.50
    User tunnel
    LocalForward 5433 db-internal:5432
    IdentityFile ~/.ssh/id_ed25519_work

Host dev-*
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519
EOF

chmod 600 ~/.ssh/config
```

Now you can connect with short names:

```bash
ssh prod              # instead of ssh -p 2222 deploy@10.0.1.50
ssh staging
ssh db-tunnel         # sets up port forwarding automatically
scp file.txt prod:/opt/app/
```'''
    },
]
