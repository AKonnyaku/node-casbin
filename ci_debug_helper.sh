#!/bin/bash
set -e

# Record start time
START_TIME=${SECONDS:-0}

# =========================================================
# Run inside node-casbin-ci-env docker to mimic GitHub runner
# =========================================================
if [ -z "${RUN_IN_DOCKER:-}" ]; then
    if command -v docker >/dev/null 2>&1; then
        echo ">>> Spawning node-casbin-ci-env container..."
        # Build image if not exists
        if ! docker image inspect node-casbin-ci-env >/dev/null 2>&1; then
             echo "Building Docker image..."
             docker build -f Dockerfile.node-ci -t node-casbin-ci-env .
        fi
        
        exec docker run --rm -t \
            -e RUN_IN_DOCKER=1 \
            -v "$PWD":/workspace \
            -w /workspace \
            node-casbin-ci-env \
            bash -lc "/workspace/ci_debug_helper.sh"
    else
        echo ">>> docker not found, continuing on host environment."
    fi
fi

# ==========================================
# Node Casbin CI Debug Helper Script
# ==========================================

echo ">>> [1/5] Checking environment dependencies..."
if ! command -v node &> /dev/null; then
    echo "Error: node is not installed."
    exit 1
fi
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed."
    exit 1
fi

# ==========================================
# Safety Mechanism
# ==========================================
if [ "$PWD" == "/workspace" ]; then
    echo "----------------------------------------------------------------"
    echo "WARNING: Running in /workspace. Copying to /root/node-casbin-debug"
    echo "to protect host files during checkout."
    echo "----------------------------------------------------------------"
    
    rm -rf /root/node-casbin-debug
    cp -r /workspace /root/node-casbin-debug
    cd /root/node-casbin-debug
    echo ">>> Switched working directory to: $(pwd)"
fi

# ==========================================
# Git Configuration & Variables
# ==========================================
echo ">>> [2/5] Configuring Git and calculating SHAs..."
export GITHUB_WORKSPACE="$PWD"

if [ -n "${RUN_IN_DOCKER:-}" ] && [ "$PWD" == "/workspace" ]; then
    # If somehow we are still in /workspace (safety failed?), treat as simulation
    BASE_SHA="CURRENT"
    HEAD_SHA="CURRENT"
    SKIP_CHECKOUT=1
else
    # In copied directory, we can checkout
    if [ -z "${HEAD_SHA:-}" ]; then
        HEAD_SHA="$(git rev-parse HEAD)"
    fi
    if [ -z "${BASE_SHA:-}" ]; then
        # Try to find merge base with master, else HEAD
        if git fetch -q origin master; then
            BASE_SHA="$(git merge-base "${HEAD_SHA}" origin/master)"
        else
            BASE_SHA="${HEAD_SHA}"
        fi
    fi
fi

echo "    BASE_SHA: ${BASE_SHA}"
echo "    HEAD_SHA: ${HEAD_SHA}"

# Backup benchmark directory as it might not exist in target SHAs
cp -r benchmark /tmp/benchmark_backup

run_bench () {
    local sha="$1"
    local out="$2"

    if [ "${SKIP_CHECKOUT:-0}" = "1" ] || [ "$sha" = "CURRENT" ]; then
        echo ">>> Using current workspace (simulation)"
    else
        echo ">>> Checkout $sha ..."
        git checkout -f "$sha"
        # Restore benchmark dir
        if [ -d "/tmp/benchmark_backup" ]; then
            rm -rf benchmark
            cp -r /tmp/benchmark_backup benchmark
        fi
    fi

    echo ">>> Installing dependencies..."
    # Try to install deps. Use yarn if lockfile exists
    if [ -f "yarn.lock" ]; then
        yarn install --ignore-scripts --frozen-lockfile || yarn install --ignore-scripts
    else
        npm install --ignore-scripts
    fi

    echo ">>> Installing benchmark dependencies..."
    npm install --no-save benchmark @types/benchmark ts-node typescript

    echo ">>> Running benchmark..."
    # Run the benchmark script
    ./node_modules/.bin/ts-node benchmark/index.ts > "$out" || echo "[]" > "$out"
    
    # Check if output is valid JSON
    if ! jq -e . "$out" >/dev/null 2>&1; then
        echo "Warning: Benchmark output is not valid JSON."
        cat "$out"
        echo "[]" > "$out"
    fi
}

echo ">>> [3/5] Running Base Benchmark..."
run_bench "$BASE_SHA" "base-bench.json"

echo ">>> [4/5] Running PR Benchmark..."
run_bench "$HEAD_SHA" "pr-bench.json"

# ==========================================
# Generate Report
# ==========================================
echo ">>> [5/5] Generating Report..."

# We use the same Python script structure as jcasbin, adapted if necessary.
# Since we output JMH-compatible JSON structure (with scoreUnit="ops/s"), the logic should hold.

python3 - <<'PY' > benchmark_report.txt
import json
import math
import os

def mean(data):
    return sum(data) / len(data) if data else 0.0

def variance(data):
    n = len(data)
    if n < 2: return 0.0
    m = mean(data)
    return sum((x - m) ** 2 for x in data) / (n - 1)

def stdev(data):
    return math.sqrt(variance(data))

def fmt_ns(ns):
    if ns < 0 or math.isnan(ns): return "-"
    if ns < 1000: return f"{ns:.2f}n"
    if ns < 1e6: return f"{ns/1e3:.2f}µ"
    if ns < 1e9: return f"{ns/1e6:.2f}m"
    return f"{ns/1e9:.2f}s"

def flatten_raw(metric):
    raw = metric.get("rawData")
    if not raw:
        return []
    vals = []
    for arr in raw:
        if isinstance(arr, list):
            vals.extend(arr)
        else:
            vals.append(arr)
    return vals

def metric_to_ns_values(metric):
    unit = str(metric.get("scoreUnit", "") or "")
    val = float(metric.get("score", 0.0))

    if unit.endswith("/op"): # ns/op, ms/op
        t_unit = unit.split("/", 1)[0]
        mult = {"ns": 1.0, "us": 1e3, "ms": 1e6, "s": 1e9}.get(t_unit)
        return [val * mult] if mult else [val]
    if unit.startswith("ops/"): # ops/s
        denom = unit.split("/", 1)[1]
        mult = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0}.get(denom)
        if mult is None or val == 0:
            return [0.0]
        ops_per_sec = val / mult
        return [1e9 / ops_per_sec] if ops_per_sec else [0.0]
    return [val]

def load_results(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    out = {}
    for bench in data:
        name = bench.get("benchmark", "Unknown")
        primary = bench.get("primaryMetric", {})
        ns_vals = metric_to_ns_values(primary)
        
        # Benchmark.js might not provide raw data easily in the same way, 
        # but our wrapper in index.ts tries to provide 'rawData' if possible.
        # If rawData is missing, we just use score.
        
        rec = out.setdefault(name, {"ns_op": []})
        rec["ns_op"].extend(ns_vals)
    return out

base = load_results("base-bench.json")
pr = load_results("pr-bench.json")
all_keys = sorted(list(set(base.keys()) | set(pr.keys())))

print("Benchmark Comparison")
print("")
print(f"Comparing base ({os.environ.get('BASE_SHA', 'unknown')[:7]}) vs PR ({os.environ.get('HEAD_SHA', 'unknown')[:7]})")
print("")

print(f"{'':<40}│ {'base':^14} │ {'pr':^14} │ {'diff':^10} │")

for k in all_keys:
    b_vals = base.get(k, {}).get("ns_op", [])
    p_vals = pr.get(k, {}).get("ns_op", [])

    if b_vals and p_vals:
        b_mean = mean(b_vals)
        p_mean = mean(p_vals)
        
        if b_mean > 0:
            diff = (p_mean - b_mean) / b_mean
            diff_str = f"{diff:+.2%}"
        else:
            diff = 0.0
            diff_str = "-"

        if diff < -0.10: status = "🚀"
        elif diff > 0.10: status = "🐌"
        else: status = "➡️"

        print(f"{k:<40} {fmt_ns(b_mean):>14}   {fmt_ns(p_mean):>14}   {diff_str:>10} {status}")
    else:
        print(f"{k:<40} {'-':>14}   {'-':>14}   {'-':>10}")
PY

cat benchmark_report.txt

ELAPSED=$(($SECONDS - $START_TIME))
echo ">>> Total Duration: $ELAPSED seconds"
