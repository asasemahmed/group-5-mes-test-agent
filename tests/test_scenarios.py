import csv
import json
import re

import pytest

from src.claims import CLAIMS, DEFECT_CLAIMS, ClaimError, counts_for, validate_claim
from src.mes.defects import known_defects
from src.mes.seed import CATALOG_PATH, WORK_ORDERS_PATH
from src.scenarios import DevScenario, ScoredScenario, load_dev, load_scored

with open(CATALOG_PATH, newline="", encoding="utf-8") as _f:
    CATALOG = {row["part_id"]: row for row in csv.DictReader(_f)}
WORK_ORDERS = {wo["work_order_id"] for wo in json.loads(WORK_ORDERS_PATH.read_text(encoding="utf-8"))}


def all_scenarios():
    return list(load_scored().values()) + list(load_dev().values())


def test_three_scored_and_three_development_scenarios():
    scored, dev = load_scored(), load_dev()
    assert list(scored) == ["SP-01", "SP-02", "SP-03"]
    assert list(dev) == ["DEV-01", "DEV-02", "DEV-03"]
    assert all(type(s) is ScoredScenario for s in scored.values())
    assert all(type(s) is DevScenario for s in dev.values())


def test_scored_scenarios_get_their_defect_from_the_defects_file():
    assert {s.id: s.defect_id for s in load_scored().values()} == {"SP-01": "DEF-01", "SP-02": "DEF-02", "SP-03": "DEF-03"}
    assert {s.defect_id for s in load_dev().values()} <= set(known_defects())


@pytest.mark.parametrize("scenario", all_scenarios(), ids=lambda s: s.id)
def test_referenced_parts_and_work_orders_exist(scenario):
    assert scenario.action.part_id in CATALOG
    if scenario.is_issue:
        assert scenario.action.work_order_id in WORK_ORDERS
        assert scenario.action.qty > 0


@pytest.mark.parametrize("scenario", all_scenarios(), ids=lambda s: s.id)
def test_precondition_agrees_with_the_catalog(scenario):
    part = CATALOG[scenario.action.part_id]
    assert scenario.action.part_id in scenario.precondition
    stock = re.search(r"has (\d+) piece", scenario.precondition)
    assert stock and int(stock.group(1)) == int(part["initial_stock"])
    reorder = re.search(r"reorder level is (\d+)", scenario.precondition)
    if reorder:
        assert int(reorder.group(1)) == int(part["reorder_level"])


@pytest.mark.parametrize("scenario", all_scenarios(), ids=lambda s: s.id)
def test_expected_values_follow_the_rules(scenario):
    part = CATALOG[scenario.action.part_id]
    stock, reorder = int(part["initial_stock"]), int(part["reorder_level"])
    if scenario.is_issue:
        accepted = scenario.action.qty <= stock
        assert scenario.expected == {"issue_accepted": accepted, "stock_after": stock - scenario.action.qty if accepted else stock}
    else:
        assert scenario.expected == {"low_stock_warning": stock < reorder}


def test_scored_and_development_scenarios_share_no_part():
    scored_parts = {s.action.part_id for s in load_scored().values()}
    dev_parts = {s.action.part_id for s in load_dev().values()}
    assert scored_parts.isdisjoint(dev_parts)


def test_public_text_is_precondition_and_instruction_only():
    scenario = load_scored()["SP-03"]
    assert scenario.public_text() == (
        "Precondition: BELT-010 has 10 pieces in stock.\n"
        "Task: Issue 2 conveyor belts (BELT-010) to maintenance repair line 3 and verify the updated stock balance."
    )
    assert "WO-2026-0903" not in scenario.public_text() and "8" not in scenario.public_text()


def test_every_defect_has_at_least_one_counting_claim():
    assert set(DEFECT_CLAIMS) == set(known_defects())
    assert all(DEFECT_CLAIMS[d] and set(DEFECT_CLAIMS[d]) <= set(CLAIMS) for d in DEFECT_CLAIMS)


def test_claims_are_validated():
    assert validate_claim({"claim": "wrong_balance", "observed_stock": 6}) == {"claim": "wrong_balance", "observed_stock": 6}
    assert validate_claim({"claim": "low_stock_warning_missing", "extra": 1}) == {"claim": "low_stock_warning_missing"}
    assert validate_claim({"claim": "other", "text": " API says false "}) == {"claim": "other", "text": "API says false"}
    for bad in [{"claim": "broken"}, {"claim": "wrong_balance"}, {"claim": "wrong_balance", "observed_stock": "6"},
                {"claim": "wrong_balance", "observed_stock": True}, {"claim": "other"}, "wrong_balance"]:
        with pytest.raises(ClaimError):
            validate_claim(bad)


def test_counts_for_uses_the_fixed_map():
    assert counts_for("DEF-03", {"claim": "wrong_balance", "observed_stock": 6})
    assert not counts_for("DEF-03", {"claim": "movement_log_wrong"})
    assert counts_for("DEF-01", {"claim": "negative_stock"})
    assert not counts_for("DEF-02", {"claim": "other", "text": "x"})
