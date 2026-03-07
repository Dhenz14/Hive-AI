"""
Shell/CLI training pairs - File management with find, xargs, rsync, tar.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''I need to find all files larger than 100MB in my home directory that haven't been accessed in 30 days. How can I list them sorted by size?''',
        "output": r'''<think>
I need to combine find with size and access time filters. The flags are:
- `-size +100M` for files over 100MB
- `-atime +30` for files not accessed in 30+ days
- `-type f` to only match regular files

For sorting by size, find alone does not sort. I can use `-printf` to output size and filename, then sort numerically. On macOS, find does not support -printf, so I would need stat instead.

I should also consider: should I follow symlinks? Probably not -- use find without -L. Should I cross filesystem boundaries? Probably not for a home dir scan, but it's worth mentioning -xdev.
</think>

```bash
# Linux (GNU find)
find ~ -type f -size +100M -atime +30 -printf '%s\t%p\n' 2>/dev/null \
  | sort -rn \
  | awk '{printf "%.1f MB\t%s\n", $1/1048576, $2}'
```

This outputs size in bytes with the path, sorts numerically (largest first), then formats as MB.

For macOS (BSD find without -printf):

```bash
find ~ -type f -size +100M -atime +30 2>/dev/null \
  | xargs stat -f '%z %N' \
  | sort -rn \
  | awk '{printf "%.1f MB\t%s\n", $1/1048576, $2}'
```

Useful additions:
- Add `-xdev` to stay on the same filesystem (skip network mounts)
- Add `-not -path '*/.*'` to skip hidden directories
- Redirect stderr to /dev/null to suppress permission denied errors

To also show the last access time:

```bash
find ~ -type f -size +100M -atime +30 \
  -printf '%s\t%A+\t%p\n' 2>/dev/null \
  | sort -rn \
  | awk -F'\t' '{printf "%.0f MB\t%s\t%s\n", $1/1048576, $2, $3}'
```'''
    },
    {
        "instruction": r'''What's the best way to rsync a project directory to a remote server, excluding node_modules, .git, and build artifacts?''',
        "output": r'''```bash
rsync -avz --progress \
  --exclude='node_modules/' \
  --exclude='.git/' \
  --exclude='dist/' \
  --exclude='build/' \
  --exclude='*.pyc' \
  --exclude='__pycache__/' \
  --exclude='.env' \
  ./my-project/ user@server:/opt/deploy/my-project/
```

Key flags:
- `-a` -- archive mode (preserves permissions, timestamps, symlinks)
- `-v` -- verbose output
- `-z` -- compress during transfer
- `--progress` -- show transfer progress per file

Important: the trailing `/` on the source path matters. `./my-project/` copies the contents into the destination. Without the slash, it would create `my-project/my-project/`.

For many excludes, use an exclude file:

```bash
# Create .rsync-exclude
cat > .rsync-exclude << 'EOF'
node_modules/
.git/
dist/
build/
*.pyc
__pycache__/
.env
.DS_Store
*.log
EOF

rsync -avz --progress --exclude-from='.rsync-exclude' \
  ./my-project/ user@server:/opt/deploy/my-project/
```

Add `--dry-run` first to preview what will be transferred:

```bash
rsync -avz --dry-run --exclude-from='.rsync-exclude' \
  ./my-project/ user@server:/opt/deploy/my-project/
```'''
    },
    {
        "instruction": r'''How do I create a tar.gz archive of a directory but exclude certain file patterns, and how do I extract specific files from it later?''',
        "output": r'''Create an archive with exclusions:

```bash
tar czf project-backup.tar.gz \
  --exclude='*.log' \
  --exclude='node_modules' \
  --exclude='.git' \
  ./project/
```

List contents without extracting:

```bash
tar tzf project-backup.tar.gz
# With details (like ls -l)
tar tzvf project-backup.tar.gz
```

Extract specific files or directories:

```bash
# Extract a single file
tar xzf project-backup.tar.gz project/src/main.py

# Extract matching a pattern (GNU tar)
tar xzf project-backup.tar.gz --wildcards '*.py'

# Extract to a specific directory
tar xzf project-backup.tar.gz -C /tmp/restore/
```

Other useful options:

```bash
# Preserve permissions (important for deployments)
tar czpf backup.tar.gz ./project/

# Show progress during creation
tar czf backup.tar.gz ./project/ --checkpoint=1000 --checkpoint-action=dot

# Create with a date stamp in the filename
tar czf "project-$(date +%Y%m%d-%H%M%S).tar.gz" ./project/

# Exclude files listed in a file
tar czf backup.tar.gz -X exclude-list.txt ./project/
```'''
    },
    {
        "instruction": r'''I accidentally have thousands of files with spaces and special characters in their names. I need to rename them to use underscores instead. What's a safe approach?''',
        "output": r'''<think>
Renaming files with special characters is tricky because naive approaches break on spaces, quotes, newlines, etc. I need to:
1. Handle spaces and special chars safely (use -print0 / xargs -0 or find -exec)
2. Only rename files, not directories (or handle directories depth-first)
3. Avoid collisions where the renamed file already exists
4. The rename should convert spaces and problematic chars to underscores

I will use find with -print0 and a bash loop, or the rename/prename utility if available. Let me provide both approaches.
</think>

Safe approach using find and bash:

```bash
# Dry run first -- show what would be renamed
find . -depth -name '*[[:space:]]*' -print0 | while IFS= read -r -d '' file; do
    dir=$(dirname "$file")
    base=$(basename "$file")
    newbase=$(echo "$base" | tr ' ' '_')
    echo "Would rename: $file -> $dir/$newbase"
done

# Actually rename (remove echo, add mv)
find . -depth -name '*[[:space:]]*' -print0 | while IFS= read -r -d '' file; do
    dir=$(dirname "$file")
    base=$(basename "$file")
    newbase=$(echo "$base" | tr ' ' '_')
    [ "$base" != "$newbase" ] && mv -n "$file" "$dir/$newbase"
done
```

Key safety features:
- `-depth` processes children before parents (so directory renames do not break child paths)
- `-print0` and `read -d ''` handle filenames with spaces and newlines
- `mv -n` refuses to overwrite existing files (prevents collisions)
- `IFS=` and `-r` prevent bash from mangling the filenames

For more aggressive cleanup (spaces, parens, brackets, etc.):

```bash
find . -depth -print0 | while IFS= read -r -d '' file; do
    dir=$(dirname "$file")
    base=$(basename "$file")
    newbase=$(echo "$base" | sed 's/[^a-zA-Z0-9._-]/_/g' | sed 's/__*/_/g')
    [ "$base" != "$newbase" ] && mv -n "$file" "$dir/$newbase"
done
```

This replaces any non-alphanumeric character (except `.`, `_`, `-`) with an underscore, then collapses consecutive underscores.'''
    },
    {
        "instruction": r'''Show me how to use xargs to run parallel downloads of a list of URLs from a file.''',
        "output": r'''```bash
# urls.txt contains one URL per line
# Download 4 files in parallel
xargs -P 4 -I {} curl -sOL {} < urls.txt
```

Flags explained:
- `-P 4` -- run up to 4 processes in parallel
- `-I {}` -- replace `{}` with each input line
- `curl -sOL` -- silent, use remote filename, follow redirects

More robust version with wget and progress:

```bash
xargs -P 8 -I {} wget -q --show-progress {} < urls.txt
```

For very large URL lists, add rate limiting and retries:

```bash
xargs -P 4 -I {} sh -c 'curl -sOL --retry 3 --retry-delay 2 "$1" && echo "Done: $1"' _ {} < urls.txt
```

Download to a specific directory:

```bash
mkdir -p downloads
xargs -P 4 -I {} sh -c 'curl -sL "$1" -o "downloads/$(basename $1)"' _ {} < urls.txt
```

If filenames might collide, use content hash:

```bash
xargs -P 4 -I {} sh -c '
    hash=$(echo "$1" | md5sum | cut -d" " -f1)
    ext="${1##*.}"
    curl -sL "$1" -o "downloads/${hash}.${ext}"
' _ {} < urls.txt
```'''
    },
]
