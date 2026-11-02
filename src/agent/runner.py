"""Run one agent scenario.

Usage:  python -m src.agent.runner --scenario SP-01
"""

import argparse
from pathlib import Path

SCENARIOS_FILE = Path(__file__).resolve().parents[2] / "tests" / "agent_tests" / "test_scenarios.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LLM computer-use agent on one scenario.")
    parser.add_argument("--scenario", required=True, help="Scenario ID, e.g. SP-01")
    args = parser.parse_args()
    print(f"Scenario {args.scenario} (from {SCENARIOS_FILE.name})")
    # TODO: load the scenario, plan with Planner, run steps with Actuator, check with the oracle.
    print("Agent loop not implemented yet.")


if __name__ == "__main__":
    main()
