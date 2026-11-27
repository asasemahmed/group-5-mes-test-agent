# Implementation plan: local MES test agent

Companion to `local-mes-test-agent-design.md`. References like "design 6.5" point there.

Status: accepted by the team on 27.11.2026. Nine review points are still open; design 16 lists
them with the step in which each must be settled.

## How to read this plan

- Each step lists what it needs first ("Needs"), the files, the tests, and how it is verified.
- Offline tests are everything `python -m pytest` runs by default. They never need an API key.
  "Verified" for a step means: its named offline tests pass locally and in CI on Ubuntu and
  Windows.
- Three steps have a local paid gate instead, run by hand with the key and never in CI:
  0.2 (smoke test), 5.7 (development trials, `python -m pytest -m live`), 8.1 (the scored
  benchmark). Each says so.
- A step is done only when its verification passes. A step starts only when the steps it needs
  are done; steps that do not depend on each other may run in parallel.
- All work is committed in small commits on `main` (the team's rule for this repository).

## Schedule (two weeks, two people)

| Days | Track A (mini MES, baseline, dashboard) | Track B (model client, harness, oracle, agent, benchmark) |
|---|---|---|
| 1 | 0.1 | 0.2 |
| 2-4 | 1.1, 1.2, 1.3 | 2.1, 5.1; then 2.3 (after 1.1) and 2.2 (after 1.3) |
| 5 | 2.4 | 3.1, 3.2 |
| 6 | 4.1, 4.2, tag `mes-v1` | 5.2 |
| 7-9 | 7.1 (on fixture reports) | 5.3, 5.4, 5.5, 5.6 |
| 10 | 7.2 (single run) | 5.7 (development scenarios), tag `agent-v1`; 6.1 |
| 11-12 | 7.2 (benchmark), 7.3 | 6.2, 6.3 |
| 13-14 | 8.2, 8.3 | 8.1 |

Cut order if the schedule slips (design 14): dashboard detail and extras first (design 6.9),
then concurrency above 1. The dashboard core (start, watch with polling, stop, results) and
steps 0.1 to 6.3 and 8.1 are never cut.

## P0 Foundations

### 0.1 Dependencies, configuration and CI together

- Needs: nothing.
- Files: `requirements.txt` (add `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `httpx`,
  `psutil`, `filelock`), `pyproject.toml` (register the `live` marker, `addopts = "-m 'not live'"`),
  `.env.example` (rewrite: `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_PRICE_INPUT_PER_MTOK`,
  `LLM_PRICE_OUTPUT_PER_MTOK`, `LLM_TEMPERATURE`, `OBSERVATION_MODE`, `MAX_AGENT_RETRIES`,
  `AGENT_MAX_STEPS`, `RUN_TIMEOUT_S`, `HEADLESS_MODE`, `BENCHMARK_CONCURRENCY`,
  `BENCHMARK_REPEATS`, `BENCHMARK_MAX_COST_USD`; remove the PostgreSQL and provider lines),
  `src/config.py` (new: loads `.env`, typed settings with defaults, `public_dict()` without
  the key), `.gitignore` (ignore `reports/*` except `.gitkeep`),
  `.github/workflows/benchmark.yml` (matrix `ubuntu-latest` and `windows-latest`, Python 3.11,
  `pip install -r requirements.txt`, `python -m playwright install chromium` with
  `--with-deps` on Ubuntu, `python -m src.main`, `python -m pytest`).
- Tests: `tests/test_config.py`: defaults load without a `.env`; `public_dict()` has no key.
- Verified: one commit holds the dependency, configuration and workflow changes; the workflow
  is green on both systems; on a fresh virtual environment the three setup commands and
  `pytest` succeed.

### 0.2 Model smoke test (local paid gate)

- Needs: nothing (uses only `httpx`).
- Files: `src/llm/__init__.py`, `src/llm/smoke.py` (`python -m src.llm.smoke`). It sends two
  probes to GLM-5.3 Flash on OpenRouter and prints, for each, status, latency, token counts and
  whether a cost field came back. Both probes ask for the same thing, one valid action as JSON
  for a small fixed page:
  1. image probe: a generated JPEG of the page (with a word that appears only in the image and
     must be repeated in the answer, to prove the image was read) plus the element list;
  2. text-only probe: the element list and page text, no image.
  A probe passes when the answer is a valid action for the page (and, for the image probe,
  contains the word).
- Records in `docs/evaluation_protocol.md`: the exact model id, the prices per million tokens
  with the date, which probes pass, whether a JSON response format is accepted. The model id
  and the chosen observation mode are also written into `data/scored_experiment.yaml`
  (design 6.8), together with the fixed plan values.
- Gate, checked by hand, with all four outcomes:
  - both probes pass: observation mode `image`;
  - only the image probe passes: observation mode `image`;
  - only the text-only probe passes: observation mode `text`, and the report will say so;
  - neither passes, or the model is unavailable: the live experiment is blocked and the team is
    told (design 14). Offline steps continue; steps 5.7 and 8.1 wait for an owner decision.

## P1 Mini MES

### 1.1 Schema and seed

- Needs: 0.1.
- Files: `src/mes/__init__.py`, `src/mes/db.py` (schema of design 6.1, `connect(path)`),
  `src/mes/seed.py` (`build_database(path)` from the two data files),
  `data/work_orders.json` (add open work order `WO-2026-0903`, "Repair Line 3 Belt
  Replacement"), `data/spare_parts_catalog.csv` (add `VLV-030`, 1 in stock, reorder at 3).
- Tests: `tests/mes/test_seed.py`: six parts with the CSV values, `stock_qty = initial_stock`,
  two work orders, empty request and movement tables; building twice gives the same content.
  `tests/test_main.py` still passes (the reference model reads the same CSV).
- Verified: offline tests pass.

### 1.2 Business rules and defects

- Needs: 1.1.
- Files: `src/mes/defects.py` (parse and validate `DEF-01..03`), `src/mes/service.py`
  (`issue_part`, `is_low_stock`, list and lookup functions; the three defect branches, each
  marked with a comment naming the defect).
- Tests: `tests/mes/test_service.py`:
  - clean: for SP-01, SP-02 and SP-03 the service result equals `src/main.py` (`Inventory`);
  - R2 and R3: stock, movement fields and audit rows after accepted and rejected issues;
  - closed work order and non-positive quantity are rejected; stock never negative (R5);
  - DEF-01: 3 of 2 bearings accepted, stock -1; DEF-02: SEN-015 not low; DEF-03: belts 10 to 6
    with exactly one correct movement row;
  - an unknown defect name raises at start-up.
- Verified: offline tests pass.

### 1.3 Pages, API and start-up protocol

- Needs: 1.2.
- Files: `src/mes/app.py` (`create_app(db_path, defects, run_id)`), `src/mes/__main__.py`
  (`--run-id`, `--db`, `--defects`, optional `--port`; binds `127.0.0.1` port 0 on its own
  socket, prints the ready line, serves on that socket; without `--db` it builds a temporary
  database), `src/mes/templates/` (`base.html`, `home.html`, `inventory.html`, `part.html`,
  `work_orders.html`, `work_order.html`, `issue_form.html`, `issue_result.html`,
  `movements.html`), `src/mes/static/style.css`.
- Rules: the home page shows only navigation; labels on all controls; table markup; selects
  show id and name; `id` and `data-testid` on rows, stock cells, badges and form controls;
  post-redirect-get for the issue form; no new balance on the result page.
- Tests: `tests/mes/test_pages.py` with FastAPI's test client: every page answers 200; the home
  page contains no part id; search filters; the issue flow accepts and rejects with the right
  messages and redirect; badge shown for a low part and missing with DEF-02; API JSON matches
  the database; `/health` returns run id and defects. `tests/mes/test_startup.py`: the module
  started as a child prints a valid ready line and answers on that port.
- Verified: offline tests pass on both systems; `python -m src.mes --port 8080` shows the pages
  in a browser.

## P2 Harness

### 2.1 Run records, timing and usage ledger format

- Needs: 0.1.
- Files: `src/harness/__init__.py`, `src/harness/records.py` (`RunRecord` with the fields of
  design 6.10 including status `cancelled`, phase timer with monotonic clock,
  `write_json_atomic`, `append_jsonl`, ledger line types `dispatch` and `response`).
- Tests: `tests/harness/test_records.py`: round trip; atomic replace; phases add up to the
  end-to-end time; appended ledger lines survive a simulated crash; a dispatch without a
  response reads back as unknown cost with its estimate.
- Verified: offline tests pass.

### 2.2 MES instances and process trees

- Needs: 1.3, 2.1.
- Files: `src/harness/mes_instance.py` (context manager of design 6.2: start, read ready line
  with timeout, check `/health` identity, stop), `src/harness/proctree.py`
  (`kill_tree(pid, grace)` and `alive_descendants(pid)` with `psutil`).
- Tests: `tests/harness/test_mes_instance.py`: instance answers with its run id and defects;
  five instances started at once all get different ports and their own identity; a child that
  exits before the ready line gives a clear error within the timeout; after exit the process is
  gone and the port and database file are free. `tests/harness/test_proctree.py`: a parent with
  a grandchild is killed completely.
- Verified: offline tests pass on both systems.

### 2.3 Scenarios and claims

- Needs: 0.1, 1.1 (the new work order and the new part must exist in the data files).
- Files: `tests/agent_tests/test_scenarios.yaml` (add per scenario a public `precondition`
  sentence from the README's scenario table and a private `action` block: `type` `issue` or
  `inspect`, `part_id`, and for issues `qty` and `work_order_id`; SP-03 uses `WO-2026-0903`),
  `tests/agent_tests/dev_scenarios.yaml` (new, unscored: DEV-01 over-issue of 5 `MOT-001` to
  `WO-2026-0891`, DEV-02 low-stock check of `VLV-030`, DEV-03 issue of 3 `FIL-020` to
  `WO-2026-0903`, each with `precondition`, `instruction`, `expected` and `action`),
  `src/scenarios.py` (load both sets and the scenario-to-defect map; `Scenario.public_text()`
  returns precondition and instruction and is the only thing an agent may receive; scored and
  development scenarios are different types so they cannot be mixed),
  `src/claims.py` (the closed claim list and the defect-to-claims map of design 6.1).
- Tests: `tests/test_scenarios.py`: three scored and three development scenarios; referenced
  parts and work orders exist; each precondition agrees with the catalog (stock and reorder
  level); the two sets share no part; every defect has at least one claim.
- Verified: offline tests pass.

### 2.4 Evidence recorder and evidence check

- Needs: 1.3, 2.3.
- Files: `src/harness/evidence.py` (recorder attached to a Playwright page: captures
  `POST /issue` with form fields and time; `mark_seen(part_id)` used by the agent loop when an
  observation with the part in the viewport is sent, and by the baseline's row helper;
  `in_viewport(page, part_id)`; `check(scenario, approach, evidence) -> EvidenceResult` with
  E1 and E2 of design 6.5).
- Tests: `tests/harness/test_evidence.py` with a real instance and browser, driven by small
  scripted page actions:
  - issue scenarios, E1: one matching submission passes; none, wrong quantity, wrong work order
    and two submissions fail;
  - issue scenarios, E2: for the two screen-judge approaches, submit and then see the part
    passes; submit without seeing it afterwards fails; seeing it only before the submission
    fails; for `agent_with_verification` E2 is not required and what happened is recorded;
  - inspection scenario: seeing the SEN-015 row passes; doing nothing on the home page fails;
    loading the inventory without a marked sighting fails; seeing only another part fails;
    submitting an issue fails; the row scrolled out of view is not "in viewport".
- Verified: offline tests pass on both systems.

## P3 Oracle

### 3.1 Inspectors and facts

- Needs: 2.2.
- Files: `src/oracle/db_inspector.py` (read-only SQLite URI built with `Path.as_uri()`;
  parts, requests, movements), `src/oracle/api_inspector.py` (httpx, read-only endpoints),
  `src/oracle/page_inspector.py` (new: own browser context; loads `/inventory`; reports whether
  the part's badge is visible according to the browser), `src/oracle/facts.py`
  (`collect(scenario, instance, evidence) -> Facts`, serialisable).
- Tests: `tests/oracle/test_inspectors.py`: values agree with a running instance; a write
  through the read-only connection fails; with a fixture page whose badge is in the HTML but
  hidden by CSS, the page inspector reports "not visible"; facts round-trip through JSON.
- Verified: offline tests pass on both systems.

### 3.2 Rules and verdict

- Needs: 3.1, 2.4.
- Files: `src/oracle/rules.py` (INV-1, 2, 3, 4a, 4b, 5, 6 and EXP of design 6.5 on a `Facts`
  object; each returns id, passed, detail, claim), `src/oracle/verdict.py`
  (`evaluate(facts) -> OracleResult`).
- Tests: `tests/oracle/test_oracle_cases.py`. The tester in these tests is a scripted browser
  helper, not a model:
  - the six truth cases (3 scenarios x clean or defect): `PASS` on clean; on defect `FAIL` with
    the expected failed checks and a claim that counts for the defect;
  - a movement with the right count but wrong work order or quantity (database edited by the
    test) fails INV-5;
  - one submission with two audit rows (database edited by the test) fails INV-6 and gives
    `FAIL`; two submissions with two audit rows pass INV-6 (and fail E1 of 2.4);
  - badge and API disagree, in both directions, on hand-made facts: a low part with a visible
    badge but API `low_stock: false` fails only INV-4b and reports `other`; a low part with a
    correct API value but no visible badge fails only INV-4a and reports
    `low_stock_warning_missing`;
  - an unreadable database gives `INCONCLUSIVE`.
- Verified: offline tests pass.

## P4 Baseline and the common run path

### 4.1 Scripts

- Needs: 1.3, 2.3, 2.4.
- Files: `src/baseline/__init__.py` (registry; `BusinessAssertion`; `expect_business(condition,
  claim, observed=None)`; `read_part_row(page, part_id)` which requires the row to be visible
  and marks the sighting), `src/baseline/sp01.py`, `sp02.py`, `sp03.py` (start at the home
  page; fixed selectors; read the row, then assert), and the three files in
  `tests/baseline_playwright/` rewritten.
- Tests: for each scenario, clean passes; with the defect it raises `BusinessAssertion` with a
  claim that counts for the defect (for DEF-03: `wrong_balance` with observed 6); against a mini
  MES whose inventory route is broken for the test, the script raises an ordinary error, not a
  `BusinessAssertion`.
- Verified: `pytest tests/baseline_playwright` green on both systems.

### 4.2 `run_one`, supervisor and the common verdict flow

- Needs: 2.2, 2.4, 3.2, 4.1.
- Files: `src/harness/run_one.py` (worker entry point: phases of design 5; watchdog for the
  tester deadline; verdict flow of design 6.7; writes `run.json` with the verdict before fact
  collection and updates it after; approach `playwright_baseline` for now),
  `src/harness/supervisor.py` (`supervise(run_spec) -> RunRecord`: writes `worker.json` with
  process id and start time, starts the worker, enforces the hard limit from outside, kills the
  tree, keeps a verdict the worker already wrote and otherwise writes `AGENT_ERROR` (`killed`);
  `recover(dir)`: for every started run without a terminal record, kills the worker from
  `worker.json` and its descendants if it is still alive with the same start time, then marks
  the run `cancelled`).
- Tests: `tests/harness/test_run_one_baseline.py`, each run started through the supervisor:
  - for each scenario clean and with defect the record has the true verdict, claim, phase
    timings, evidence and facts;
  - a baseline forced to hang ends by the watchdog as `AGENT_ERROR` (`timeout`);
  - a worker that ignores its watchdog (test hook that blocks the main thread) is killed by the
    supervisor, recorded as `AGENT_ERROR` (`killed`), and leaves no process, on both systems;
  - a baseline forced to skip its action, and one forced to assert without reading the row
    after submitting, end as `AGENT_ERROR` (`not_carried_out`);
  - fact collection forced to time out: the verdict and the published duration are unchanged
    and facts are marked missing;
  - fact collection forced to hang without reacting, after the verdict was written: the
    supervisor hard-kills the worker, and the record still has the worker's `PASS` or `FAIL`,
    not `AGENT_ERROR`;
  - `recover` on a folder whose worker is still alive but whose supervisor is gone (the test
    kills only the supervising process): the worker and its mini MES are terminated and the run
    is `cancelled`; a `worker.json` whose process id now belongs to an unrelated process with
    another start time is left alone.
- Verified: offline tests pass on both systems. This closes acceptance criterion 2. Then tag
  the commit `mes-v1`. From here the mini MES pages, scenarios and defects change only for bugs,
  and every such change is noted in `docs/evaluation_protocol.md`.

## P5 Agent

### 5.1 Model client

- Needs: 0.1, 2.1.
- Files: `src/llm/client.py` (`ChatClient` with the fixed OpenRouter origin and `max_tokens` on
  every request, `ChatReply`, `FakeChatClient` that records requests, `parse_json_reply`,
  ledger writing with dispatch estimate and response).
- Tests: `tests/llm/test_client.py` with `httpx.MockTransport`: normal reply; image attached as
  data URL; every request goes to `https://openrouter.ai` and nothing else; 429 and 500 retried
  with backoff then succeed, each try with its own dispatch line; a network failure followed by
  a successful retry leaves two dispatch lines and one response line; retries exhausted raises
  a clear error; invalid JSON is re-asked once; cost from usage, from prices, and `null` with
  the estimate kept when usage is missing; the key is absent from `repr`, logs and errors.
- Verified: offline tests pass.

### 5.2 Observer

- Needs: 1.3.
- Files: `src/agent/observer.py` (`Observation`: screenshot path, URL, title, page text,
  elements), `src/agent/page_script.js` (lists visible interactive elements with role, name,
  value and, for selects, option labels; marks each with a number).
- Tests: `tests/agent/test_observer.py` on mini MES pages in Chromium: the issue form lists two
  selects with their option labels, the quantity box and the submit button; hidden elements are
  left out; the text output contains no `data-testid`, `id` or option values; the screenshot is
  a JPEG of 1280 x 800 at the path for its step and attempt; in text mode no image is attached.
- Verified: offline tests pass on both systems.

### 5.3 Actuator

- Needs: 5.2.
- Files: `src/agent/actuator.py` (`execute(step) -> ActionResult` for `click`, `type`,
  `select` by label, `press`, `scroll`, `back`; waits for the page to settle; raises
  `ActionError` whose message comes from the fixed list of design 6.4, with the raw error kept
  for the trace).
- Tests: `tests/agent/test_actuator.py`: each action on mini MES pages; unknown number, wrong
  element kind, missing option and unknown action raise `ActionError` with a listed message
  that contains no selector.
- Verified: offline tests pass.

### 5.4 Planner and prompt

- Needs: 5.1, 5.2, 2.3.
- Files: `src/agent/prompts.py` (system prompt with R1..R5, the claim list and the action
  format; message builder that puts in the scenario's precondition and instruction and nothing
  else from the scenario), `src/agent/planner.py`
  (`Planner.next_step(goal, observation, history) -> Step`; validates the reply; `done` needs
  a verdict, and a `FAIL` needs a claim from the list, with observed stock for `wrong_balance`).
- Tests: `tests/agent/test_planner.py`: valid replies become steps; invalid ones raise; a
  `FAIL` without a claim, with an unknown claim, or `wrong_balance` without a number is invalid;
  the system prompt contains no part id, work-order id or route from the data files and
  templates.
- Verified: offline tests pass.

### 5.5 Loop and self-correction

- Needs: 5.3, 5.4, 2.4.
- Files: `src/agent/loop.py` (`run_agent(instruction, page, client, max_retries, max_steps,
  deadline, evidence, on_attempt) -> AgentResult`; marks a sighting when an observation with
  the scenario part in the viewport has been sent), `src/agent/self_correction.py` (attempt
  and retry policy of design 6.4; replaces the old helper).
- Tests: `tests/agent/test_loop.py` with `FakeChatClient` on a real instance and browser:
  - scripted happy path ends `done`;
  - a step that fails three times and succeeds on the fourth attempt continues (retries 3), and
    all four screenshots exist at different paths named in the trace;
  - four failures end as error; with retries 0 exactly one attempt is made and a failure ends
    as error;
  - step limit and deadline end as error; counters for transport retries, JSON re-asks and step
    retries are separate;
  - submission guard: an action that raises after its form was posted is not repeated by the
    loop, and the next request says the form was submitted;
  - a sighting is marked only for observations that were sent, not for pages passed through;
  - in text-only mode, a part row that is in the viewport but falls behind the text cut-off of
    the sent request is not a sighting; the same row inside the sent text is.
- Verified: offline tests pass on both systems.

### 5.6 Agents in `run_one`, leak test and secret scan

- Needs: 4.2, 5.5.
- Files: `src/harness/run_one.py` (approaches `pure_agent` and `agent_with_verification`;
  trace and screenshots through `on_attempt`; model verdict and oracle verdict stored;
  `--fake-llm <file>`), `src/agent/runner.py` (command line: runs one supervised worker into
  `reports/adhoc/` and prints the verdict), `src/harness/secret_scan.py`
  (`python -m src.harness.secret_scan <paths>`; excludes only the repository's `.env`),
  `tests/fixtures/fake_llm/` (scripted replies).
- Tests: `tests/harness/test_run_one_agent.py`, all with scripted replies:
  - for each scenario clean and with defect, `agent_with_verification` returns the true verdict
    from the oracle and `pure_agent` returns the scripted model verdict;
  - "done" on the home page with `PASS` and with `FAIL`, on clean and on defect instances, ends
    as `AGENT_ERROR` in both agent approaches; so does SP-02 without seeing the part;
  - SP-03 submit and then "done" without looking at the balance, on clean and on DEF-03:
    `pure_agent` ends as `AGENT_ERROR`; `agent_with_verification` gets the oracle's verdict
    (`PASS`, `FAIL`) and the record says the agent did not look;
  - SP-03 by the direct route (home, issue form, submit, inventory, done) for `pure_agent`, on
    clean and on DEF-03: the requests contain the precondition "10 pieces in stock"; the
    scripted verdicts `PASS` with 8 seen and `FAIL` `wrong_balance` observed 6 are accepted and
    scored correct pass and detected;
  - `agent_with_verification` whose inspectors become unavailable right after the verdict was
    written (test hook): the record keeps the verdict and the facts the oracle judged on, and
    a DEF-03 `FAIL` is still scored detected;
  - leak test of design 6.4: identical requests with real and with sentinel private data, on
    normal and retry paths; no `data-testid`, element `id` or internal marker in any request.
  `tests/harness/test_secret_scan.py`: with a canary key in the environment, in a temporary
  repository's `.env` and in one log file, the scan reports the log file and not the `.env`;
  after an offline run with the canary, the scan of the run folder and captured child output
  is clean.
- Verified: offline tests pass on both systems. The whole pipeline now works offline.

### 5.7 Development trials and freeze (local paid gate)

- Needs: 5.6, a working mode from 0.2, the API key.
- Only the development scenarios are run with the real model, clean and with defects, with both
  agent approaches. The three scored scenarios are not run live in this step.
- Tune only the generic prompt and the observation format. The leak test of 5.6 stays green.
- Tests: `tests/live/test_live_agent.py` (marker `live`, by hand): one clean run per
  development scenario completes.
- Exit check, by hand: with `agent_with_verification`, each development scenario ends with
  `PASS` or `FAIL` in at least 4 of 5 clean trial runs. Step count, time and cost per run are
  written into `docs/evaluation_protocol.md`.
- Then tag `agent-v1`.
- If the exit check is not met after two days, the trials stop. The team either runs the scored
  benchmark as it is and reports the completion rate as a finding, or switches the observation
  mode if 0.2 allows both. Both keep GLM-5.3 Flash. The choice is recorded.

## P6 Benchmark

### 6.1 Scoring and metrics

- Needs: 2.1, 2.3, 3.1.
- Files: `src/benchmark/scoring.py` (`claim_is_true(claim, facts)` per design 6.1;
  `classify(record) -> class` per design 6.8), `src/benchmark/metrics_calculator.py` (the four
  helpers return "no value" for an empty denominator; new
  `summarise(manifest, records, interventions) -> dict`, which reports this experiment's own
  intervention count), `src/benchmark/attempts.py` (append one line per scored attempt to
  `reports/scored/attempts.jsonl`; `summarise_attempts()` gives the number of attempts and, per
  attempt, interventions and started over planned runs).
- Tests: `tests/benchmark/test_scoring.py` with hand-made records and facts:
  - DEF-03 with `wrong_balance` observed 6: detected; with `wrong_balance` observed 7:
    unconfirmed; with `movement_log_wrong`: unconfirmed; with `other`: unconfirmed;
  - DEF-01 with `over_issue_accepted`, `negative_stock` or `wrong_balance` observed -1:
    detected; DEF-02 with `low_stock_warning_missing`: detected;
  - a `FAIL` on a defect run whose facts are missing: unconfirmed; any `FAIL` on a clean run:
    false alarm.
  `tests/benchmark/test_metrics.py` with exact expected values: the full plan; one repeat (six
  runs per approach, a perfect approach scores 100%); a filtered plan; an interrupted plan
  (partial label; planned, terminal, cancelled and pending counts); unconfirmed reports lower
  DRP and do not raise DDR; no `FAIL` at all (DRP "n/a"); known, estimated and unknown cost; an
  intervention with and without approach. `tests/benchmark/test_attempts.py`: a stopped attempt
  with one intervention and 40 of 90 runs started, followed by an eligible attempt, gives two
  attempts with exactly those figures; offline and development runs never appear.
- Verified: offline tests pass.

### 6.2 Runner, lock, manifest, resume and eligibility

- Needs: 5.6, 6.1.
- Files: `src/benchmark/lock.py` (operating-system file lock through `filelock`, non-blocking,
  held for the runner's lifetime), `src/benchmark/manifest.py` (build with the content hash
  over the listed file types of design 6.8, compare), `src/benchmark/scored_spec.py` (load
  `data/scored_experiment.yaml`, validate a plan against it), `src/benchmark/runner.py` (take
  lock; `recover`; write manifest first; start supervised workers with a thread pool; resume
  rules; cost admission from the ledgers with estimates; eligibility; attempts line;
  write `progress.json`, `results.csv`, `summary.json`; options `--output-dir`,
  `--approaches`, `--scenarios`, `--repeats`, `--concurrency`, `--fake-llm`, `--scored`,
  `--note-intervention`).
- Tests: `tests/benchmark/test_runner.py`, all offline:
  - one repeat with `--fake-llm`: 18 runs finish; the three files exist and agree; the summary
    is not eligible (fake mode);
  - two runners started at the same time on one folder: one is refused, no run is executed
    twice;
  - the lock owner is killed, then two new runners are started at the same moment on that
    folder: exactly one gets the lock and continues, the other is refused;
  - starting again resumes and skips terminal runs; the summary is then not eligible; a resume
    after a cold start (the first start created `__pycache__` folders under `src/`) is accepted,
    because generated files are not hashed;
  - a live-mode start into a folder made in fake mode is refused; so is a resume after a file
    under `src/`, a data file, the prompt or the scripted reply file changed;
  - a `run.json` from another experiment id in the folder is not accepted as finished;
  - `--scored` refuses a dirty worktree, fake mode, a prompt hash that differs from the tag,
    and a folder that already has runs; it also refuses, before any worker starts, a subset of
    approaches or scenarios, one repeat, a model id other than the one in
    `data/scored_experiment.yaml`, and a retry limit other than 0 and 3; a summary computed for
    such a plan without `--scored` is not eligible;
  - a tiny cost limit with concurrency 3 and scripted usage: no worker starts after the limit
    is reached, in-flight runs finish, status is `stopped_cost`, not eligible; a dispatched call
    without response counts with its estimate; the summary separates known and estimated cost.
- Verified: offline tests pass on both systems; an offline benchmark with five repeats
  (90 runs) finishes on the laptop.

### 6.3 Stop, cancel and clean-up

- Needs: 6.2.
- Files: stop handling in `src/benchmark/runner.py` (stop file checked by the runner), using
  `src/harness/proctree.py` and `supervisor.recover`.
- Tests: `tests/benchmark/test_stop.py` on both systems:
  - stop a running benchmark with three workers: no descendant process is alive, the ports are
    reusable, the in-flight runs are `cancelled` (not `AGENT_ERROR`), the folder can be deleted;
  - resume after that stop: the cancelled runs are executed again, their old folders are kept
    with the `.cancelled-N` suffix, all planned runs become terminal, and the summary is not
    eligible;
  - a worker that exceeds its hard limit during a benchmark is killed by its supervisor and
    recorded as `AGENT_ERROR` (`killed`); this alone does not make the experiment ineligible;
  - only the runner process is killed from outside while three workers run (the workers stay
    alive): the next start runs `recover`, which finds them through `worker.json`, kills each
    worker with its mini MES and browser, marks the runs `cancelled`, and leaves no process.
- Verified: offline tests pass on both systems. This closes acceptance criterion 7 offline.

## P7 Dashboard

### 7.1 Read side, built on fixture reports

- Needs: 2.1 (record format). Does not need the runner: it uses a small `reports` fixture
  folder checked in under `tests/fixtures/reports/`.
- Files: `src/dashboard/__init__.py`, `src/dashboard/__main__.py` (`--port` default 8000,
  host `127.0.0.1`), `src/dashboard/app.py`, `src/dashboard/store.py`, templates `home.html`,
  `run.html`, `results.html`, `static/dashboard.css`, `static/dashboard.js` (polls once a
  second: latest screenshot, status, verdict).
- Tests: `tests/dashboard/test_read.py` with the test client on the fixture folder: pages
  render; the run endpoint returns status, attempts and the latest screenshot name; the results
  page shows the same numbers and eligibility as the fixture `summary.json`; a path outside
  `reports/` is refused.
- Verified: offline tests pass.

### 7.2 Starting and stopping jobs

- Needs: 7.1, 5.6 for single runs, 6.3 for the benchmark.
- Files: `src/dashboard/jobs.py` (start one supervised run or the benchmark runner as a child
  process, one job at a time, status, stop with escalation to process-tree kill and
  `recover`), `src/dashboard/security.py` (token, `Host` and `Origin` checks), forms on the
  home page.
- Tests: `tests/dashboard/test_jobs.py`:
  - start a `--fake-llm` run through the endpoint, poll until done, the record exists;
  - start an offline benchmark (one repeat), see progress change, and at the end the results
    page shows the summary whose experiment id is the one the dashboard started;
  - a second start while a job runs is refused with a clear message; stop ends the job and
    leaves no process;
  - stop with a runner that does not react (test hook) while workers are active: the dashboard
    kills the tree, the in-flight runs are `cancelled`, no process is left;
  - a start or stop request without the token, with a foreign `Origin`, or with another `Host`
    is refused.
- Verified: offline tests pass on both systems; by hand, a running agent is visible on the run
  page with at most two seconds delay.

### 7.3 Check with real output

- Needs: 7.2, 6.2.
- Run an offline 90-run benchmark from the dashboard on macOS and on Windows and look at all
  three pages.
- Verified: by hand; findings fixed.

## P8 Experiment and documents

### 8.1 The 90 runs (local paid gate)

- Needs: 5.7 (tag `agent-v1`), 6.3.
- Run `python -m src.benchmark.runner --scored` with the real model, in one go. It creates its
  own folder under `reports/scored/`.
- Checks afterwards, by hand: the summary says `eligible: true`; baseline runs are `PASS` on all
  clean cells and detected on all defect cells;
  `python -m src.harness.secret_scan . reports/scored docs/results` reports nothing.
- Measure the speed targets exactly as design 7 describes (the page measurement is a small
  script, `python -m src.harness.measure_pages`) and store them with operating system,
  concurrency and statistic.
- Copy `results.csv`, `summary.json` and `experiment.json` of the eligible attempt, and
  `attempts.jsonl`, to `docs/results/experiment_01/`.
- If the benchmark had to be stopped, its folder is kept as a diagnostic result, its line stays
  in `attempts.jsonl`, and a new scored benchmark is started.
- Verified: acceptance criteria 4, 6 and 8.

### 8.2 Documents

- Needs: 6.2.
- Files: `README.md` (what the project is now, setup for macOS and Windows, the four commands,
  architecture picture, results link; remove OpenMES and PostgreSQL), `docs/architecture.md`,
  `docs/evaluation_protocol.md` (runs, state per run, verdict flow, evidence, claims and
  scoring classes, metric definitions, eligibility, model facts from 0.2, trial numbers from
  5.7, limitations of design 8 and 13).
- Verified: a team member follows the README on a machine that never had the project and
  reaches a green `pytest` and an offline benchmark without help.

### 8.3 Final check on Windows

- Needs: 7.3, 8.1.
- On the Windows laptop: fresh clone, setup, `pytest`, one live development run, the dashboard,
  stop of a running offline benchmark.
- Verified: acceptance criteria 1, 5 and 7 on both systems.

## Stretch (only after P8)

- S1 `--ui-variant B` for the mini MES and a second benchmark that compares baseline and agent
  under interface change.
- S2 several actions per model call, measured against the one-action loop.
- S3 more scenarios (for example duplicate submit, closed work order).
- S4 dashboard extras: run-list filters, "Open mini MES".

## Acceptance criteria and where they are checked

| Criterion (design 15) | Checked in |
|---|---|
| 1 Setup and offline tests on both systems | 0.1, 8.3 |
| 2 Baseline gate | 4.1, 4.2, 8.1 |
| 3 Oracle and evidence gate | 2.4, 3.2, 4.2, 5.6 |
| 4 90 runs in one go, all metrics, eligibility | 6.1, 6.2, 6.3 (offline), 8.1 (live) |
| 5 Dashboard | 7.2, 7.3, 8.3 |
| 6 Key only in `.env` | 5.1, 5.6, 8.1 |
| 7 Nothing left after stop, timeout or stuck worker | 2.2, 4.2, 6.3, 7.2, 8.3 |
| 8 Speed targets measured | 8.1 |

## Not part of this plan

Updating the bibliography report and the slides for the changed system under test
(design 13), choosing another model, and anything in the stretch list.
