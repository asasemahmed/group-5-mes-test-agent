import socket
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psutil
import pytest

from src.harness.mes_instance import MesInstance, MesStartError


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def test_instance_answers_with_its_identity_and_defects(tmp_path):
    with MesInstance(tmp_path, run_id="r-1", defects={"DEF-03"}) as mes:
        assert httpx.get(f"{mes.base_url}/health").json() == {"status": "ok", "run_id": "r-1", "defects": ["DEF-03"]}
        assert httpx.get(f"{mes.base_url}/api/parts/BELT-010").json()["stock_qty"] == 10
        assert mes.db_path.exists()


def test_parallel_instances_get_their_own_port_and_identity(tmp_path):
    def run(i):
        with MesInstance(tmp_path / f"run-{i}", run_id=f"r-{i}") as mes:
            return mes.port, httpx.get(f"{mes.base_url}/health").json()["run_id"]

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(run, range(5)))
    assert len({port for port, _ in results}) == 5
    assert [run_id for _, run_id in results] == [f"r-{i}" for i in range(5)]


def test_a_child_that_exits_early_gives_a_clear_error_quickly(tmp_path):
    started = time.monotonic()
    with pytest.raises(MesStartError, match="exited with code 2"):
        MesInstance(tmp_path, run_id="bad", defects={"DEF-99"}).start()
    assert time.monotonic() - started < 15


def test_after_exit_the_process_is_gone_and_port_and_files_are_free(tmp_path):
    with MesInstance(tmp_path, run_id="r-1") as mes:
        pid, port = mes.pid, mes.port
        httpx.post(f"{mes.base_url}/issue", data={"work_order_id": "WO-2026-0903", "part_id": "BELT-010", "qty": "2"})
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    assert port_is_free(port)
    mes.db_path.unlink()  # fails on Windows if the file were still open
    mes.log_path.unlink()
