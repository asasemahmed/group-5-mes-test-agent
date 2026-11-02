# Evaluation Protocol

- Scenarios: SP-01, SP-02, SP-03 (`tests/agent_tests/test_scenarios.yaml`).
- Injected defects: `data/injected_defects.yaml`.
- Approaches: Playwright baseline, pure agent, agent with verification and self-correction.
- Metrics: TCR, DDR, DRP, FPR, run time, token cost, human interventions (`src/benchmark/metrics_calculator.py`).

TODO: number of runs per scenario and how the MES is reset between runs.
