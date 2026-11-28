"""Run records, phase timing and the usage ledger (design sections 6.2, 6.3 and 6.10).

Files in a run folder:
    run.json      the run record, always replaced as a whole (atomic write)
    trace.jsonl   one line per agent attempt
    usage.jsonl   the usage ledger: a "dispatch" line before every model call and a
                  "response" line after it
"""

import json
import os
import platform
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE", "AGENT_ERROR")
STATUS_RUNNING = "running"
STATUS_CANCELLED = "cancelled"  # taken away from the approach; not a verdict, not terminal

RUN_FILE = "run.json"
TRACE_FILE = "trace.jsonl"
USAGE_FILE = "usage.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ---- files -------------------------------------------------------------------


def write_json_atomic(path: Path | str, data) -> None:
    """Write JSON to a temporary file next to `path`, then replace `path` in one step.

    A reader never sees half a file. On Windows the replace can fail for a moment
    while another process has the file open, so it is retried briefly.
    """
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.02)


def read_json(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_jsonl(path: Path | str, entry: dict) -> None:
    """Append one line and flush it to disk, so it survives a crash right after."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path | str) -> list[dict]:
    """All complete lines. A line cut off by a crash is skipped."""
    path = Path(path)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


# ---- phase timing --------------------------------------------------------------

PHASES = ("startup", "act", "evidence", "judge", "facts", "teardown")
STARTUP_MILESTONES = ("worker_start", "mes_ready", "browser_ready", "first_page")


class PhaseTimer:
    """Monotonic timing of a run's phases and start-up milestones, in seconds."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._start = clock()
        self.phases: dict[str, float] = {}
        self.milestones: dict[str, float] = {}

    def since_start(self) -> float:
        return self._clock() - self._start

    def milestone(self, name: str) -> None:
        self.milestones[name] = round(self.since_start(), 4)

    def phase(self, name: str):
        timer = self

        class _Phase:
            def __enter__(self):
                self.begin = timer._clock()
                return self

            def __exit__(self, *exc):
                timer.phases[name] = round(timer.phases.get(name, 0.0) + timer._clock() - self.begin, 4)
                return False

        return _Phase()

    def end_to_end(self) -> float:
        return round(self.since_start(), 4)

    def to_dict(self) -> dict:
        return {"phases": dict(self.phases), "milestones": dict(self.milestones), "end_to_end": self.end_to_end()}


# ---- run record ------------------------------------------------------------------


@dataclass
class RunRecord:
    run_id: str
    experiment_id: str
    scenario_id: str
    approach: str
    defect_state: str                  # "clean" or "defect"
    defect_id: str | None = None
    repeat: int = 1
    status: str = STATUS_RUNNING       # a verdict, "running" or "cancelled"
    verdict: str | None = None
    judge: str | None = None           # "script", "model" or "oracle"
    error_kind: str | None = None      # for AGENT_ERROR: timeout, killed, not_carried_out, script, ...
    claim: dict | None = None          # the counting claim of a FAIL
    model_verdict: dict | None = None
    oracle_verdict: dict | None = None
    evidence: dict | None = None
    facts: dict | None = None
    facts_status: str | None = None    # collected, missing, cut_short
    timing: dict = field(default_factory=dict)
    steps: int = 0
    counters: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    os: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status in VERDICTS

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, run_dir: Path | str) -> None:
        write_json_atomic(Path(run_dir) / RUN_FILE, self.to_dict())

    @classmethod
    def load(cls, run_dir: Path | str) -> "RunRecord | None":
        path = Path(run_dir) / RUN_FILE
        return cls.from_dict(read_json(path)) if path.exists() else None


# ---- usage ledger ------------------------------------------------------------------


def ledger_dispatch(path: Path | str, call_id: str, estimate_usd: float) -> None:
    """Written before a model request is sent: if the run dies now, the call still counts."""
    append_jsonl(path, {"type": "dispatch", "call_id": call_id, "estimate_usd": estimate_usd, "time": utc_now()})


def ledger_response(path: Path | str, call_id: str, tokens_in: int | None, tokens_out: int | None, cost_usd: float | None) -> None:
    """Written after a response. cost_usd None means the provider gave no cost."""
    append_jsonl(path, {"type": "response", "call_id": call_id, "tokens_in": tokens_in, "tokens_out": tokens_out,
                        "cost_usd": cost_usd, "time": utc_now()})


@dataclass
class LedgerSummary:
    calls: int = 0
    known_cost_usd: float = 0.0        # sum of costs the provider reported
    unknown_calls: int = 0             # no response line, or a response without cost
    unknown_estimate_usd: float = 0.0  # dispatch estimates of those unknown calls
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def budget_usd(self) -> float:
        """What budget decisions count: known cost plus estimates for the unknown part."""
        return self.known_cost_usd + self.unknown_estimate_usd

    def to_dict(self) -> dict:
        data = asdict(self)
        data["budget_usd"] = self.budget_usd
        data["cost_usd"] = None if self.unknown_calls else self.known_cost_usd
        return data


def summarise_ledger(path: Path | str) -> LedgerSummary:
    dispatches: dict[str, dict] = {}
    responses: dict[str, dict] = {}
    for entry in read_jsonl(path):
        if entry.get("type") == "dispatch":
            dispatches[entry["call_id"]] = entry
        elif entry.get("type") == "response":
            responses[entry["call_id"]] = entry

    summary = LedgerSummary(calls=len(dispatches))
    for call_id, dispatch in dispatches.items():
        response = responses.get(call_id)
        if response is not None:
            summary.tokens_in += response.get("tokens_in") or 0
            summary.tokens_out += response.get("tokens_out") or 0
        if response is not None and response.get("cost_usd") is not None:
            summary.known_cost_usd += response["cost_usd"]
        else:
            summary.unknown_calls += 1
            summary.unknown_estimate_usd += dispatch.get("estimate_usd") or 0.0
    return summary
