# 🌐 Network Incident — Jira Ticket `DCO-NET-38657`

---

## 📋 Ticket Metadata

| Field | Value |
|---|---|
| **Ticket ID** | `DCO-NET-38657` |
| **Priority** | `Medium` |
| **Severity** | 🟡 `SEV-3` |
| **Component** | `DCO-Network/Physical` |
| **On-Call Team** | `DCO-NET` |
| **Reporter** | `net_diag_ticket.py v2.0 (Automated)` |
| **Created** | `2026-11-14 09:19:50 UTC` |
| **Report ID** | `09FE5989` |
| **Hostname** | `DESKTOP-AVET5II` |
| **Interface** | `veth0` |
| **Mode** | `🔵 Simulation — degraded_fiber` |
| **Labels** | `network` `dco` `physical-layer` `automated` `sev-sev-3` `l1-fiber` |

---

## 🟡 SLA Assessment

> **Severity: SEV-3**
> **SLA Breach in:** `120 minutes`

### Triggered Alert Rules

- ⚠️  `L1-CRC-ERRORS: RX CRC errors=15,509 (threshold=1,000)`\n- ⚠️  `L1-OPTICAL-RX-LOW: RX power=-17.891 dBm (threshold=-17.0 dBm)`\n- ⚠️  `L3-HIGH-LATENCY: avg=85.32ms (threshold=50.0ms)`\n

---

## 🔬 Root Cause Analysis (RCA)

```
LAYER 1 PHYSICAL SIGNAL DEGRADATION — 15,509 RX CRC errors detected. CRC errors on fiber links typically indicate dirty or contaminated LC/UPC ferrules, exceeding fiber bend radius limits, or a marginal SFP+ transceiver.

OPTICAL POWER BUDGET EXCEEDED — Received optical power is -17.891 dBm, below the minimum acceptable threshold of -17.0 dBm. Possible causes: excessive fiber attenuation, dirty ferrules, bad fiber splice, or dying SFP+ laser diode.
```

---

## 📡 OSI Layer 1 — Physical Layer Diagnostics

| Metric | Value | Status |
|---|---|---|
| **Link State** | `UP` | ✅ |
| **Operational State** | `up` | ✅ |
| **Speed** | `10000 Mbps` | ✅ |
| **Duplex** | `full` | ✅ |
| **Media Type** | `Fiber (SFP+)` | ℹ️  |
| **MTU** | `9000 bytes` | ℹ️  |
| **RX CRC Errors** | `15,509` | 🔴 CRITICAL |
| **TX CRC Errors** | `1` | ✅ |
| **RX Dropped** | `306` | 🟡 |
| **TX Dropped** | `0` | ✅ |
| **RX Bytes** | `2,688,389` | ℹ️  |
| **TX Bytes** | `2,056,787` | ℹ️  |
| **Transceiver Present** | `Yes` | ✅ |
| **Optical RX Power** | `-17.891 dBm` | 🔴 BELOW THRESHOLD |
| **Optical TX Power** | `-2.15 dBm` | ℹ️  |

---

## 🔗 OSI Layer 2 — Data Link Layer Diagnostics

| Metric | Value | Status |
|---|---|---|
| **MAC Address** | `0a:dc:00:f1:be:01` | ℹ️  |
| **VLAN ID** | `42` | ℹ️  |
| **ARP Neighbor State** | `STALE` | 🟡 |
| **ARP Neighbor MAC** | `0a:dc:00:f1:be:02` | ℹ️  |
| **Interface Flags** | `BROADCAST, MULTICAST, UP` | ✅ |

---

## 🌐 OSI Layer 3 — Network Layer Diagnostics

| Metric | Value | Status |
|---|---|---|
| **Target IP** | `10.200.1.2` | ℹ️  |
| **Packets Sent** | `20` | ℹ️  |
| **Packets Received** | `17` | ℹ️  |
| **Packet Loss** | `15.0%` | 🟡 WARNING |
| **RTT Min** | `75.511 ms` | ℹ️  |
| **RTT Average** | `85.32 ms` | 🟡 |
| **RTT Max** | `137.764 ms` | ℹ️  |
| **RTT Mdev** | `18.157 ms` | ℹ️  |
| **DNS Hostname** | `ec2.internal` | ✅ |
| **DNS Resolved IP** | `10.200.1.2` | ℹ️  |
| **DNS Latency** | `1.144 ms` | ℹ️  |
| **Route Next-Hop** | `10.200.1.1` | ✅ |
| **TTL** | `64` | ℹ️  |

---

## 🛠️ Physical Remediation Steps (DCO Field Technician)

> **SLA Timer:** Resolve within **120 minutes** from ticket creation.

1. 🔬 STEP A — Inspect LC/UPC fiber connector ferrules with a fiber endface inspection scope (e.g. JDSU FBP-SD15 or Fluke FI-500 FiberInspector). Contaminated ferrules show as dark spots in the core region.\n2. 🧹 STEP B — Clean LC/UPC ferrules using a one-click fiber optic cleaner (e.g. Fujikura CLC-22). Clean both the patch cable and the SFP+ transceiver ferrule. NEVER blow with breath (moisture causes contamination).\n3. 📡 STEP C — After cleaning, re-measure optical RX power with `ethtool -m <iface>`. Target RX power range: -3.0 dBm to -13.0 dBm (current: -17.891 dBm).\n4. 🔭 STEP D — Use an optical power meter (e.g. EXFO PPM-350B) at the far end to measure insertion loss of the fiber run. Per-connector loss should be < 0.5 dB; total run loss < 3.5 dB for OM4 MMF.\n5. 🔁 STEP E — If optical loss is within budget, replace the SFP+ transceiver module. Use OEM-compatible modules meeting enterprise network specs (e.g. Finisar FTLX8571D3BCL for 10GBase-SR).\n

### Post-Remediation Verification Checklist

- [ ] `ip link show veth0` → shows `state UP` and `LOWER_UP`
- [ ] `ethtool veth0` → shows `Link detected: yes` and correct speed/duplex
- [ ] `ethtool -m veth0` → optical RX power within -3 to -13 dBm (if fiber)
- [ ] `ping -c 50 -I veth0 10.200.1.2` → 0% packet loss
- [ ] `ip -s link show veth0` → RX CRC errors not incrementing
- [ ] Network monitoring telemetry → `NetworkCRCErrors` returning to baseline
- [ ] Notify on-call NOC lead and update Jira ticket status to **RESOLVED**

---

## 📊 Diagnostic Summary

```
Report ID  : 09FE5989
Timestamp  : 2026-11-14T09:19:50.275636Z
Interface  : veth0
Scenario   : degraded_fiber
Severity   : SEV-3
Ticket ID  : DCO-NET-38657
Mode       : simulate
```

---

*Generated automatically by `net_diag_ticket.py v2.0` — Network Diagnostics & SLA Toolkit*
*Do not edit manually — re-run diagnostic tool for updated telemetry*
