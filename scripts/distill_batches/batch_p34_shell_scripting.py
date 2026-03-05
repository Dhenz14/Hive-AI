"""Shell scripting — Bash patterns, automation, and DevOps scripting."""

PAIRS = [
    (
        "devops/bash-scripting",
        "Show Bash scripting best practices: error handling, argument parsing, logging, and portable scripts.",
        '''Production Bash scripting patterns:

```bash
#!/usr/bin/env bash
# deploy.sh — Production deployment script
# Usage: ./deploy.sh --env production --version v1.2.0 [--dry-run]

# --- Strict mode ---
set -euo pipefail  # Exit on error, undefined vars, pipe failures
IFS=$'\\n\\t'       # Safer word splitting

# --- Constants ---
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly LOG_FILE="/var/log/deploy-$(date +%Y%m%d-%H%M%S).log"

# --- Colors (only if terminal) ---
if [[ -t 1 ]]; then
    RED=$'\\e[31m'
    GREEN=$'\\e[32m'
    YELLOW=$'\\e[33m'
    BLUE=$'\\e[34m'
    RESET=$'\\e[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' RESET=''
fi

# --- Logging ---
log()   { echo "${GREEN}[INFO]${RESET} $(date +%H:%M:%S) $*" | tee -a "$LOG_FILE"; }
warn()  { echo "${YELLOW}[WARN]${RESET} $(date +%H:%M:%S) $*" | tee -a "$LOG_FILE" >&2; }
error() { echo "${RED}[ERROR]${RESET} $(date +%H:%M:%S) $*" | tee -a "$LOG_FILE" >&2; }
die()   { error "$@"; exit 1; }

# --- Cleanup on exit ---
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        error "Script failed with exit code $exit_code"
        # Rollback logic here
    fi
    # Remove temp files
    rm -f "${TEMP_FILE:-}"
    exit $exit_code
}
trap cleanup EXIT
trap 'die "Interrupted"' INT TERM

# --- Argument parsing ---
ENV=""
VERSION=""
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Options:
    --env ENV        Target environment (staging|production)
    --version VER    Version to deploy (e.g., v1.2.0)
    --dry-run        Show what would be done without doing it
    -h, --help       Show this help message

Example:
    $SCRIPT_NAME --env production --version v1.2.0
    $SCRIPT_NAME --env staging --version latest --dry-run
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)
            ENV="${2:?--env requires a value}"
            shift 2
            ;;
        --version)
            VERSION="${2:?--version requires a value}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1 (use --help for usage)"
            ;;
    esac
done

# --- Validation ---
[[ -z "$ENV" ]] && die "Missing required: --env"
[[ -z "$VERSION" ]] && die "Missing required: --version"
[[ "$ENV" =~ ^(staging|production)$ ]] || die "Invalid env: $ENV (must be staging|production)"

# --- Prerequisites check ---
check_prerequisites() {
    local missing=()
    for cmd in docker kubectl jq curl; do
        command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing required tools: ${missing[*]}"
    fi
}

# --- Helper: run or dry-run ---
run() {
    if $DRY_RUN; then
        log "${BLUE}[DRY-RUN]${RESET} $*"
    else
        log "Running: $*"
        "$@"
    fi
}

# --- Confirmation prompt ---
confirm() {
    local message="${1:-Continue?}"
    if $DRY_RUN; then return 0; fi
    read -rp "${YELLOW}$message [y/N]${RESET} " response
    [[ "$response" =~ ^[Yy]$ ]]
}

# --- Main deployment ---
main() {
    log "Starting deployment: env=$ENV version=$VERSION dry_run=$DRY_RUN"

    check_prerequisites

    if [[ "$ENV" == "production" ]]; then
        confirm "Deploy $VERSION to PRODUCTION?" || die "Aborted by user"
    fi

    # Create temp file safely
    TEMP_FILE=$(mktemp)

    log "Step 1: Building image..."
    run docker build -t "app:$VERSION" .

    log "Step 2: Pushing image..."
    run docker push "registry.example.com/app:$VERSION"

    log "Step 3: Updating deployment..."
    run kubectl set image "deployment/api" "api=app:$VERSION" -n "$ENV"

    log "Step 4: Waiting for rollout..."
    if ! $DRY_RUN; then
        kubectl rollout status "deployment/api" -n "$ENV" --timeout=300s
    fi

    log "Deployment complete: $VERSION -> $ENV"
}

main "$@"
```

Best practices:
1. **`set -euo pipefail`** — fail fast on errors, undefined variables, pipe failures
2. **Argument parsing** — `while/case` loop with validation and help text
3. **Cleanup trap** — `trap cleanup EXIT` ensures cleanup even on failure
4. **Dry-run mode** — preview actions without executing
5. **Logging functions** — consistent, colorized output with timestamps
6. **Prerequisites check** — verify required tools before starting
7. **Confirmation prompts** — for destructive or production operations'''
    ),
    (
        "devops/bash-automation",
        "Show Bash automation patterns: parallel execution, file processing, API interaction, and monitoring scripts.",
        '''Bash automation for DevOps tasks:

```bash
#!/usr/bin/env bash
set -euo pipefail

# --- Parallel execution ---

parallel_deploy() {
    local services=("api" "worker" "scheduler" "web")
    local pids=()
    local failures=0

    for service in "${services[@]}"; do
        (
            echo "Deploying $service..."
            docker compose up -d "$service" 2>&1 | sed "s/^/[$service] /"
        ) &
        pids+=($!)
    done

    # Wait for all and collect failures
    for pid in "${pids[@]}"; do
        if ! wait "$pid"; then
            ((failures++))
        fi
    done

    return $failures
}

# With GNU parallel (if available):
# parallel --jobs 4 --halt soon,fail=1 deploy_service ::: api worker scheduler web


# --- File processing ---

process_csv() {
    local input="$1"
    local output="${2:-/dev/stdout}"

    # Skip header, extract fields, deduplicate
    tail -n +2 "$input" |
        awk -F',' '{print $2, $5}' |
        sort -u |
        while IFS=' ' read -r email status; do
            if [[ "$status" == "active" ]]; then
                echo "$email"
            fi
        done > "$output"

    echo "Processed $(wc -l < "$output") records" >&2
}

# Find and process files
find_and_compress() {
    local dir="${1:-.}"
    local days="${2:-30}"

    find "$dir" -type f -name "*.log" -mtime "+$days" -print0 |
        while IFS= read -r -d '' file; do
            echo "Compressing: $file"
            gzip "$file"
        done
}


# --- API interaction ---

api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local base_url="${API_URL:-https://api.example.com}"

    local args=(
        -s -S                        # Silent but show errors
        -w "\\n%{http_code}"         # Append status code
        -H "Authorization: Bearer $API_TOKEN"
        -H "Content-Type: application/json"
        -X "$method"
    )

    if [[ -n "$data" ]]; then
        args+=(-d "$data")
    fi

    local response
    response=$(curl "${args[@]}" "$base_url$endpoint")

    local status_code
    status_code=$(echo "$response" | tail -1)
    local body
    body=$(echo "$response" | sed '$d')

    if [[ "$status_code" -ge 400 ]]; then
        echo "API error ($status_code): $body" >&2
        return 1
    fi

    echo "$body"
}

# Usage:
# users=$(api_call GET "/users?page=1")
# api_call POST "/users" '{"name": "Alice", "email": "a@b.com"}'
# echo "$users" | jq '.data[] | .email'


# --- Retry with backoff ---

retry() {
    local max_attempts="${1:-3}"
    local delay="${2:-5}"
    shift 2

    local attempt=1
    until "$@"; do
        if ((attempt >= max_attempts)); then
            echo "Failed after $max_attempts attempts: $*" >&2
            return 1
        fi
        echo "Attempt $attempt failed, retrying in ${delay}s..." >&2
        sleep "$delay"
        ((attempt++))
        ((delay *= 2))  # Exponential backoff
    done
}

# Usage: retry 3 5 curl -f https://api.example.com/health


# --- Health check monitoring ---

health_check() {
    local services=(
        "API|https://api.example.com/health"
        "Web|https://www.example.com"
        "DB|pg_isready -h db.internal"
    )

    local all_ok=true

    for entry in "${services[@]}"; do
        IFS='|' read -r name check <<< "$entry"
        if [[ "$check" == http* ]]; then
            if curl -sf --max-time 5 "$check" > /dev/null 2>&1; then
                echo "OK    $name"
            else
                echo "FAIL  $name"
                all_ok=false
            fi
        else
            if eval "$check" > /dev/null 2>&1; then
                echo "OK    $name"
            else
                echo "FAIL  $name"
                all_ok=false
            fi
        fi
    done

    $all_ok
}


# --- Safe config file editing ---

update_config() {
    local file="$1"
    local key="$2"
    local value="$3"

    if [[ ! -f "$file" ]]; then
        echo "$key=$value" > "$file"
        return
    fi

    # Backup
    cp "$file" "$file.bak"

    # Update or append
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
}
```

Patterns:
1. **Parallel jobs** — background processes with PID tracking and failure counting
2. **File processing** — pipelines with `find -print0`, `while read -r`, `awk`
3. **API wrapper** — curl with auth headers, status code extraction, error handling
4. **Retry with backoff** — generic retry function for flaky operations
5. **Health checks** — iterate service list with configurable check types'''
    ),
]
"""
