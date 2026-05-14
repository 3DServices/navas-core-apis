#!/usr/bin/env python3
import os
import re
import time
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import psutil
from flask import Blueprint, jsonify, request

# -----------------------------
# Blueprint
# -----------------------------
metrics_bp = Blueprint("server_metrics", __name__)

# -----------------------------
# Config
# -----------------------------
SECTOR_SIZE = 512
DEFAULT_WINDOW_SEC = 1.0
MIN_WINDOW_SEC = 0.2
MAX_WINDOW_SEC = 5.0

# Optional: protect endpoint with a shared key
# export METRICS_AUTH_KEY="some-long-secret"
AUTH_ENV_KEY = "METRICS_AUTH_KEY"

# If supervisorctl is installed inside a venv only, set:
# export METRICS_VENV_BIN="/root/py39env/bin"
VENV_BIN = os.getenv("METRICS_VENV_BIN", os.path.expanduser("~/py39env/bin"))

SUPERVISOR_PROGRAMS = [
    "bce",
    "et01-socket",
    "imei_distributor",
    "kafka_producer_1",
    "kafka_producer_2",
    "kafka_producer_3",
    "kafka_producer_4",
    "kafka_producer_5",
    "kafka_producer_6",
    "live-location-v3",
    "narvas-apis",
    "narvas-development-apis",
    "teltonika-socket",
    "wetrack-socket",
]

SYSTEMD_UNITS = {
    "nginx": "nginx.service",
    "kafka": "kafka.service",
    "redis": "redis-server.service",
    # postgresql.service can be "active exited"; monitor the cluster:
    "postgresql": "postgresql@16-main.service",
    # cassandra is exactly this on your server:
    "cassandra": "cassandra.service",
}

# -----------------------------
# Helpers
# -----------------------------
def safe_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None

def clamp_window(v: float) -> float:
    return max(MIN_WINDOW_SEC, min(MAX_WINDOW_SEC, v))

def resolve_bin(cmd: str) -> str:
    """
    Prefer PATH binary. If missing, try VENV_BIN/cmd (useful when app runs in systemd without venv PATH).
    """
    from shutil import which
    p = which(cmd)
    if p:
        return p
    v = os.path.join(VENV_BIN, cmd)
    return v if os.path.exists(v) else cmd

def run(cmd: List[str], timeout: int = 10) -> str:
    # Ensure a sane PATH even when running under systemd
    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "") + ":/usr/sbin:/usr/bin:/sbin:/bin"
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout, text=True, env=env)

def require_auth_if_configured():
    expected = os.getenv(AUTH_ENV_KEY)
    if not expected:
        return None
    provided = request.headers.get("Auth-Key") or request.args.get("auth_key")
    if not provided or provided != expected:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    return None

# -----------------------------
# Disk IOPS + Throughput
# -----------------------------
@dataclass
class DiskCounters:
    reads_completed: int
    writes_completed: int
    sectors_read: int
    sectors_written: int

def read_diskstats() -> Dict[str, DiskCounters]:
    devices: Dict[str, DiskCounters] = {}
    with open("/proc/diskstats", "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 14:
                continue

            name = parts[2]

            # Skip partitions (sda1, nvme0n1p1), keep dm-* and md-*
            if re.match(r".*\d+$", name) and not name.startswith("dm-") and not name.startswith("md"):
                continue

            rc = safe_int(parts[3])
            sr = safe_int(parts[5])
            wc = safe_int(parts[7])
            sw = safe_int(parts[9])
            if None in (rc, sr, wc, sw):
                continue

            devices[name] = DiskCounters(
                reads_completed=rc,
                writes_completed=wc,
                sectors_read=sr,
                sectors_written=sw,
            )
    return devices

def compute_disk_io(before: Dict[str, DiskCounters], after: Dict[str, DiskCounters], window_sec: float) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for dev, b in before.items():
        a = after.get(dev)
        if not a:
            continue

        d_reads = a.reads_completed - b.reads_completed
        d_writes = a.writes_completed - b.writes_completed
        d_sec_r = a.sectors_read - b.sectors_read
        d_sec_w = a.sectors_written - b.sectors_written

        read_bytes = d_sec_r * SECTOR_SIZE
        write_bytes = d_sec_w * SECTOR_SIZE

        out[dev] = {
            "read_iops": round(d_reads / window_sec, 3),
            "write_iops": round(d_writes / window_sec, 3),
            "read_MBps": round((read_bytes / window_sec) / (1024 * 1024), 3),
            "write_MBps": round((write_bytes / window_sec) / (1024 * 1024), 3),
        }
    return out

# -----------------------------
# systemd PID discovery (robust)
# -----------------------------
def systemd_pid(unit_name: str) -> Optional[int]:
    """
    Try MainPID, then ExecMainPID, then parse `systemctl status` as fallback.
    """
    systemctl = resolve_bin("systemctl")

    # 1) MainPID
    try:
        val = run([systemctl, "show", "-p", "MainPID", "--value", unit_name]).strip()
        pid = safe_int(val)
        if pid and pid > 0:
            return pid
    except Exception:
        pass

    # 2) ExecMainPID (sometimes better for forking/LSB)
    try:
        val = run([systemctl, "show", "-p", "ExecMainPID", "--value", unit_name]).strip()
        pid = safe_int(val)
        if pid and pid > 0:
            return pid
    except Exception:
        pass

    # 3) Parse `systemctl status`
    try:
        txt = run([systemctl, "status", unit_name, "--no-pager"], timeout=10)
        m = re.search(r"Main PID:\s*(\d+)", txt)
        if m:
            pid = safe_int(m.group(1))
            if pid and pid > 0:
                return pid
    except Exception:
        pass

    return None

def find_cassandra_jvm_pid() -> Optional[int]:
    """
    Last-resort: find Cassandra JVM by cmdline. Cassandra is Java; choose the largest RSS match.
    """
    best_pid = None
    best_rss = 0

    for p in psutil.process_iter(attrs=["pid", "name", "cmdline", "memory_info"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()

            if "java" not in name and "java" not in cmd:
                continue

            # Common Cassandra identifiers
            if ("cassandra" in cmd) or ("org.apache.cassandra" in cmd) or ("cassandra.daemon" in cmd):
                rss = (p.info.get("memory_info").rss if p.info.get("memory_info") else 0)
                if rss > best_rss:
                    best_rss = rss
                    best_pid = p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return best_pid

# -----------------------------
# Supervisor parsing (parse once)
# -----------------------------
def supervisor_status_map() -> Dict[str, Dict[str, Any]]:
    """
    Runs `supervisorctl status` once and parses all lines.
    Returns {name: {status, pid}}
    """
    out: Dict[str, Dict[str, Any]] = {}
    supervisorctl = resolve_bin("supervisorctl")

    try:
        txt = run([supervisorctl, "status"], timeout=12)
    except Exception:
        return out

    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = re.split(r"\s+", line, maxsplit=2)
        if len(parts) < 2:
            continue

        name, status = parts[0], parts[1].upper()
        pid = None
        m = re.search(r"pid\s+(\d+)", line)
        if m:
            pid = safe_int(m.group(1))

        out[name] = {"status": status, "pid": pid}
    return out

# -----------------------------
# Sampling (single sleep)
# -----------------------------
def build_process_objects(pid_map: Dict[str, Optional[int]]) -> Dict[str, psutil.Process]:
    procs: Dict[str, psutil.Process] = {}
    for label, pid in pid_map.items():
        if not pid or pid <= 0:
            continue
        try:
            procs[label] = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs

def prime_cpu(procs: Dict[str, psutil.Process]) -> None:
    for p in procs.values():
        try:
            p.cpu_percent(interval=None)
        except Exception:
            pass

def collect_proc_metrics(procs: Dict[str, psutil.Process]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for label, p in procs.items():
        try:
            cpu = p.cpu_percent(interval=None)
            mem = p.memory_percent()
            rss_mb = p.memory_info().rss / (1024 * 1024)
            out[label] = {
                "cpu_percent": round(cpu, 3),
                "mem_percent": round(mem, 6),
                "rss_MB": round(rss_mb, 2),
                "status": "running",
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            out[label] = {"status": "unavailable"}
        except Exception:
            out[label] = {"status": "error"}
    return out

# -----------------------------
# Route
# -----------------------------
@metrics_bp.route("/metrics/server", methods=["GET"])
def get_server_metrics():
    auth_resp = require_auth_if_configured()
    if auth_resp is not None:
        return auth_resp

    # Sampling window
    try:
        window_sec = float(request.args.get("window", DEFAULT_WINDOW_SEC))
    except Exception:
        window_sec = DEFAULT_WINDOW_SEC
    window_sec = clamp_window(window_sec)

    # Prime overall CPU and disk snapshot before sleep
    psutil.cpu_percent(interval=None)
    disk_before = read_diskstats()

    # Resolve systemd pids (with cassandra fallback)
    systemd_info: Dict[str, Dict[str, Any]] = {}
    for key, unit in SYSTEMD_UNITS.items():
        pid = systemd_pid(unit)

        # Special fallback for cassandra if PID not tracked properly
        if key == "cassandra" and not pid:
            pid = find_cassandra_jvm_pid()

        systemd_info[key] = {
            "service": key,
            "unit": unit,
            "pid": pid,
            "status": "running" if pid else "not_running",
        }

    # Resolve supervisor pids
    sup_all = supervisor_status_map()
    supervisor_info: Dict[str, Dict[str, Any]] = {}
    for name in SUPERVISOR_PROGRAMS:
        s = sup_all.get(name)
        if s:
            supervisor_info[name] = {"program": name, "pid": s.get("pid"), "status": s.get("status")}
        else:
            supervisor_info[name] = {"program": name, "pid": None, "status": "NOT_FOUND"}

    # Prepare all PIDs to sample in one sleep
    pid_labels: Dict[str, Optional[int]] = {}
    for key, info in systemd_info.items():
        pid_labels[f"systemd:{key}"] = info.get("pid")
    for name, info in supervisor_info.items():
        pid_labels[f"supervisor:{name}"] = info.get("pid")

    # include gunicorn worker/master processes if present
    for p in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            nm = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if "gunicorn" in nm or "gunicorn" in cmd:
                pid = p.info.get("pid")
                if pid and pid > 0:
                    label = f"gunicorn:{pid}"
                    pid_labels[label] = pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs = build_process_objects(pid_labels)
    prime_cpu(procs)

    # Single sampling window
    time.sleep(window_sec)

    # System metrics after window
    cpu_total = psutil.cpu_percent(interval=None)
    mem_total = psutil.virtual_memory().percent

    du = shutil.disk_usage("/")
    disk_space_root_percent = round((du.used / du.total) * 100.0, 2)

    disk_after = read_diskstats()
    disk_io = compute_disk_io(disk_before, disk_after, window_sec)

    proc_metrics = collect_proc_metrics(procs)

    # Merge
    systemd_out: Dict[str, Any] = {}
    for key, info in systemd_info.items():
        label = f"systemd:{key}"
        row = dict(info)
        row.update(proc_metrics.get(label, {}))
        systemd_out[key] = row

    supervisor_out: Dict[str, Any] = {}
    for name, info in supervisor_info.items():
        label = f"supervisor:{name}"
        row = dict(info)
        row.update(proc_metrics.get(label, {}))
        supervisor_out[name] = row

    # extract any gunicorn entries from proc_metrics
    gunicorn_out: Dict[str, Any] = {}
    for label, metrics in proc_metrics.items():
        if label.startswith("gunicorn:"):
            gunicorn_out[label] = metrics

    payload = {
        "ok": True,
        "ts": int(time.time()),
        "hostname": os.uname().nodename,
        "window_sec": window_sec,
        "system": {
            "cpu_percent": round(float(cpu_total), 3),
            "memory_percent": round(float(mem_total), 3),
            "disk_space_root_percent": float(disk_space_root_percent),
        },
        "disk_io": {"devices": disk_io},
        "processes": {
            "systemd": systemd_out,
            "supervisor": supervisor_out,
            "gunicorn": gunicorn_out,
        },
    }
    return jsonify(payload)
