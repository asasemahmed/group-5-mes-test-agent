import pytest

from src.main import Inventory
from src.mes.db import connect
from src.mes.defects import DefectError, parse_defects
from src.mes.seed import build_database
from src.mes.service import MesService

WO = "WO-2026-0891"
WO_LINE3 = "WO-2026-0903"


@pytest.fixture
def make_service(tmp_path):
    connections = []

    def make(defects=""):
        conn = connect(build_database(tmp_path / f"mes-{len(connections)}.db"))
        connections.append(conn)
        return MesService(conn, parse_defects(defects))

    yield make
    for conn in connections:
        conn.close()


def stock(service, part_id):
    return service.get_part(part_id)["stock_qty"]


# ---- clean behaviour equals the reference model in src/main.py ----------


@pytest.mark.parametrize("part_id, qty, work_order", [("BRG-6205", 3, WO), ("BELT-010", 2, WO_LINE3)])
def test_issue_matches_reference_model(make_service, part_id, qty, work_order):
    service = make_service()
    reference = Inventory.from_csv()
    expected_accepted = reference.issue(part_id, qty)

    result = service.issue_part(part_id, work_order, qty)

    assert result.accepted == expected_accepted
    assert stock(service, part_id) == reference.parts[part_id].stock


def test_low_stock_matches_reference_model(make_service):
    service = make_service()
    reference = Inventory.from_csv()
    parts = service.list_parts()
    assert {p["part_id"] for p in parts} == set(reference.parts)
    for part in parts:
        assert part["low_stock"] == reference.parts[part["part_id"]].low_stock


def test_scenario_expectations_on_a_clean_mes(make_service):
    service = make_service()
    assert service.issue_part("BRG-6205", WO, 3).accepted is False  # SP-01
    assert stock(service, "BRG-6205") == 2
    assert service.get_part("SEN-015")["low_stock"] is True  # SP-02
    assert service.issue_part("BELT-010", WO_LINE3, 2).accepted is True  # SP-03
    assert stock(service, "BELT-010") == 8


# ---- R2 and R3 -----------------------------------------------------------


def test_accepted_issue_writes_one_matching_movement_and_audit_row(make_service):
    service = make_service()
    result = service.issue_part("BELT-010", WO_LINE3, 2)

    assert result.message == "Issued 2 x BELT-010 to WO-2026-0903."
    [request] = service.list_issue_requests()
    assert (request["id"], request["part_id"], request["work_order_id"], request["qty"], request["accepted"]) == (
        result.request_id, "BELT-010", WO_LINE3, 2, 1)
    [movement] = service.list_movements()
    assert (movement["request_id"], movement["part_id"], movement["work_order_id"], movement["qty"], movement["movement_type"]) == (
        result.request_id, "BELT-010", WO_LINE3, 2, "ISSUE")


def test_rejected_issue_changes_nothing_but_the_audit_log(make_service):
    service = make_service()
    result = service.issue_part("BRG-6205", WO, 3)

    assert result.message == "Rejected: requested 3, only 2 in stock."
    assert stock(service, "BRG-6205") == 2
    assert service.list_movements() == []
    [request] = service.list_issue_requests()
    assert request["accepted"] == 0 and request["qty"] == 3


@pytest.mark.parametrize("qty", [0, -1, None])
def test_non_positive_or_missing_quantity_is_rejected(make_service, qty):
    service = make_service()
    assert service.issue_part("BELT-010", WO, qty).accepted is False
    assert stock(service, "BELT-010") == 10


def test_closed_work_order_is_rejected(make_service):
    service = make_service()
    service.conn.execute("UPDATE work_orders SET status = 'CLOSED' WHERE work_order_id = ?", (WO,))
    result = service.issue_part("BELT-010", WO, 1)
    assert result.accepted is False and "CLOSED" in result.message


def test_unknown_part_and_work_order_are_rejected_and_logged(make_service):
    service = make_service()
    assert service.issue_part("XXX-999", WO, 1).accepted is False
    assert service.issue_part("BELT-010", "WO-0000", 1).accepted is False
    assert len(service.list_issue_requests()) == 2 and service.list_movements() == []


def test_stock_never_goes_negative_on_a_clean_mes(make_service):
    service = make_service()
    for _ in range(5):
        service.issue_part("BRG-6205", WO, 1)
    assert stock(service, "BRG-6205") == 0
    assert min(p["stock_qty"] for p in service.list_parts()) >= 0


# ---- the three defects ---------------------------------------------------


def test_def01_accepts_an_over_issue_and_stock_goes_negative(make_service):
    service = make_service("DEF-01")
    assert service.issue_part("BRG-6205", WO, 3).accepted is True
    assert stock(service, "BRG-6205") == -1


def test_def02_hides_the_low_stock_warning(make_service):
    service = make_service("DEF-02")
    assert service.get_part("SEN-015")["low_stock"] is False
    service.conn.execute("UPDATE parts SET stock_qty = 0 WHERE part_id = 'SEN-015'")
    assert service.get_part("SEN-015")["low_stock"] is True


def test_def03_deducts_twice_but_logs_one_correct_movement(make_service):
    service = make_service("DEF-03")
    assert service.issue_part("BELT-010", WO_LINE3, 2).accepted is True
    assert stock(service, "BELT-010") == 6
    [movement] = service.list_movements()
    assert (movement["part_id"], movement["work_order_id"], movement["qty"]) == ("BELT-010", WO_LINE3, 2)


def test_a_defect_only_affects_its_own_rule(make_service):
    service = make_service("DEF-03")
    assert service.issue_part("BRG-6205", WO, 3).accepted is False  # R1 still works
    assert service.get_part("SEN-015")["low_stock"] is True  # R4 still works


def test_defect_ids_are_parsed_and_unknown_ids_refused():
    assert parse_defects("DEF-01, def-03") == {"DEF-01", "DEF-03"}
    assert parse_defects(None) == parse_defects("") == frozenset()
    with pytest.raises(DefectError):
        parse_defects("DEF-01,DEF-99")
