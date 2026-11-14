#!/usr/bin/env python3
"""
net_diag_ticket.py
==================
Enterprise Network Operations — OSI Layer 1-3 Network Diagnostics &
Automated Jira SLA Incident Ticketing Toolkit

Author : Senior Infrastructure & Data Center Automation Engineer
Version: 2.0.0
Python : 3.8+

Usage:
  # Live kernel mode (requires root + veth lab set up):
  python3 src/net_diag_ticket.py --interface veth0 --target-ip 10.200.1.2

  # Simulation mode (no root, no special hardware):
  python3 src/net_diag_ticket.py --simulate --scenario degraded_fiber
  python3 src/net_diag_ticket.py --simulate --scenario link_down
  python3 src/net_diag_ticket.py --simulate --scenario healthy
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Layer1Diagnostics:
    """OSI Layer 1 — Physical layer metrics."""
    link_state: str = "UNKNOWN"            # UP | DOWN | NO-CARRIER
    operational_state: str = "UNKNOWN"     # up | down | unknown
    speed_mbps: int = 0                    # e.g. 1000, 10000
    duplex: str = "UNKNOWN"               # full | half | unknown
    rx_crc_errors: int = 0
    tx_crc_errors: int = 0
    rx_dropped: int = 0
    tx_dropped: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    optical_rx_power_dbm: Optional[float] = None   # None for copper
    optical_tx_power_dbm: Optional[float] = None
    media_type: str = "Copper"             # Copper | Fiber (SFP+)
    transceiver_present: bool = True
    mtu: int = 1500


@dataclass
class Layer2Diagnostics:
    """OSI Layer 2 — Data link layer metrics."""
    mac_address: str = "00:00:00:00:00:00"
    arp_neighbor_state: str = "UNKNOWN"    # REACHABLE | STALE | FAILED | NONE
    arp_neighbor_mac: str = "N/A"
    vlan_id: Optional[int] = None
    interface_flags: list = field(default_factory=list)   # BROADCAST, MULTICAST, UP


@dataclass
class Layer3Diagnostics:
    """OSI Layer 3 — Network layer metrics."""
    ping_min_ms: float = 0.0
    ping_avg_ms: float = 0.0
    ping_max_ms: float = 0.0
    ping_mdev_ms: float = 0.0
    packet_loss_pct: float = 0.0
    packets_sent: int = 10
    packets_received: int = 10
    target_ip: str = "0.0.0.0"
    dns_hostname: Optional[str] = None
    dns_resolved_ip: Optional[str] = None
    dns_latency_ms: float = 0.0
    route_next_hop: Optional[str] = None
    ttl: int = 64


@dataclass
class SLAEvaluation:
    """Automated SLA severity classification and remediation."""
    severity: str = "OK"              # OK | SEV-3 | SEV-2 | SEV-1
    sla_breach_minutes: int = 0       # 0 = no breach yet
    remediation_timer_minutes: int = 0
    triggered_rules: list = field(default_factory=list)
    remediation_steps: list = field(default_factory=list)
    root_cause_analysis: str = ""
    jira_ticket_id: str = ""
    jira_priority: str = "Low"
    jira_component: str = "DCO-Network"
    jira_labels: list = field(default_factory=list)
    oncall_team: str = "DCO-NOC"


@dataclass
class DiagnosticReport:
    """Complete diagnostic report container."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"))
    hostname: str = field(default_factory=socket.gethostname)
    interface: str = "veth0"
    scenario: str = "live"
    mode: str = "live"              # live | simulate
    layer1: Layer1Diagnostics = field(default_factory=Layer1Diagnostics)
    layer2: Layer2Diagnostics = field(default_factory=Layer2Diagnostics)
    layer3: Layer3Diagnostics = field(default_factory=Layer3Diagnostics)
    sla: SLAEvaluation = field(default_factory=SLAEvaluation)
    raw_commands: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# ANSI Colour Helpers
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    DIM    = "\033[2m"

def cprint(msg: str, colour: str = C.RESET, bold: bool = False) -> None:
    prefix = (C.BOLD if bold else "") + colour
    print(f"{prefix}{msg}{C.RESET}")

def banner(title: str) -> None:
    width = 60
    bar = "═" * width
    print(f"\n{C.BOLD}{C.CYAN}╔{bar}╗{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║  {title:<{width - 2}}║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╚{bar}╝{C.RESET}\n")

def section(title: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}── {title} {'─' * (50 - len(title))}{C.RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# Simulation Engine
# ═══════════════════════════════════════════════════════════════════════════════

def _jitter(base: float, pct: float = 0.05) -> float:
    """Add ±pct% jitter to a value for realistic simulation."""
    delta = base * pct
    return round(base + random.uniform(-delta, delta), 3)


def simulate_degraded_fiber(iface: str, target_ip: str) -> DiagnosticReport:
    """
    Scenario: degraded_fiber
    Simulates a dirty/damaged LC/UPC fiber connector or marginal SFP+ transceiver.
    Symptoms: High RX CRC errors, low optical RX power, 15% ICMP packet loss,
              82ms average latency.
    """
    report = DiagnosticReport(interface=iface, scenario="degraded_fiber", mode="simulate")

    # Layer 1 — Fiber physical metrics
    report.layer1 = Layer1Diagnostics(
        link_state       = "UP",
        operational_state= "up",
        speed_mbps       = 10000,
        duplex           = "full",
        rx_crc_errors    = random.randint(14_200, 15_800),
        tx_crc_errors    = random.randint(0, 12),
        rx_dropped       = random.randint(300, 450),
        tx_dropped       = 0,
        rx_bytes         = random.randint(2_400_000, 3_100_000),
        tx_bytes         = random.randint(1_800_000, 2_600_000),
        optical_rx_power_dbm = _jitter(-18.4),    # Critical: below -17 dBm threshold
        optical_tx_power_dbm = _jitter(-2.1),
        media_type       = "Fiber (SFP+)",
        transceiver_present = True,
        mtu              = 9000,                  # Jumbo frames enabled
    )

    # Layer 2 — ARP still resolves (link is UP but degraded)
    report.layer2 = Layer2Diagnostics(
        mac_address        = "0a:dc:00:f1:be:01",
        arp_neighbor_state = "STALE",
        arp_neighbor_mac   = "0a:dc:00:f1:be:02",
        vlan_id            = 42,
        interface_flags    = ["BROADCAST", "MULTICAST", "UP"],
    )

    # Layer 3 — Degraded ICMP with packet loss
    pkts_recv = 8   # 2 out of 10 lost → 20% (simulating burst)
    report.layer3 = Layer3Diagnostics(
        ping_min_ms      = _jitter(74.2),
        ping_avg_ms      = _jitter(82.1),
        ping_max_ms      = _jitter(143.7),
        ping_mdev_ms     = _jitter(18.3),
        packet_loss_pct  = 15.0,
        packets_sent     = 20,
        packets_received = 17,
        target_ip        = target_ip,
        dns_hostname     = "ec2.internal",
        dns_resolved_ip  = target_ip,
        dns_latency_ms   = _jitter(1.2),
        route_next_hop   = "10.200.1.1",
        ttl              = 64,
    )

    report.sla = evaluate_sla(report.layer1, report.layer2, report.layer3)
    return report


def simulate_link_down(iface: str, target_ip: str) -> DiagnosticReport:
    """
    Scenario: link_down
    Simulates an unplugged RJ45 patch cable or failed SFP+ transceiver.
    Symptoms: NO-CARRIER, all Layer 3 unreachable.
    """
    report = DiagnosticReport(interface=iface, scenario="link_down", mode="simulate")

    report.layer1 = Layer1Diagnostics(
        link_state        = "NO-CARRIER",
        operational_state = "down",
        speed_mbps        = 0,
        duplex            = "unknown",
        rx_crc_errors     = 0,
        tx_crc_errors     = 0,
        rx_dropped        = 0,
        tx_dropped        = 0,
        rx_bytes          = random.randint(0, 1024),
        tx_bytes          = random.randint(0, 1024),
        optical_rx_power_dbm = None,
        optical_tx_power_dbm = None,
        media_type        = "Copper",
        transceiver_present  = False,
        mtu               = 1500,
    )

    report.layer2 = Layer2Diagnostics(
        mac_address        = "0a:dc:00:f1:be:01",
        arp_neighbor_state = "FAILED",
        arp_neighbor_mac   = "N/A",
        vlan_id            = None,
        interface_flags    = ["BROADCAST", "MULTICAST"],   # NO UP flag
    )

    report.layer3 = Layer3Diagnostics(
        ping_min_ms      = 0.0,
        ping_avg_ms      = 0.0,
        ping_max_ms      = 0.0,
        ping_mdev_ms     = 0.0,
        packet_loss_pct  = 100.0,
        packets_sent     = 10,
        packets_received = 0,
        target_ip        = target_ip,
        dns_hostname     = None,
        dns_resolved_ip  = None,
        dns_latency_ms   = 0.0,
        route_next_hop   = None,
        ttl              = 0,
    )

    report.sla = evaluate_sla(report.layer1, report.layer2, report.layer3)
    return report


def simulate_healthy(iface: str, target_ip: str) -> DiagnosticReport:
    """
    Scenario: healthy
    Simulates a clean, well-functioning copper or fiber link.
    """
    report = DiagnosticReport(interface=iface, scenario="healthy", mode="simulate")

    report.layer1 = Layer1Diagnostics(
        link_state        = "UP",
        operational_state = "up",
        speed_mbps        = 1000,
        duplex            = "full",
        rx_crc_errors     = 0,
        tx_crc_errors     = 0,
        rx_dropped        = 0,
        tx_dropped        = 0,
        rx_bytes          = random.randint(5_000_000, 8_000_000),
        tx_bytes          = random.randint(4_000_000, 7_000_000),
        optical_rx_power_dbm = None,
        optical_tx_power_dbm = None,
        media_type        = "Copper",
        transceiver_present  = True,
        mtu               = 1500,
    )

    report.layer2 = Layer2Diagnostics(
        mac_address        = "0a:dc:00:f1:be:01",
        arp_neighbor_state = "REACHABLE",
        arp_neighbor_mac   = "0a:dc:00:f1:be:02",
        vlan_id            = 10,
        interface_flags    = ["BROADCAST", "MULTICAST", "UP"],
    )

    report.layer3 = Layer3Diagnostics(
        ping_min_ms      = _jitter(0.3),
        ping_avg_ms      = _jitter(0.4),
        ping_max_ms      = _jitter(0.7),
        ping_mdev_ms     = _jitter(0.08),
        packet_loss_pct  = 0.0,
        packets_sent     = 10,
        packets_received = 10,
        target_ip        = target_ip,
        dns_hostname     = "ec2.internal",
        dns_resolved_ip  = target_ip,
        dns_latency_ms   = _jitter(0.3),
        route_next_hop   = "10.200.1.1",
        ttl              = 64,
    )

    report.sla = evaluate_sla(report.layer1, report.layer2, report.layer3)
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# Live Kernel Mode Collectors
# ═══════════════════════════════════════════════════════════════════════════════

def _run(cmd: list[str], timeout: int = 30) -> tuple[str, str, int]:
    """Run a shell command safely; return (stdout, stderr, returncode)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout, proc.stderr, proc.returncode
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", 127
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", 124
    except Exception as exc:
        return "", str(exc), 1


def collect_layer1_live(iface: str) -> tuple[Layer1Diagnostics, dict]:
    """Collect real Layer 1 data via ip, ethtool, /sys."""
    l1 = Layer1Diagnostics()
    raw: dict = {}

    # ip link show
    out, _, _ = _run(["ip", "-s", "link", "show", iface])
    raw["ip_link"] = out

    # Operational state
    state_path = f"/sys/class/net/{iface}/operstate"
    if os.path.exists(state_path):
        l1.operational_state = open(state_path).read().strip()

    # Parse ip -s link output for stats
    # Example: RX:  bytes  packets  errors  dropped  missed  mcast
    rx_match = re.search(
        r"RX:\s+bytes\s+packets\s+errors\s+dropped.*?\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        out, re.DOTALL)
    tx_match = re.search(
        r"TX:\s+bytes\s+packets\s+errors\s+dropped.*?\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        out, re.DOTALL)

    if rx_match:
        l1.rx_bytes   = int(rx_match.group(1))
        l1.rx_crc_errors = int(rx_match.group(3))
        l1.rx_dropped = int(rx_match.group(4))
    if tx_match:
        l1.tx_bytes   = int(tx_match.group(1))
        l1.tx_crc_errors = int(tx_match.group(3))
        l1.tx_dropped = int(tx_match.group(4))

    # Flags / link state from LOWER_UP / NO-CARRIER
    if "LOWER_UP" in out:
        l1.link_state = "UP"
    elif "NO-CARRIER" in out:
        l1.link_state = "NO-CARRIER"
    else:
        l1.link_state = "DOWN"

    # MTU
    mtu_m = re.search(r"mtu (\d+)", out)
    if mtu_m:
        l1.mtu = int(mtu_m.group(1))

    # ethtool
    etho, _, _ = _run(["ethtool", iface])
    raw["ethtool"] = etho

    speed_m = re.search(r"Speed:\s+(\d+)", etho)
    if speed_m:
        l1.speed_mbps = int(speed_m.group(1))

    duplex_m = re.search(r"Duplex:\s+(\w+)", etho)
    if duplex_m:
        l1.duplex = duplex_m.group(1).lower()

    # ethtool -m for optics (SFP+)
    optics, _, rc = _run(["ethtool", "-m", iface])
    raw["ethtool_m"] = optics
    if rc == 0 and optics:
        l1.media_type = "Fiber (SFP+)"
        rx_m = re.search(r"Receiver signal average optical power\s*:\s*([-\d.]+)", optics)
        tx_m = re.search(r"Laser output power\s*:\s*([-\d.]+)", optics)
        if rx_m:
            l1.optical_rx_power_dbm = float(rx_m.group(1))
        if tx_m:
            l1.optical_tx_power_dbm = float(tx_m.group(1))

    return l1, raw


def collect_layer2_live(iface: str, target_ip: str) -> tuple[Layer2Diagnostics, dict]:
    """Collect real Layer 2 data: MAC address, ARP state."""
    l2 = Layer2Diagnostics()
    raw: dict = {}

    # MAC address from /sys
    mac_path = f"/sys/class/net/{iface}/address"
    if os.path.exists(mac_path):
        l2.mac_address = open(mac_path).read().strip()

    # ARP neighbor
    out, _, _ = _run(["ip", "neighbor", "show", target_ip])
    raw["ip_neighbor"] = out

    if out.strip():
        parts = out.strip().split()
        # Format: <ip> dev <iface> lladdr <mac> <state>
        if "lladdr" in parts:
            idx = parts.index("lladdr")
            l2.arp_neighbor_mac = parts[idx + 1]
        for state in ("REACHABLE", "STALE", "FAILED", "DELAY", "PROBE", "INCOMPLETE"):
            if state in out.upper():
                l2.arp_neighbor_state = state
                break
    else:
        l2.arp_neighbor_state = "NONE"

    # Interface flags from ip link
    out2, _, _ = _run(["ip", "link", "show", iface])
    raw["ip_link_l2"] = out2
    flags = re.findall(r"<([^>]+)>", out2)
    if flags:
        l2.interface_flags = flags[0].split(",")

    return l2, raw


def collect_layer3_live(iface: str, target_ip: str, count: int = 10) -> tuple[Layer3Diagnostics, dict]:
    """Collect real Layer 3 data: ICMP ping, DNS, routing."""
    l3 = Layer3Diagnostics(target_ip=target_ip)
    raw: dict = {}

    # ICMP ping
    ping_cmd = ["ping", "-c", str(count), "-W", "2", "-I", iface, target_ip]
    out, _, _ = _run(ping_cmd, timeout=60)
    raw["ping"] = out

    # Parse: 10 packets transmitted, 8 received, 20% packet loss
    loss_m = re.search(r"(\d+) packets transmitted, (\d+) received, ([\d.]+)% packet loss", out)
    if loss_m:
        l3.packets_sent     = int(loss_m.group(1))
        l3.packets_received = int(loss_m.group(2))
        l3.packet_loss_pct  = float(loss_m.group(3))

    # Parse: rtt min/avg/max/mdev = 0.432/0.512/0.891/0.112 ms
    rtt_m = re.search(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", out)
    if rtt_m:
        l3.ping_min_ms  = float(rtt_m.group(1))
        l3.ping_avg_ms  = float(rtt_m.group(2))
        l3.ping_max_ms  = float(rtt_m.group(3))
        l3.ping_mdev_ms = float(rtt_m.group(4))

    # DNS resolution check
    try:
        import time
        t0 = time.time()
        l3.dns_hostname   = socket.getfqdn(target_ip)
        l3.dns_resolved_ip = target_ip
        l3.dns_latency_ms  = round((time.time() - t0) * 1000, 3)
    except Exception:
        l3.dns_hostname = None

    # Route next-hop
    route_out, _, _ = _run(["ip", "route", "get", target_ip])
    raw["ip_route"] = route_out
    via_m = re.search(r"via ([\d.]+)", route_out)
    l3.route_next_hop = via_m.group(1) if via_m else None

    return l3, raw


# ═══════════════════════════════════════════════════════════════════════════════
# SLA Evaluation Engine
# ═══════════════════════════════════════════════════════════════════════════════

# SLA thresholds (Enterprise Network standards)
THRESHOLDS = {
    "link_down_severity"      : "SEV-2",
    "crc_error_threshold"     : 1_000,       # errors above this → SEV-3
    "optical_rx_min_dbm"      : -17.0,       # below this → degraded optics SEV-3
    "packet_loss_sev3_pct"    : 5.0,         # above this → SEV-3
    "latency_sev3_ms"         : 50.0,        # above this → SEV-3
    "sev2_remediation_minutes": 30,          # SLA: resolve within 30 min
    "sev3_remediation_minutes": 120,         # SLA: resolve within 2 hrs
}


def evaluate_sla(l1: Layer1Diagnostics, l2: Layer2Diagnostics, l3: Layer3Diagnostics) -> SLAEvaluation:
    """
    Multi-layer SLA evaluation engine.
    Returns an SLAEvaluation with severity, triggered rules, remediation steps, and RCA.
    """
    sla = SLAEvaluation()
    sla.jira_ticket_id = f"DCO-NET-{random.randint(10000, 99999)}"
    sla.jira_labels    = ["network", "dco", "physical-layer", "automated"]

    rules_triggered = []
    remediation     = []
    rca_parts       = []

    # ── Rule 1: Layer 1 Link Down ─────────────────────────────────────────────
    if l1.link_state in ("NO-CARRIER", "DOWN") or l1.operational_state == "down":
        rules_triggered.append(
            f"L1-LINK-DOWN: Interface operational state is '{l1.operational_state}' "
            f"(link_state={l1.link_state})"
        )
        sla.severity               = "SEV-2"
        sla.jira_priority          = "High"
        sla.sla_breach_minutes     = 0
        sla.remediation_timer_minutes = THRESHOLDS["sev2_remediation_minutes"]
        rca_parts.append(
            "PHYSICAL LINK FAILURE — OSI Layer 1 carrier signal is absent. "
            "Probable causes: (1) Unplugged or damaged RJ45 patch cable, "
            "(2) Failed or unseated SFP+/SFP28 transceiver module, "
            "(3) Faulty upstream switch/router port, "
            "(4) Broken copper pair in cable run."
        )
        if not l1.transceiver_present:
            remediation.append(
                "🔌 STEP 1 — Verify SFP+ transceiver is fully seated in the cage. "
                "Re-seat transceiver and check for the green LED indicator."
            )
            remediation.append(
                "🔦 STEP 2 — Use a Visual Fault Locator (VFL) to test fiber continuity. "
                "Inspect both ends of the LC/PC or LC/UPC cable run for visible red light break."
            )
        else:
            remediation.append(
                "🔌 STEP 1 — Physically inspect RJ45 patch cable at both server NIC and ToR switch port. "
                "Confirm clip is engaged and LED link light is ON (amber = 1G, green = 10G on most NICs)."
            )
            remediation.append(
                "🔄 STEP 2 — Swap the patch cable with a known-good Cat6/Cat6A cable of equivalent length."
            )
            remediation.append(
                "🛠️  STEP 3 — Test the ToR switch port with a cable tester or loopback plug."
            )
        remediation.append(
            "📋 STEP 3 — After physical fix, verify: "
            "`ip link show <iface>` should show LOWER_UP, "
            "`ethtool <iface>` should show 'Link detected: yes'."
        )

    # ── Rule 2: High RX CRC Errors ────────────────────────────────────────────
    if l1.rx_crc_errors > THRESHOLDS["crc_error_threshold"]:
        rules_triggered.append(
            f"L1-CRC-ERRORS: RX CRC errors={l1.rx_crc_errors:,} "
            f"(threshold={THRESHOLDS['crc_error_threshold']:,})"
        )
        if sla.severity == "OK":
            sla.severity               = "SEV-3"
            sla.jira_priority          = "Medium"
            sla.remediation_timer_minutes = THRESHOLDS["sev3_remediation_minutes"]
        rca_parts.append(
            f"LAYER 1 PHYSICAL SIGNAL DEGRADATION — {l1.rx_crc_errors:,} RX CRC errors detected. "
            "CRC errors on fiber links typically indicate dirty or contaminated LC/UPC ferrules, "
            "exceeding fiber bend radius limits, or a marginal SFP+ transceiver."
        )
        remediation.append(
            "🔬 STEP A — Inspect LC/UPC fiber connector ferrules with a fiber endface inspection "
            "scope (e.g. JDSU FBP-SD15 or Fluke FI-500 FiberInspector). "
            "Contaminated ferrules show as dark spots in the core region."
        )
        remediation.append(
            "🧹 STEP B — Clean LC/UPC ferrules using a one-click fiber optic cleaner "
            "(e.g. Fujikura CLC-22). Clean both the patch cable and the SFP+ transceiver ferrule. "
            "NEVER blow with breath (moisture causes contamination)."
        )
        remediation.append(
            "📡 STEP C — After cleaning, re-measure optical RX power with `ethtool -m <iface>`. "
            f"Target RX power range: -3.0 dBm to -13.0 dBm (current: {l1.optical_rx_power_dbm} dBm)."
        )

    # ── Rule 3: Low Optical RX Power ─────────────────────────────────────────
    if (l1.optical_rx_power_dbm is not None and
            l1.optical_rx_power_dbm < THRESHOLDS["optical_rx_min_dbm"]):
        rules_triggered.append(
            f"L1-OPTICAL-RX-LOW: RX power={l1.optical_rx_power_dbm} dBm "
            f"(threshold={THRESHOLDS['optical_rx_min_dbm']} dBm)"
        )
        if sla.severity == "OK":
            sla.severity               = "SEV-3"
            sla.jira_priority          = "Medium"
            sla.remediation_timer_minutes = THRESHOLDS["sev3_remediation_minutes"]
        rca_parts.append(
            f"OPTICAL POWER BUDGET EXCEEDED — Received optical power is {l1.optical_rx_power_dbm} dBm, "
            f"below the minimum acceptable threshold of {THRESHOLDS['optical_rx_min_dbm']} dBm. "
            "Possible causes: excessive fiber attenuation, dirty ferrules, bad fiber splice, "
            "or dying SFP+ laser diode."
        )
        remediation.append(
            "🔭 STEP D — Use an optical power meter (e.g. EXFO PPM-350B) at the far end to "
            "measure insertion loss of the fiber run. "
            "Per-connector loss should be < 0.5 dB; total run loss < 3.5 dB for OM4 MMF."
        )
        remediation.append(
            "🔁 STEP E — If optical loss is within budget, replace the SFP+ transceiver module. "
            "Use OEM-compatible modules meeting enterprise network specs (e.g. Finisar FTLX8571D3BCL for 10GBase-SR)."
        )

    # ── Rule 4: Packet Loss SEV-3 ─────────────────────────────────────────────
    if l3.packet_loss_pct >= THRESHOLDS["packet_loss_sev3_pct"] and sla.severity == "OK":
        rules_triggered.append(
            f"L3-PACKET-LOSS: {l3.packet_loss_pct}% loss "
            f"(threshold={THRESHOLDS['packet_loss_sev3_pct']}%)"
        )
        sla.severity               = "SEV-3"
        sla.jira_priority          = "Medium"
        sla.remediation_timer_minutes = THRESHOLDS["sev3_remediation_minutes"]
        rca_parts.append(
            f"LAYER 3 PACKET LOSS — {l3.packet_loss_pct}% ICMP packet loss detected to {l3.target_ip}. "
            "Combined with physical layer CRC errors, this is consistent with a signal integrity issue "
            "at the physical layer causing frame drops at the MAC sublayer."
        )

    # ── Rule 5: ARP State Degraded ────────────────────────────────────────────
    if l2.arp_neighbor_state in ("FAILED", "INCOMPLETE"):
        rules_triggered.append(
            f"L2-ARP-{l2.arp_neighbor_state}: ARP neighbor resolution failed for {l3.target_ip}"
        )
        rca_parts.append(
            f"LAYER 2 ARP FAILURE — ARP neighbor state is '{l2.arp_neighbor_state}'. "
            "The MAC address of the remote host cannot be resolved, confirming Layer 2 connectivity loss."
        )

    # ── Rule 6: High Latency ──────────────────────────────────────────────────
    if l3.ping_avg_ms > THRESHOLDS["latency_sev3_ms"] and sla.severity not in ("SEV-2",):
        rules_triggered.append(
            f"L3-HIGH-LATENCY: avg={l3.ping_avg_ms}ms "
            f"(threshold={THRESHOLDS['latency_sev3_ms']}ms)"
        )
        if sla.severity == "OK":
            sla.severity               = "SEV-3"
            sla.jira_priority          = "Medium"
            sla.remediation_timer_minutes = THRESHOLDS["sev3_remediation_minutes"]

    # ── Healthy baseline ──────────────────────────────────────────────────────
    if sla.severity == "OK":
        sla.jira_priority          = "Low"
        sla.remediation_timer_minutes = 0
        rca_parts.append(
            "All Layer 1-3 diagnostics are within normal operational parameters. "
            "No remediation required."
        )
        remediation.append(
            "✅ No action required — interface is healthy. "
            "Continue periodic monitoring via CloudWatch + SNMP polling."
        )

    sla.triggered_rules       = rules_triggered
    sla.remediation_steps     = remediation
    sla.root_cause_analysis   = "\n\n".join(rca_parts) if rca_parts else "No anomalies detected."
    sla.oncall_team           = "DCO-NOC" if sla.severity == "SEV-2" else "DCO-NET"
    sla.jira_component        = "DCO-Network/Physical"
    sla.jira_labels           = ["network", "dco", "physical-layer", "automated",
                                 f"sev-{sla.severity.lower()}", f"l1-{l1.media_type.lower().split()[0]}"]

    return sla


# ═══════════════════════════════════════════════════════════════════════════════
# Report Generators
# ═══════════════════════════════════════════════════════════════════════════════

SEV_COLOURS = {
    "SEV-1": "🔴",
    "SEV-2": "🟠",
    "SEV-3": "🟡",
    "OK"   : "🟢",
}


def generate_markdown_ticket(report: DiagnosticReport, output_path: Path) -> None:
    """Generate a detailed Jira-compatible Markdown incident ticket."""
    l1, l2, l3, sla = report.layer1, report.layer2, report.layer3, report.sla
    sev_icon = SEV_COLOURS.get(sla.severity, "⚪")
    ts = datetime.datetime.now(datetime.timezone.utc)
    breach_note = (
        f"**SLA Breach in:** `{sla.remediation_timer_minutes} minutes`"
        if sla.remediation_timer_minutes > 0
        else "**SLA Status:** ✅ No breach — system healthy"
    )

    md = f"""# 🌐 Network Incident — Jira Ticket `{sla.jira_ticket_id}`

---

## 📋 Ticket Metadata

| Field | Value |
|---|---|
| **Ticket ID** | `{sla.jira_ticket_id}` |
| **Priority** | `{sla.jira_priority}` |
| **Severity** | {sev_icon} `{sla.severity}` |
| **Component** | `{sla.jira_component}` |
| **On-Call Team** | `{sla.oncall_team}` |
| **Reporter** | `net_diag_ticket.py v2.0 (Automated)` |
| **Created** | `{ts.strftime('%Y-%m-%d %H:%M:%S UTC')}` |
| **Report ID** | `{report.report_id}` |
| **Hostname** | `{report.hostname}` |
| **Interface** | `{report.interface}` |
| **Mode** | `{"🔴 LIVE Kernel" if report.mode == "live" else "🔵 Simulation — " + report.scenario}` |
| **Labels** | {" ".join(f"`{lb}`" for lb in sla.jira_labels)} |

---

## {sev_icon} SLA Assessment

> **Severity: {sla.severity}**
> {breach_note}

### Triggered Alert Rules

{"".join(f"- ⚠️  `{rule}`\\n" for rule in sla.triggered_rules) if sla.triggered_rules else "- ✅ No rules triggered — all metrics nominal"}

---

## 🔬 Root Cause Analysis (RCA)

```
{sla.root_cause_analysis}
```

---

## 📡 OSI Layer 1 — Physical Layer Diagnostics

| Metric | Value | Status |
|---|---|---|
| **Link State** | `{l1.link_state}` | {"✅" if l1.link_state == "UP" else "🔴"} |
| **Operational State** | `{l1.operational_state}` | {"✅" if l1.operational_state == "up" else "🔴"} |
| **Speed** | `{l1.speed_mbps} Mbps` | {"✅" if l1.speed_mbps >= 1000 else ("🔴" if l1.speed_mbps == 0 else "🟡")} |
| **Duplex** | `{l1.duplex}` | {"✅" if l1.duplex == "full" else "🟡"} |
| **Media Type** | `{l1.media_type}` | ℹ️  |
| **MTU** | `{l1.mtu} bytes` | ℹ️  |
| **RX CRC Errors** | `{l1.rx_crc_errors:,}` | {"🔴 CRITICAL" if l1.rx_crc_errors > 1000 else ("🟡 WARNING" if l1.rx_crc_errors > 100 else "✅ Normal")} |
| **TX CRC Errors** | `{l1.tx_crc_errors:,}` | {"🔴" if l1.tx_crc_errors > 100 else "✅"} |
| **RX Dropped** | `{l1.rx_dropped:,}` | {"🟡" if l1.rx_dropped > 0 else "✅"} |
| **TX Dropped** | `{l1.tx_dropped:,}` | {"🟡" if l1.tx_dropped > 0 else "✅"} |
| **RX Bytes** | `{l1.rx_bytes:,}` | ℹ️  |
| **TX Bytes** | `{l1.tx_bytes:,}` | ℹ️  |
| **Transceiver Present** | `{"Yes" if l1.transceiver_present else "NO — MISSING/FAILED"}` | {"✅" if l1.transceiver_present else "🔴"} |
| **Optical RX Power** | `{f"{l1.optical_rx_power_dbm} dBm" if l1.optical_rx_power_dbm is not None else "N/A (Copper)"}` | {"🔴 BELOW THRESHOLD" if l1.optical_rx_power_dbm is not None and l1.optical_rx_power_dbm < -17.0 else ("✅" if l1.optical_rx_power_dbm is not None else "ℹ️ ")} |
| **Optical TX Power** | `{f"{l1.optical_tx_power_dbm} dBm" if l1.optical_tx_power_dbm is not None else "N/A (Copper)"}` | ℹ️  |

---

## 🔗 OSI Layer 2 — Data Link Layer Diagnostics

| Metric | Value | Status |
|---|---|---|
| **MAC Address** | `{l2.mac_address}` | ℹ️  |
| **VLAN ID** | `{l2.vlan_id if l2.vlan_id else "Untagged / N/A"}` | ℹ️  |
| **ARP Neighbor State** | `{l2.arp_neighbor_state}` | {"✅" if l2.arp_neighbor_state == "REACHABLE" else ("🟡" if l2.arp_neighbor_state == "STALE" else "🔴")} |
| **ARP Neighbor MAC** | `{l2.arp_neighbor_mac}` | ℹ️  |
| **Interface Flags** | `{", ".join(l2.interface_flags)}` | {"✅" if "UP" in l2.interface_flags else "🔴 Link flag missing"} |

---

## 🌐 OSI Layer 3 — Network Layer Diagnostics

| Metric | Value | Status |
|---|---|---|
| **Target IP** | `{l3.target_ip}` | ℹ️  |
| **Packets Sent** | `{l3.packets_sent}` | ℹ️  |
| **Packets Received** | `{l3.packets_received}` | ℹ️  |
| **Packet Loss** | `{l3.packet_loss_pct}%` | {"🔴 CRITICAL" if l3.packet_loss_pct == 100 else ("🟡 WARNING" if l3.packet_loss_pct >= 5 else "✅ Normal")} |
| **RTT Min** | `{l3.ping_min_ms} ms` | ℹ️  |
| **RTT Average** | `{l3.ping_avg_ms} ms` | {"🟡" if l3.ping_avg_ms > 50 else "✅"} |
| **RTT Max** | `{l3.ping_max_ms} ms` | ℹ️  |
| **RTT Mdev** | `{l3.ping_mdev_ms} ms` | ℹ️  |
| **DNS Hostname** | `{l3.dns_hostname or "N/A — Resolution failed"}` | {"✅" if l3.dns_hostname else "🔴"} |
| **DNS Resolved IP** | `{l3.dns_resolved_ip or "N/A"}` | ℹ️  |
| **DNS Latency** | `{l3.dns_latency_ms} ms` | ℹ️  |
| **Route Next-Hop** | `{l3.route_next_hop or "N/A — No route"}` | {"✅" if l3.route_next_hop else "🔴"} |
| **TTL** | `{l3.ttl}` | ℹ️  |

---

## 🛠️ Physical Remediation Steps (DCO Field Technician)

> **SLA Timer:** Resolve within **{sla.remediation_timer_minutes} minutes** from ticket creation.

{"".join(f"{i+1}. {step}\\n" for i, step in enumerate(sla.remediation_steps))}

### Post-Remediation Verification Checklist

- [ ] `ip link show {report.interface}` → shows `state UP` and `LOWER_UP`
- [ ] `ethtool {report.interface}` → shows `Link detected: yes` and correct speed/duplex
- [ ] `ethtool -m {report.interface}` → optical RX power within -3 to -13 dBm (if fiber)
- [ ] `ping -c 50 -I {report.interface} {l3.target_ip}` → 0% packet loss
- [ ] `ip -s link show {report.interface}` → RX CRC errors not incrementing
- [ ] Network monitoring telemetry → `NetworkCRCErrors` returning to baseline
- [ ] Notify on-call NOC lead and update Jira ticket status to **RESOLVED**

---

## 📊 Diagnostic Summary

```
Report ID  : {report.report_id}
Timestamp  : {report.timestamp}
Interface  : {report.interface}
Scenario   : {report.scenario}
Severity   : {sla.severity}
Ticket ID  : {sla.jira_ticket_id}
Mode       : {report.mode}
```

---

*Generated automatically by `net_diag_ticket.py v2.0` — Network Diagnostics & SLA Toolkit*
*Do not edit manually — re-run diagnostic tool for updated telemetry*
"""

    output_path.write_text(md, encoding="utf-8")


def generate_json_payload(report: DiagnosticReport, output_path: Path) -> None:
    """Generate a machine-readable JSON Jira API payload."""
    l1, l2, l3, sla = report.layer1, report.layer2, report.layer3, report.sla

    payload = {
        "jira_api_version": "3",
        "project": {"key": "DCO"},
        "issuetype": {"name": "Incident"},
        "summary": f"[{sla.severity}] Network Physical Layer Fault — {report.interface} @ {report.hostname}",
        "priority": {"name": sla.jira_priority},
        "labels": sla.jira_labels,
        "components": [{"name": sla.jira_component}],
        "customfield_oncall_team": sla.oncall_team,
        "customfield_severity": sla.severity,
        "customfield_sla_minutes": sla.remediation_timer_minutes,
        "customfield_report_id": report.report_id,
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": f"Automated network diagnostic report. Severity: {sla.severity}. "}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": f"RCA: {sla.root_cause_analysis[:500]}"}
                ]},
            ]
        },
        "diagnostic_telemetry": {
            "metadata": {
                "report_id"  : report.report_id,
                "timestamp"  : report.timestamp,
                "hostname"   : report.hostname,
                "interface"  : report.interface,
                "scenario"   : report.scenario,
                "mode"       : report.mode,
            },
            "layer1_physical": asdict(report.layer1),
            "layer2_datalink": asdict(report.layer2),
            "layer3_network" : asdict(report.layer3),
            "sla_evaluation" : {
                "severity"              : sla.severity,
                "jira_ticket_id"        : sla.jira_ticket_id,
                "jira_priority"         : sla.jira_priority,
                "remediation_timer_min" : sla.remediation_timer_minutes,
                "triggered_rules"       : sla.triggered_rules,
                "remediation_steps"     : sla.remediation_steps,
                "root_cause_analysis"   : sla.root_cause_analysis,
                "oncall_team"           : sla.oncall_team,
                "jira_labels"           : sla.jira_labels,
            }
        }
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Report Printer
# ═══════════════════════════════════════════════════════════════════════════════

def print_diagnostic_report(report: DiagnosticReport) -> None:
    """Print a formatted terminal summary of the diagnostic report."""
    l1, l2, l3, sla = report.layer1, report.layer2, report.layer3, report.sla
    sev_colour = {
        "SEV-1": C.RED, "SEV-2": C.RED, "SEV-3": C.YELLOW, "OK": C.GREEN
    }.get(sla.severity, C.RESET)

    banner("OSI Layer 1-3 Network Diagnostic Report")

    # Header
    section("Diagnostic Metadata")
    print(f"  Report ID   : {C.BOLD}{report.report_id}{C.RESET}")
    print(f"  Timestamp   : {report.timestamp}")
    print(f"  Hostname    : {report.hostname}")
    print(f"  Interface   : {C.BOLD}{report.interface}{C.RESET}")
    print(f"  Mode        : {'LIVE Kernel Mode' if report.mode == 'live' else f'Simulation ({report.scenario})'}")
    print(f"  Scenario    : {report.scenario}")

    # SLA
    section("SLA Assessment")
    sev_icon = SEV_COLOURS.get(sla.severity, "⚪")
    cprint(f"  Severity    : {sev_icon}  {sla.severity}", sev_colour, bold=True)
    cprint(f"  Ticket ID   : {sla.jira_ticket_id}", C.CYAN)
    print(f"  Priority    : {sla.jira_priority}")
    print(f"  On-Call     : {sla.oncall_team}")
    if sla.remediation_timer_minutes:
        cprint(f"  SLA Timer   : Resolve within {sla.remediation_timer_minutes} minutes!", C.YELLOW, bold=True)
    else:
        cprint(f"  SLA Timer   : No breach — system healthy ✅", C.GREEN)

    if sla.triggered_rules:
        section("Triggered Alert Rules")
        for rule in sla.triggered_rules:
            cprint(f"  ⚠  {rule}", C.YELLOW)

    # Layer 1
    section("OSI Layer 1 — Physical")
    state_c = C.GREEN if l1.link_state == "UP" else C.RED
    cprint(f"  Link State  : {l1.link_state}", state_c, bold=True)
    print(f"  Oper State  : {l1.operational_state}")
    print(f"  Speed       : {l1.speed_mbps} Mbps")
    print(f"  Duplex      : {l1.duplex}")
    print(f"  Media       : {l1.media_type}")
    print(f"  MTU         : {l1.mtu} bytes")
    crc_c = C.RED if l1.rx_crc_errors > 1000 else (C.YELLOW if l1.rx_crc_errors > 100 else C.GREEN)
    cprint(f"  RX CRC Err  : {l1.rx_crc_errors:,}", crc_c)
    print(f"  TX CRC Err  : {l1.tx_crc_errors:,}")
    print(f"  RX Dropped  : {l1.rx_dropped:,}")
    if l1.optical_rx_power_dbm is not None:
        opt_c = C.RED if l1.optical_rx_power_dbm < -17.0 else C.GREEN
        cprint(f"  Optical RX  : {l1.optical_rx_power_dbm} dBm", opt_c)
        print(f"  Optical TX  : {l1.optical_tx_power_dbm} dBm")
    else:
        print(f"  Optical     : N/A (Copper interface)")

    # Layer 2
    section("OSI Layer 2 — Data Link")
    print(f"  MAC Address : {l2.mac_address}")
    arp_c = C.GREEN if l2.arp_neighbor_state == "REACHABLE" else (C.YELLOW if l2.arp_neighbor_state == "STALE" else C.RED)
    cprint(f"  ARP State   : {l2.arp_neighbor_state}", arp_c)
    print(f"  ARP MAC     : {l2.arp_neighbor_mac}")
    print(f"  VLAN        : {l2.vlan_id or 'Untagged'}")
    print(f"  Flags       : {', '.join(l2.interface_flags)}")

    # Layer 3
    section("OSI Layer 3 — Network")
    loss_c = C.RED if l3.packet_loss_pct >= 50 else (C.YELLOW if l3.packet_loss_pct >= 5 else C.GREEN)
    cprint(f"  Packet Loss : {l3.packet_loss_pct}%", loss_c, bold=True)
    print(f"  RTT Min/Avg/Max : {l3.ping_min_ms}/{l3.ping_avg_ms}/{l3.ping_max_ms} ms")
    print(f"  Mdev        : {l3.ping_mdev_ms} ms")
    print(f"  Pkts Sent   : {l3.packets_sent}  Received: {l3.packets_received}")
    print(f"  Target IP   : {l3.target_ip}")
    print(f"  DNS         : {l3.dns_hostname or 'FAILED'} → {l3.dns_resolved_ip or 'N/A'}")
    print(f"  Next-Hop    : {l3.route_next_hop or 'N/A'}")

    # RCA
    section("Root Cause Analysis")
    for line in sla.root_cause_analysis.split("\n"):
        print(f"  {line}")

    # Remediation
    if sla.remediation_steps:
        section("Remediation Steps")
        for i, step in enumerate(sla.remediation_steps, 1):
            print(f"\n  {i}. {step}")

    print()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="net_diag_ticket",
        description=(
            "OSI Layer 1-3 Network Diagnostics & "
            "Automated Jira SLA Incident Ticketing Toolkit\n\n"
            "Examples:\n"
            "  python3 src/net_diag_ticket.py --simulate --scenario degraded_fiber\n"
            "  python3 src/net_diag_ticket.py --simulate --scenario link_down\n"
            "  python3 src/net_diag_ticket.py --interface veth0 --target-ip 10.200.1.2\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--interface",   default="veth0",
                        help="Network interface to diagnose (default: veth0)")
    parser.add_argument("--target-ip",  default="10.200.1.2",
                        help="Target IP for ICMP and ARP checks (default: 10.200.1.2)")
    parser.add_argument("--simulate",   action="store_true",
                        help="Enable deterministic simulation mode (no root required)")
    parser.add_argument("--scenario",   default="degraded_fiber",
                        choices=["degraded_fiber", "link_down", "healthy"],
                        help="Simulation scenario (default: degraded_fiber)")
    parser.add_argument("--output-dir", default="reports",
                        help="Directory for generated reports (default: reports/)")
    parser.add_argument("--seed",       type=int, default=None,
                        help="Random seed for reproducible simulation output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    banner("Network Diagnostics & SLA Toolkit v2.0")
    cprint("  Initialising diagnostic engine...", C.CYAN)

    # ── Run diagnostics ───────────────────────────────────────────────────────
    if args.simulate:
        cprint(f"  Mode: 🔵 SIMULATION ({args.scenario})\n", C.BLUE, bold=True)
        scenario_map = {
            "degraded_fiber": simulate_degraded_fiber,
            "link_down"     : simulate_link_down,
            "healthy"       : simulate_healthy,
        }
        report = scenario_map[args.scenario](args.interface, args.target_ip)

    else:
        cprint(f"  Mode: 🔴 LIVE Kernel — Interface: {args.interface}\n", C.RED, bold=True)

        # Check root on Linux
        if sys.platform.startswith("linux") and os.geteuid() != 0:
            cprint("  ⚠  WARNING: Not running as root. Some commands may fail.", C.YELLOW)

        report = DiagnosticReport(
            interface=args.interface,
            scenario="live",
            mode="live",
        )
        raw_all: dict = {}

        cprint("  → Collecting Layer 1 (Physical) data...", C.DIM)
        report.layer1, raw1 = collect_layer1_live(args.interface)
        raw_all.update(raw1)

        cprint("  → Collecting Layer 2 (Data Link) data...", C.DIM)
        report.layer2, raw2 = collect_layer2_live(args.interface, args.target_ip)
        raw_all.update(raw2)

        cprint("  → Collecting Layer 3 (Network) data...", C.DIM)
        report.layer3, raw3 = collect_layer3_live(args.interface, args.target_ip)
        raw_all.update(raw3)

        report.raw_commands = raw_all
        report.sla = evaluate_sla(report.layer1, report.layer2, report.layer3)

    # ── Print terminal report ─────────────────────────────────────────────────
    print_diagnostic_report(report)

    # ── Write Markdown ticket ─────────────────────────────────────────────────
    md_path   = output_dir / "jira_incident_ticket.md"
    json_path = output_dir / "jira_incident_ticket.json"

    cprint("  Generating reports...", C.CYAN)
    generate_markdown_ticket(report, md_path)
    generate_json_payload(report, json_path)

    cprint(f"\n  ✅ Markdown ticket : {md_path}", C.GREEN)
    cprint(f"  ✅ JSON payload    : {json_path}", C.GREEN)
    cprint(f"  ✅ Ticket ID       : {report.sla.jira_ticket_id}", C.CYAN, bold=True)
    cprint(f"  ✅ Severity        : {report.sla.severity}\n", C.CYAN, bold=True)


if __name__ == "__main__":
    main()
