# Evaluation Protocol

- Scenarios: SP-01, SP-02, SP-03 (`tests/agent_tests/test_scenarios.yaml`).
- Injected defects: `data/injected_defects.yaml`.
- Approaches: Playwright baseline, pure agent, agent with verification and self-correction.
- Metrics: TCR, DDR, DRP, FPR, run time, token cost, human interventions (`src/benchmark/metrics_calculator.py`).

TODO: number of runs per scenario and how the MES is reset between runs.

## Model (plan step 0.2)

Checked with `python -m src.llm.smoke --info-only` on 2026-11-27, from OpenRouter's public model list:

| Item | Value |
|---|---|
| Model id | `z-ai/glm-5.3-flash` |
| Input types | text, image, video |
| Price per 1M tokens | input $0.15, output $0.50 |
| JSON response format | listed as supported |

Paid probes, `python -m src.llm.smoke` on 2026-11-27 (saved in `reports/smoke/`):

| Probe | Result | Latency | Tokens in/out | Cost |
|---|---|---|---|---|
| Image (screenshot + element list, code word only in the image) | PASS, chose the right element and read the word | 1.8 s | 496 / 94 | $0.000091 |
| Text only (element list + page text) | PASS, chose the right element | 0.46 s | 127 / 19 | $0.000020 |

- The JSON response format was accepted in both probes.
- OpenRouter returns the cost of each call in its usage data.
- Decision: observation mode **image**. Written into `data/scored_experiment.yaml`.
