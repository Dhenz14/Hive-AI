"""
Shell/CLI training pairs - Text processing with grep, sed, awk, cut, sort, uniq.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''I have a large Apache access log file. I need to find the top 10 IP addresses making the most requests, but exclude any requests to /health or /status endpoints. How do I do this in bash?''',
        "output": r'''<think>
The user wants to analyze an Apache access log. The standard format has IP as the first field. I need to:
1. Filter out lines containing /health or /status
2. Extract the IP address (first field)
3. Count occurrences and sort by frequency
4. Show top 10

I could use grep -v to exclude, then awk to extract field 1, then sort | uniq -c | sort -rn | head. Alternatively, awk alone could do the filtering and extraction in one pass, which would be more efficient for large files.

Let me go with a pipeline approach -- it's more readable and each step is independently testable.
</think>

Here's the pipeline:

```bash
grep -v -E '/health|/status' access.log \
  | awk '{print $1}' \
  | sort \
  | uniq -c \
  | sort -rn \
  | head -10
```

Breakdown:
- `grep -v -E '/health|/status'` -- exclude lines matching either pattern
- `awk '{print $1}'` -- extract the first field (IP address)
- `sort` -- group identical IPs together (required by uniq)
- `uniq -c` -- count consecutive identical lines
- `sort -rn` -- sort numerically in reverse (highest first)
- `head -10` -- show top 10

For a faster single-pass alternative using only awk:

```bash
awk '!/\/(health|status)/ {count[$1]++} END {for (ip in count) print count[ip], ip}' access.log \
  | sort -rn \
  | head -10
```

This avoids piping through multiple commands, which matters on multi-GB log files.'''
    },
    {
        "instruction": r'''How do I use sed to replace all occurrences of http:// with https:// in every .html file in a directory?''',
        "output": r'''Use `find` with `sed -i` for in-place editing:

```bash
# GNU sed (Linux)
find . -name '*.html' -exec sed -i 's|http://|https://|g' {} +

# macOS (BSD sed requires backup extension)
find . -name '*.html' -exec sed -i '' 's|http://|https://|g' {} +
```

Notes:
- Using `|` as the sed delimiter instead of `/` avoids escaping the slashes in URLs
- `{}  +` passes multiple files to a single sed invocation (faster than `{} \;`)
- The `g` flag replaces all occurrences per line, not just the first
- `-i` edits files in place -- make a backup first if you want safety:

```bash
# Create backups with .bak extension before editing
find . -name '*.html' -exec sed -i.bak 's|http://|https://|g' {} +

# Verify changes look correct, then remove backups
find . -name '*.html.bak' -delete
```'''
    },
    {
        "instruction": r'''I have a CSV file where field 3 is an email address. I need to extract unique domain names and count them. The file has a header row.''',
        "output": r'''<think>
CSV parsing in bash has caveats -- fields might be quoted or contain commas. But for a simple case where field 3 is just an email, cut or awk should work fine. I need to:
1. Skip the header (tail -n +2 or sed 1d or awk NR>1)
2. Extract field 3 (cut -d, -f3)
3. Extract domain from email (everything after @)
4. Count unique domains

I should handle possible quoting and whitespace around the email. Also, the domain comparison should probably be case-insensitive since domains are case-insensitive.
</think>

```bash
tail -n +2 data.csv \
  | cut -d',' -f3 \
  | sed 's/^[[:space:]]*"*//; s/"*[[:space:]]*$//' \
  | awk -F'@' '{print tolower($2)}' \
  | sort \
  | uniq -c \
  | sort -rn
```

Step by step:
- `tail -n +2` -- skip the header row
- `cut -d',' -f3` -- extract the third comma-separated field
- `sed` -- strip any leading/trailing whitespace and quotes
- `awk -F'@' '{print tolower($2)}'` -- extract domain part, lowercase it
- `sort | uniq -c | sort -rn` -- count and rank by frequency

If your CSV has quoted fields with embedded commas, use a proper CSV tool instead:

```bash
# Using csvkit (pip install csvkit)
csvcut -c 3 data.csv \
  | tail -n +2 \
  | awk -F'@' '{print tolower($2)}' \
  | sort | uniq -c | sort -rn
```'''
    },
    {
        "instruction": r'''Show me how to use awk to print a summary of disk usage by filesystem type from df output.''',
        "output": r'''```bash
df -h --output=fstype,size,used,avail | tail -n +2 | awk '
{
    type = $1
    size[type] += $2
    used[type] += $3
    avail[type] += $4
    count[type]++
}
END {
    printf "%-12s %6s %8s %8s %8s\n", "FSTYPE", "COUNT", "SIZE_GB", "USED_GB", "AVAIL_GB"
    printf "%-12s %6s %8s %8s %8s\n", "------", "-----", "-------", "-------", "--------"
    for (t in size) {
        printf "%-12s %6d %8.1f %8.1f %8.1f\n", t, count[t], size[t], used[t], avail[t]
    }
}
'
```

For a simpler version that just groups by filesystem type:

```bash
df -T | tail -n +2 | awk '{fs[$2]+=$3} END {for (t in fs) printf "%s: %.1f GB\n", t, fs[t]/1048576}' | sort -t: -k2 -rn
```

This sums the 1K-blocks column grouped by filesystem type and converts to GB.'''
    },
    {
        "instruction": r'''How do I find and delete all duplicate lines in a file, keeping only the first occurrence of each line?''',
        "output": r'''The classic one-liner using awk:

```bash
awk '!seen[$0]++' input.txt > output.txt
```

How it works:
- `seen[$0]` -- uses the whole line as a hash key
- `++` -- post-increment, so first time it's 0 (falsy becomes truthy with `!`)
- `!seen[$0]++` -- true only for the first occurrence of each line
- awk prints the line when the expression is true

To edit in place (without a temp file):

```bash
# Using sponge from moreutils
awk '!seen[$0]++' file.txt | sponge file.txt

# Or with a temp file
awk '!seen[$0]++' file.txt > file.tmp && mv file.tmp file.txt
```

If you only want to remove adjacent duplicates (like uniq but for the whole file):

```bash
# uniq only removes adjacent duplicates, so sort first
sort file.txt | uniq > output.txt

# To preserve order and remove all duplicates (keep only unique lines):
sort file.txt | uniq -u > only_unique.txt
```

Note: `sort -u` combines sort and unique but changes line order. The awk approach preserves original order.'''
    },
]
