"""
Shell/CLI training pairs - jq, csvkit, data transformation pipelines in shell.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''I have a JSON API response with nested data. Show me how to use jq to extract and transform it into a flat CSV.''',
        "output": r'''<think>
The user wants to go from nested JSON to flat CSV using jq. I should show:
1. How to navigate nested JSON with jq
2. How to flatten nested objects
3. How to output CSV format with headers

jq has a built-in @csv formatter that handles quoting correctly. I need to construct an array of values per row and pipe through @csv.

Let me use a realistic example -- an API response with users that have nested addresses.
</think>

Given this JSON structure:

```json
{
  "users": [
    {"id": 1, "name": "Alice", "address": {"city": "Portland", "state": "OR"}, "tags": ["admin", "dev"]},
    {"id": 2, "name": "Bob", "address": {"city": "Austin", "state": "TX"}, "tags": ["dev"]}
  ]
}
```

Extract and flatten to CSV:

```bash
# Basic flat extraction
cat data.json | jq -r '.users[] | [.id, .name, .address.city, .address.state] | @csv'
# Output:
# 1,"Alice","Portland","OR"
# 2,"Bob","Austin","TX"

# With headers
cat data.json | jq -r '
  ["id","name","city","state"],
  (.users[] | [.id, .name, .address.city, .address.state])
  | @csv
'

# Join array fields into a semicolon-separated string
cat data.json | jq -r '
  ["id","name","city","state","tags"],
  (.users[] | [.id, .name, .address.city, .address.state, (.tags | join(";"))])
  | @csv
'
```

For more complex transformations:

```bash
# Filter users by state, then extract
cat data.json | jq -r '
  .users[]
  | select(.address.state == "OR")
  | [.id, .name, .address.city]
  | @csv
'

# Pipe API response directly
curl -s "https://api.example.com/users" | jq -r '
  .data[]
  | [.id, .email, .created_at]
  | @csv
' > users.csv
```

If the JSON has inconsistent fields, use `//` for defaults:

```bash
jq -r '.users[] | [.id, .name, (.email // "N/A"), (.phone // "")] | @csv' data.json
```'''
    },
    {
        "instruction": r'''How do I use jq to merge two JSON files, combining arrays and handling conflicts?''',
        "output": r'''```bash
# Simple merge (second file overrides first on conflicts)
jq -s '.[0] * .[1]' base.json overrides.json

# Merge and concatenate arrays instead of replacing
jq -s '.[0] as $a | .[1] as $b | $a * $b * {
  "items": ($a.items + $b.items)
}' file1.json file2.json

# Deep merge with custom conflict resolution
jq -s 'def deepmerge:
  reduce .[] as $item ({}; . * $item);
  [.[]] | deepmerge
' file1.json file2.json
```

Practical examples:

```bash
# Merge config files (overrides win)
jq -s '.[0] * .[1]' config.default.json config.local.json > config.json

# Combine API pages into one array
jq -s '[.[].results[]]' page1.json page2.json page3.json > all.json

# Or using a glob
jq -s '[.[].results[]]' pages/*.json > combined.json

# Merge and deduplicate by a key
jq -s '
  [.[][][]] | group_by(.id) | map(
    reduce .[] as $item ({}; . * $item)
  )
' file1.json file2.json

# Add/update a field in existing JSON
jq '.version = "2.0" | .updated = now' config.json > config.updated.json

# Merge environment-specific values
jq --arg env "production" -s '
  .[0] * .[1] * {"environment": $env}
' base.json prod.json
```'''
    },
    {
        "instruction": r'''Show me how to build a shell pipeline that processes a large CSV log file -- filter rows, aggregate data, and produce a summary report.''',
        "output": r'''<think>
I should show a realistic data pipeline using standard Unix tools. The scenario: a web application access log in CSV format. The pipeline should:
1. Filter rows by criteria (date range, status code)
2. Aggregate (count by endpoint, sum response times)
3. Produce a summary

I can use awk for most of this, or combine cut/grep/sort/uniq. For a CSV-heavy workflow, csvkit is great but I should show both approaches.
</think>

Scenario: `requests.csv` with columns: timestamp, method, endpoint, status, response_ms, user_id

```bash
# Pipeline 1: Top 10 slowest endpoints (avg response time)
tail -n +2 requests.csv \
  | awk -F',' '{
      endpoint=$3; ms=$5
      sum[endpoint] += ms
      count[endpoint]++
    }
    END {
      for (e in sum)
        printf "%d\t%d\t%s\n", sum[e]/count[e], count[e], e
    }' \
  | sort -rn \
  | head -10 \
  | awk 'BEGIN {printf "%-8s %-8s %s\n", "AVG_MS", "COUNT", "ENDPOINT"}
         {printf "%-8s %-8s %s\n", $1, $2, $3}'
```

```bash
# Pipeline 2: Error rate by hour
tail -n +2 requests.csv \
  | awk -F',' '{
      hour = substr($1, 1, 13)  # "2025-01-15 14"
      total[hour]++
      if ($4 >= 500) errors[hour]++
    }
    END {
      for (h in total)
        printf "%s\t%.1f%%\t(%d/%d)\n", h, (errors[h]+0)/total[h]*100, errors[h]+0, total[h]
    }' \
  | sort
```

```bash
# Pipeline 3: Full report using csvkit (pip install csvkit)
# Filter to POST requests with 5xx errors in January
csvgrep -c method -m POST requests.csv \
  | csvgrep -c status -r '^5' \
  | csvgrep -c timestamp -r '^2025-01' \
  | csvcut -c endpoint,status,response_ms \
  | csvsort -c response_ms -r \
  | csvstat --mean response_ms --count
```

Combine into a report script:

```bash
#!/bin/bash
FILE="${1:?Usage: report.sh <csv_file>}"
echo "=== Request Summary ==="
echo "Total requests: $(tail -n +2 "$FILE" | wc -l)"
echo "Unique endpoints: $(tail -n +2 "$FILE" | cut -d',' -f3 | sort -u | wc -l)"
echo ""
echo "=== Status Distribution ==="
tail -n +2 "$FILE" | cut -d',' -f4 | sort | uniq -c | sort -rn
```'''
    },
    {
        "instruction": r'''How do I use jq to transform a flat list of key-value pairs into a nested JSON structure?''',
        "output": r'''```bash
# Input: flat config-style key-value pairs
echo '{"database.host": "localhost", "database.port": 5432, "database.name": "mydb", "cache.host": "redis", "cache.ttl": 300}' \
  | jq '
    to_entries
    | group_by(.key | split(".")[0])
    | map({
        (.[0].key | split(".")[0]):
        (map({(.key | split(".")[1:]| join(".")): .value}) | add)
      })
    | add
  '
```

Output:
```json
{
  "database": {"host": "localhost", "port": 5432, "name": "mydb"},
  "cache": {"host": "redis", "ttl": 300}
}
```

More transformations:

```bash
# Array of objects -> object keyed by ID
echo '[{"id": "a", "val": 1}, {"id": "b", "val": 2}]' \
  | jq 'map({(.id): .val}) | add'
# {"a": 1, "b": 2}

# Object -> array of objects
echo '{"a": 1, "b": 2, "c": 3}' \
  | jq 'to_entries | map({name: .key, value: .value})'

# Pivot: rows to columns
echo '[{"date": "Mon", "metric": "cpu", "val": 80}, {"date": "Mon", "metric": "mem", "val": 60}]' \
  | jq 'group_by(.date) | map({
      date: .[0].date,
      metrics: map({(.metric): .val}) | add
    })'

# Unflatten dotted keys (generic)
echo '{"a.b.c": 1, "a.b.d": 2, "a.e": 3}' \
  | jq 'to_entries | reduce .[] as $e (
      {};
      setpath($e.key | split("."); $e.value)
    )'
# {"a": {"b": {"c": 1, "d": 2}, "e": 3}}
```'''
    },
    {
        "instruction": r'''Show me how to convert between JSON, CSV, and TSV formats using command-line tools.''',
        "output": r'''```bash
# === JSON to CSV ===
# Using jq (for arrays of objects)
echo '[{"name":"Alice","age":30},{"name":"Bob","age":25}]' \
  | jq -r '(.[0] | keys_unsorted) as $keys | $keys, (.[] | [.[$keys[]]]) | @csv'
# Output:
# "name","age"
# "Alice",30
# "Bob",25

# === CSV to JSON ===
# Using csvkit
csvjson input.csv > output.json

# Using awk (no dependencies)
awk -F',' 'NR==1 {split($0, h); next}
  {printf "{"; for(i=1;i<=NF;i++) printf "%s\"%s\":\"%s\"", (i>1?",":""), h[i], $i; print "}"}
' input.csv

# === JSON to TSV ===
echo '[{"name":"Alice","score":95},{"name":"Bob","score":87}]' \
  | jq -r '(.[0] | keys_unsorted) as $k | $k, (.[] | [.[$k[]]]) | @tsv'

# === TSV to CSV ===
tr '\t' ',' < input.tsv > output.csv
# Or with proper quoting:
awk -F'\t' '{for(i=1;i<=NF;i++){gsub(/"/, "\"\"", $i); printf "%s\"%s\"", (i>1?",":""), $i}; print ""}' input.tsv

# === CSV to TSV ===
csvformat -T input.csv > output.tsv  # csvkit
# Or: sed 's/,/\t/g' input.csv  (only works if no commas in quoted fields)

# === JSONL (one JSON per line) to CSV ===
cat data.jsonl | jq -rs '(.[0]|keys_unsorted) as $k | ($k|@csv), (.[]|[.[$k[]]]|@csv)'

# === CSV to JSONL ===
csvjson --stream input.csv  # csvkit, one JSON per line
```'''
    },
]
