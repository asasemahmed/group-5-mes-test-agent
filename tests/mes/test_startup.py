"""Start the mini MES as its own process, the way the harness will."""

import json
import queue
import subprocess
import sys
import threading
import time

import httpx

from src.config import ROOT


def start(*args):
    process = subprocess.Popen(
        [sys.executable, "-m", "src.mes", *args],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
    return process, lines


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def test_prints_a_ready_line_and_serves_on_that_port(tmp_path):
    started = time.monotonic()
    process, lines = start("--run-id", "startup-test", "--db", str(tmp_path / "mes.db"), "--defects", "DEF-03")
    try:
        ready = json.loads(lines.get(timeout=20))
        assert ready["ready"] is True and ready["run_id"] == "startup-test" and ready["port"] > 0

        health = httpx.get(f"http://127.0.0.1:{ready['port']}/health", timeout=10).json()
        assert health == {"status": "ok", "run_id": "startup-test", "defects": ["DEF-03"]}
        assert (tmp_path / "mes.db").exists()
        assert time.monotonic() - started < 15  # loose bound; the real start-up target is measured in plan step 8.1
    finally:
        stop(process)


def test_unknown_defect_stops_with_an_error():
    process = subprocess.run([sys.executable, "-m", "src.mes", "--defects", "DEF-99"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert process.returncode == 2
    assert "DEF-99" in process.stderr
