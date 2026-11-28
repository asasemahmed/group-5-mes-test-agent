"""Find and stop whole process trees, the same way on macOS and Windows (psutil)."""

import psutil


def alive_descendants(pid: int) -> list[int]:
    """Process ids of all living children, grandchildren, ... of `pid`."""
    try:
        return [child.pid for child in psutil.Process(pid).children(recursive=True) if child.is_running()]
    except psutil.NoSuchProcess:
        return []


def kill_tree(pid: int, grace: float = 3.0) -> list[int]:
    """Stop `pid` and all its descendants: ask first, then force after `grace` seconds.

    Returns the ids of processes that are still alive afterwards (normally none).
    """
    try:
        root = psutil.Process(pid)
        processes = root.children(recursive=True) + [root]
    except psutil.NoSuchProcess:
        return []

    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=grace)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    _, still_alive = psutil.wait_procs(alive, timeout=grace)
    return [process.pid for process in still_alive]


def identity(pid: int) -> dict:
    """What identifies a process beyond its id, which the system may reuse later."""
    return {"pid": pid, "create_time": psutil.Process(pid).create_time()}


def is_same_process(saved: dict) -> bool:
    """True if the process saved with identity() is still running (and not a reused id)."""
    try:
        process = psutil.Process(saved["pid"])
        return process.is_running() and abs(process.create_time() - saved["create_time"]) < 0.01
    except (psutil.NoSuchProcess, KeyError):
        return False
