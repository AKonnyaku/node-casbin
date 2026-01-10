import json
import os
import sys
import datetime
import re


def normalize_name(name):
    # Strip "Benchmark" prefix if present (node-casbin usually names them BenchmarkXxx)
    name = re.sub(r"^Benchmark", "", name)
    
    # Ensure standard casing if needed, but node-casbin names seem fine (e.g., CachedRBACModel)
    # If we need to match the specific CamelCase logic:
    # parts = name.split("_") ... (node-casbin names are usually CamelCase already)
    return name


def main():
    if len(sys.argv) < 3:
        print("Usage: python format_benchmark_data.py input.json output.json")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {input_path}: {e}")
        sys.exit(1)

    # Get commit info from environment variables
    commit_info = {
        "author": {
            "email": os.environ.get("COMMIT_AUTHOR_EMAIL", ""),
            "name": os.environ.get("COMMIT_AUTHOR_NAME", ""),
            "username": os.environ.get("COMMIT_AUTHOR_USERNAME", ""),
        },
        "committer": {
            "email": os.environ.get("COMMIT_COMMITTER_EMAIL", ""),
            "name": os.environ.get("COMMIT_COMMITTER_NAME", ""),
            "username": os.environ.get("COMMIT_COMMITTER_USERNAME", ""),
        },
        "distinct": True,
        "id": os.environ.get("COMMIT_ID", ""),
        "message": os.environ.get("COMMIT_MESSAGE", ""),
        "timestamp": os.environ.get("COMMIT_TIMESTAMP", ""),
        "tree_id": os.environ.get("COMMIT_TREE_ID", ""),
        "url": os.environ.get("COMMIT_URL", ""),
    }

    # Node.js benchmarks usually run on a single thread unless clustered
    cpu_count = os.cpu_count() or 1

    benches = []
    
    # Node-casbin benchmark.js output structure:
    # [ { "benchmark": "Name", "primaryMetric": { "score": 123, "scoreUnit": "ops/s" } }, ... ]
    
    for bench in data:
        name = normalize_name(bench.get("benchmark", ""))
        score = bench.get("primaryMetric", {}).get("score", 0)
        unit = bench.get("primaryMetric", {}).get("scoreUnit", "")
        
        if score > 0 and unit == "ops/s":
            # Convert ops/s to ns/op
            # 1 op / score (ops/s) = seconds/op
            # seconds/op * 1e9 = ns/op
            val_ns = (1.0 / score) * 1e9
            
            # We don't have total ops count in this JSON format usually, unless we add it
            extra = "" 
            
            benches.append(
                {"name": name, "value": round(val_ns, 2), "unit": "ns/op", "extra": extra}
            )

    output_data = {
        "commit": commit_info,
        "date": int(datetime.datetime.now().timestamp() * 1000),
        "tool": "node", # Changed from python to node
        "procs": cpu_count,
        "benches": benches,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"Successfully formatted benchmark data to {output_path}")


if __name__ == "__main__":
    main()
