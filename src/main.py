"""Base code for the MES spare-parts test agent.

Loads the synthetic spare-parts catalog and runs the three core scenarios
(SP-01, SP-02, SP-03) against a simple in-memory inventory. This is the
reference behaviour the agent, the Playwright baseline and the oracle will
later be checked against.

Run:  python -m src.main
"""

import csv
from dataclasses import dataclass
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "spare_parts_catalog.csv"


@dataclass
class SparePart:
    part_id: str
    part_name: str
    stock: int
    reorder_level: int
    unit: str
    bin_location: str

    @property
    def low_stock(self) -> bool:
        return self.stock < self.reorder_level


class Inventory:
    def __init__(self, parts: dict[str, SparePart]):
        self.parts = parts

    @classmethod
    def from_csv(cls, path: Path = CATALOG_PATH) -> "Inventory":
        parts = {}
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                parts[row["part_id"]] = SparePart(
                    part_id=row["part_id"],
                    part_name=row["part_name"],
                    stock=int(row["initial_stock"]),
                    reorder_level=int(row["reorder_level"]),
                    unit=row["unit"],
                    bin_location=row["bin_location"],
                )
        return cls(parts)

    def issue(self, part_id: str, qty: int) -> bool:
        """Issue parts to a work order. Rejects the issue if stock is too low."""
        part = self.parts[part_id]
        if qty <= 0 or qty > part.stock:
            return False
        part.stock -= qty
        return True


def run_scenarios() -> dict[str, bool]:
    results = {}

    # SP-01: issuing 3 bearings with only 2 in stock must be rejected.
    inv = Inventory.from_csv()
    accepted = inv.issue("BRG-6205", 3)
    results["SP-01"] = not accepted and inv.parts["BRG-6205"].stock == 2

    # SP-02: sensor with 3 pcs and reorder level 4 must show low stock.
    inv = Inventory.from_csv()
    results["SP-02"] = inv.parts["SEN-015"].low_stock

    # SP-03: issuing 2 of 10 belts must leave exactly 8.
    inv = Inventory.from_csv()
    accepted = inv.issue("BELT-010", 2)
    results["SP-03"] = accepted and inv.parts["BELT-010"].stock == 8

    return results


def main() -> None:
    inv = Inventory.from_csv()
    print(f"Loaded {len(inv.parts)} spare parts from {CATALOG_PATH.name}")
    for scenario, passed in run_scenarios().items():
        print(f"{scenario}: {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()
