"""A mini MES for one run: own database, own process, own port (design section 6.2).

    with MesInstance(run_dir, run_id="r-1", defects={"DEF-03"}) as mes:
        mes.base_url   # e.g. http://127.0.0.1:51234
        mes.db_path    # run_dir / "mes.db"

The child binds its own free port and reports it on a ready line; the parent never
chooses a port, so parallel runs cannot race for one. /health must report the same
run id and defects, so a run never talks to another run's instance.
"""

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from src.config import ROOT
from src.harness.proctree import kill_tree
from src.mes.seed import build_database


class MesStartError(RuntimeError):
    pass


class MesInstance:
    def __init__(self, run_dir: Path | str, run_id: str, defects=(), start_timeout: float = 20.0):
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.defects = sorted(defects)
        self.start_timeout = start_timeout
        self.db_path = self.run_dir / "mes.db"
        self.log_path = self.run_dir / "mes.log"
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self._log = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    def start(self) -> "MesInstance":
        self.run_dir.mkdir(parents=True, exist_ok=True)
        build_database(self.db_path)
        self._log = open(self.log_path, "w", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "src.mes", "--run-id", self.run_id, "--db", str(self.db_path),
             "--defects", ",".join(self.defects)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=self._log, text=True,
        )
        try:
            ready = self._read_ready_line()
            self.port = int(ready["port"])
            self._check_identity()
        except BaseException:
            self.stop()
            raise
        return self

    def _read_ready_line(self) -> dict:
        lines: queue.Queue = queue.Queue()

        def reader(stream):
            for line in stream:
                lines.put(line)
            lines.put(None)  # the child closed its output: it has exited

        threading.Thread(target=reader, args=(self.process.stdout,), daemon=True).start()
        deadline = time.monotonic() + self.start_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MesStartError(f"mini MES for {self.run_id} gave no ready line within {self.start_timeout} s")
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                self.process.wait(timeout=5)
                raise MesStartError(f"mini MES for {self.run_id} exited with code {self.process.returncode} before it was ready: {self._log_tail()}")
            try:
                ready = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ready.get("ready"):
                return ready

    def _check_identity(self) -> None:
        deadline = time.monotonic() + self.start_timeout
        while True:
            try:
                health = httpx.get(f"{self.base_url}/health", timeout=2).json()
                break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise MesStartError(f"mini MES for {self.run_id} does not answer on port {self.port}") from None
                time.sleep(0.05)
        if health.get("run_id") != self.run_id or sorted(health.get("defects", [])) != self.defects:
            raise MesStartError(f"instance on port {self.port} reports {health}, expected run {self.run_id} with {self.defects}")

    def _log_tail(self) -> str:
        if self._log:
            self._log.flush()
        try:
            return self.log_path.read_text(encoding="utf-8")[-500:].strip()
        except OSError:
            return ""

    def stop(self, grace: float = 3.0) -> None:
        if self.process is not None and self.process.poll() is None:
            kill_tree(self.process.pid, grace=grace)
        if self.process is not None:
            try:
                self.process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                pass
            if self.process.stdout:
                self.process.stdout.close()
        if self._log:
            self._log.close()
            self._log = None

    def __enter__(self) -> "MesInstance":
        return self.start()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False
