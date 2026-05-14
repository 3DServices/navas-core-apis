from flask import Blueprint, jsonify
from typing import Dict
import psutil
import subprocess

_system_hardware_apis = Blueprint("SystemHardwareApis", __name__)

PORT_MONITORS = {
    3140: "teltonika_socket.py",
    3139: "wetrack_socket.py",
    3160: "bce_socket_receiver.py",
    3170: "et01.py",
}

# Store previous iptables totals per port
_prev_port_totals: Dict[int, Dict[str, int]] = {}

# Cumulative totals per port
_port_cumulative: Dict[int, Dict[str, int]] = {}


def get_iptables_bytes(port: int):
    """
    Returns exact (bytes_received, bytes_sent) for a port
    using iptables raw counters.
    """

    try:
        output = subprocess.check_output(
            ["sudo", "iptables", "-L", "-v", "-n", "-x"],
            text=True
        )
    except Exception:
        return 0, 0

    recv_bytes = 0
    sent_bytes = 0

    for line in output.splitlines():

        # Incoming traffic (destination port)
        if f"dpt:{port}" in line:
            parts = line.split()
            if len(parts) > 1 and parts[1].isdigit():
                recv_bytes += int(parts[1])

        # Outgoing traffic (source port)
        if f"spt:{port}" in line:
            parts = line.split()
            if len(parts) > 1 and parts[1].isdigit():
                sent_bytes += int(parts[1])

    return recv_bytes, sent_bytes


def human_readable(value: int) -> str:
    if value >= 1024 ** 3:
        return f"{value / (1024 ** 3):.2f} GB"
    if value >= 1024 ** 2:
        return f"{value / (1024 ** 2):.2f} MB"
    if value >= 1024:
        return f"{value / 1024:.2f} KB"
    return f"{value} B"


# -------------------------------
# helper using ss output for tcp threads
# -------------------------------
def count_tcp_threads_for_port(port: int) -> int:
    try:
        output = subprocess.check_output(
            ["ss", "-tan", f"sport = :{port}"],
            text=True
        )
    except Exception:
        return 0

    count = 0
    for line in output.splitlines():
        if "ESTAB" in line:
            count += 1
    return count


@_system_hardware_apis.route("/ports/activity", methods=["GET"])
def get_ports_activity():

    try:
        connections = psutil.net_connections(kind="tcp")
    except Exception:
        connections = []

    result = {}

    for port, script in PORT_MONITORS.items():

        # Established connections on this local port
        port_conns = [
            c for c in connections
            if c.laddr and c.laddr.port == port
            and c.status == psutil.CONN_ESTABLISHED
        ]
        # count tcp threads via ss output (faster, simpler)
        tcp_thread_count = count_tcp_threads_for_port(port)

        # --- GET IPTABLES TOTALS ---
        current_recv, current_sent = get_iptables_bytes(port)

        prev = _prev_port_totals.get(port, {"recv": 0, "sent": 0})

        delta_recv = max(0, current_recv - prev["recv"])
        delta_sent = max(0, current_sent - prev["sent"])

        _prev_port_totals[port] = {
            "recv": current_recv,
            "sent": current_sent
        }

        cumulative = _port_cumulative.setdefault(port, {
            "bytes_recv": 0,
            "bytes_sent": 0
        })

        cumulative["bytes_recv"] += delta_recv
        cumulative["bytes_sent"] += delta_sent

        result[port] = {
            "script": script,
            "active": len(port_conns) > 0,
            "connections": len(port_conns),
            "outgoing_connections": len([c for c in port_conns if c.raddr]),
            "tcp_threads": tcp_thread_count,
            "remote_endpoints": [
                {
                    "remote_ip": c.raddr.ip,
                    "remote_port": c.raddr.port
                }
                for c in port_conns if c.raddr
            ],
            "bytes_recv": cumulative["bytes_recv"],
            "bytes_sent": cumulative["bytes_sent"],
            "bytes_recv_hr": human_readable(cumulative["bytes_recv"]),
            "bytes_sent_hr": human_readable(cumulative["bytes_sent"]),
        }

    return jsonify({"ports": result})