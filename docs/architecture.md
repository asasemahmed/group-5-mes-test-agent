# Architecture

The system has three parts:

1. **Agent** (`src/agent/`): the planner turns a test goal into steps, the actuator runs them in the browser, the observer captures the screen, and self-correction retries failed steps.
2. **Oracle** (`src/oracle/`): checks the real state in the database or REST API, separate from what the agent sees.
3. **Benchmark** (`src/benchmark/`): runs the Playwright baseline and both agent variants and computes the metrics.

TODO: prompt design and the agent loop in detail.
