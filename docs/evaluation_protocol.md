# Evaluation Protocol

- Scenarios: SP-01, SP-02, SP-03 (`tests/agent_tests/test_scenarios.yaml`).
- Injected defects: `data/injected_defects.yaml`.
- Approaches: Playwright baseline, pure agent, agent with verification and self-correction.
- Metrics: TCR, DDR, DRP, FPR, run time, token cost, human interventions (`src/benchmark/metrics_calculator.py`).

TODO: number of runs per scenario and how the MES is reset between runs.

## Model (plan step 0.2)

Checked with `python -m src.llm.smoke --info-only` on 2026-11-28, from OpenRouter's public model list:

| Item | Value |
|---|---|
| Model id | `z-ai/glm-5.3-flash` |
| Input types | text, image, video |
| Price per 1M tokens | input $0.15, output $0.50 |
| JSON response format | listed as supported |

Still open: the two paid probes (`python -m src.llm.smoke` with `OPENROUTER_API_KEY` in `.env`).
They decide the observation mode (image or text), and whether the JSON response format is
accepted in practice. The results then go here and into `data/scored_experiment.yaml`.
