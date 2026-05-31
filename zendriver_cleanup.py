import os
import re
import shutil
import signal
import subprocess
import time
from typing import Callable, List, Optional


Runner = Callable[..., subprocess.CompletedProcess]
Which = Callable[[str], Optional[str]]
Killer = Callable[[int, int], None]
Sleeper = Callable[[float], None]


def _run(
    cmd: List[str],
    runner: Runner,
    timeout: float,
) -> subprocess.CompletedProcess:
    return runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _dedupe_pids(pids: List[int]) -> List[int]:
    return sorted({pid for pid in pids if isinstance(pid, int) and pid > 0})


def find_port_pids(
    port: int,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> List[int]:
    port = int(port)

    if which("lsof"):
        result = _run(["lsof", "-ti", f"tcp:{port}"], runner, timeout=3)
        return _dedupe_pids([int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()])

    if which("ss"):
        result = _run(["ss", "-ltnp"], runner, timeout=3)
        pids: List[int] = []
        for line in result.stdout.splitlines():
            if f":{port} " not in line:
                continue
            pids.extend(int(pid) for pid in re.findall(r"pid=(\d+)", line))
        return _dedupe_pids(pids)

    if which("netstat"):
        result = _run(["netstat", "-ltnp"], runner, timeout=3)
        pids = []
        for line in result.stdout.splitlines():
            if f":{port} " not in line:
                continue
            match = re.search(r"\s(\d+)/(?:python|python3|chrome|chromium|[^\s]+)\s*$", line)
            if match:
                pids.append(int(match.group(1)))
        return _dedupe_pids(pids)

    return []


def find_stale_browser_pids(
    runner: Runner = subprocess.run,
) -> List[int]:
    result = _run(["ps", "-eo", "pid=,args="], runner, timeout=5)
    pids: List[int] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or "zd_daemon_" not in line:
            continue
        if not any(token in line for token in ("chrome", "chromium", "/proc/self/exe")):
            continue
        parts = line.split(None, 1)
        if parts and parts[0].isdigit():
            pids.append(int(parts[0]))
    return _dedupe_pids(pids)


def terminate_pids(
    pids: List[int],
    kill_func: Killer = os.kill,
    sleep_func: Sleeper = time.sleep,
) -> None:
    unique_pids = _dedupe_pids(pids)
    if not unique_pids:
        return

    for pid in unique_pids:
        try:
            kill_func(pid, signal.SIGTERM)
        except OSError:
            pass

    sleep_func(1.0)

    for pid in unique_pids:
        try:
            kill_func(pid, 0)
        except OSError:
            continue
        try:
            kill_func(pid, signal.SIGKILL)
        except OSError:
            pass
