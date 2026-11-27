"""Build a fresh mini MES database from the data files.

Every run starts from a database built here, so every run starts in the same state.
"""

import csv
import json
from pathlib import Path

from src.config import ROOT
from src.mes.db import connect, create_schema

CATALOG_PATH = ROOT / "data" / "spare_parts_catalog.csv"
WORK_ORDERS_PATH = ROOT / "data" / "work_orders.json"


def build_database(path: Path | str, catalog_path: Path = CATALOG_PATH, work_orders_path: Path = WORK_ORDERS_PATH) -> Path:
    """Create (or replace) the database at `path` and fill it with the seed data."""
    path = Path(path)
    for leftover in (path, path.with_name(path.name + "-journal")):
        leftover.unlink(missing_ok=True)

    with open(catalog_path, newline="", encoding="utf-8") as f:
        parts = [
            (
                row["part_id"], row["part_name"], int(row["initial_stock"]), int(row["initial_stock"]),
                int(row["reorder_level"]), row["unit"], row["bin_location"], float(row["unit_cost_usd"]), row["category"],
            )
            for row in csv.DictReader(f)
        ]
    work_orders = [
        (wo["work_order_id"], wo["title"], wo["status"], wo["technician_id"], json.dumps(wo["equipment_ids"]))
        for wo in json.loads(Path(work_orders_path).read_text(encoding="utf-8"))
    ]

    conn = connect(path)
    try:
        create_schema(conn)  # executescript manages its own transaction
        conn.execute("BEGIN")
        conn.executemany("INSERT INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", parts)
        conn.executemany("INSERT INTO work_orders VALUES (?, ?, ?, ?, ?)", work_orders)
        conn.execute("COMMIT")
    finally:
        conn.close()
    return path
