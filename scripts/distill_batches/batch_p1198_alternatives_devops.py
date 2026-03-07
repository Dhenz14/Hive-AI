"""
Proactive alternatives training pairs - DevOps practices
"""

pairs = [
    {
        "instruction": r'''I deploy my Node.js app to a VPS by SSHing in and running `git pull && npm install && pm2 restart app`. It works well for my single server. Should I keep doing this or is there a better approach?''',
        "output": r'''<think>
Manual SSH deploys work for a single server, but they are error-prone (forgetting a step, deploying the wrong branch) and do not scale. A simple CI/CD pipeline with GitHub Actions would automate the same steps, add consistency, and enable rollbacks. I should not suggest Kubernetes or anything heavy -- just automate what they already do.
</think>

That workflow is fine for a single server, and there is no reason to over-engineer it. The main risks are human ones: deploying the wrong branch, forgetting npm install, or running it during peak hours by accident.

A GitHub Actions workflow automates exactly what you already do, with zero additional infrastructure:

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/myapp
            git pull origin main
            npm ci --production
            pm2 restart app
```

Add your VPS credentials as GitHub repository secrets (Settings -> Secrets). Now every push to main auto-deploys.

You can add safety checks too:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test

  deploy:
    needs: test  # Only deploy if tests pass
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/myapp
            git pull origin main
            npm ci --production
            pm2 restart app
```

Benefits over manual SSH:
- **Consistent** -- same steps every time, no forgotten commands
- **Auditable** -- you can see every deployment in the Actions tab
- **Gated** -- tests must pass before deploy
- **No SSH access needed** for team members to trigger deploys

Note: I used `npm ci` instead of `npm install` -- it is faster and uses the exact versions from package-lock.json, which avoids "works on my machine" issues.'''
    },
    {
        "instruction": r'''I'm running my Python web app directly on an EC2 instance -- installed Python, pip, nginx, and gunicorn manually. Works great. But every time I need a new server (staging, testing) I have to repeat the whole setup. Any suggestions?''',
        "output": r'''<think>
The pain point is reproducibility, not the approach itself. Containers solve this perfectly -- package the app and its dependencies into a Docker image, run it anywhere. I should not suggest ECS/Kubernetes since they are running a single EC2 instance. Docker + docker-compose on the same EC2 is the minimal step up. I can also mention that if they want to keep bare metal, Ansible automates the provisioning.
</think>

Docker would solve the reproducibility problem directly. You package your app and all its dependencies into an image once, then run it identically on any server:

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - web
    restart: unless-stopped
```

Setting up a new server becomes:

```bash
# On any fresh EC2 instance
sudo apt update && sudo apt install -y docker.io docker-compose
git clone your-repo /opt/myapp
cd /opt/myapp
docker-compose up -d
```

That is it -- the same three commands for staging, testing, or production. No more installing Python versions, pip packages, or configuring nginx by hand.

Other benefits:
- **Rollback** -- just point to the previous image tag
- **Local dev matches prod** -- run the same docker-compose on your laptop
- **Isolation** -- app dependencies never conflict with system packages

If you prefer to stay on bare metal (valid choice -- Docker adds a small layer of complexity), Ansible automates the manual provisioning:

```yaml
# ansible playbook excerpt
- name: Install Python
  apt:
    name: [python3.12, python3.12-venv, python3-pip]

- name: Install app dependencies
  pip:
    requirements: /opt/myapp/requirements.txt
    virtualenv: /opt/myapp/venv

- name: Configure gunicorn service
  template:
    src: gunicorn.service.j2
    dest: /etc/systemd/system/myapp.service
```

Docker is the more common path these days, but both approaches get you to "one command to set up a new server."'''
    },
    {
        "instruction": r'''I'm logging in my Python app using print statements:

```python
print(f"[{datetime.now()}] User {user_id} logged in")
print(f"[{datetime.now()}] ERROR: Payment failed for order {order_id}")
print(f"[{datetime.now()}] Processing batch of {len(items)} items")
```

My app is running in production. Should I switch to something else?''',
        "output": r'''<think>
Print statements go to stdout with no way to filter by severity, search structured fields, or route to different destinations. The built-in logging module is the minimum upgrade -- structured logging with something like structlog or python-json-logger is even better for production since logs become searchable JSON. I should show the progression from print to logging to structured.
</think>

Print works for development, but in production you lose important capabilities: filtering by severity, routing errors to a separate file, and searching logs by structured fields. Python's built-in `logging` module is the first step up:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/myapp/app.log')
    ]
)

logger = logging.getLogger(__name__)

# Replace your print statements
logger.info("User %s logged in", user_id)
logger.error("Payment failed for order %s", order_id)
logger.info("Processing batch of %d items", len(items))
```

For production, structured logging (JSON output) makes your logs searchable and parseable by tools like CloudWatch, Datadog, or ELK:

```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

logger.info("user_login", user_id=user_id, ip=request.remote_addr)
# Output: {"event": "user_login", "user_id": 42, "ip": "10.0.1.5", "level": "info", "timestamp": "2026-03-06T14:30:00Z"}

logger.error("payment_failed", order_id=order_id, amount=99.99, gateway="stripe")
# Output: {"event": "payment_failed", "order_id": 1234, "amount": 99.99, "gateway": "stripe", "level": "error", "timestamp": "..."}
```

Why this matters in production:

```bash
# With print -- good luck finding payment errors
grep "ERROR" app.log | grep "Payment"

# With structured JSON -- precise queries
cat app.log | jq 'select(.event == "payment_failed" and .amount > 50)'
```

You can also set different log levels per environment:

```python
# Production -- only warnings and errors
logging.basicConfig(level=logging.WARNING)

# Development -- everything including debug
logging.basicConfig(level=logging.DEBUG)
```

Start with the built-in `logging` module as a direct replacement for print. Add `structlog` or `python-json-logger` when you need to search or aggregate logs.'''
    },
    {
        "instruction": r'''I'm running a web app on a single server. When traffic spikes I SSH in and manually start more gunicorn workers, or sometimes spin up another EC2 instance and add it to the load balancer by hand. How can I handle this more gracefully?''',
        "output": r'''<think>
Manual scaling means downtime during traffic spikes while the human reacts. AWS Auto Scaling Groups handle this automatically based on metrics like CPU or request count. If they are already on EC2 with a load balancer, an ASG is the natural next step. I should keep it practical -- show the core concept, not a full Terraform config.
</think>

Manual scaling means your app is down (or degraded) for however long it takes you to notice the spike and react. AWS Auto Scaling Groups automate exactly what you are doing by hand.

The concept is straightforward: define a launch template (what to spin up), attach it to an Auto Scaling Group (when and how many), and connect it to your existing load balancer:

```bash
# 1. Create a launch template from your current instance
aws ec2 create-launch-template \
    --launch-template-name myapp-template \
    --launch-template-data '{
        "ImageId": "ami-your-app-image",
        "InstanceType": "t3.medium",
        "KeyName": "your-key",
        "SecurityGroupIds": ["sg-xxx"],
        "UserData": "base64-encoded-startup-script"
    }'

# 2. Create the Auto Scaling Group
aws autoscaling create-auto-scaling-group \
    --auto-scaling-group-name myapp-asg \
    --launch-template LaunchTemplateName=myapp-template,Version='$Latest' \
    --min-size 1 \
    --max-size 5 \
    --desired-capacity 2 \
    --target-group-arns arn:aws:elasticloadbalancing:...:targetgroup/myapp/xxx

# 3. Add a scaling policy based on CPU
aws autoscaling put-scaling-policy \
    --auto-scaling-group-name myapp-asg \
    --policy-name cpu-scale-out \
    --policy-type TargetTrackingScaling \
    --target-tracking-configuration '{
        "PredefinedMetricSpecification": {
            "PredefinedMetricType": "ASGAverageCPUUtilization"
        },
        "TargetValue": 60.0
    }'
```

What this does:
- Keeps at least 1 instance running, up to 5
- When average CPU across instances exceeds 60%, adds instances
- When CPU drops, removes extra instances after a cooldown
- New instances automatically register with your load balancer

Your startup script (UserData) should bootstrap the instance:

```bash
#!/bin/bash
cd /opt/myapp
git pull origin main
pip install -r requirements.txt
systemctl start gunicorn
```

For the gunicorn workers on each instance, set it based on CPU cores and leave it fixed:

```python
# gunicorn.conf.py
import multiprocessing
workers = multiprocessing.cpu_count() * 2 + 1
bind = "0.0.0.0:8000"
```

This way, scaling is handled by adding/removing instances (horizontal) rather than adjusting workers on a single box (vertical). You never SSH in to respond to traffic again.'''
    },
    {
        "instruction": r'''I manage a few Linux servers for our team. Everyone connects with username and password over SSH. It works, but I keep hearing we should change our authentication method. What do you recommend?''',
        "output": r'''<think>
Password auth for SSH is a real security risk -- brute force attacks, credential stuffing, shared passwords. SSH key authentication is the standard. It is more secure (no password to guess) and more convenient (no typing passwords). I should explain the setup clearly and mention disabling password auth once keys are in place.
</think>

SSH key authentication is more secure and more convenient than passwords. Keys are virtually impossible to brute-force (compared to passwords which get attacked constantly), and you never have to type a password to connect.

Here is how to set it up for each team member:

On the team member's local machine:

```bash
# Generate a key pair (do this once)
ssh-keygen -t ed25519 -C "alice@company.com"
# Creates ~/.ssh/id_ed25519 (private -- never share)
# and ~/.ssh/id_ed25519.pub (public -- goes on servers)

# Copy the public key to each server
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@your-server.com
```

That is it for the user side. Now they connect without a password:

```bash
ssh user@your-server.com
# Authenticated automatically via key
```

Once all team members have keys set up, disable password authentication on each server:

```bash
# /etc/ssh/sshd_config
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no

# Restart SSH
sudo systemctl restart sshd
```

A few more security improvements while you are at it:

```bash
# /etc/ssh/sshd_config additions

# Only allow specific users
AllowUsers alice bob charlie

# Change default port (reduces automated scan noise)
Port 2222

# Disable empty passwords
PermitEmptyPasswords no

# Limit authentication attempts
MaxAuthTries 3
```

For managing keys across multiple servers, a simple script helps:

```bash
#!/bin/bash
# add_user_key.sh -- run when a new team member joins
SERVERS="server1.example.com server2.example.com server3.example.com"
PUBKEY="$1"

for server in $SERVERS; do
    ssh admin@$server "echo '$PUBKEY' >> ~/.ssh/authorized_keys"
    echo "Key added to $server"
done
```

And when someone leaves the team:

```bash
#!/bin/bash
# remove_user_key.sh
SERVERS="server1.example.com server2.example.com server3.example.com"
EMAIL="$1"

for server in $SERVERS; do
    ssh admin@$server "sed -i '/$EMAIL/d' ~/.ssh/authorized_keys"
    echo "Key removed from $server"
done
```

The transition is smooth -- enable key auth first, get everyone set up, then disable password auth. Your servers will immediately stop seeing the thousands of daily brute-force login attempts that every internet-facing SSH server gets.'''
    },
]
