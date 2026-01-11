import json
import sys
import math
import re
import platform
import subprocess

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}", file=sys.stderr)
        return None

def format_val(val):
    if val is None:
        return "N/A"
    # val is in ns
    if val < 1e3:
        return f"{val:.2f}n" # ns
    if val < 1e6:
        return f"{val/1e3:.2f}µ" # us
    if val < 1e9:
        return f"{val/1e6:.2f}m" # ms
    return f"{val/1e9:.2f}s" # s

def main():
    if len(sys.argv) < 3:
        print("Usage: python benchstat_simulator.py base.json pr.json")
        sys.exit(1)

    base_data = load_json(sys.argv[1])
    pr_data = load_json(sys.argv[2])

    if not base_data or not pr_data:
        sys.exit(1)

    base_map = {b["name"]: b["value"] for b in base_data.get("benches", [])}
    pr_map = {b["name"]: b["value"] for b in pr_data.get("benches", [])}

    all_names = sorted(set(base_map.keys()) | set(pr_map.keys()))

    print("Comparison:")
    print("```")
    print("goos: linux")
    print("goarch: amd64")
    print("pkg: github.com/casbin/node-casbin")
    
    cpu_info = "GitHub Actions Runner"
    try:
        if platform.system() == "Windows":
             cpu_info = platform.processor()
        elif platform.system() == "Linux":
            try:
                # Try lscpu first
                command = "lscpu"
                output = subprocess.check_output(command, shell=True).decode()
                for line in output.splitlines():
                    if "Model name" in line:
                        cpu_info = line.split(":")[1].strip()
                        break
            except:
                # Fallback to /proc/cpuinfo
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line:
                            cpu_info = line.split(":")[1].strip()
                            break
    except:
        pass
    print(f"cpu: {cpu_info}")
    
    # Reduced padding: 52 instead of 50
    # Header
    print(f"{'':<52}│ {'base':<19} │           {'pr':<19}           │")
    print(f"{'':<52}│       sec/op        │    sec/op      vs base                │   Diff")

    base_values = []
    pr_values = []

    for name in all_names:
        base_val = base_map.get(name, 0)
        pr_val = pr_map.get(name, 0)

        if base_val > 0: base_values.append(base_val)
        if pr_val > 0: pr_values.append(pr_val)

        def format_cell(val):
            if val == 0: return "N/A"
            return f"{format_val(val)} ± ∞ ¹"

        base_str = format_cell(base_val)
        pr_str = format_cell(pr_val)

        comp_str = ""
        if base_val > 0 and pr_val > 0:
            comp_str = "~ (p=1.000 n=1) ²"
        
        print(f"{name:<52}{base_str:<22}{pr_str:<22}{comp_str}")

    if base_values and pr_values:
        def calc_geo(vals):
            return math.exp(sum(math.log(x) for x in vals) / len(vals))
        g_base = calc_geo(base_values)
        g_pr = calc_geo(pr_values)
        print(f"{'geomean':<52}{format_val(g_base):<22}{format_val(g_pr):<22}")

    print("¹ need >= 6 samples for confidence interval at level 0.95")
    print("² all samples are equal")
    print("³ need >= 4 samples to detect a difference at alpha level 0.05")
    print("⁴ summaries must be >0 to compute geomean")
    print("```")

if __name__ == "__main__":
    main()
