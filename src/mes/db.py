"""SQLite schema and connections for the mini MES (design section 6.1)."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE parts (
    part_id        TEXT PRIMARY KEY,
    part_name      TEXT NOT NULL,
    initial_stock  INTEGER NOT NULL,
    stock_qty      INTEGER NOT NULL,      -- no CHECK >= 0: DEF-01 must be able to drive it negative
    reorder_level  INTEGER NOT NULL,
    unit           TEXT NOT NULL,
    bin_location   TEXT NOT NULL,
    unit_cost_usd  REAL NOT NULL,
    category       TEXT NOT NULL
);

CREATE TABLE work_orders (
    work_order_id  TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    status         TEXT NOT NULL,
    technician_id  TEXT NOT NULL,
    equipment_ids  TEXT NOT NULL          -- JSON list
);

-- Audit log: one row for every submitted issue form, accepted or not.
CREATE TABLE issue_requests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id        TEXT NOT NULL,
    work_order_id  TEXT NOT NULL,
    qty            INTEGER,               -- NULL when the submitted quantity was not a number
    accepted       INTEGER NOT NULL,      -- 0 or 1
    message        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

-- One row per accepted issue.
CREATE TABLE stock_movements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id     INTEGER NOT NULL REFERENCES issue_requests(id),
    part_id        TEXT NOT NULL REFERENCES parts(part_id),
    work_order_id  TEXT NOT NULL REFERENCES work_orders(work_order_id),
    qty            INTEGER NOT NULL,
    movement_type  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database for reading and writing. Rows behave like dicts."""
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
