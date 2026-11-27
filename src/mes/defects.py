"""The defects that can be switched on in the mini MES (data/injected_defects.yaml)."""

from collections.abc import Iterable

import yaml

from src.config import ROOT

DEFECTS_PATH = ROOT / "data" / "injected_defects.yaml"


class DefectError(ValueError):
    pass


def known_defects() -> dict[str, dict]:
    """Defect id -> its entry (scenario, description)."""
    entries = yaml.safe_load(DEFECTS_PATH.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in entries}


def parse_defects(value: str | Iterable[str] | None) -> frozenset[str]:
    """Turn "DEF-01,DEF-03" (or a list) into a set of ids. Unknown ids raise DefectError."""
    if value is None:
        return frozenset()
    items = value.split(",") if isinstance(value, str) else value
    ids = frozenset(item.strip().upper() for item in items if item and item.strip())
    unknown = ids - known_defects().keys()
    if unknown:
        raise DefectError(f"Unknown defect(s): {', '.join(sorted(unknown))}")
    return ids
