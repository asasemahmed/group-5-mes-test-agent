# Design: local MES test agent

Status: accepted by the team on 27.11.2026 as the basis for implementation. A four-round review
closed 26 of 35 findings; the nine that stayed open are listed in section 16 and are handled
during implementation. Companion document: `local-mes-test-agent-impl-plan.md` (ordered steps).

## 1. Outcome

A project that runs completely on one laptop and answers the research question:

> Can an LLM computer-use agent, judged by an independent rule-based oracle, detect defects in
> MES spare-parts workflows as reliably as scripted tests, and at what cost?

After this work a team member can, on macOS or Windows:

1. clone the repository and install it with a handful of commands,
2. open a local dashboard,
3. run one test or the whole 90-run benchmark with one click (or one command),
4. watch the agent work, and read verdicts and a metrics table per approach.

Everything except the language-model call runs locally. Nothing is deployed.

## 2. Decisions already taken

| Topic | Decision | Consequence |
|---|---|---|
| System under test | Our own small MES ("mini MES"), in this repository | No OpenMES, no PostgreSQL, no Docker. See section 13 for what this changes in the report. |
| Language model | GLM-5.3 Flash through OpenRouter | Fixed for every scored run. The key lives in a local `.env`. No other model or provider is part of this plan. |
| Interface | Local web dashboard, plus the same actions as commands | One more small web app, bound to `127.0.0.1`. |
| Machines | macOS and Windows | Python only, no shell scripts, no fork-only code. |
| Time | Two weeks | Scope is the 90-run experiment. Everything else is marked stretch. |
| Priorities | Simple, reliable, fast | Few dependencies, one process per run, server-rendered pages. |

Fixed by earlier project documents and kept: three scenarios (SP-01..03), three injected defects
(DEF-01..03), three approaches, five repeats, at most three retries per step, the seven metrics,
and the four verdicts `PASS`, `FAIL`, `INCONCLUSIVE`, `AGENT_ERROR`.

## 3. Scope

In scope:

- Mini MES with spare-parts inventory, work orders, material issue, movement log, read-only API.
- Three switchable defects inside the mini MES.
- Agent: observe, decide, act, check, with bounded self-correction.
- Execution evidence recorded by the harness for all three approaches.
- Oracle: read-only checks of database, API and rendered page against business rules.
- Scripted Playwright baseline for the same scenarios.
- Benchmark runner, metrics, run records.
- Local dashboard that starts and shows single runs and the benchmark.
- Tests that run offline, and CI on Linux and Windows.
- Updated README, `.env.example`, `docs/architecture.md`, `docs/evaluation_protocol.md`.

Not in scope:

- OpenMES, PostgreSQL, Docker, any deployment or hosting.
- Login, users and roles in the mini MES.
- Running the model locally, or any model other than GLM-5.3 Flash.
- Rewriting the bibliography report or the slides (listed as follow-up in section 13).
- More than three scored scenarios. Stretch items are listed in section 14.

## 4. What exists today

- `src/main.py`: an in-memory reference model of the three scenarios (`Inventory.issue`,
  `SparePart.low_stock`). It stays, and the mini MES is tested against it.
- `src/agent/` (`planner`, `actuator`, `observer`, `self_correction`, `runner`),
  `src/oracle/` (`db_inspector`, `api_inspector`), `src/benchmark/` (`runner`,
  `metrics_calculator`): stubs with `TODO`s. The module names are kept because the slides use them.
  `self_correction.with_retries` treats its `retries` argument as the total number of calls and
  does nothing for 0; it is replaced (section 6.4). `metrics_calculator._percent` returns 0 for
  an empty denominator; that changes to "no value" (section 6.8).
- `tests/baseline_playwright/test_sp0x_*.py`: skipped stubs.
- Data: `data/spare_parts_catalog.csv` (5 parts), `data/work_orders.json` (1 work order),
  `data/injected_defects.yaml`, `tests/agent_tests/test_scenarios.yaml`.
- `.env.example` and README still describe OpenMES and PostgreSQL.
- CI runs `python -m src.main` and `pytest` on Ubuntu with Python 3.11 and installs only pytest.

## 5. Architecture

The central rule: **one test run = one worker process = one folder**, and every worker has a
supervisor outside it.

```
dashboard (127.0.0.1:8000)          commands (python -m src....)
        |                                   |
        +---------------+-------------------+
                        v
              benchmark runner            lock, manifest, starts up to N supervised workers
                        |
                        v   supervisor (outside the worker): deadline, kill, record
   +--------------------------------------------------------------+
   | run_one worker                                               |
   |  1. build a fresh SQLite database from the data files        |
   |  2. start a mini MES for this run and check its identity     |
   |  3. start the browser at the MES home page, attach the       |
   |     evidence recorder                                        |
   |  4. the tester acts (baseline script or agent loop)          |
   |  5. execution evidence is checked                            |
   |  6. the judge of this approach gives the verdict; run.json   |
   |     is written                                               |
   |  7. final-state facts are collected (bounded, cannot change  |
   |     the verdict); everything is stopped                      |
   +--------------------------------------------------------------+
                        |
                        v
        reports/<experiment>/<run_id>/...   +   results.csv, summary.json
```

Why a process per run:

- Every run starts from the same state by construction. There is no reset logic that could fail.
- The mini MES needs no test-only endpoints. Defects are fixed when its process starts.
- Runs cannot influence each other, so several can run at the same time.
- A hung run can be killed as a whole from outside and still gets a record.
- The same mechanism serves the command line, the benchmark and the dashboard.

## 6. Components

### 6.1 Mini MES (`src/mes/`)

Stack: FastAPI, Jinja2 templates, SQLite through the standard `sqlite3` module, one stylesheet,
no JavaScript build. Pages are rendered on the server, so they load in a few milliseconds and have
a plain, well-labelled structure.

Pages:

| Route | Content |
|---|---|
| `/` | Home: the three navigation links only. Every tester starts here; the page shows no part data. |
| `/inventory` | Parts table: id, name, stock, reorder level, bin, status. Parts flagged low show a "Low stock" badge. Search by id or name. |
| `/parts/{part_id}` | Part details, the same badge, recent movements, link "Issue to work order". |
| `/work-orders` | Work-order list. |
| `/work-orders/{id}` | Work-order details, parts issued so far, link "Issue spare part". |
| `/issue` (GET) | Form: work order, part, quantity. The two selects show id and name ("WO-2026-0903 Repair Line 3 Belt Replacement"). |
| `/issue` (POST) | Applies the business rules, writes the audit row, redirects (303) to the result page. |
| `/issue/result/{request_id}` | "Issued 2 x BELT-010 to WO-..." or "Rejected: requested 3, only 2 in stock". It does not show the new balance; the user checks the inventory. |
| `/movements` | Movement log. |
| `/api/parts`, `/api/parts/{id}`, `/api/work-orders/{id}`, `/api/movements`, `/api/issue-requests` | Read-only JSON. |
| `/health` | Run id and active defects of this instance. |

Tables:

- `parts(part_id, part_name, initial_stock, stock_qty, reorder_level, unit, bin_location, unit_cost_usd, category)`
- `work_orders(work_order_id, title, status, technician_id, equipment_ids)`
- `issue_requests(id, part_id, work_order_id, qty, accepted, message, created_at)`: audit log,
  one row for every submitted issue form, accepted or not.
- `stock_movements(id, request_id, part_id, work_order_id, qty, movement_type, created_at)`: one
  row per accepted issue.

Business rules (clean behaviour, equal to `src/main.py`):

- R1: an issue is accepted only if `0 < qty <= stock_qty` and the work order is `OPEN`.
- R2: an accepted issue lowers `stock_qty` by exactly `qty` and writes exactly one movement row
  with the same part, work order and quantity, in one transaction.
- R3: a rejected issue changes neither stock nor movements.
- R4: a part is low when `stock_qty < reorder_level`. One function computes this flag; the badge
  and the API field `low_stock` both use it.
- R5: stock is never negative.

Defects, each one clearly marked branch in `src/mes/service.py`, chosen at start-up with
`--defects DEF-01,DEF-03`:

| Defect | Change | Visible effect |
|---|---|---|
| DEF-01 | The stock check in R1 is skipped. | Issuing 3 of 2 bearings is accepted, stock becomes -1. |
| DEF-02 | The low-stock function returns false unless stock is 0. | SEN-015 (3 in stock, reorder at 4) shows no badge, API says `low_stock: false`. |
| DEF-03 | The deduction in R2 is applied twice. | Issuing 2 of 10 belts leaves 6. One correct movement row of 2 is written. |

Claims. A `FAIL` must say what is wrong, as one claim from a closed list. The same list is used
by the baseline, the model and the oracle, and it is fixed here, before any run:

| Claim | Says | Is true in a run's final state when |
|---|---|---|
| `over_issue_accepted` | an issue larger than the stock was accepted | an accepted request asks for more than the stock at that moment (replayed from initial stock) |
| `negative_stock` | a part has negative stock | some `stock_qty < 0` |
| `wrong_balance`, with the observed stock | the part's stock is not what the rules give | the scenario part's `stock_qty` differs from the value the rules give for the submitted requests, and the stated observed stock equals the actual `stock_qty` |
| `movement_log_wrong` | movements do not match the accepted issues | check INV-5 (section 6.5) fails |
| `low_stock_warning_missing` | a low part shows no warning | the part is low by R4 and the badge is not visible |
| `low_stock_warning_unexpected` | a part that is not low shows a warning | the reverse |
| `other`, with text | anything else | never confirmed automatically |

Which claims count as finding each defect:

| Defect | Claims that count |
|---|---|
| DEF-01 | `over_issue_accepted`, `negative_stock`, `wrong_balance` |
| DEF-02 | `low_stock_warning_missing` |
| DEF-03 | `wrong_balance` |

So on DEF-03 a report of "two movement rows were written" (`movement_log_wrong`) does not
count, because it is not true: the defect writes one correct row.

Start-up protocol: `python -m src.mes --run-id <id> --db <file> --defects ...` binds
`127.0.0.1` port 0 itself, so the operating system assigns a free port inside the process that
uses it. It then prints one line of JSON (`{"ready": true, "port": ..., "run_id": ...}`) to
standard output and serves. `--port` can be given for manual use.

Markup rules that matter for the experiment:

- Every control has a proper label, and tables use table markup. This is normal good practice
  and it is what the agent's page reading relies on.
- Elements also carry `id` and `data-testid` attributes. Only the baseline scripts, the
  evidence recorder and the oracle use them. The agent never sees them (section 6.4).

Data changes:

- `data/work_orders.json` gets a second open work order for repair line 3 (`WO-2026-0903`,
  "Repair Line 3 Belt Replacement"), because SP-03 issues belts "to maintenance repair line 3"
  and today no such work order exists.
- `data/spare_parts_catalog.csv` gets a sixth part used only for development,
  `VLV-030` (pneumatic valve, 1 in stock, reorder at 3).
- `tests/agent_tests/test_scenarios.yaml` gets, per scenario, a public `precondition` sentence
  taken from the README's scenario table ("BELT-010 has 10 pieces in stock.", "BRG-6205 has 2
  pieces in stock.", "SEN-015 has 3 pieces in stock; its reorder level is 4.") and a
  machine-readable, private `action` block. A test case consists of precondition and
  instruction, as it would for a human tester. Without the starting balance a tester who sees
  6 belts after issuing 2 could not tell a correct result from a wrong one.
- New `tests/agent_tests/dev_scenarios.yaml` with three unscored development scenarios on parts
  no scored scenario uses (`MOT-001`, `VLV-030`, `FIL-020`), see section 8.
- The agent is never given an `action` or `expected` block.

### 6.2 Run harness (`src/harness/`)

**Instances** (`mes_instance.py`): builds the database, starts the mini MES child with
`sys.executable`, reads the ready line with a timeout, then calls `/health` and requires the
same run id and the expected defects. A child that exits early or reports another identity is an
error for this run. The parent never chooses a port, so two runs cannot race for one.

**Supervisor** (`supervisor.py`): every worker is started through `supervise(run_spec)`, by the
command line, the benchmark runner and the dashboard alike. The supervisor is a different
process from the worker. It waits until the worker's hard limit, kills the worker's whole
process tree if it is still alive, checks that no descendant is left, and makes sure the run
folder ends with a record. If the worker had already written its counting verdict, the
supervisor keeps that verdict and only notes that fact collection or teardown was cut short. It
writes `AGENT_ERROR` (`killed`) only when no verdict exists yet. A worker can therefore be
completely stuck and still be stopped and recorded. Before a worker is started, its process id
and process start time are written to `worker.json` in the run folder.

**Deadlines.** The tester phase has `RUN_TIMEOUT_S` (180 s). The counting judge has its own 20 s.
The verdict is written to `run.json` at that point. Collecting final-state facts afterwards has
a separate 20 s limit; if it fails, the verdict and the published duration stay as they are and
the facts are marked missing. The supervisor's hard limit is the sum plus start-up allowance and
margin. Inside the worker a watchdog ends the tester phase at its deadline and gives
`AGENT_ERROR` (`timeout`); if the worker does not react, the supervisor kills it and, when no
verdict was written yet, writes `AGENT_ERROR` (`killed`).

For `agent_with_verification` the oracle needs the facts to judge, so they are collected once,
inside the judge phase, and stored together with the verdict in one atomic write; they are not
collected a second time. For the other two approaches the facts are collected after the verdict.

**How a run can end:**

| End | Recorded as | Counts as |
|---|---|---|
| The approach produced a verdict | `PASS`, `FAIL` or `INCONCLUSIVE` | terminal |
| Tester error, limit or deadline; or evidence missing | `AGENT_ERROR` with `error_kind` | terminal |
| Worker killed by its supervisor for exceeding the hard limit, before it wrote a verdict | `AGENT_ERROR` (`killed`) | terminal |
| Worker killed by its supervisor after it wrote a verdict | the verdict it wrote; facts or teardown marked cut short | terminal |
| Interrupted from outside: operator stop, benchmark runner crashed or killed | status `cancelled`, no verdict | not terminal |

`cancelled` is not a verdict. It means the run was taken away from the approach.
`recover(dir)` goes through every run that was started but has no terminal record. If the
worker named in its `worker.json` is still alive (same process id and same start time, so a
reused id is not mistaken for it), for example because only the runner was killed and its
workers live on, `recover` kills that worker's whole process tree first. Then it marks the run
`cancelled`. The runner calls `recover` when it stops and before it resumes, and the dashboard
calls it after it had to kill a runner. Process trees are found and killed with `psutil` on
both systems.

**Evidence recorder** (`evidence.py`): attached to the tester's browser page for every approach.
It records, independently of the mini MES:

- every `POST /issue` the browser sends, with its form fields and a timestamp;
- every time the tester *saw* the scenario's part, with a timestamp. For an agent this is
  decided from the request that was actually sent to the model: in image mode, the part's
  inventory row or detail page was in the viewport of the screenshot that was sent; in
  text-only mode, the part's id is in the page text or element list that was sent, after
  trimming. For a script, it is a read of that row through the shared row helper
  (section 6.6). Merely loading a page does not count.

**Run records and timing** (`records.py`): the run-record schema, atomic file writing (write a
temporary file, then `os.replace`), and monotonic timestamps for the phases `startup`
(worker start, MES ready, browser ready, first page usable), `act`, `evidence`, `judge`,
`facts`, `teardown`.

**Secret scan** (`secret_scan.py`): searches given folders for the key value from the
environment. The repository's own `.env` file is the one and only excluded file.

### 6.3 Model client (`src/llm/`)

- One class, `ChatClient`, that posts OpenAI-style chat requests with `httpx`.
- Destination: live requests carry the key only to the fixed origin `https://openrouter.ai`.
  The base URL is a constant, not a setting. Tests inject a transport and never use a real key.
- Model: `LLM_MODEL`, the OpenRouter id of GLM-5.3 Flash, verified in the first plan step.
- Input: system text, user text, optional JPEG screenshot as a data URL. Every request sets
  `max_tokens`.
- Output: reply text, token counts, cost and latency. Cost comes from the provider's usage data
  when present, otherwise from `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK`,
  which are copied from the model's OpenRouter page with the date in the first plan step.
- Usage ledger (`usage.jsonl` in the run folder), two lines per call:
  - a `dispatch` line written before the request is sent, with a call id and an upper estimate
    of its cost (request size and an image allowance for the input, `max_tokens` for the output);
  - a `response` line with the same call id and the actual tokens and cost.
  A call with a dispatch line but no response line (killed worker, network failure) or with
  missing usage has unknown cost. Unknown is stored as `null`, never 0, and budget decisions use
  the dispatch estimate for it.
- Transport retries: network errors, HTTP 429 and 5xx are retried with backoff (at most 3 times),
  each retry with its own ledger lines. A reply that is not valid JSON for our schema is
  re-asked once. These are counted separately and are active in both agent approaches; they are
  not self-correction.
- `FakeChatClient`: returns scripted replies and records every request it was given.
- Temperature is 0 by default, configurable, and stored in the manifest.

### 6.4 Agent (`src/agent/`)

One loop, one action per model decision:

1. **Observe** (`observer.py`): take a JPEG screenshot (1280 x 800), saved as
   `screenshots/sNN_aM.jpg` (step and attempt, never overwritten), and run one injected script
   that lists the visible interactive elements. Each gets a number and is described by ARIA
   role, accessible name and current value, for example `[7] textbox "Quantity" value=""`. A
   select also lists the visible labels of its options. The script returns the visible page
   text, trimmed. `id`, `data-testid` and option values are not included.
   In text-only mode (section 14) the screenshot is still saved for the record but not sent.
2. **Think** (`planner.py`): send the precondition and instruction, the business rules in plain language, the
   last steps and their results, the element list and the screenshot. The model answers with
   one JSON object: a short thought and one action.
3. **Act** (`actuator.py`): `click`, `type`, `select` (by visible option label), `press`,
   `scroll`, `back`, or `done`. Actions address elements by number. `done` carries a summary
   and the model's verdict; a `FAIL` must carry one claim from the list in section 6.1 (with
   the observed stock for `wrong_balance`) and a one-sentence reason.
4. **Check**: after an action the loop waits for the page to settle and records whether URL or
   page text changed. The outcome is part of the next request.

Errors shown to the model come from a short fixed list ("element 12 does not exist",
"element 7 is not a select", "option not found", "the page did not respond"). Playwright's own
messages, which can contain selectors, go to the trace only.

Attempts and retries. An *attempt* is one model decision plus its execution. A step fails when
the action names a missing element, has an unknown type, or its execution raises. With
`max_retries = R` a step gets one attempt plus at most R retries, so 4 attempts for R = 3 and
exactly 1 for R = 0. Each retry observes again and tells the model the sanitized error. When the
attempts are used up, the run ends as `AGENT_ERROR`. The step limit and the deadline end the run
the same way. Transport retries, JSON re-asks and step retries are counted in separate fields.
The trace has one entry per attempt, with the path of the screenshot the model was given.

Submission guard. If an attempt raised after the evidence recorder saw its `POST /issue` leave
the browser, the step is not retried: the loop observes the resulting page and tells the model
that the form was already submitted. The model can still decide to submit again; the evidence
check then sees two submissions (section 6.5).

Prompt rules: there is one generic system prompt. It contains the action format, the claim list
and the business rules R1 to R5 in plain language, the way a human tester would know them. It
contains no part ids, no page names and no navigation hints. The only scenario-specific inputs
are the `precondition` and `instruction` sentences from the scenario file.

Leak test. The agent's requests must depend only on public input. The test runs the same
scripted session twice against identical instances with identical public sentences, once with the
real private scenario data and once with private fields replaced by sentinel values (other
`expected` numbers, another `action` block, another defect label passed to the harness), and
requires the recorded outgoing requests to be identical. Separately it checks that no request
contains a `data-testid`, an element `id` or an internal element marker. Both are run on normal
and retry paths.

The existing stub `Planner.plan(goal) -> list[Step]` becomes
`Planner.next_step(goal, observation, history) -> Step`.

### 6.5 Execution evidence and oracle

**Execution evidence (`src/harness/evidence.py`).** It answers one question: was the test
actually carried out? It uses only what the recorder saw in the browser.

| Scenario type | Evidence required |
|---|---|
| Issue (SP-01, SP-03) | E1: exactly one `POST /issue` left the browser, and its part, quantity and work order are the scenario's. E2, for approaches whose judge reads the screen (`playwright_baseline`, `pure_agent`): after that submission the tester saw the part (definition in section 6.2), so a verdict about the resulting balance has a basis. For `agent_with_verification` the oracle's balance check takes that role; whether the agent looked is recorded but not required. |
| Inspection (SP-02) | No `POST /issue` left the browser, and the tester saw the part at least once. Required in all three approaches. |

If the tester did not finish, or the required evidence is missing, the run is `AGENT_ERROR`,
whatever any judge says. Saying "done" on the home page earns nothing in any approach, and a
pure agent that submits and reports `PASS` without looking at the balance has not carried out
the test.

**Oracle (`src/oracle/`).** It never uses the model and never writes.

- `db_inspector.py`: opens the run's SQLite file read-only (`mode=ro`).
- `api_inspector.py`: calls the read-only API.
- `page_inspector.py`: opens its own page in a separate browser context, loads the inventory,
  and checks with the browser whether the part's badge is actually visible (computed
  visibility, not just present in the HTML).
- `facts.py`: collects these readings into one "final-state facts" object. It is stored for
  every run of every approach (step 7 in section 5) and is what scoring uses to confirm claims.
- `rules.py`: the checks. `verdict.py`: turns them into a verdict.

| Id | Check | Claim reported when it fails |
|---|---|---|
| INV-1 | No part has `stock_qty < 0`. | `negative_stock` |
| INV-2 | For every part, `stock_qty = initial_stock - sum(accepted issue quantities)`. | `wrong_balance` |
| INV-3 | The scenario part's stock in the API equals the database. | `other` |
| INV-4a | For the scenario part, the visible badge equals `stock_qty < reorder_level`. | `low_stock_warning_missing` or `low_stock_warning_unexpected` |
| INV-4b | For the scenario part, API `low_stock` equals `stock_qty < reorder_level`. | `other`, with the two observed values |
| INV-5 | Each accepted request has exactly one movement row with the same part, work order, quantity and type `ISSUE`; each rejected request has none. | `movement_log_wrong` |
| INV-6 | The audit log matches the browser: the rows in `issue_requests` are the submissions the recorder saw, in number and content. | `other` |
| EXP | The scenario's `expected` values hold: `issue_accepted`, `stock_after`, `low_stock_warning`. | `over_issue_accepted`, `wrong_balance`, `low_stock_warning_missing`, or `other` |

INV-6 separates the two cases the audit table alone cannot: one submission logged twice by the
MES is a product defect (`FAIL`), two submissions by the tester is a test that was not carried
out as specified (`AGENT_ERROR`, from the evidence check).

Oracle verdict: `INCONCLUSIVE` if a source cannot be read; `FAIL` with the failed checks and
their claims if any check fails; otherwise `PASS`.

How each defect is caught: DEF-01 by INV-1 and EXP, DEF-02 by INV-4a, INV-4b and EXP, DEF-03 by
INV-2 and EXP. A fault in the API alone, with a correct badge, fails only INV-4b and is
reported as `other`, not as a badge problem.

### 6.6 Baseline (`src/baseline/` and `tests/baseline_playwright/`)

One plain Python function per scenario, written the way such tests are written today: fixed
selectors (`#id`, `data-testid`), fixed steps, assertions on what the page shows. Scripts start
at the home page like every tester.

- Reading a part's row goes through one shared helper, `read_part_row(page, part_id)`. It
  locates the row, requires it to be visible, returns its cells, and tells the evidence
  recorder that the script saw the part.
- Business assertions go through `expect_business(condition, claim, observed=None)`. A failed
  one raises `BusinessAssertion` and gives `FAIL` with that claim. Example for SP-02: the script
  reads the SEN-015 row (execution), then asserts the badge inside it is visible (business,
  `low_stock_warning_missing`). A missing badge is therefore a `FAIL`, not a locator error.
- Everything else (a page that does not open, a row or form control that is not found, a
  timeout, any other exception) is an execution failure and gives `AGENT_ERROR` with
  `error_kind: script`. The four verdicts stay four.

### 6.7 The three approaches and one verdict flow

| Approach | Who acts | Step retries | Judge |
|---|---|---|---|
| `playwright_baseline` | Script | none | The script's business assertions |
| `pure_agent` | Model | 0 | The model, in its `done` action |
| `agent_with_verification` | Model | 3 | The oracle |

The flow is the same for all three:

1. Tester did not finish (error, limit, deadline): `AGENT_ERROR`.
2. Required execution evidence missing (section 6.5): `AGENT_ERROR`
   (`error_kind: not_carried_out`).
3. Otherwise the approach's judge decides: `PASS`, `FAIL` with a claim, or (oracle only)
   `INCONCLUSIVE`. `run.json` is written. For `agent_with_verification` the facts the oracle
   judged on are written in the same step.
4. For the other two approaches the final-state facts are collected now, for the record and
   for scoring. In agent runs the model's opinion and the oracle's opinion are both stored,
   whichever one counts.

### 6.8 Benchmark and metrics (`src/benchmark/`)

**Plan.** 3 approaches x 3 scenarios x 2 states (clean, defect on) x 5 repeats = 90 runs. In a
defect run only the scenario's own defect is on. The order is shuffled with a stored seed. Up to
`BENCHMARK_CONCURRENCY` (default 3) supervised workers run at once.

**Lock.** Before anything else the runner takes an operating-system file lock on
`experiment.lock` in the experiment folder (through the `filelock` library, which uses the
system's own locking on macOS and Windows) and keeps it until the summary is written. A second
runner on the same folder is refused. The system releases the lock when its owner dies, so
there is no stale-lock takeover that two starters could get wrong. The runner that gets the lock
runs `recover(dir)` before anything else.

**Scored specification.** The committed file `data/scored_experiment.yaml` fixes the published
experiment: the model id verified in the first plan step, the observation mode chosen there,
all three approaches, all three scored scenarios, both states, five repeats, step retries 0 for
`pure_agent` and 3 for `agent_with_verification`, temperature 0, the step and time limits.
A `--scored` start takes its settings from this file only. Any override (a subset of approaches
or scenarios, other repeats, another model, another retry limit) is refused before a worker
starts.

**Manifest.** Before any worker starts, the runner writes `experiment.json`: experiment id,
mode (`live` or `fake`), model id, temperature, observation mode, retry settings, hashes of the
system prompt and the observer script, one hash over the contents on disk of the execution
inputs (the files ending in `.py`, `.js`, `.html`, `.css`, `.csv`, `.json` and `.yaml` under
`src/`, `data/` and `tests/agent_tests/`, plus `requirements.txt`; generated files such as
`__pycache__` are not part of it), in fake mode the hash of the scripted reply files, the git
commit and whether the worktree is clean, the limits, the seed and the full list of planned run
ids. It is never rewritten; progress goes to `progress.json`. Every
`run.json` carries the experiment id.

**Resume.** A stopped benchmark can be continued only into its own folder: the runner
recomputes the manifest and refuses if anything differs (a folder made in `fake` mode is refused
for a `live` start; so is any changed file under the hashed folders). A planned run is skipped
only if its record is terminal, has this experiment id and matches its planned cell. `cancelled`
runs are run again; their old folder is kept as `<run_id>.cancelled-N`.

**Eligibility.** The summary states whether the experiment is eligible for publication. It is
only if: mode is `live`, the worktree was clean, the prompt and observer hashes equal those of
the tag `agent-v1`, the manifest equals the scored specification (all 90 cells, the verified
model id, the observation mode, the fixed retry settings), all planned runs are terminal, and
the experiment was never stopped, cancelled in part, or resumed. Anything else is a diagnostic
result. The published numbers come from one uninterrupted benchmark started with `--scored`,
which checks the first four conditions before spending anything.

**Attempts.** Every `--scored` start gets its own folder under `reports/scored/` and one line in
`reports/scored/attempts.jsonl` when it ends: folder, start time, planned runs, runs that were
started, outcome (eligible, stopped, failed) and its number of interventions.

**Cost limit.** `BENCHMARK_MAX_COST_USD` is an admission limit. Before starting a worker the
runner sums all ledgers: actual cost where known, the dispatch estimate where the cost is
unknown or the response is missing. At or above the limit no new run starts and the experiment
ends as `stopped_cost` (not eligible). Runs in flight finish, so the overshoot is at most what
those runs spend. The summary shows known cost, estimated cost and token totals separately.

**Scoring.** Each run is put in one class, using the defect map of section 6.1 and the run's
final-state facts:

| State | Verdict | Class |
|---|---|---|
| defect on | `FAIL` whose claim counts for this defect and is true in the final-state facts | detected |
| defect on | any other `FAIL` (claim does not count, is not true, or cannot be checked because facts are missing) | unconfirmed report; the defect counts as missed |
| defect on | `PASS` | missed |
| clean | `FAIL` | false alarm |
| clean | `PASS` | correct pass |
| any | `AGENT_ERROR` or `INCONCLUSIVE` | not completed |

Confirming claims with the facts is done by the scorer, which knows the truth; it is the same
for all three approaches and is not part of any approach's judge.

**Metrics.** Denominators come from the manifest's planned cells for that approach, never from
fixed numbers, so a filtered or one-repeat experiment is computed correctly. For the full plan
they are 30 runs, 15 clean and 15 with defect.

| Metric | Definition |
|---|---|
| TCR | runs with `PASS` or `FAIL` / planned runs |
| DDR | detected / planned defect runs |
| DRP | detected / all `FAIL` verdicts (detected + unconfirmed + false alarms) |
| FPR | false alarms / planned clean runs |
| Time | mean, standard deviation and median of the published duration: `act` plus the counting `judge`, the work the approach needs to produce its verdict. Start-up, evidence check, fact collection and teardown are stored separately, and the end-to-end time is kept too. The same boundaries apply to the baseline. |
| Cost | mean cost and tokens per run (the baseline has none) |
| Human interventions | number of times a person had to restart or repair something during this experiment. Each is one line in its `interventions.jsonl` with time, text and, if known, the approach. Reported in the experiment's own summary next to the other six metrics, per approach where attributed. For the published experiment it is 0 by the eligibility rule. The effort it took to get there is published separately from `attempts.jsonl`: the number of scored attempts, and for each attempt its interventions and how many of its planned runs were started. No development or offline run is part of that figure. |

A metric with an empty denominator has no value (`null`, shown as "n/a"). While runs are
pending, the summary is labelled partial and shows planned, terminal, cancelled and pending
counts.

Outputs: `results.csv` (one row per run), `summary.json`, plus the manifest.

### 6.9 Dashboard (`src/dashboard/`)

FastAPI with server-rendered pages and a small plain script that polls once a second. It reads
the files in `reports/`; it has no database of its own.

Core, always kept:

1. **Start, watch and stop a single run**: scenario, approach, defect on or off. The run page
   polls and shows at least the latest screenshot, the status and, at the end, the verdict.
2. **Start, watch and stop the benchmark**: progress (planned, terminal, pending), eligibility.
3. **Results**: the metrics table per approach and the list of runs.

Detail that can be cut if time is short: the list of thoughts, actions and results on the run
page, the evidence and oracle-check tables there, filters on the run list, and "Open mini MES"
(the command `python -m src.mes --port 8080 --defects DEF-03` does the same).

Single runs started from the dashboard or the command line go to `reports/adhoc/<run_id>/`.
The dashboard uses the same supervisor and runner as the commands. One job runs at a time.
If a benchmark runner does not react to stop, the dashboard kills its process tree and calls
`recover` on the experiment folder.

Protection of the buttons that start and stop jobs: the app creates a random token when it
starts; every state-changing request must carry it (hidden form field or header), its `Host`
must be the dashboard's own `127.0.0.1` or `localhost` address, and an `Origin` header, when
present, must match. Requests from other pages are refused.

Commands: `python -m src.mes`, `python -m src.agent.runner --scenario SP-03 --approach
agent_with_verification --defect on`, `python -m src.benchmark.runner --output-dir
reports/experiment_01`, `python -m src.dashboard`.

### 6.10 Run record

`reports/<experiment>/<run_id>/`:

- `run.json`: experiment id, status (terminal verdict or `cancelled`), scenario, approach,
  defect state and id, repeat, verdict, judge, error kind, claim, model verdict, oracle verdict
  with each check, evidence (submissions seen, times the tester saw the part), final-state
  facts or "missing", phase timings, steps, attempt and retry counters, tokens, cost, operating
  system.
- `trace.jsonl`: one line per attempt, with its screenshot path. `usage.jsonl`: dispatch and
  response lines.
- `screenshots/sNN_aM.jpg`.
- `mes.db` (final database) and `mes.log`.

`reports/` stays out of git. The final `results.csv`, `summary.json` and `experiment.json` are
copied to `docs/results/` on purpose when the experiment is done.

## 7. Speed

| Item | Target | How it is measured |
|---|---|---|
| Mini MES page | median under 50 ms | 50 requests over real HTTP to a running instance on the laptop, after 5 warm-up requests, for `/inventory` and `/issue` |
| Run start-up | median under 3 s | `startup` phase of the run record: worker start to first usable page (database, MES, browser), at concurrency 1, over the baseline runs of one benchmark |
| Baseline run | median under 5 s end to end | run records |
| Agent run | median published duration under 45 s; depends on the provider and is measured, not promised | run records |
| Full benchmark, concurrency 3 | under 20 minutes | manifest and progress timestamps |

Every measurement is stored with operating system, concurrency and the statistic used.

Measures taken for speed: server-rendered pages, SQLite, headless Chromium, JPEG screenshots at
fixed size, a short element list instead of the full page source, only the last few steps in the
prompt, one warm HTTP connection per run, parallel runs.

## 8. Reliability and reproducibility

- Identical start state for every run (fresh database from the same files).
- Fixed seed for the run order, temperature 0, all settings and content hashes in the manifest.
- Every run folder ends with a record, also when a process is killed.
- Offline tests cover the mini MES, the evidence check, the oracle, the baseline and the agent
  loop (with the fake model), so most of the system is checked without spending tokens.

Keeping the scored scenarios unseen:

- The prompt and the observation format are developed only on the three development scenarios
  in `dev_scenarios.yaml`: an over-issue of motors (`MOT-001`), a low-stock check of the valve
  (`VLV-030`), an issue of filters (`FIL-020`), clean and with the defects. No scored scenario
  uses these parts.
- The three scored scenarios are run with the real model for the first time in the scored
  benchmark. Before that they are exercised only with scripted replies, which involve no model.
- When development ends, the commit is tagged `agent-v1`. The scored benchmark must show the
  prompt and observer hashes of that tag (section 6.8, eligibility).
- If a harness bug shows up during the scored benchmark, it may be fixed and a whole new
  benchmark run with the same prompt and observer hashes. Both are reported.
- Stated limitation: development and scored scenarios are the same kinds of task on the same
  application, so the result says how the agent performs on unseen cases of known task types,
  not on unknown workflows.

## 9. Cross-platform

Python 3.10 or newer. Setup is `python -m venv`, `pip install -r requirements.txt`,
`python -m playwright install chromium`. Paths use `pathlib`, child processes use
`sys.executable`, process trees use `psutil`, SQLite read-only URIs are built with
`Path.as_uri()`. No shell scripts. CI runs the offline tests on Ubuntu and Windows.

## 10. Security and privacy

- The API key is read from the repository's `.env`, which is ignored by git. That file is the
  only place where the key may be. It is sent only to `https://openrouter.ai` and never written
  to run records, logs or child output.
- The secret scan (section 6.2) is tested with a canary key that is placed both in `.env` and
  in a log file: it must report the log and not the `.env`. Before publication it is run over
  the repository working tree, the experiment folder and `docs/results/`.
- Both web apps bind to `127.0.0.1`. The dashboard's state-changing endpoints need its token and
  a matching `Host` and `Origin`.
- The only data sent to OpenRouter is the instruction, the page text, the element list and
  screenshots of the mini MES, all synthetic.

## 11. Testing

| Layer | What | Needs |
|---|---|---|
| Unit | business rules against `src/main.py`, each defect, claims and scoring, metrics, record writing, model client with a fake transport | nothing |
| Service | mini MES pages and API through FastAPI's test client | nothing |
| Harness | instance start (also concurrent and early exit), evidence recorder, supervisor, process-tree stop, lock, secret scan | Chromium for the recorder |
| Oracle | the six truth cases, a hidden badge, a movement with wrong fields, one submission logged twice | Chromium |
| Baseline | the three scripts pass on a clean MES and fail with the defect; a missing page is an error, a missing badge is a `FAIL` | Chromium |
| Agent offline | full loop with `FakeChatClient` on a real mini MES and browser; leak test | Chromium |
| Live | development scenarios with the real model; marked `live`, run by hand, never in CI | API key |

## 12. Dependencies

Added: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `httpx`, `psutil`, `filelock`. Existing:
`pytest`, `playwright`, `python-dotenv`, `pyyaml`. No ORM, no front-end toolchain.

## 13. What changes compared with the report and slides

The report and both presentations name OpenMES on PostgreSQL in Docker as the system under test.
This design tests our own mini MES on SQLite instead. Reasons: no Docker on the team laptops
(8 GB RAM), a two-week window, and the wish for a fast, simple, fully local setup.

Effect on the study: the system under test is no longer independent production software. To
limit that weakness the mini MES has several pages and two ways to reach the issue form, the
defects were defined before any agent work, and the rules of section 8 apply. The report
should state this as a limitation.

Follow-up, not part of this plan: update report section 3.2 and the "technical stack" and
"architecture" slides (OpenMES, PostgreSQL, Docker become mini MES, SQLite, none; the catalog
now has six parts).

## 14. Risks and stretch

| Risk | Handling |
|---|---|
| GLM-5.3 Flash on OpenRouter does not accept or cannot read our screenshots | The first plan step tests the same model in two modes: with image, and text-only (element list and page text). If only text-only works, the experiment runs text-only and the manifest and the report say so. |
| GLM-5.3 Flash is not available on OpenRouter, or fails both modes | The live experiment is blocked. The team is told; choosing another model is an owner decision outside this plan. All offline parts can still be built and tested. |
| Provider rate limits or slow responses | Concurrency is configurable, transport retries with backoff. A benchmark that had to be stopped is diagnostic; the scored one is run again in one go. |
| Windows process and file handling | CI on Windows from the first step; supervisor and process-tree tests on both systems. |
| The agent submits twice or the wrong thing | Execution evidence turns this into `AGENT_ERROR` instead of a false MES verdict. |
| Two weeks is short | Cut order: dashboard detail and extras (section 6.9), then concurrency above 1 (run sequentially). The dashboard core, the 90 runs and their scoring are never cut. |

Stretch, only after the 90 runs work: a second look of the mini MES (`--ui-variant B`: renamed
ids, reordered columns, different button wording) to measure how baseline and agent cope with
interface change; several actions per model call to save time; more scenarios; dashboard extras.

## 15. Acceptance criteria

1. On a fresh clone, on macOS and on Windows, the documented setup commands succeed and
   `python -m pytest` passes without an API key.
2. Baseline gate: on a clean MES the three scripts pass; with the scenario's defect on, each
   gives `FAIL` with a claim that counts for that defect; a page that cannot be reached gives
   `AGENT_ERROR`.
3. Oracle and evidence gate: in the six scripted cases (3 scenarios x clean or defect) the
   verdict equals the truth. In all three approaches, "done" on the home page ends as
   `AGENT_ERROR`, including SP-02 without looking at the part; with a screen judge, submitting
   and judging without looking at the balance ends as `AGENT_ERROR` too.
4. With a valid key, `python -m src.benchmark.runner --scored` finishes the 90 runs unattended
   in one go and writes `results.csv` and `summary.json` with all metrics of section 6.8 and
   `eligible: true`. A folder from an offline benchmark, a changed file, a second runner on the
   same folder, a subset of the plan, another model or retry limit, and a stopped-and-resumed
   experiment are each refused or marked not eligible.
5. The dashboard can start and stop one run and the full benchmark, shows a running agent with
   at most two seconds delay, and shows the metrics table. A request without its token is
   refused.
6. The key appears nowhere except the repository's `.env`: not in tracked files, run records,
   logs or published results. The canary test passes.
7. After a stopped benchmark and after a timed-out or stuck run, on both systems, no child
   process is left, the ports are free and the run folders can be deleted.
8. The speed targets of section 7 are measured as described there and reported; the first
   three are met.

## 16. Open points from the review

The plan was accepted with these nine points open. Each one is to be settled in the step named,
before that step counts as done.

| Point | Severity | What is still open | Settle in |
|---|---|---|---|
| Seeing a part in text-only mode | high | Settled in 2.4: only the part's inventory row or detail section counts, never the dropdown or the result page; in text mode the whole row, with stock and status, must be in the sent text (`src/harness/evidence.py`). The agent loop must use it in 5.5. | 5.5 |
| Looking at the balance in text-only mode | high | Settled in 2.4 by the same rule: a sighting after the submission always includes the stock value; the result page does not count. The agent runs must use it in 5.6. | 5.6 |
| Clean-up of a stuck run that already has a verdict | high | `recover` must check every registered worker, also when a verdict exists, and keep that verdict. The worker must be registered before it starts its own children. | 4.2, 6.3 |
| One counting claim from the oracle | high | When several checks fail (DEF-02 fails two), the oracle needs a fixed rule for which single claim counts, independent of the order of checks and of which defect is on. | 3.2, 6.1 |
| Files changing during a benchmark | high | Scored workers should run from one frozen copy of the hashed inputs, or the experiment must become ineligible when a file changes between workers. | 6.2 |
| Order of scoring tests | middle | The tests in 5.6 that expect "correct pass" and "detected" need the scorer of 6.1. Move those checks to 6.1 or build the scorer first. | 5.6, 6.1 |
| Attempts log | middle | A scored attempt must be written to `attempts.jsonl` when it starts, and unfinished attempts reconciled from their folders before publication. | 6.1, 6.2 |
| Time of a killed run | middle | Define how the published duration counts a run that was killed during the tester phase. | 4.2, 6.1 |
| Observation mode after the trials | middle | If step 5.7 switches the mode, it must be written into `data/scored_experiment.yaml` before the tag `agent-v1`. | 5.7 |
