import csv
import time

from src.mes.db import connect
from src.mes.seed import CATALOG_PATH, build_database


def dump(path):
    conn = connect(path)
    try:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("parts", "work_orders", "issue_requests", "stock_movements")
        }
    finally:
        conn.close()


def test_seed_has_the_catalog_and_both_work_orders(tmp_path):
    content = dump(build_database(tmp_path / "mes.db"))

    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        catalog = {row["part_id"]: row for row in csv.DictReader(f)}
    assert len(content["parts"]) == len(catalog) == 6
    for part_id, name, initial, stock, reorder, unit, bin_location, cost, category in content["parts"]:
        row = catalog[part_id]
        assert (name, initial, reorder, unit, bin_location, cost, category) == (
            row["part_name"], int(row["initial_stock"]), int(row["reorder_level"]),
            row["unit"], row["bin_location"], float(row["unit_cost_usd"]), row["category"],
        )
        assert stock == initial

    assert [wo[0] for wo in content["work_orders"]] == ["WO-2026-0891", "WO-2026-0903"]
    assert all(wo[2] == "OPEN" for wo in content["work_orders"])
    assert content["issue_requests"] == [] and content["stock_movements"] == []


def test_building_twice_gives_the_same_content(tmp_path):
    path = tmp_path / "mes.db"
    first = dump(build_database(path))
    conn = connect(path)
    conn.execute("UPDATE parts SET stock_qty = 0")
    conn.close()
    assert dump(build_database(path)) == first


def test_building_is_fast(tmp_path):
    start = time.perf_counter()
    build_database(tmp_path / "mes.db")
    assert time.perf_counter() - start < 1.0  # typically a few milliseconds
