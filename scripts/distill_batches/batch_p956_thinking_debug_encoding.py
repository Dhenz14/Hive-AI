PAIRS = [
    ("thinking/debugging", r'''My Python script fails when reading a CSV file that works fine in Excel:

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xef at position 0: invalid continuation byte
```

Code:
```python
with open('data.csv', 'r', encoding='utf-8') as f:
    content = f.read()
```

Hex dump of the first few bytes:
```
EF BB BF 22 6E 61 6D 65 22 2C 22 61 67 65 22
```

The file opens perfectly in Excel and Notepad. What's wrong?''', r'''<think>
Looking at the hex dump: EF BB BF -- those are the bytes for the UTF-8 BOM (Byte Order Mark). The BOM is U+FEFF encoded in UTF-8.

The error says "'utf-8' codec can't decode byte 0xef at position 0". Wait, that does not make sense. UTF-8 can decode BOM bytes just fine -- 0xEF starts a valid 3-byte sequence, and 0xBB and 0xBF are valid continuation bytes (10xxxxxx pattern). So the 'utf-8' codec should handle this without error.

Hmm, let me reconsider. Maybe the user tried 'ascii' first and is showing a slightly inaccurate error message, or maybe the file has non-UTF-8 bytes further in that are causing the actual error, not the BOM. The error says "position 0" which points to the first byte, but that could also be misleading if the user is paraphrasing.

Actually, I think there might be two separate issues here. The BOM is definitely present (the hex dump confirms it), and even though it does not cause a decode error with 'utf-8', it WILL cause subtle bugs: the BOM character U+FEFF becomes an invisible prefix on the first CSV field, so `row['name']` would actually be `row['\ufeffname']`, which silently fails key lookups. The actual UnicodeDecodeError might be from a different encoding issue elsewhere in the file.

The practical fix is to use 'utf-8-sig' which strips the BOM. This handles both problems: it removes the invisible BOM prefix AND still decodes valid UTF-8. I should also mention chardet for detecting files that are not actually UTF-8 at all (e.g., Windows-1252 or Latin-1), since that could be the real source of the decode error.
</think>

The bytes `EF BB BF` at the start of the file are the UTF-8 BOM (Byte Order Mark). This is a special 3-byte sequence that some editors (notably Windows Notepad and Excel) prepend to UTF-8 files to signal the encoding.

While Python's `'utf-8'` codec can technically decode BOM bytes, the BOM character (U+FEFF) ends up in your data as an invisible character at the start of the first field. This causes subtle bugs: string comparisons fail, CSV headers have an invisible prefix, and JSON parsing may choke.

The real fix depends on whether the actual error comes from the BOM or from mixed encoding later in the file.

**Fix 1: Use utf-8-sig to strip the BOM**

```python
with open('data.csv', 'r', encoding='utf-8-sig') as f:
    content = f.read()
```

The `'utf-8-sig'` codec works exactly like `'utf-8'` but automatically strips a leading BOM if present. If there is no BOM, it behaves identically to `'utf-8'`. This is the correct encoding to use for files that might come from Windows tools.

**Fix 2: For CSV files specifically**

```python
import csv

with open('data.csv', 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(row['name'])  # Without utf-8-sig, key would be '\ufeffname'
```

Without `utf-8-sig`, the first column header would be `'\ufeffname'` instead of `'name'`, and `row['name']` would raise a KeyError.

**Fix 3: For pandas**

```python
import pandas as pd

# pandas handles BOM automatically with engine='python'
df = pd.read_csv('data.csv', encoding='utf-8-sig')
```

**If the actual error is about non-UTF-8 bytes elsewhere in the file:**

```python
# Detect the actual encoding
import chardet

with open('data.csv', 'rb') as f:
    raw = f.read()
    result = chardet.detect(raw)
    print(result)
    # {'encoding': 'Windows-1252', 'confidence': 0.73}

# Then open with the detected encoding
with open('data.csv', 'r', encoding=result['encoding']) as f:
    content = f.read()
```

**Handling mixed encodings (common with user-uploaded data):**

```python
with open('data.csv', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()  # replaces undecodable bytes with the Unicode replacement char
```

**Prevention tips:**
- Always use `'utf-8-sig'` when reading files that might originate from Windows
- When writing files, use `'utf-8'` (without BOM) unless the consumer specifically requires BOM
- Validate encoding early in your data pipeline
- Store the detected encoding alongside uploaded files for later processing
- Use the `chardet` or `charset-normalizer` library for automatic encoding detection'''),

    ("thinking/debugging", r'''My application crashes when processing user input from a web form:

```
UnicodeEncodeError: 'latin-1' codec can't encode character '\u2019' in position 15: ordinal not in range(256)
```

The input contains a smart quote (right single quotation mark). Code:

```python
import smtplib
from email.mime.text import MIMEText

def send_notification(user_name, message):
    msg = MIMEText(message)
    msg['Subject'] = f'Message from {user_name}'
    msg['From'] = 'noreply@example.com'
    msg['To'] = 'admin@example.com'

    with smtplib.SMTP('localhost') as server:
        server.send_message(msg)
```

The message variable contains: "Don\u2019t forget to check" (with a smart quote from a mobile keyboard). Why is latin-1 involved? I never specified it.''', r'''<think>
The user never specified latin-1 anywhere, so why is it involved? Let me trace through the email library internals.

The MIMEText constructor defaults to charset 'us-ascii' for plain text. When it encounters characters outside ASCII, it falls back to encoding detection. I initially thought this might use utf-8 as a fallback, but actually the behavior depends on the Python version and the specific code path.

Looking more carefully: `MIMEText(message)` with no charset parameter will try to encode the text body. In Python 3.6+, the email library was rewritten to handle non-ASCII better, but the SMTP protocol itself has legacy constraints -- headers are traditionally limited to ASCII/latin-1 encoding. The specific error "latin-1 codec can't encode" suggests the issue is in the SMTP layer when encoding the Subject header, not the message body.

But wait, where exactly does latin-1 come in? The Subject header contains `f'Message from {user_name}'`, which includes the smart quote. SMTP headers must be pure ASCII (or RFC 2047 encoded). The email library's internal encoding path tries latin-1 as an intermediate step. U+2019 is code point 0x2019, well above the latin-1 range of 0x00-0xFF, so this fails.

Hmm, I considered whether just specifying `charset='utf-8'` in MIMEText would fix the Subject header too, but actually no -- MIMEText's charset only affects the body encoding. The Subject header needs separate treatment with `email.header.Header()` for proper RFC 2047 encoding. The modern EmailMessage API handles both automatically, which is a simpler fix overall.
</think>

The `latin-1` codec is being used internally by Python's email/SMTP libraries as the default encoding for message content. The smart quote character U+2019 (right single quotation mark) has a Unicode code point of 0x2019, which is outside the Latin-1 range of 0x00-0xFF.

**Why latin-1 is involved:**

`MIMEText(message)` without a charset parameter tries to encode the text body. Python's email library uses a charset detection chain: it tries `us-ascii` first, then `utf-8`. However, certain code paths in the SMTP layer and header encoding still use `latin-1` as a fallback, particularly for the Subject header which contains the user name.

**Fix: Explicitly specify UTF-8 encoding**

```python
from email.mime.text import MIMEText
from email.header import Header
import smtplib

def send_notification(user_name, message):
    # Explicitly use utf-8 for the message body
    msg = MIMEText(message, 'plain', 'utf-8')

    # Use Header for proper RFC 2047 encoding of non-ASCII in headers
    msg['Subject'] = Header(f'Message from {user_name}', 'utf-8')
    msg['From'] = 'noreply@example.com'
    msg['To'] = 'admin@example.com'

    with smtplib.SMTP('localhost') as server:
        server.send_message(msg)
```

**What this does:**

1. `MIMEText(message, 'plain', 'utf-8')` encodes the body as UTF-8 and sets the `Content-Type: text/plain; charset="utf-8"` header
2. `Header(subject, 'utf-8')` encodes the subject using RFC 2047 encoding, which represents non-ASCII characters as `=?utf-8?q?...?=` sequences that are valid in SMTP headers

**Alternative: Use the modern email.message API (Python 3.6+)**

```python
from email.message import EmailMessage
import smtplib

def send_notification(user_name, message):
    msg = EmailMessage()
    msg['Subject'] = f'Message from {user_name}'
    msg['From'] = 'noreply@example.com'
    msg['To'] = 'admin@example.com'
    msg.set_content(message)  # automatically handles encoding

    with smtplib.SMTP('localhost') as server:
        server.send_message(msg)
```

`EmailMessage` with `set_content()` automatically detects non-ASCII content and uses the appropriate encoding. This is the recommended approach for Python 3.6+.

**Sanitize user input as a defense-in-depth measure:**

```python
import unicodedata

def normalize_text(text):
    """Replace smart quotes and other typographic characters with ASCII equivalents."""
    replacements = {
        '\u2018': "'",   # left single quote
        '\u2019': "'",   # right single quote
        '\u201c': '"',   # left double quote
        '\u201d': '"',   # right double quote
        '\u2013': '-',   # en dash
        '\u2014': '--',  # em dash
        '\u2026': '...', # ellipsis
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text
```

**Prevention tips:**
- Always specify `charset='utf-8'` when creating MIME messages
- Use the modern `EmailMessage` API instead of the legacy `MIMEText`
- Test with non-ASCII input (accented characters, CJK, emoji) during development
- Use `Header()` for any header that might contain user-supplied text
- Log the repr() of strings when debugging encoding issues to see the actual code points'''),

    ("thinking/debugging", r'''I'm getting surrogate escape errors when processing filenames from a Linux filesystem:

```
UnicodeEncodeError: 'utf-8' codec can't encode character '\udce9' in position 8: surrogates not allowed
```

Code:
```python
import os
import json

def list_files(directory):
    files = []
    for entry in os.scandir(directory):
        files.append({'name': entry.name, 'size': entry.stat().st_size})
    return json.dumps(files)
```

The filesystem has files created by a legacy application that used Latin-1 encoding for filenames. Python reads them with surrogate escapes. How do I handle this?''', r'''<think>
On Linux, filenames are byte sequences. They are NOT required to be valid UTF-8 -- the only byte not allowed in a filename is 0x00 (null) and 0x2F (slash). Python 3 uses the "surrogateescape" error handler when decoding filenames from the OS.

My first thought was "just use utf-8 with errors='replace'"... but wait, that would permanently lose the original byte information. The surrogateescape handler is specifically designed to be reversible -- each invalid byte 0xNN is mapped to surrogate character U+DCNN (in the range U+DC80 to U+DCFF). These surrogates are not valid Unicode code points, but they preserve the original bytes for roundtripping.

For example, the byte 0xE9 (which is the Latin-1 encoding of "e-acute") is not valid as a standalone UTF-8 byte. Python maps it to U+DCE9 -- a surrogate character. When the user tries to pass this to json.dumps(), it fails because json.dumps uses strict UTF-8 encoding and surrogates are not valid Unicode.

I considered several approaches. Option 1: re-encode to bytes using surrogateescape, then decode with Latin-1 -- this gives the correct display name but assumes the legacy encoding is Latin-1 (what if it is actually Shift-JIS?). Option 2: use errors='replace' for lossy but safe conversion -- good for display but bad for data processing. Option 3: fix the filenames on disk -- this is the cleanest long-term solution but requires coordination with any systems that reference the old filenames.

The tradeoff between preserving data fidelity and producing valid Unicode is unavoidable here. For JSON output, we must produce valid UTF-8, so some transformation is necessary.
</think>

On Linux, filenames are raw byte sequences with no enforced encoding. When Python 3 reads a filename that contains bytes invalid for UTF-8, it uses the "surrogateescape" error handler: each invalid byte `0xNN` becomes the surrogate character `U+DCNN`. These surrogates are placeholders that preserve the original bytes, but they are not valid Unicode and cannot be encoded to UTF-8.

Your file has a name containing byte `0xE9` (the Latin-1 encoding of the accented letter "e"). Python maps it to `\udce9`. When `json.dumps()` tries to encode this to UTF-8, it rightfully rejects the surrogate.

**Fix 1: Re-encode filenames from bytes with the correct encoding**

```python
import os
import json

def safe_filename(name):
    """Convert a filename with surrogates back to a readable string."""
    # Encode back to bytes using surrogateescape, then decode as latin-1
    try:
        raw_bytes = name.encode('utf-8', 'surrogateescape')
        return raw_bytes.decode('latin-1')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name.encode('utf-8', 'replace').decode('utf-8')

def list_files(directory):
    files = []
    for entry in os.scandir(directory):
        files.append({
            'name': safe_filename(entry.name),
            'size': entry.stat().st_size,
        })
    return json.dumps(files, ensure_ascii=False)
```

**Fix 2: Use os.fsencode to work with raw bytes**

```python
import os
import json

def list_files(directory):
    files = []
    for entry in os.scandir(directory):
        # Get the raw bytes of the filename
        raw_name = os.fsencode(entry.name)
        # Decode with a forgiving encoding
        display_name = raw_name.decode('utf-8', errors='replace')
        files.append({
            'name': display_name,
            'size': entry.stat().st_size,
        })
    return json.dumps(files, ensure_ascii=False)
```

**Fix 3: Use json.dumps with a custom encoder**

```python
import json

class SurrogateEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, str):
            # Replace surrogates with the Unicode replacement character
            obj = obj.encode('utf-8', 'surrogateescape').decode('utf-8', 'replace')
        return super().encode(obj)

def list_files(directory):
    files = []
    for entry in os.scandir(directory):
        files.append({'name': entry.name, 'size': entry.stat().st_size})
    return json.dumps(files, cls=SurrogateEncoder)
```

**Fix 4: Rename the problematic files (fix at the source)**

```python
import os

def fix_filenames(directory):
    for entry in os.scandir(directory):
        raw_name = os.fsencode(entry.name)
        try:
            raw_name.decode('utf-8')  # test if valid UTF-8
        except UnicodeDecodeError:
            # Convert from latin-1 to UTF-8
            new_name = raw_name.decode('latin-1')
            old_path = os.path.join(directory, entry.name)
            new_path = os.path.join(directory, new_name)
            os.rename(old_path, new_path)
            print(f"Renamed: {raw_name!r} -> {new_name}")
```

**Understanding the surrogate escape cycle:**

```
Filesystem bytes:  [0x66, 0x69, 0x6c, 0xe9]  -> "fil\xe9" in latin-1
Python str:        "fil\udce9"                 -> 0xe9 became surrogate U+DCE9
Encode to bytes:   b"fil\xe9"                 -> using 'surrogateescape' handler
Decode as latin-1: "file"                     -> correct display name
```

**Prevention tips:**
- Always handle surrogateescape when processing filenames from Linux
- Use `os.fsencode()` / `os.fsdecode()` for safe roundtripping
- Set `LANG=en_US.UTF-8` in production to encourage UTF-8 filenames
- Validate and fix legacy filenames during migration instead of handling surrogates forever'''),

    ("thinking/debugging", r'''JSON files from our Java backend contain Unicode escape sequences that Python handles differently:

```python
import json

data = '{"message": "Price: \\u20AC100"}'
parsed = json.loads(data)
print(parsed['message'])  # Expected: Price: EUR100 (euro sign)
# Got: Price: \u20AC100
```

The JSON is generated by Java's Jackson library. The Unicode escape is not being decoded. But if I use single backslashes, it works:

```python
data2 = '{"message": "Price: \u20AC100"}'
parsed2 = json.loads(data2)
print(parsed2['message'])  # Price: EUR100 -- correct!
```

What's the difference?''', r'''<think>
This is about the difference between Python string escapes and JSON string escapes. There are two levels of escaping to track, which makes this confusing.

In `'{"message": "Price: \\u20AC100"}'`:
- The `\\u20AC` in the Python string literal produces a single backslash followed by `u20AC` in the actual string.
- So the string passed to json.loads is: `{"message": "Price: \u20AC100"}`
- json.loads sees `\u20AC` in the JSON and should decode it as the Euro sign.

Wait, that should work then. The user says it does NOT work and they get the literal string `\u20AC100`. Let me re-read their code...

Hmm, actually the user's example output says "Got: Price: \u20AC100" -- meaning the literal backslash-u sequence appears in the output instead of the Euro sign. But based on my analysis, `json.loads('{"message": "Price: \\u20AC100"}')` should produce the Euro sign. Something does not add up.

Unless... the actual data from the Java backend has DOUBLE-escaped backslashes in the JSON itself! If Jackson produces: `{"message": "Price: \\u20AC100"}` (with a literal double backslash in the serialized JSON bytes), then:
- In JSON, `\\` represents a single literal backslash character
- The decoded JSON string value is `Price: \u20AC100` (literal characters, not a Unicode escape)
- json.loads would correctly produce a string with a literal backslash -- no Euro sign

And to represent this doubly-escaped JSON in Python source, you would need four backslashes: `'\\\\u20AC'`. So the user's Python code with `\\u20AC` actually corresponds to a correctly-escaped JSON unicode sequence that SHOULD decode. The real problem is likely that the data coming from the wire has an extra level of escaping that the user is not seeing in their test case.

This is the classic double-escaping problem between Java and Python. Jackson's ESCAPE_NON_ASCII feature can cause this by converting Unicode characters to `\uXXXX` and then the JSON serializer escapes the backslash again.
</think>

This is a multi-level escaping issue. You need to distinguish between Python string escapes and JSON string escapes.

**Level 1: Python string literal**

In `'{"message": "Price: \\u20AC100"}'`:
- `\\u20AC` in Python source code becomes `\u20AC` in the actual string (double backslash becomes single)
- The string passed to `json.loads()` is: `{"message": "Price: \u20AC100"}`

**Level 2: JSON parsing**

`json.loads()` sees `\u20AC` inside the JSON string value and correctly interprets it as the Euro sign Unicode escape. This SHOULD produce the Euro sign character.

**But if your actual data has double-escaped backslashes:**

If the Java backend is producing JSON like this (with a literal double backslash):
```json
{"message": "Price: \\u20AC100"}
```

Then in JSON:
- `\\` represents a single literal backslash character
- The decoded value is `Price: \u20AC100` (literal characters, not a Unicode escape)

To represent this doubly-escaped JSON in Python source code:
```python
data = '{"message": "Price: \\\\u20AC100"}'
# or equivalently:
data = r'{"message": "Price: \\u20AC100"}'
```

**Diagnosing the actual escaping:**

```python
# Print the raw bytes to see what you actually have
data = '{"message": "Price: \\u20AC100"}'
print(repr(data))
# '{"message": "Price: \\u20AC100"}'
# The repr shows \\ which means ONE actual backslash in the string

# Check what json.loads produces
parsed = json.loads(data)
print(repr(parsed['message']))
# Should be 'Price: \u20ac100' -- the Euro sign character
```

If `json.loads` is producing a literal backslash in the result, your input has double-escaped backslashes.

**Fix for over-escaped JSON from Java:**

```python
import json

def fix_double_escaped_json(raw_json):
    """Handle JSON where unicode escapes are double-escaped."""
    # First parse: resolves JSON structural escaping
    parsed = json.loads(raw_json)
    # Second pass: resolve any remaining unicode escapes in string values
    return json.loads(json.dumps(parsed))

# Or fix at the string level before parsing:
import re

def unescape_unicode(s):
    """Convert literal \\uXXXX sequences to actual Unicode characters."""
    return re.sub(
        r'\\u([0-9a-fA-F]{4})',
        lambda m: chr(int(m.group(1), 16)),
        s
    )
```

**Fix the Java backend (preferred):**

In Jackson, ensure you are not double-escaping:

```java
ObjectMapper mapper = new ObjectMapper();
// Do NOT use ESCAPE_NON_ASCII if you want raw Unicode in JSON
mapper.configure(JsonGenerator.Feature.ESCAPE_NON_ASCII, false);
```

**Prevention tips:**
- Always use `repr()` to inspect strings when debugging encoding issues -- it shows the actual escape sequences
- Count the backslashes carefully: `\\` in source = `\` in string, `\\\\` in source = `\\` in string
- Use raw strings (`r'...'`) for JSON test data to avoid one level of escaping
- Validate JSON encoding at API boundaries using `json.loads(json.dumps(data))` roundtrip tests
- Agree on a UTF-8-everywhere policy between frontend and backend teams'''),

    ("thinking/debugging", r'''Reading a CSV file with mixed encodings -- some rows have Latin-1 characters, others have UTF-8:

```python
import csv

with open('export.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
        try:
            print(row)
        except Exception as e:
            print(f"Row {i}: {e}")
```

Error on row 1547:
```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 23: invalid continuation byte
```

The file was created by concatenating exports from two different systems. How do I read it?''', r'''<think>
The file has mixed encodings because it was created by concatenating exports from two different systems. Some rows are valid UTF-8, others are Latin-1. Byte 0xE9 is "e-acute" in Latin-1 but is an invalid start of a 2-byte UTF-8 sequence (would need a continuation byte 10xxxxxx after it, but the next byte does not have that pattern).

My first thought was to use `errors='replace'` or `errors='surrogateescape'` as the encoding error handler. But wait -- `errors='replace'` is lossy (it destroys the original characters with a replacement symbol), and `errors='surrogateescape'` produces surrogates that will break downstream JSON serialization or database storage.

I then considered using chardet to detect the encoding of the entire file, but that will not work here because the file is genuinely mixed -- no single encoding is correct for all rows. Chardet would pick whichever encoding matches the majority and mangle the rest.

The most robust approach is to read as binary and decode each line individually: try UTF-8 first, and if that fails, fall back to Latin-1. Latin-1 is a safe fallback because it can decode ANY byte sequence (it maps all 256 byte values to characters), so it will never throw an error. The tradeoff is that if a non-Latin-1 encoding is present (like Shift-JIS or CP1252), the fallback will produce incorrect characters. But for the common case of UTF-8 + Latin-1 mixed files from Western European systems, this approach works well.

I should also mention the caveat about multi-line CSV fields -- if a quoted field spans multiple lines, the line-by-line approach would split it incorrectly. But for most real-world mixed-encoding CSVs, the line-by-line approach is sufficient.
</think>

A file with mixed encodings cannot be opened with a single encoding parameter. You need to read it as binary and decode each line individually, trying UTF-8 first and falling back to Latin-1.

**Fix 1: Read as binary, decode per-line with fallback**

```python
import csv
import io

def read_mixed_csv(filepath):
    rows = []
    with open(filepath, 'rb') as f:
        for line_num, raw_line in enumerate(f):
            try:
                line = raw_line.decode('utf-8')
            except UnicodeDecodeError:
                line = raw_line.decode('latin-1')

            reader = csv.reader(io.StringIO(line))
            for row in reader:
                rows.append(row)
    return rows

rows = read_mixed_csv('export.csv')
```

**Fix 2: Use chardet for per-line detection**

```python
import csv
import io
import chardet

def read_mixed_csv_detected(filepath):
    rows = []
    with open(filepath, 'rb') as f:
        for raw_line in f:
            detected = chardet.detect(raw_line)
            encoding = detected['encoding'] or 'utf-8'
            line = raw_line.decode(encoding, errors='replace')
            reader = csv.reader(io.StringIO(line))
            for row in reader:
                rows.append(row)
    return rows
```

Note: chardet per line is slow. Use it only when you need to handle many possible encodings.

**Fix 3: Use errors='replace' for lossy but safe reading**

```python
import csv

with open('export.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.reader(f)
    for row in reader:
        print(row)
```

This replaces undecodable bytes with the Unicode replacement character (a diamond with a question mark). You lose the original characters but avoid crashes. Good for logging or display, bad for data processing.

**Fix 4: Normalize the file before processing**

```python
def normalize_csv_encoding(input_path, output_path):
    """Convert a mixed-encoding CSV to clean UTF-8."""
    with open(input_path, 'rb') as fin, \
         open(output_path, 'w', encoding='utf-8', newline='') as fout:

        for raw_line in fin:
            try:
                line = raw_line.decode('utf-8')
            except UnicodeDecodeError:
                line = raw_line.decode('latin-1')
            fout.write(line)

    print(f"Normalized file written to {output_path}")

normalize_csv_encoding('export.csv', 'export_clean.csv')
```

Run this once, then use the clean file for all subsequent processing.

**Fix 5: Handle multi-line CSV fields correctly**

The line-by-line approach above breaks if CSV fields contain embedded newlines (quoted fields spanning multiple lines). For that, use a binary CSV reader:

```python
import csv
import io

def decode_row(row_bytes):
    """Decode a list of byte strings with encoding fallback."""
    decoded = []
    for cell in row_bytes:
        if isinstance(cell, bytes):
            try:
                decoded.append(cell.decode('utf-8'))
            except UnicodeDecodeError:
                decoded.append(cell.decode('latin-1'))
        else:
            decoded.append(cell)
    return decoded

# For files with simple structure (no multi-line fields),
# the line-by-line approach is safest
```

**Prevention tips:**
- Fix encoding at the source: ensure all exporting systems use UTF-8
- When concatenating files, re-encode to a common encoding first
- Add encoding validation as a step in your data pipeline
- Store the source encoding as metadata alongside exported files
- Use `file` command on Linux or `chardet` to detect encoding before processing'''),
]
