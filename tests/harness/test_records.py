import json

import pytest

from src.harness.records import (
    STATUS_CANCELLED,
    PhaseTimer,
    RunRecord,
    append_jsonl,
    ledger_dispatch,
    ledger_response,
    read_json,
    read_jsonl,
    summarise_ledger,
    write_json_atomic,
)


def make_record(**changes):
    record = RunRecord(run_id="r-1", experiment_id="exp-1", scenario_id="SP-03", approach="agent_with_verification",
                       defect_state="defect", defect_id="DEF-03", repeat=2)
    for key, value in changes.items():
        setattr(record, key, value)
    return record


def test_run_record_round_trip(tmp_path):
    record = make_record(status="FAIL", verdict="FAIL", judge="oracle",
                         claim={"claim": "wrong_balance", "observed_stock": 6}, counters={"step_retries": 1})
    record.save(tmp_path)
    loaded = RunRecord.load(tmp_path)
    assert loaded == record
    assert loaded.terminal


def test_running_and_cancelled_are_not_terminal(tmp_path):
    assert not make_record().terminal
    assert not make_record(status=STATUS_CANCELLED).terminal
    assert RunRecord.load(tmp_path) is None


def test_unknown_fields_in_a_record_are_ignored():
    data = make_record().to_dict() | {"field_from_a_later_version": 1}
    assert RunRecord.from_dict(data).run_id == "r-1"


def test_atomic_write_replaces_the_whole_file_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "run.json"
    write_json_atomic(path, {"a": 1})
    write_json_atomic(path, {"b": 2})
    assert read_json(path) == {"b": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["run.json"]


def test_phases_add_up_to_end_to_end():
    now = [0.0]
    timer = PhaseTimer(clock=lambda: now[0])
    for name, seconds in [("startup", 1.5), ("act", 20.0), ("evidence", 0.1), ("judge", 0.4), ("facts", 0.3), ("teardown", 0.7)]:
        with timer.phase(name):
            now[0] += seconds
        if name == "startup":
            timer.milestone("first_page")
    data = timer.to_dict()
    assert sum(data["phases"].values()) == pytest.approx(data["end_to_end"]) == pytest.approx(23.0)
    assert data["milestones"] == {"first_page": 1.5}


def test_phase_time_is_kept_when_the_phase_raises():
    now = [0.0]
    timer = PhaseTimer(clock=lambda: now[0])
    with pytest.raises(RuntimeError):
        with timer.phase("act"):
            now[0] += 2.0
            raise RuntimeError("tester failed")
    assert timer.phases["act"] == 2.0


def test_jsonl_lines_survive_and_a_cut_off_line_is_skipped(tmp_path):
    path = tmp_path / "trace.jsonl"
    append_jsonl(path, {"step": 1})
    append_jsonl(path, {"step": 2})
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"step": 3, "cut')  # crash in the middle of a write
    assert read_jsonl(path) == [{"step": 1}, {"step": 2}]
    assert read_jsonl(tmp_path / "missing.jsonl") == []


def test_ledger_known_unknown_and_estimated_cost(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    ledger_dispatch(ledger, "c1", 0.001)
    ledger_response(ledger, "c1", 500, 90, 0.0002)
    ledger_dispatch(ledger, "c2", 0.001)
    ledger_response(ledger, "c2", 400, 50, None)  # provider gave no cost
    ledger_dispatch(ledger, "c3", 0.002)          # killed before the response came back

    summary = summarise_ledger(ledger)
    assert summary.calls == 3
    assert summary.known_cost_usd == pytest.approx(0.0002)
    assert summary.unknown_calls == 2
    assert summary.unknown_estimate_usd == pytest.approx(0.003)
    assert summary.budget_usd == pytest.approx(0.0032)
    assert (summary.tokens_in, summary.tokens_out) == (900, 140)
    assert summary.to_dict()["cost_usd"] is None  # unknown is never shown as a number


def test_ledger_with_all_costs_known(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    ledger_dispatch(ledger, "c1", 0.001)
    ledger_response(ledger, "c1", 10, 5, 0.0001)
    assert summarise_ledger(ledger).to_dict()["cost_usd"] == pytest.approx(0.0001)
    assert summarise_ledger(tmp_path / "none.jsonl").calls == 0


def test_ledger_dispatch_line_is_on_disk_immediately(tmp_path):
    ledger = tmp_path / "usage.jsonl"
    ledger_dispatch(ledger, "c1", 0.004)
    line = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert line["type"] == "dispatch" and line["estimate_usd"] == 0.004
