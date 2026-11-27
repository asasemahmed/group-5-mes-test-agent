"""Business rules of the mini MES (design section 6.1).

R1  An issue is accepted only if 0 < qty <= stock and the work order is OPEN.
R2  An accepted issue lowers the stock by exactly qty and writes exactly one
    movement row with the same part, work order and quantity, in one transaction.
R3  A rejected issue changes neither stock nor movements.
R4  A part is low when stock < reorder level. is_low_stock() is the only place
    that decides this; pages and API both use it.
R5  Stock is never negative.

The three injected defects are the only places where the rules are broken on
purpose. Each is marked with its id.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

MOVEMENT_ISSUE = "ISSUE"


@dataclass(frozen=True)
class IssueResult:
    request_id: int
    accepted: bool
    message: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class MesService:
    def __init__(self, conn: sqlite3.Connection, defects: frozenset[str] = frozenset()):
        self.conn = conn
        self.defects = defects

    # ---- R4 -------------------------------------------------------------

    def is_low_stock(self, stock_qty: int, reorder_level: int) -> bool:
        if "DEF-02" in self.defects:
            # DEF-02: the warning only appears once the part has run out.
            return stock_qty <= 0
        return stock_qty < reorder_level

    # ---- reading --------------------------------------------------------

    def _part_dict(self, row: sqlite3.Row) -> dict:
        part = dict(row)
        part["low_stock"] = self.is_low_stock(part["stock_qty"], part["reorder_level"])
        return part

    def list_parts(self, search: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM parts", ()
        if search and search.strip():
            sql += " WHERE part_id LIKE ? OR part_name LIKE ?"
            pattern = f"%{search.strip()}%"
            args = (pattern, pattern)
        return [self._part_dict(row) for row in self.conn.execute(sql + " ORDER BY part_id", args)]

    def get_part(self, part_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM parts WHERE part_id = ?", (part_id,)).fetchone()
        return self._part_dict(row) if row else None

    def _work_order_dict(self, row: sqlite3.Row) -> dict:
        work_order = dict(row)
        work_order["equipment_ids"] = json.loads(work_order["equipment_ids"])
        return work_order

    def list_work_orders(self) -> list[dict]:
        return [self._work_order_dict(row) for row in self.conn.execute("SELECT * FROM work_orders ORDER BY work_order_id")]

    def get_work_order(self, work_order_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM work_orders WHERE work_order_id = ?", (work_order_id,)).fetchone()
        return self._work_order_dict(row) if row else None

    def list_movements(self, part_id: str | None = None, work_order_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM stock_movements", []
        conditions = []
        if part_id:
            conditions.append("part_id = ?")
            args.append(part_id)
        if work_order_id:
            conditions.append("work_order_id = ?")
            args.append(work_order_id)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return [dict(row) for row in self.conn.execute(sql + " ORDER BY id DESC", args)]

    def list_issue_requests(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM issue_requests ORDER BY id")]

    def get_issue_request(self, request_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM issue_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

    # ---- R1, R2, R3, R5 -------------------------------------------------

    def issue_part(self, part_id: str, work_order_id: str, qty: int | None) -> IssueResult:
        """Issue `qty` pieces of a part to a work order. Every call writes one audit row."""
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            part = conn.execute("SELECT * FROM parts WHERE part_id = ?", (part_id,)).fetchone()
            work_order = conn.execute("SELECT * FROM work_orders WHERE work_order_id = ?", (work_order_id,)).fetchone()

            if part is None:
                accepted, message = False, f"Rejected: unknown part {part_id}."
            elif work_order is None:
                accepted, message = False, f"Rejected: unknown work order {work_order_id}."
            elif work_order["status"] != "OPEN":
                accepted, message = False, f"Rejected: work order {work_order_id} is {work_order['status']}."
            elif qty is None or qty <= 0:
                accepted, message = False, "Rejected: quantity must be a whole number of at least 1."
            elif qty > part["stock_qty"] and "DEF-01" not in self.defects:
                # DEF-01 skips this stock check, so an over-issue is accepted.
                accepted, message = False, f"Rejected: requested {qty}, only {part['stock_qty']} in stock."
            else:
                accepted, message = True, f"Issued {qty} x {part_id} to {work_order_id}."

            now = _now()
            cursor = conn.execute(
                "INSERT INTO issue_requests (part_id, work_order_id, qty, accepted, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (part_id, work_order_id, qty, int(accepted), message, now),
            )
            request_id = cursor.lastrowid

            if accepted:
                deduction = qty * 2 if "DEF-03" in self.defects else qty  # DEF-03: the stock is deducted twice
                conn.execute("UPDATE parts SET stock_qty = stock_qty - ? WHERE part_id = ?", (deduction, part_id))
                conn.execute(
                    "INSERT INTO stock_movements (request_id, part_id, work_order_id, qty, movement_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (request_id, part_id, work_order_id, qty, MOVEMENT_ISSUE, now),
                )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return IssueResult(request_id=request_id, accepted=accepted, message=message)
