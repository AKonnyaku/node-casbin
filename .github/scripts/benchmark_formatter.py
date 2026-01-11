import pathlib, re, sys

try:
    p = pathlib.Path("comparison.md")
    if not p.exists():
        print("comparison.md not found, skipping post-processing.")
        sys.exit(0)

    lines = p.read_text(encoding="utf-8").splitlines()
    processed_lines = []
    in_code = False

    def strip_worker_suffix(text: str) -> str:
        # Also strip "Benchmark" prefix if it somehow sneaked in
        text = re.sub(r"^Benchmark", "", text)
        return re.sub(r"(\S+?)-\d+(\s|$)", r"\1\2", text)

    def get_icon(diff_val: float) -> str:
        if diff_val > 10:
            return "🐌"
        if diff_val < -10:
            return "🚀"
        return "➡️"

    def clean_superscripts(text: str) -> str:
        return re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]", "", text)

    def parse_val(token: str):
        if "%" in token or "=" in token:
            return None
        token = clean_superscripts(token)
        token = token.split("±")[0].strip()
        token = token.split("(")[0].strip()
        if not token:
            return None

        m = re.match(r"^([-+]?\d*\.?\d+)([a-zA-Zµ]+)?$", token)
        if not m:
            return None
        try:
            val = float(m.group(1))
        except ValueError:
            return None
        suffix = (m.group(2) or "").replace("µ", "u")
        
        if suffix in ["n", "ns"]: return val * 1e-9
        if suffix in ["u", "us"]: return val * 1e-6
        if suffix in ["m", "ms"]: return val * 1e-3
        if suffix == "s": return val
        if suffix == "": return val # Handle unitless numbers (e.g. counts) if any
        
        # If we reach here, it's an unexpected unit
        raise ValueError(f"Unexpected unit: {suffix}")

    def extract_two_numbers(tokens):
        found = []
        for t in tokens[1:]:  # skip name
            if t in {"±", "∞", "~", "│", "|"}:
                continue
            if "%" in t or "=" in t:
                continue
            # Skip p=... n=...
            if t.startswith("p=") or t.startswith("n="):
                continue
                
            val = parse_val(t)
            if val is not None:
                found.append(val)
                if len(found) == 2:
                    break
        return found

    # Pass 0: Calculate widths
    max_content_width = 0

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            continue

        if re.match(r"^\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]", line) or re.search(r"need\s*>?=\s*\d+\s+samples", line):
            continue
        if not line.strip() or line.strip().startswith(("goos:", "goarch:", "pkg:", "cpu:")):
            continue
        if "│" in line and ("vs base" in line or "old" in line or "new" in line):
            continue

        curr_line = strip_worker_suffix(line).rstrip()
        w = len(curr_line)
        if w > max_content_width:
            max_content_width = w

    diff_col_start = max_content_width - 13
    # User asked to shift first column by 8 chars. 
    # This means the whole table shifts right? Or just the text inside?
    # I'll prepend 8 spaces to the final output line.
    INDENT = "        "

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            processed_lines.append(line)
            continue

        if not in_code:
            processed_lines.append(line)
            continue

        # Footnotes
        if re.match(r"^\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]", line) or re.search(r"need\s*>?=\s*\d+\s+samples", line):
            processed_lines.append(INDENT + line)
            continue

        # Header
        if "│" in line and ("vs base" in line or "old" in line or "new" in line):
            stripped_header = line.rstrip().rstrip("│").rstrip()
            stripped_header = re.sub(r"\s+Diff\s*$", "", stripped_header, flags=re.IGNORECASE)
            
            if len(stripped_header) < diff_col_start:
                new_header = stripped_header + " " * (diff_col_start - len(stripped_header))
            else:
                new_header = stripped_header + "  "
            
            if "vs base" in line:
                new_header += "Diff"
            
            new_header += "│"
            processed_lines.append(INDENT + new_header)
            continue

        # Metadata
        if not line.strip() or line.strip().startswith(("goos:", "goarch:", "pkg:", "cpu:")):
            processed_lines.append(INDENT + line)
            continue

        # Data Lines
        original_line = line
        line = strip_worker_suffix(line)
        tokens = line.split()
        if not tokens:
            processed_lines.append(INDENT + line)
            continue

        numbers = extract_two_numbers(tokens)
        
        def append_aligned(left_part, content):
            if len(left_part) < diff_col_start:
                aligned = left_part + " " * (diff_col_start - len(left_part))
            else:
                aligned = left_part + "  "
            return f"{INDENT}{aligned}{content}"

        # Geomean
        is_geomean = tokens[0] == "geomean"
        
        if len(numbers) == 2 and numbers[0] != 0:
            diff_val = (numbers[1] - numbers[0]) / numbers[0] * 100
            icon = get_icon(diff_val)
            left = line.rstrip()
            processed_lines.append(append_aligned(left, f"{diff_val:+.2f}% {icon}"))
            continue
            
        processed_lines.append(INDENT + line)

    p.write_text("\n".join(processed_lines) + "\n", encoding="utf-8")

except Exception as e:
    print(f"Error post-processing comparison.md: {e}")
    sys.exit(1)
