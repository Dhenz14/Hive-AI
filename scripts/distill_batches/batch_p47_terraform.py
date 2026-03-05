"""Terraform — infrastructure as code, modules, state management, and AWS patterns."""

PAIRS = [
    (
        "devops/terraform-fundamentals",
        "Show Terraform patterns: resource definitions, variables, outputs, data sources, and state management.",
        """Terraform infrastructure-as-code patterns:

```hcl
# --- Provider and backend configuration ---

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }

  backend "s3" {
    bucket         = "myapp-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = var.project_name
    }
  }
}


# --- Variables with validation ---

variable "environment" {
  type        = string
  description = "Deployment environment"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "allowed_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to access the service"
  default     = []
  sensitive   = false
}

variable "db_password" {
  type      = string
  sensitive = true  # Won't show in logs/output
}


# --- Locals for computed values ---

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
  }
  is_prod = var.environment == "prod"
}


# --- VPC and networking ---

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  map_public_ip_on_launch = true
  tags = { Name = "${local.name_prefix}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "${local.name_prefix}-private-${count.index}" }
}

data "aws_availability_zones" "available" {
  state = "available"
}


# --- Security group ---

resource "aws_security_group" "web" {
  name_prefix = "${local.name_prefix}-web-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}


# --- Outputs ---

output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}
```

Terraform fundamentals:
1. **Remote backend** — S3 + DynamoDB for state locking and team collaboration
2. **Variable validation** — catch errors before `apply`
3. **`sensitive = true`** — mask secrets in plan output
4. **`count` / `for_each`** — create multiple similar resources
5. **`lifecycle`** — control resource replacement behavior"""
    ),
    (
        "devops/terraform-modules",
        "Show Terraform module patterns: reusable modules, composition, and production AWS infrastructure.",
        """Terraform module patterns for production:

```hcl
# --- Reusable ECS module ---
# modules/ecs-service/variables.tf

variable "name" { type = string }
variable "environment" { type = string }
variable "container_image" { type = string }
variable "container_port" { type = number, default = 8080 }
variable "cpu" { type = number, default = 256 }
variable "memory" { type = number, default = 512 }
variable "desired_count" { type = number, default = 2 }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "health_check_path" { type = string, default = "/health" }
variable "environment_variables" {
  type    = map(string)
  default = {}
}
variable "secrets" {
  type    = map(string)  # name -> SSM parameter ARN
  default = {}
}


# modules/ecs-service/main.tf

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name}-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name  = var.name
    image = var.container_image
    portMappings = [{ containerPort = var.container_port }]

    environment = [
      for k, v in var.environment_variables : { name = k, value = v }
    ]

    secrets = [
      for k, v in var.secrets : { name = k, valueFrom = v }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = var.name
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}${var.health_check_path} || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_ecs_service" "this" {
  name            = "${var.name}-${var.environment}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = var.name
    container_port   = var.container_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [desired_count]  # Managed by autoscaling
  }
}

resource "aws_appautoscaling_target" "this" {
  max_capacity       = var.desired_count * 4
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}


# --- Using the module ---
# environments/prod/main.tf

module "api" {
  source = "../../modules/ecs-service"

  name           = "api"
  environment    = "prod"
  container_image = "${aws_ecr_repository.api.repository_url}:${var.api_version}"
  container_port = 8080
  cpu            = 512
  memory         = 1024
  desired_count  = 3
  vpc_id         = module.networking.vpc_id
  subnet_ids     = module.networking.private_subnet_ids

  environment_variables = {
    LOG_LEVEL    = "info"
    DATABASE_URL = "postgresql://${module.rds.endpoint}:5432/app"
  }

  secrets = {
    DB_PASSWORD = aws_ssm_parameter.db_password.arn
    API_KEY     = aws_ssm_parameter.api_key.arn
  }
}

module "worker" {
  source = "../../modules/ecs-service"

  name            = "worker"
  environment     = "prod"
  container_image = "${aws_ecr_repository.worker.repository_url}:${var.worker_version}"
  desired_count   = 2
  cpu             = 1024
  memory          = 2048
  vpc_id          = module.networking.vpc_id
  subnet_ids      = module.networking.private_subnet_ids
}
```

Module patterns:
1. **Input variables** — parameterize everything that varies between environments
2. **Sensible defaults** — most variables should have defaults
3. **Composition** — use modules for logical groups (networking, compute, storage)
4. **`lifecycle` blocks** — prevent unwanted replacements or ignore autoscaler changes
5. **Circuit breaker** — auto-rollback failed ECS deployments"""
    ),
    (
        "devops/ansible-patterns",
        "Show Ansible patterns: playbooks, roles, handlers, templates, and idempotent operations.",
        """Ansible automation patterns:

```yaml
# --- Playbook: deploy web application ---
# deploy.yml

- name: Deploy web application
  hosts: webservers
  become: true
  vars:
    app_name: myapp
    app_user: deploy
    app_dir: /opt/{{ app_name }}
    app_version: "{{ lookup('env', 'APP_VERSION') | default('latest') }}"
    nginx_server_name: "{{ inventory_hostname }}"

  pre_tasks:
    - name: Update apt cache
      apt:
        update_cache: true
        cache_valid_time: 3600

  roles:
    - common
    - role: nginx
      vars:
        nginx_vhosts:
          - server_name: "{{ nginx_server_name }}"
            upstream_port: 8000
    - role: app
      tags: [app, deploy]

  post_tasks:
    - name: Verify application health
      uri:
        url: "http://localhost:8000/health"
        status_code: 200
      retries: 5
      delay: 3
      register: health_check
      until: health_check.status == 200


# --- Role: common ---
# roles/common/tasks/main.yml

- name: Install system packages
  apt:
    name:
      - python3
      - python3-pip
      - python3-venv
      - curl
      - htop
      - unzip
    state: present

- name: Create application user
  user:
    name: "{{ app_user }}"
    system: true
    shell: /bin/bash
    home: "{{ app_dir }}"

- name: Set up log rotation
  template:
    src: logrotate.conf.j2
    dest: /etc/logrotate.d/{{ app_name }}
    mode: "0644"

- name: Configure firewall
  ufw:
    rule: allow
    port: "{{ item }}"
    proto: tcp
  loop:
    - "22"
    - "80"
    - "443"

- name: Enable firewall
  ufw:
    state: enabled
    policy: deny


# --- Role: app ---
# roles/app/tasks/main.yml

- name: Create application directory
  file:
    path: "{{ item }}"
    state: directory
    owner: "{{ app_user }}"
    mode: "0755"
  loop:
    - "{{ app_dir }}"
    - "{{ app_dir }}/releases"
    - "{{ app_dir }}/shared"

- name: Download application artifact
  get_url:
    url: "https://artifacts.example.com/{{ app_name }}/{{ app_version }}.tar.gz"
    dest: "/tmp/{{ app_name }}-{{ app_version }}.tar.gz"
    checksum: "sha256:{{ app_checksum }}"
  register: download

- name: Extract application
  unarchive:
    src: "/tmp/{{ app_name }}-{{ app_version }}.tar.gz"
    dest: "{{ app_dir }}/releases/{{ app_version }}"
    remote_src: true
    owner: "{{ app_user }}"
  when: download.changed

- name: Install Python dependencies
  pip:
    requirements: "{{ app_dir }}/releases/{{ app_version }}/requirements.txt"
    virtualenv: "{{ app_dir }}/venv"
    virtualenv_command: python3 -m venv

- name: Deploy configuration
  template:
    src: app.env.j2
    dest: "{{ app_dir }}/shared/.env"
    owner: "{{ app_user }}"
    mode: "0600"
  notify: restart app

- name: Update symlink to current release
  file:
    src: "{{ app_dir }}/releases/{{ app_version }}"
    dest: "{{ app_dir }}/current"
    state: link
    owner: "{{ app_user }}"
  notify: restart app

- name: Deploy systemd service
  template:
    src: app.service.j2
    dest: /etc/systemd/system/{{ app_name }}.service
  notify:
    - reload systemd
    - restart app

- name: Ensure app is running
  systemd:
    name: "{{ app_name }}"
    state: started
    enabled: true


# --- Handlers ---
# roles/app/handlers/main.yml

- name: reload systemd
  systemd:
    daemon_reload: true

- name: restart app
  systemd:
    name: "{{ app_name }}"
    state: restarted

- name: restart nginx
  systemd:
    name: nginx
    state: restarted


# --- Template ---
# roles/app/templates/app.service.j2

# [Unit]
# Description={{ app_name }}
# After=network.target
#
# [Service]
# Type=exec
# User={{ app_user }}
# WorkingDirectory={{ app_dir }}/current
# EnvironmentFile={{ app_dir }}/shared/.env
# ExecStart={{ app_dir }}/venv/bin/gunicorn app:create_app() \
#   --bind 127.0.0.1:8000 \
#   --workers {{ ansible_processor_vcpus * 2 + 1 }} \
#   --timeout 30
# Restart=always
# RestartSec=5
#
# [Install]
# WantedBy=multi-user.target
```

Ansible patterns:
1. **Idempotent** — running twice produces the same result (use `state: present`, not shell commands)
2. **Handlers** — only restart services when config actually changes
3. **Roles** — reusable, parameterized bundles of tasks/templates/handlers
4. **Templates** — Jinja2 for config files with environment-specific values
5. **Health checks** — verify deployment success with retries"""
    ),
]
