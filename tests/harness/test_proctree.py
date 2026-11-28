import subprocess
import sys
import time

import psutil

from src.harness.proctree import alive_descendants, identity, is_same_process, kill_tree

# A parent that starts a long-sleeping child and then sleeps itself.
PARENT = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
print(child.pid, flush=True)
time.sleep(120)
"""


def gone(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def test_kill_tree_stops_parent_and_grandchild():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    assert child_pid in alive_descendants(parent.pid)

    assert kill_tree(parent.pid, grace=2) == []
    parent.wait(timeout=10)
    parent.stdout.close()
    deadline = time.monotonic() + 5
    while not gone(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert gone(child_pid)


def test_kill_tree_of_a_finished_process_is_harmless():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=10)
    assert kill_tree(process.pid) == []


def test_identity_tells_a_living_process_from_a_reused_id():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        saved = identity(process.pid)
        assert is_same_process(saved)
        assert not is_same_process({"pid": process.pid, "create_time": saved["create_time"] - 100})
    finally:
        kill_tree(process.pid)
        process.wait(timeout=10)
    assert not is_same_process(saved)
