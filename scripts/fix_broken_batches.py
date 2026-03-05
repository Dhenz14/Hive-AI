"""Fix broken batch files by extracting content and rebuilding with proper delimiters."""
import os
import re
import sys
import importlib.util

TRIPLE_SINGLE = "'''"
TRIPLE_DOUBLE = '"""'

UNICODE_MAP = {
    '\u2014': '--', '\u2013': '-', '\u2018': "'", '\u2019': "'",
    '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u2248': '~=',
    '\u2264': '<=', '\u2265': '>=', '\u2260': '!=', '\u2192': '->',
    '\u00d7': 'x', '\u00a0': ' ', '\ufffd': '', '\u200b': '',
    '\u00b0': ' degrees', '\u00b2': '**2', '\u00b3': '**3',
    '\u2022': '*', '\u00b7': '*',
}


def clean_unicode(text):
    for old, new in UNICODE_MAP.items():
        text = text.replace(old, new)
    return text


def extract_and_rebuild(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    content = clean_unicode(content)
    content = re.sub(r'\br"""', '"""', content)
    content = re.sub(r"\br'''", "'''", content)
    content = content.replace(TRIPLE_DOUBLE + '\\\n', TRIPLE_DOUBLE + '\n')

    lines = content.split('\n')

    # Find module docstring
    module_doc = ""
    pairs_idx = -1
    for i, line in enumerate(lines):
        if 'PAIRS' in line and '[' in line:
            pairs_idx = i
            break

    if pairs_idx == -1:
        return None

    pre_pairs = '\n'.join(lines[:pairs_idx])
    for pattern in [r'"""(.*?)"""', r"'''(.*?)'''"]:
        m = re.search(pattern, pre_pairs, re.DOTALL)
        if m:
            module_doc = m.group(1).strip()
            break

    if not module_doc:
        basename = os.path.basename(filepath)
        module_doc = basename.replace('batch_', '').replace('.py', '').replace('_', ' ')

    # Extract pairs content
    pairs_content = '\n'.join(lines[pairs_idx:])

    # Find all tag strings
    tag_pattern = re.compile(r'^\s+"([a-zA-Z0-9/_-]+(?:/[a-zA-Z0-9_-]+)*)"', re.MULTILINE)
    tag_positions = [(m.start(), m.group(1)) for m in tag_pattern.finditer(pairs_content)]

    if not tag_positions:
        return None

    pairs = []
    for idx, (pos, tag) in enumerate(tag_positions):
        if idx + 1 < len(tag_positions):
            end_pos = tag_positions[idx + 1][0]
        else:
            end_pos = len(pairs_content)

        block = pairs_content[pos:end_pos]
        block_lines = block.split('\n')

        prompt_lines = []
        response_lines = []
        in_prompt = True
        skip_first = True

        for bline in block_lines:
            if skip_first:
                skip_first = False
                continue

            stripped = bline.strip()

            if in_prompt:
                if (stripped.startswith('# ') or stripped.startswith('## ') or
                    stripped.startswith('```') or
                    (len(stripped) > 100 and not stripped.startswith('"')) or
                    stripped.startswith('**')):
                    in_prompt = False
                    response_lines.append(bline)
                elif stripped.startswith((TRIPLE_DOUBLE, TRIPLE_SINGLE)):
                    if not prompt_lines:
                        cleaned = re.sub(r'^["\']+(.*)', r'\1', stripped)
                        if cleaned:
                            prompt_lines.append(cleaned)
                    else:
                        in_prompt = False
                elif stripped.endswith((TRIPLE_DOUBLE, TRIPLE_SINGLE)):
                    cleaned = re.sub(r'["\']+[,]?$', '', stripped)
                    if cleaned:
                        prompt_lines.append(cleaned)
                else:
                    cleaned = stripped.strip('"').strip("'").strip(',').strip()
                    if cleaned and cleaned not in ('",', "',", ',', ''):
                        prompt_lines.append(cleaned)
            else:
                if stripped in ('),', ')'):
                    break
                response_lines.append(bline)

        prompt = ' '.join(prompt_lines).strip()
        for q in [TRIPLE_DOUBLE, TRIPLE_SINGLE]:
            prompt = prompt.replace(q, '')
        prompt = prompt.strip().strip('"').strip("'").strip(',').strip()

        response = '\n'.join(response_lines).strip()
        for q in [TRIPLE_DOUBLE, TRIPLE_SINGLE]:
            if response.startswith(q):
                response = response[3:]
            if response.endswith(q):
                response = response[:-3]
        response = response.strip()

        if tag and prompt and response and len(response) > 100:
            # Ensure response doesn't contain ''' (our delimiter)
            if TRIPLE_SINGLE in response:
                response = response.replace(TRIPLE_SINGLE, TRIPLE_DOUBLE)
            pairs.append((tag, prompt, response))

    if not pairs:
        return None

    # Rebuild
    out = []
    out.append(TRIPLE_DOUBLE + module_doc + TRIPLE_DOUBLE)
    out.append('')
    out.append('PAIRS = [')

    for tag, prompt, response in pairs:
        prompt_clean = prompt.replace('"', "'")
        out.append('    (')
        out.append(f'        "{tag}",')
        out.append(f'        "{prompt_clean}",')
        out.append(f'        {TRIPLE_SINGLE}{response}{TRIPLE_SINGLE}')
        out.append('    ),')

    out.append(']')
    result = '\n'.join(out) + '\n'

    try:
        compile(result, filepath, 'exec')
        return result
    except SyntaxError:
        # Try with """ for responses, ''' for internal
        out2 = []
        out2.append(TRIPLE_SINGLE + module_doc + TRIPLE_SINGLE)
        out2.append('')
        out2.append('PAIRS = [')
        for tag, prompt, response in pairs:
            # Swap: if response has """ that would conflict with outer """, use '''
            resp = response
            if TRIPLE_DOUBLE in resp:
                resp = resp.replace(TRIPLE_DOUBLE, TRIPLE_SINGLE)
            prompt_clean = prompt.replace('"', "'")
            out2.append('    (')
            out2.append(f'        "{tag}",')
            out2.append(f'        "{prompt_clean}",')
            out2.append(f'        {TRIPLE_DOUBLE}{resp}{TRIPLE_DOUBLE}')
            out2.append('    ),')
        out2.append(']')
        result2 = '\n'.join(out2) + '\n'
        try:
            compile(result2, filepath, 'exec')
            return result2
        except SyntaxError:
            return None


def main():
    batch_dir = 'scripts/distill_batches'
    broken_files = [
        'batch_p120_cli_tools.py', 'batch_p12_accessibility.py', 'batch_p12_testing.py',
        'batch_p12_web_scraping.py', 'batch_p13_reactive_systems.py', 'batch_p14_docker_deep.py',
        'batch_p14_git_internals.py', 'batch_p14_python_async.py', 'batch_p14_redis_patterns.py',
        'batch_p14_sql_optimization.py', 'batch_p15_ddd.py', 'batch_p15_grpc.py',
        'batch_p16_transformer_arch.py', 'batch_p16_vector_databases.py', 'batch_p171_sqlalchemy_async.py',
        'batch_p17_resilience_patterns.py', 'batch_p184_container_optimization.py',
        'batch_p185_immutable_infra.py', 'batch_p18_data_structures.py', 'batch_p191_timeseries_db.py',
        'batch_p19_python_tooling.py', 'batch_p202_supply_chain_security.py', 'batch_p20_networking.py',
        'batch_p21_patterns.py', 'batch_p288_cli_tools.py', 'batch_p5_compilers.py',
        'batch_p9_code_gen_ai.py',
    ]

    fixed = 0
    still_broken = []

    for fname in broken_files:
        fpath = os.path.join(batch_dir, fname)
        if not os.path.exists(fpath):
            still_broken.append(fname)
            continue

        result = extract_and_rebuild(fpath)
        if result:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(result)
            # Verify
            spec = importlib.util.spec_from_file_location('mod', fpath)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                n = len(mod.PAIRS)
                if n > 0:
                    fixed += 1
                    print(f"  OK: {fname} -> {n} pairs")
                else:
                    still_broken.append(fname)
                    print(f"  EMPTY: {fname} -> 0 pairs")
            except Exception as e:
                still_broken.append(fname)
                print(f"  FAIL-IMPORT: {fname} -> {str(e)[:60]}")
        else:
            still_broken.append(fname)
            print(f"  SKIP: {fname} -> extraction failed")

    print(f"\nFixed: {fixed}/{len(broken_files)}")
    print(f"Still broken: {len(still_broken)}")
    for b in still_broken:
        print(f"  {b}")


if __name__ == '__main__':
    main()
