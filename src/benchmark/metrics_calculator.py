"""Benchmark metrics from the README: TCR, DDR, DRP and FPR (all in percent)."""


def _percent(part: int, total: int) -> float:
    return 100.0 * part / total if total else 0.0


def test_completion_rate(completed: int, total: int) -> float:
    return _percent(completed, total)


def defect_detection_recall(detected: int, injected: int) -> float:
    return _percent(detected, injected)


def defect_report_precision(confirmed: int, reported: int) -> float:
    return _percent(confirmed, reported)


def false_positive_rate(false_alarms: int, valid_behaviours: int) -> float:
    return _percent(false_alarms, valid_behaviours)
