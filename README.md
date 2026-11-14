# 🌐 Network Diagnostics & SLA Incident Ticketing Toolkit

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Linux](https://img.shields.io/badge/OS-Linux-orange.svg)](https://kernel.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Network Engineering](https://img.shields.io/badge/Domain-Network%20Engineering%20%26%20SRE-blueviolet.svg)](https://github.com/Pujitha-pitta/network-diagnostics-sla-tool)

> **OSI Layer 1–3 Linux Network Diagnostics + Automated Jira SLA Incident Ticketing**  
> Enterprise Network Operations & Infrastructure Engineering — Physical Layer Fault Detection & Automated Remediation

---

## 📖 Table of Contents

- [Project Overview](#project-overview)
- [Architecture Overview](#architecture-overview)
- [OSI Layer 1–3 Troubleshooting Workflow](#osi-layer-13-troubleshooting-workflow)
- [Directory Structure](#directory-structure)
- [Quick Start](#quick-start)
- [CLI Usage](#cli-usage)
- [Simulation Scenarios](#simulation-scenarios)
- [SLA Severity Matrix](#sla-severity-matrix)
- [Sample Ticket Output](#sample-ticket-output)
- [Virtual Ethernet Lab Setup](#virtual-ethernet-lab-setup)
- [Running Tests](#running-tests)
- [Network Field Remediation Guide](#network-field-remediation-guide)
- [Technology Stack](#technology-stack)
- [Engineering Highlights](#engineering-highlights)

---

## Project Overview

This toolkit automates the most time-critical part of enterprise network engineering: **diagnosing physical and logical layer faults and generating Jira SLA incident tickets before an on-call engineer even picks up a cable tester**.

### What It Does

| Capability | Details |
|---|---|
| **Multi-layer diagnostics** | Automated OSI Layer 1 (Physical), 2 (Data Link), and 3 (Network) checks |
| **Physical signal analysis** | CRC error counters, SFP+ optical RX/TX power (dBm), link speed/duplex |
| **SLA auto-escalation** | SEV-2 (30-min SLA) for link-down, SEV-3 (2-hr SLA) for degraded signals |
| **Jira ticket generation** | Full Markdown + JSON Jira API payload with RCA and remediation steps |
| **Simulation mode** | Deterministic `--simulate` flag for CI/CD, demos, and training environments |
| **Virtual lab** | `veth` pair with `tc netem` impairment injection for realistic testing |

### Two Execution Modes

```
┌─────────────────────────────────────────────────────────────┐
│  LIVE Kernel Mode          │  Simulation Mode               │
│  (requires root + veth)    │  (--simulate flag, no root)    │
├─────────────────────────────────────────────────────────────┤
│  Real iproute2 commands    │  Deterministic telemetry       │
│  Real ethtool SFP+ data    │  Realistic degraded fiber data │
│  Real tc netem impairments │  Three named scenarios         │
│  Real tcpdump captures     │  Identical report output       │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    net_diag_ticket.py                           │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Layer 1     │  │  Layer 2     │  │  Layer 3             │  │
│  │  Physical    │  │  Data Link   │  │  Network             │  │
│  │  Collector   │  │  Collector   │  │  Collector           │  │
│  │              │  │              │  │                      │  │
│  │ • ethtool    │  │ • ip neigh   │  │ • ping (ICMP)        │  │
│  │ • ethtool -m │  │ • ip link    │  │ • ip route get       │  │
│  │ • ip -s link │  │ • /sys/net/  │  │ • socket.getfqdn()   │  │
│  │ • /sys/class │  │   address    │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                     │               │
│         └────────────────►▼◄────────────────────┘               │
│                     ┌────────────┐                              │
│                     │    SLA     │                              │
│                     │ Evaluation │                              │
│                     │  Engine    │                              │
│                     │            │                              │
│                     │ SEV-2/3/OK │                              │
│                     └─────┬──────┘                              │
│                           │                                     │
│              ┌────────────┼────────────┐                        │
│              ▼            ▼            ▼                        │
│        ┌──────────┐ ┌──────────┐ ┌──────────┐                  │
│        │ Terminal │ │ Markdown │ │   JSON   │                  │
│        │  Report  │ │  Ticket  │ │ Payload  │                  │
│        │ (colour) │ │ (.md)    │ │ (.json)  │                  │
│        └──────────┘ └──────────┘ └──────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File | Responsibility |
|---|---|---|
| **CLI Entry Point** | `src/net_diag_ticket.py` | argparse, mode routing, report orchestration |
| **Simulation Engine** | `src/net_diag_ticket.py` | Deterministic per-scenario telemetry generation |
| **SLA Evaluation** | `src/net_diag_ticket.py` | Rule engine: thresholds → severity → remediation |
| **Report Generators** | `src/net_diag_ticket.py` | Markdown Jira ticket + JSON API payload |
| **veth Lab** | `scripts/setup_veth_lab.sh` | Real kernel-mode network impairment lab |
| **Test Suite** | `tests/test_net_diag.py` | 113 unit test cases across all scenarios |

---

## OSI Layer 1–3 Troubleshooting Workflow

```
START: Network Alert / Telemetry Anomaly
           │
           ▼
┌─────────────────────┐
│   LAYER 1 — Physical │
│                     │
│ • ip link show      │◄── Is LOWER_UP flag present?
│ • ethtool <iface>   │◄── Link detected? Speed? Duplex?
│ • ethtool -m <iface>│◄── SFP+ RX power > -17 dBm?
│ • ip -s link show   │◄── RX CRC errors < 1,000?
└──────────┬──────────┘
           │  PASS ──────────────────────────┐
           │  FAIL (NO-CARRIER / CRC / Optics)│
           ▼                                 │
     ┌──────────┐                            │
     │  SEV-2?  │◄── Link completely down    │
     │  SEV-3?  │◄── Degraded signal quality │
     └──────────┘                            │
           │                                 ▼
           ▼                   ┌─────────────────────┐
   PHYSICAL REMEDIATION        │   LAYER 2 — Data    │
   (see Field Guide below)     │   Link              │
                               │                     │
                               │ • ip neigh show     │◄── ARP REACHABLE?
                               │ • ip link flags     │◄── BROADCAST + UP?
                               │ • VLAN membership   │◄── Correct VLAN?
                               └──────────┬──────────┘
                                          │  PASS ─────────────┐
                                          │  FAIL (ARP FAILED) │
                                          ▼                    │
                                    ┌──────────┐               │
                                    │ Check    │               │
                                    │ VLAN/STP │               │
                                    └──────────┘               │
                                                               ▼
                                               ┌─────────────────────┐
                                               │  LAYER 3 — Network  │
                                               │                     │
                                               │ • ping -c 50        │◄── 0% loss?
                                               │ • ip route get      │◄── Route exists?
                                               │ • DNS resolution    │◄── FQDN resolves?
                                               └──────────┬──────────┘
                                                         │
                                                    ┌────┴────┐
                                                    │ GENERATE │
                                                    │  JIRA    │
                                                    │ TICKET   │
                                                    └─────────┘
```

### OSI Layer Diagnostic Commands Reference

#### Layer 1 — Physical

```bash
# Check link state and flags
ip link show veth0

# Detailed stats: RX/TX bytes, errors, dropped
ip -s link show veth0

# Speed, duplex, link detection
ethtool veth0

# SFP+ optical power levels (fiber only)
ethtool -m veth0

# Check operational state via sysfs
cat /sys/class/net/veth0/operstate

# Apply network impairments (netem)
tc qdisc add dev veth0 root netem delay 80ms loss 15%
tc qdisc show dev veth0
```

#### Layer 2 — Data Link

```bash
# ARP neighbor table (REACHABLE / STALE / FAILED)
ip neighbor show 10.200.1.2

# MAC address
cat /sys/class/net/veth0/address

# Interface flags (BROADCAST, MULTICAST, UP, LOWER_UP)
ip link show veth0
```

#### Layer 3 — Network

```bash
# ICMP ping with interface binding
ping -c 50 -W 2 -I veth0 10.200.1.2

# Routing table lookup
ip route get 10.200.1.2

# DNS reverse lookup
dig -x 10.200.1.2

# Packet capture (10 ICMP packets)
tcpdump -i veth1 -c 10 icmp
```

---

## Directory Structure

```
network-diagnostics-sla-tool/
│
├── scripts/
│   └── setup_veth_lab.sh          # Kernel-mode veth lab setup + netem injection
│
├── src/
│   └── net_diag_ticket.py         # Main CLI diagnostic + ticket generator
│
├── tests/
│   └── test_net_diag.py           # 113 unittest cases across all scenarios
│
├── reports/                       # Generated output (auto-created)
│   ├── jira_incident_ticket.md    # Jira-compatible Markdown ticket
│   └── jira_incident_ticket.json  # JSON Jira API payload
│
└── README.md                      # This file
```

---

## Quick Start

### Option A — Simulation Mode (Recommended, No Root Required)

```bash
# Clone / enter project
cd network-diagnostics-sla-tool

# Run degraded fiber simulation
python3 src/net_diag_ticket.py --simulate --scenario degraded_fiber

# Run link-down simulation
python3 src/net_diag_ticket.py --simulate --scenario link_down

# Run healthy baseline
python3 src/net_diag_ticket.py --simulate --scenario healthy

# View generated ticket
cat reports/jira_incident_ticket.md
```

### Option B — Live Kernel Mode (Requires Linux + Root)

```bash
# 1. Set up the virtual Ethernet lab
sudo bash scripts/setup_veth_lab.sh

# 2. Run live diagnostics against the veth pair
sudo python3 src/net_diag_ticket.py --interface veth0 --target-ip 10.200.1.2

# 3. Clean up
sudo bash scripts/setup_veth_lab.sh --cleanup
```

---

## CLI Usage

```
usage: net_diag_ticket [-h] [--interface INTERFACE] [--target-ip TARGET_IP]
                       [--simulate] [--scenario {degraded_fiber,link_down,healthy}]
                       [--output-dir OUTPUT_DIR] [--seed SEED]

Network Diagnostics & Automated Jira SLA Incident Ticketing Toolkit

options:
  -h, --help            show this help message and exit
  --interface INTERFACE
                        Network interface to diagnose (default: veth0)
  --target-ip TARGET_IP
                        Target IP for ICMP and ARP checks (default: 10.200.1.2)
  --simulate            Enable deterministic simulation mode (no root required)
  --scenario {degraded_fiber,link_down,healthy}
                        Simulation scenario (default: degraded_fiber)
  --output-dir OUTPUT_DIR
                        Directory for generated reports (default: reports/)
  --seed SEED           Random seed for reproducible simulation output
```

### Example Commands

```bash
# Degraded fiber simulation with custom output directory
python3 src/net_diag_ticket.py --simulate --scenario degraded_fiber --output-dir /tmp/net-reports

# Reproducible simulation (fixed random seed for CI/CD)
python3 src/net_diag_ticket.py --simulate --scenario degraded_fiber --seed 42

# Link down — escalates to SEV-2
python3 src/net_diag_ticket.py --simulate --scenario link_down

# Live kernel mode (requires root + veth pair configured)
sudo python3 src/net_diag_ticket.py --interface veth0 --target-ip 10.200.1.2

# Custom interface and target
sudo python3 src/net_diag_ticket.py --interface eth0 --target-ip 192.168.1.1
```

---

## Simulation Scenarios

### `degraded_fiber` — Contaminated LC/UPC Fiber Connector

Simulates dirty fiber ferrules or a marginal SFP+ transceiver causing signal degradation.

| Metric | Simulated Value | Threshold | Status |
|---|---|---|---|
| Link State | `UP` | — | ✅ |
| Operational State | `up` | — | ✅ |
| Speed | `10,000 Mbps` | — | ✅ |
| RX CRC Errors | `~15,000` | `> 1,000` | 🔴 |
| Optical RX Power | `~-18.4 dBm` | `> -17.0 dBm` | 🔴 |
| ARP State | `STALE` | `REACHABLE` | 🟡 |
| Packet Loss | `15%` | `< 5%` | 🟡 |
| Avg Latency | `~82 ms` | `< 50 ms` | 🟡 |
| **SLA Severity** | **SEV-3** | — | 🟡 |
| **SLA Timer** | **120 minutes** | — | 🟡 |

### `link_down` — Unplugged Cable or Failed SFP+

Simulates a complete Layer 1 failure: NO-CARRIER, 100% packet loss.

| Metric | Simulated Value | Status |
|---|---|---|
| Link State | `NO-CARRIER` | 🔴 |
| Operational State | `down` | 🔴 |
| Speed | `0 Mbps` | 🔴 |
| Transceiver Present | `No` | 🔴 |
| ARP State | `FAILED` | 🔴 |
| Packet Loss | `100%` | 🔴 |
| **SLA Severity** | **SEV-2** | 🔴 |
| **SLA Timer** | **30 minutes** | 🔴 |

### `healthy` — Nominal Copper Link

Simulates a correctly functioning 1GbE copper interface.

| Metric | Simulated Value | Status |
|---|---|---|
| Link State | `UP` | ✅ |
| Speed | `1,000 Mbps` | ✅ |
| RX CRC Errors | `0` | ✅ |
| ARP State | `REACHABLE` | ✅ |
| Packet Loss | `0%` | ✅ |
| Avg Latency | `~0.4 ms` | ✅ |
| **SLA Severity** | **OK** | ✅ |

---

## SLA Severity Matrix

| Severity | Trigger Condition | SLA Timer | Priority | On-Call Team |
|---|---|---|---|---|
| **SEV-2** 🔴 | Link DOWN / NO-CARRIER | **30 minutes** | High | NOC-Level-2 |
| **SEV-3** 🟡 | CRC errors > 1,000 OR optical RX < -17 dBm OR packet loss > 5% OR latency > 50ms | **120 minutes** | Medium | NetOps-Queue |
| **OK** ✅ | All metrics within thresholds | None | Low | — |

> **Note:** SEV-2 always overrides SEV-3 when both conditions are met simultaneously.

---

## Sample Ticket Output

```markdown
# 🌐 Network Incident — Jira Ticket `NET-INC-54821`

## 📋 Ticket Metadata

| Field | Value |
|---|---|
| Ticket ID | `NET-INC-54821` |
| Priority | `Medium` |
| Severity | 🟡 `SEV-3` |
| Component | `Network/Physical` |
| On-Call Team | `NetOps-Queue` |
| Reporter | `net_diag_ticket.py v2.0 (Automated)` |

## SLA Assessment

> **Severity: SEV-3**
> **SLA Breach in:** `120 minutes`

### Triggered Alert Rules

- ⚠ `L1-CRC-ERRORS: RX CRC errors=15,243 (threshold=1,000)`
- ⚠ `L1-OPTICAL-RX-LOW: RX power=-18.4 dBm (threshold=-17.0 dBm)`
- ⚠ `L3-PACKET-LOSS: 15.0% loss (threshold=5.0%)`

## 🔬 Root Cause Analysis

LAYER 1 PHYSICAL SIGNAL DEGRADATION — 15,243 RX CRC errors detected.
CRC errors on fiber links typically indicate dirty or contaminated LC/UPC ferrules,
exceeding fiber bend radius limits, or a marginal SFP+ transceiver.

OPTICAL POWER BUDGET EXCEEDED — Received optical power is -18.4 dBm,
below the minimum acceptable threshold of -17.0 dBm.

## 🛠️ Physical Remediation Steps

1. 🔬 Inspect LC/UPC fiber connector ferrules with a fiber endface inspection scope
2. 🧹 Clean LC/UPC ferrules using a one-click fiber optic cleaner (e.g. Fujikura CLC-22)
3. 📡 Re-measure optical RX power with `ethtool -m <iface>`. Target: -3 to -13 dBm
4. 🔭 Use optical power meter to measure insertion loss of fiber run
5. 🔁 If optical loss within budget, replace SFP+ transceiver module
```

---

## Virtual Ethernet Lab Setup

The `setup_veth_lab.sh` script creates a complete virtual network lab on any Linux host:

```bash
# Full lab setup
sudo bash scripts/setup_veth_lab.sh
```

**What it does:**

1. ✅ Checks for root privileges  
2. ✅ Verifies `iproute2`, `ethtool`, `tc`, `tcpdump` are installed  
3. ✅ Creates `veth0 ↔ veth1` virtual Ethernet pair  
4. ✅ Assigns `10.200.1.1/24` → `veth0`, `10.200.1.2/24` → `veth1`  
5. ✅ Brings both interfaces UP  
6. ✅ Verifies with `ethtool veth0` and `ip -s link show veth0`  
7. ✅ Injects `80ms latency + 15% packet loss` via `tc qdisc add dev veth0 root netem delay 80ms loss 15%`  
8. ✅ Captures 10 ICMP packets with `tcpdump -i veth1 -c 10 icmp`  

```bash
# Clean teardown
sudo bash scripts/setup_veth_lab.sh --cleanup
```

---

## Running Tests

```bash
# Run all tests (discover mode)
python3 -m unittest discover -s tests

# Verbose output
python3 -m unittest tests.test_net_diag -v

# Run a specific test class
python3 -m unittest tests.test_net_diag.TestDegradedFiberScenario -v
python3 -m unittest tests.test_net_diag.TestLinkDownScenario -v
python3 -m unittest tests.test_net_diag.TestHealthyScenario -v
python3 -m unittest tests.test_net_diag.TestSLAEvaluationEngine -v
python3 -m unittest tests.test_net_diag.TestReportFileGeneration -v
python3 -m unittest tests.test_net_diag.TestDataModelIntegrity -v
```

**Test suite coverage:**

| Test Class | Tests | What It Covers |
|---|---|---|
| `TestDegradedFiberScenario` | 20 | L1/L2/L3 metrics, SEV-3 severity, fiber-specific values |
| `TestLinkDownScenario` | 15 | NO-CARRIER state, SEV-2 severity, ARP failure |
| `TestHealthyScenario` | 15 | OK severity, zero errors, REACHABLE ARP |
| `TestSLAEvaluationEngine` | 13 | Direct SLA rule engine tests, severity overrides |
| `TestReportFileGeneration` | 16 | File creation, Markdown/JSON content validation |
| `TestDataModelIntegrity` | 34 | Dataclass defaults, unique IDs, all scenarios |
| **Total** | **113** | **All Passed (0 errors, 0 failures)** |

---

## Network Field Remediation Guide

### Fiber Link (SFP+/LC-UPC) — Degraded Signal

```
1. INSPECT  → Fiber endface inspection scope on both LC connectors
               (look for contamination in core region)
2. CLEAN    → One-click cleaner on LC/UPC ferrule (patch cable + SFP+ port)
               NEVER blow with breath
3. MEASURE  → ethtool -m <iface> → Target RX: -3 to -13 dBm
4. BEND     → Check fiber bend radius at cable management rings
               Minimum bend radius: 10x cable diameter
5. REPLACE  → Swap SFP+ if optical power still marginal after cleaning
               Use OEM-approved modules (e.g. Finisar FTLX8571D3BCL)
```

### Copper Link (RJ45/Cat6) — Link Down

```
1. VISUAL   → Check both ends of patch cable — clip engaged? LED on?
2. SWAP     → Replace with known-good Cat6A patch cable
3. TEST     → Cable tester on suspect cable
4. PORT     → Try different switch port (loopback plug to test)
5. NIC      → If switch port OK, check NIC with different cable/port
```

### Verification After Remediation

```bash
ip link show <iface>              # Should show LOWER_UP
ethtool <iface>                   # Should show "Link detected: yes"
ethtool -m <iface>                # Optical RX should be -3 to -13 dBm
ping -c 50 -I <iface> <target>    # Should show 0% packet loss
ip -s link show <iface>           # CRC errors should stop incrementing
```

---

## Technology Stack

| Component | Technology |
|---|---|
| **Language** | Python 3.8+ (stdlib only — no pip dependencies) |
| **CLI Framework** | `argparse` |
| **Network Commands** | `iproute2` (`ip`), `ethtool`, `tc netem`, `ping`, `tcpdump` |
| **Virtualisation** | Linux `veth` (virtual Ethernet pairs) |
| **Impairment Injection** | `tc qdisc netem` (kernel traffic control) |
| **Testing** | `unittest` (stdlib) |
| **Report Formats** | Markdown (Jira-compatible) + JSON (Jira API v3) |
| **Target Platform** | Linux kernel 4.15+ (bare-metal, cloud instances, containers) |

---

## Engineering Highlights

This project demonstrates core network and systems engineering competencies:

- **Physical layer diagnostics**: Reading `ethtool` SFP+ optical power, interpreting CRC counters, understanding fiber loss budgets
- **Linux networking internals**: `iproute2` (`ip link`, `ip neigh`, `ip route`), `/sys/class/net/` sysfs, `tc qdisc netem`
- **Automation mindset**: Zero-human-intervention ticket generation with actionable RCA and step-by-step physical remediation
- **SLA management**: Automated severity classification with timer enforcement (SEV-2 = 30 min, SEV-3 = 2 hr)
- **Infrastructure as Code**: Deterministic simulation mode enables CI/CD integration without physical hardware
- **Professional tooling**: 113 unit tests, structured JSON output compatible with Jira API v3, coloured terminal output

---

*Production-Grade Network Diagnostics & SLA Incident Automation Engine*
