import re

import pytest
from fastapi.testclient import TestClient

from src.mes.app import create_app
from src.mes.db import connect
from src.mes.defects import parse_defects
from src.mes.seed import build_database

WO = "WO-2026-0891"
WO_LINE3 = "WO-2026-0903"


@pytest.fixture
def make_client(tmp_path):
    def make(defects="", run_id="test-run"):
        db = build_database(tmp_path / f"mes-{defects or 'clean'}.db")
        return TestClient(create_app(db, parse_defects(defects), run_id)), db

    return make


def test_every_page_answers(make_client):
    client, _ = make_client()
    for path in ["/", "/inventory", "/parts/BELT-010", "/work-orders", f"/work-orders/{WO}", "/issue",
                 "/issue?part=BELT-010", f"/issue?work_order={WO_LINE3}", "/movements", "/static/style.css"]:
        response = client.get(path)
        assert response.status_code == 200, path


def test_unknown_part_and_work_order_give_404(make_client):
    client, _ = make_client()
    assert client.get("/parts/NOPE").status_code == 404
    assert client.get("/work-orders/NOPE").status_code == 404
    assert client.get("/api/parts/NOPE").status_code == 404


def test_home_page_shows_no_part_data(make_client, tmp_path):
    client, db = make_client()
    html = client.get("/").text
    conn = connect(db)
    part_ids = [row[0] for row in conn.execute("SELECT part_id FROM parts")]
    conn.close()
    assert not any(part_id in html for part_id in part_ids)


def test_inventory_lists_parts_with_test_ids_and_search(make_client):
    client, _ = make_client()
    html = client.get("/inventory").text
    assert 'data-testid="part-row-BELT-010"' in html
    assert re.search(r'data-testid="stock-BELT-010">\s*10<', html)

    found = client.get("/inventory", params={"q": "sensor"}).text
    assert "SEN-015" in found and "BELT-010" not in found
    assert "No parts match" in client.get("/inventory", params={"q": "zzz"}).text


def test_low_stock_badge_and_def02(make_client):
    clean, _ = make_client()
    assert 'data-testid="low-stock-badge-SEN-015"' in clean.get("/inventory").text
    assert 'data-testid="low-stock-badge-SEN-015"' in clean.get("/parts/SEN-015").text
    assert 'data-testid="low-stock-badge-BELT-010"' not in clean.get("/inventory").text

    defective, _ = make_client("DEF-02")
    assert 'data-testid="low-stock-badge-SEN-015"' not in defective.get("/inventory").text
    assert defective.get("/api/parts/SEN-015").json()["low_stock"] is False


def test_issue_form_has_labelled_controls_and_prefill(make_client):
    client, _ = make_client()
    html = client.get("/issue", params={"part": "BELT-010", "work_order": WO_LINE3}).text
    for control in ("work_order_id", "part_id", "qty"):
        assert f'<label for="{control}">' in html and f'id="{control}"' in html
    assert 'value="BELT-010" selected' in html and f'value="{WO_LINE3}" selected' in html
    assert "WO-2026-0903 Repair Line 3 Belt Replacement" in html


def test_accepted_issue_redirects_to_a_result_without_the_new_balance(make_client):
    client, _ = make_client()
    response = client.post("/issue", data={"work_order_id": WO_LINE3, "part_id": "BELT-010", "qty": "2"}, follow_redirects=False)
    assert response.status_code == 303
    assert re.fullmatch(r"/issue/result/\d+", response.headers["location"])

    result = client.get(response.headers["location"]).text
    assert "Issued 2 x BELT-010 to WO-2026-0903." in result
    assert ">8<" not in result and " 8 " not in result
    assert client.get("/api/parts/BELT-010").json()["stock_qty"] == 8


def test_rejected_issue_shows_the_reason(make_client):
    client, _ = make_client()
    result = client.post("/issue", data={"work_order_id": WO, "part_id": "BRG-6205", "qty": "3"}).text
    assert "Rejected: requested 3, only 2 in stock." in result
    assert client.get("/api/parts/BRG-6205").json()["stock_qty"] == 2


def test_non_numeric_quantity_is_logged_and_rejected(make_client):
    client, _ = make_client()
    result = client.post("/issue", data={"work_order_id": WO, "part_id": "BELT-010", "qty": "two"}).text
    assert "quantity must be a whole number" in result
    [request] = client.get("/api/issue-requests").json()
    assert request["qty"] is None and request["accepted"] == 0


def test_def03_through_the_web(make_client):
    client, _ = make_client("DEF-03")
    client.post("/issue", data={"work_order_id": WO_LINE3, "part_id": "BELT-010", "qty": "2"})
    assert client.get("/api/parts/BELT-010").json()["stock_qty"] == 6
    [movement] = client.get("/api/movements").json()
    assert movement["qty"] == 2
    assert "BELT-010" in client.get("/movements").text
    assert "BELT-010" in client.get(f"/work-orders/{WO_LINE3}").text


def test_api_matches_the_database(make_client):
    client, db = make_client()
    conn = connect(db)
    rows = {row["part_id"]: dict(row) for row in conn.execute("SELECT * FROM parts")}
    conn.close()
    for part in client.get("/api/parts").json():
        assert part["stock_qty"] == rows[part["part_id"]]["stock_qty"]
        assert part["low_stock"] == (part["stock_qty"] < part["reorder_level"])
    assert client.get(f"/api/work-orders/{WO}").json()["equipment_ids"] == ["CNC-MILL-04", "CONV-LINE-B"]


def test_health_reports_identity_and_defects(make_client):
    client, _ = make_client("DEF-03,DEF-01", run_id="run-42")
    assert client.get("/health").json() == {"status": "ok", "run_id": "run-42", "defects": ["DEF-01", "DEF-03"]}
