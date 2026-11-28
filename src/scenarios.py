"""Test scenarios (design sections 6.1 and 8).

Scored scenarios (SP-01..03) produce the published numbers. Development scenarios
(DEV-01..03) are only for tuning the agent. They are different types, so one can
never be passed where the other is expected by mistake.

A tester gets only `public_text()`: the precondition and the instruction.
"""

from dataclasses import dataclass, field

import yaml

from src.config import ROOT

SCORED_PATH = ROOT / "tests" / "agent_tests" / "test_scenarios.yaml"
DEV_PATH = ROOT / "tests" / "agent_tests" / "dev_scenarios.yaml"
DEFECTS_PATH = ROOT / "data" / "injected_defects.yaml"

ISSUE = "issue"
INSPECT = "inspect"


@dataclass(frozen=True)
class Action:
    type: str                      # "issue" or "inspect"
    part_id: str
    qty: int | None = None
    work_order_id: str | None = None


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    precondition: str
    instruction: str
    defect_id: str
    action: Action = field(repr=False)
    expected: dict = field(repr=False)

    def public_text(self) -> str:
        """All a tester may know about the scenario."""
        return f"Precondition: {self.precondition}\nTask: {self.instruction}"

    @property
    def is_issue(self) -> bool:
        return self.action.type == ISSUE


class ScoredScenario(Scenario):
    pass


class DevScenario(Scenario):
    pass


def _load(path, cls, defect_for) -> dict[str, Scenario]:
    scenarios = {}
    for entry in yaml.safe_load(path.read_text(encoding="utf-8")):
        action = Action(**entry["action"])
        if action.type not in (ISSUE, INSPECT):
            raise ValueError(f"{entry['id']}: unknown action type {action.type!r}")
        scenarios[entry["id"]] = cls(
            id=entry["id"], name=entry["name"], precondition=entry["precondition"], instruction=entry["instruction"],
            defect_id=defect_for(entry), action=action, expected=dict(entry["expected"]),
        )
    return scenarios


def scored_defects() -> dict[str, str]:
    """Scored scenario id -> its defect id, from data/injected_defects.yaml."""
    return {d["scenario"]: d["id"] for d in yaml.safe_load(DEFECTS_PATH.read_text(encoding="utf-8"))}


def load_scored() -> dict[str, ScoredScenario]:
    defects = scored_defects()
    return _load(SCORED_PATH, ScoredScenario, lambda entry: defects[entry["id"]])


def load_dev() -> dict[str, DevScenario]:
    return _load(DEV_PATH, DevScenario, lambda entry: entry["defect"])
