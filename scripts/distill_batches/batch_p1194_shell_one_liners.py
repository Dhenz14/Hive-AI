"""
Shell/CLI training pairs - Powerful one-liners for common dev tasks.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''Give me useful one-liners for analyzing application log files -- finding errors, counting patterns, tracking response times.''',
        "output": r'''<think>
Log analysis one-liners are extremely practical. I should cover:
1. Error frequency and patterns
2. Time-based analysis (errors per hour)
3. Response time percentiles
4. Recent errors with context
5. Unique error messages

I will use common log formats and keep each one-liner focused on a single task.
</think>

```bash
# Count errors per hour
grep -i 'error\|exception' app.log | awk '{print substr($1, 1, 13)}' | sort | uniq -c

# Top 10 most frequent error messages (deduped)
grep -i error app.log | sed 's/[0-9]\{4\}-[0-9-]* [0-9:]*//' | sort | uniq -c | sort -rn | head -10

# Show errors with 3 lines of context before and after
grep -B3 -A3 -i 'exception\|traceback' app.log | head -80

# Extract response times and calculate basic stats
grep 'response_time=' app.log | grep -oP 'response_time=\K[0-9.]+' | sort -n | awk '
  {a[NR]=$1; s+=$1}
  END {printf "count=%d min=%.1f max=%.1f avg=%.1f p50=%.1f p95=%.1f p99=%.1f\n",
    NR, a[1], a[NR], s/NR, a[int(NR*0.5)], a[int(NR*0.95)], a[int(NR*0.99)]}'

# Find requests slower than 5 seconds
grep 'response_time=' app.log | awk -F'response_time=' '$2+0 > 5000 {print}'

# Count HTTP status codes from access log
awk '{print $9}' access.log | sort | uniq -c | sort -rn
# Output: 45123 200, 1234 404, 56 500, ...

# Find errors in the last hour
awk -v d="$(date -d '1 hour ago' '+%Y-%m-%d %H')" '$0 ~ d && /ERROR/' app.log

# Unique IPs that got 403 errors
awk '$9 == 403 {print $1}' access.log | sort -u | wc -l

# Watch a log file for errors in real time, highlighted
tail -f app.log | grep --color=always -i 'error\|warn\|fail'
```'''
    },
    {
        "instruction": r'''Give me one-liners for quickly testing and debugging APIs from the command line.''',
        "output": r'''```bash
# GET with pretty-printed JSON
curl -s https://api.example.com/users | jq .

# POST with JSON body
curl -s -X POST https://api.example.com/users \
  -H 'Content-Type: application/json' \
  -d '{"name": "Alice", "email": "alice@example.com"}' | jq .

# PUT with auth token
curl -s -X PUT https://api.example.com/users/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Updated"}' | jq .

# Show response headers alongside body
curl -si https://api.example.com/health

# Measure response time breakdown
curl -o /dev/null -s -w "DNS: %{time_namelookup}s\nConnect: %{time_connect}s\nTLS: %{time_appconnect}s\nFirst byte: %{time_starttransfer}s\nTotal: %{time_total}s\n" https://api.example.com/

# Loop: hit an endpoint 100 times and show status codes
for i in $(seq 1 100); do curl -so /dev/null -w "%{http_code}\n" https://api.example.com/health; done | sort | uniq -c

# Quick load test: 10 concurrent requests
seq 1 10 | xargs -P 10 -I {} curl -so /dev/null -w "{}: %{http_code} %{time_total}s\n" https://api.example.com/

# POST from a JSON file
curl -s -X POST https://api.example.com/data \
  -H 'Content-Type: application/json' \
  -d @payload.json | jq .

# Follow redirects and show the chain
curl -sIL https://example.com 2>&1 | grep -i 'location\|HTTP/'

# Download and extract a specific field
curl -s https://api.github.com/repos/torvalds/linux | jq -r '.stargazers_count'
```'''
    },
    {
        "instruction": r'''What are some handy one-liners for working with files -- finding, comparing, and bulk operations?''',
        "output": r'''```bash
# Find files modified in the last 24 hours
find . -type f -mtime -1 -ls

# Find the 20 largest files in a directory tree
find . -type f -exec du -h {} + 2>/dev/null | sort -rh | head -20

# Compare two directories (show files that differ)
diff -rq dir1/ dir2/ | head -30

# Find duplicate files by checksum
find . -type f -exec md5sum {} + | sort | awk '{if (prev==$1) print prev_file " = " $2; prev=$1; prev_file=$2}'

# Rename files: replace spaces with underscores
for f in *\ *; do mv "$f" "${f// /_}"; done

# Batch rename with sequential numbering
ls *.jpg | cat -n | while read n f; do mv "$f" "photo_$(printf '%03d' $n).jpg"; done

# Find files containing a string, show filename and line
grep -rn "TODO" --include='*.py' .

# Count lines of code by file extension
find . -type f -name '*.py' | xargs wc -l | sort -n | tail -20

# Find empty directories
find . -type d -empty

# Show directory sizes sorted (top-level only)
du -h --max-depth=1 | sort -rh

# Find broken symlinks
find . -xtype l

# Find files NOT matching a pattern
find . -type f -not -name '*.py' -not -name '*.js' -not -path '*/.git/*'

# Sync only changed files between directories
rsync -av --dry-run src/ backup/
# Remove --dry-run when satisfied

# Quick file server (share files over HTTP)
python3 -m http.server 8080
```'''
    },
    {
        "instruction": r'''I need to process a bunch of JSON files in a directory -- extract a field from each, aggregate the results, and find outliers. What's the best shell approach?''',
        "output": r'''<think>
The user wants to process multiple JSON files. This is a common pattern in data analysis:
1. Extract a field from each file
2. Aggregate (sum, count, average)
3. Find outliers

jq can process multiple files. I should show both the one-liner approach and a slightly more structured pipeline. I will use a realistic example -- say response_time from API test results.
</think>

Example: JSON files with `{"endpoint": "...", "response_ms": 123, "status": 200}`

```bash
# Extract response_ms from all files, one per line
jq -r '.response_ms' results/*.json

# With filename for traceability
for f in results/*.json; do
    echo "$(basename "$f"): $(jq -r '.response_ms' "$f")"
done

# Aggregate: count, sum, average, min, max
jq -r '.response_ms' results/*.json | awk '
  {sum+=$1; a[NR]=$1; if(!min||$1<min)min=$1; if($1>max)max=$1}
  END {printf "count=%d sum=%.0f avg=%.1f min=%.0f max=%.0f\n",
    NR, sum, sum/NR, min, max}'

# Find outliers (> 2 standard deviations from mean)
jq -r '.response_ms' results/*.json | awk '
  {a[NR]=$1; sum+=$1; sumsq+=$1*$1}
  END {
    mean=sum/NR; stddev=sqrt(sumsq/NR - mean*mean)
    threshold=mean + 2*stddev
    printf "mean=%.1f stddev=%.1f threshold=%.1f\n", mean, stddev, threshold
    for(i=1;i<=NR;i++) if(a[i]>threshold) printf "OUTLIER: %.0f\n", a[i]
  }'

# Group by endpoint and show averages
jq -r '[.endpoint, .response_ms] | @tsv' results/*.json \
  | awk -F'\t' '{sum[$1]+=$2; cnt[$1]++}
    END {for(e in sum) printf "%s\t%.1f ms (n=%d)\n", e, sum[e]/cnt[e], cnt[e]}' \
  | sort -t$'\t' -k2 -rn

# Find files where status != 200
for f in results/*.json; do
    status=$(jq -r '.status' "$f")
    [ "$status" != "200" ] && echo "FAILED ($status): $f"
done

# Combine all JSON files into a single array
jq -s '.' results/*.json > combined.json
```'''
    },
    {
        "instruction": r'''Show me one-liners for git that help with code review and repository analysis.''',
        "output": r'''```bash
# Files changed the most in the last 30 days (hotspots)
git log --since="30 days ago" --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20

# Who changed which files the most (code ownership)
git log --format='%an' -- src/auth/ | sort | uniq -c | sort -rn

# Lines of code added/removed per author
git log --format='%an' --numstat | awk '/^[a-zA-Z]/ {author=$0; next} NF==3 {add[author]+=$1; del[author]+=$2} END {for(a in add) printf "%s: +%d -%d\n", a, add[a], del[a]}' | sort -t+ -k2 -rn

# Show all TODOs/FIXMEs added in the last week
git diff $(git log --since="1 week ago" --format=%H | tail -1)..HEAD | grep '^\+.*\(TODO\|FIXME\|HACK\|XXX\)'

# Commits per day (activity chart)
git log --format='%ad' --date=short | sort | uniq -c | tail -30

# Find large files in git history
git rev-list --objects --all | git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize) %(rest)' | awk '$3 > 1048576' | sort -k3 -rn | head -10

# Show files in a commit without the diff
git diff-tree --no-commit-id --name-status -r HEAD

# Compare branches: what commits are in feature but not main
git log main..feature --oneline

# Find commits that touched a specific function
git log -p --all -S 'def process_payment' -- '*.py'

# Show the diff stats for a PR (files changed, insertions, deletions)
git diff --stat main...feature

# List all authors who contributed to a file
git log --follow --format='%an <%ae>' -- path/to/file.py | sort -u

# Weekly commit count summary
git shortlog -sn --since="4 weeks ago" --no-merges
```'''
    },
]
