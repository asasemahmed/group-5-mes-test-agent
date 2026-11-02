"""Run the benchmark across the three approaches.

Usage:  python -m src.benchmark.runner --output-dir reports/experiment_01/
"""

import argparse
from pathlib import Path

APPROACHES = ["playwright_baseline", "pure_agent", "agent_with_verification"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MES testing benchmark.")
    parser.add_argument("--output-dir", default="reports/experiment_01/")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for approach in APPROACHES:
        # TODO: run every scenario with this approach and save the results.
        print(f"{approach}: not implemented yet")
    print(f"Results folder: {out}")


if __name__ == "__main__":
    main()
