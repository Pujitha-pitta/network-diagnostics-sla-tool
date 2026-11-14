#!/usr/bin/env python3
"""
test_net_diag.py
================
Comprehensive unittest suite for net_diag_ticket.py

Tests all three simulation scenarios, SLA severity assignment,
Layer 1-3 diagnostic values, and report file generation.

Run:
    python3 -m unittest discover -s tests
    python3 -m unittest tests.test_net_diag -v
"""

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Path setup: allow import of src/ from project root ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from net_diag_ticket import (
    # Data models
    Layer1Diagnostics,
    Layer2Diagnostics,
    Layer3Diagnostics,
    SLAEvaluation,
    DiagnosticReport,

    # Simulation functions
    simulate_degraded_fiber,
    simulate_link_down,
    simulate_healthy,

    # SLA engine
    evaluate_sla,
    THRESHOLDS,

    # Report generators
    generate_markdown_ticket,
    generate_json_payload,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared fixtures
# ═══════════════════════════════════════════════════════════════════════════════

IFACE     = "veth0"
TARGET_IP = "10.200.1.2"
SEED      = 42   # Fixed seed for reproducible jitter values


def seeded_report(fn, iface=IFACE, target_ip=TARGET_IP):
    """Run a simulation function with a fixed random seed."""
    random.seed(SEED)
    return fn(iface, target_ip)


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Scenario: degraded_fiber
# ═══════════════════════════════════════════════════════════════════════════════

class TestDegradedFiberScenario(unittest.TestCase):
    """Tests for the 'degraded_fiber' simulation scenario."""

    def setUp(self):
        self.report = seeded_report(simulate_degraded_fiber)

    # ── Layer 1 assertions ────────────────────────────────────────────────────
    def test_l1_link_state_is_up(self):
        """Degraded fiber: physical link must still report UP."""
        self.assertEqual(self.report.layer1.link_state, "UP",
                         "Link should remain UP — only signal quality is degraded")

    def test_l1_operational_state_is_up(self):
        self.assertEqual(self.report.layer1.operational_state, "up")

    def test_l1_speed_is_10g(self):
        """SFP+ fiber link should be 10 Gbps."""
        self.assertEqual(self.report.layer1.speed_mbps, 10000)

    def test_l1_duplex_is_full(self):
        self.assertEqual(self.report.layer1.duplex, "full")

    def test_l1_rx_crc_errors_above_threshold(self):
        """Degraded fiber MUST have RX CRC errors above the SEV-3 threshold."""
        self.assertGreater(self.report.layer1.rx_crc_errors,
                           THRESHOLDS["crc_error_threshold"],
                           f"Expected RX CRC > {THRESHOLDS['crc_error_threshold']:,}")

    def test_l1_optical_rx_power_is_present(self):
        """Fiber interface should report optical RX power."""
        self.assertIsNotNone(self.report.layer1.optical_rx_power_dbm)

    def test_l1_optical_rx_power_below_threshold(self):
        """RX optical power should be below the minimum acceptable level."""
        self.assertLess(self.report.layer1.optical_rx_power_dbm,
                        THRESHOLDS["optical_rx_min_dbm"],
                        f"RX power {self.report.layer1.optical_rx_power_dbm} dBm "
                        f"should be < {THRESHOLDS['optical_rx_min_dbm']} dBm")

    def test_l1_media_type_is_fiber(self):
        self.assertIn("Fiber", self.report.layer1.media_type)

    def test_l1_mtu_is_jumbo(self):
        """Fiber backbone links use jumbo frames (9000 byte MTU)."""
        self.assertEqual(self.report.layer1.mtu, 9000)

    # ── Layer 2 assertions ────────────────────────────────────────────────────
    def test_l2_arp_state_is_stale(self):
        """ARP should be STALE on a degraded (not down) link."""
        self.assertEqual(self.report.layer2.arp_neighbor_state, "STALE")

    def test_l2_mac_address_is_valid(self):
        """MAC address must be a valid 6-octet colon-separated string."""
        mac = self.report.layer2.mac_address
        parts = mac.split(":")
        self.assertEqual(len(parts), 6)
        for part in parts:
            self.assertEqual(len(part), 2)
            int(part, 16)   # Must be valid hex

    def test_l2_vlan_id_assigned(self):
        self.assertIsNotNone(self.report.layer2.vlan_id)
        self.assertEqual(self.report.layer2.vlan_id, 42)

    def test_l2_up_flag_present(self):
        self.assertIn("UP", self.report.layer2.interface_flags)

    # ── Layer 3 assertions ────────────────────────────────────────────────────
    def test_l3_packet_loss_is_15_percent(self):
        self.assertAlmostEqual(self.report.layer3.packet_loss_pct, 15.0, places=1)

    def test_l3_avg_latency_is_elevated(self):
        """Average RTT should be in the 70-100ms band."""
        self.assertGreater(self.report.layer3.ping_avg_ms, 70.0)
        self.assertLess(self.report.layer3.ping_avg_ms, 110.0)

    def test_l3_min_latency_less_than_avg(self):
        self.assertLessEqual(self.report.layer3.ping_min_ms,
                             self.report.layer3.ping_avg_ms)

    def test_l3_max_latency_greater_than_avg(self):
        self.assertGreaterEqual(self.report.layer3.ping_max_ms,
                                self.report.layer3.ping_avg_ms)

    def test_l3_target_ip_matches(self):
        self.assertEqual(self.report.layer3.target_ip, TARGET_IP)

    def test_l3_dns_hostname_present(self):
        self.assertIsNotNone(self.report.layer3.dns_hostname)

    # ── SLA assertions ────────────────────────────────────────────────────────
    def test_sla_severity_is_sev3(self):
        """Degraded fiber MUST trigger SEV-3 severity."""
        self.assertEqual(self.report.sla.severity, "SEV-3",
                         "Degraded fiber with CRC errors and packet loss must be SEV-3")

    def test_sla_priority_is_medium(self):
        self.assertEqual(self.report.sla.jira_priority, "Medium")

    def test_sla_remediation_timer_is_120_min(self):
        self.assertEqual(self.report.sla.remediation_timer_minutes,
                         THRESHOLDS["sev3_remediation_minutes"])

    def test_sla_triggered_rules_not_empty(self):
        self.assertTrue(len(self.report.sla.triggered_rules) > 0)

    def test_sla_remediation_steps_not_empty(self):
        self.assertTrue(len(self.report.sla.remediation_steps) > 0)

    def test_sla_rca_mentions_crc(self):
        """RCA text should reference CRC errors."""
        self.assertIn("CRC", self.report.sla.root_cause_analysis.upper())

    def test_sla_ticket_id_format(self):
        """Ticket ID must follow DCO-NET-NNNNN pattern."""
        self.assertRegex(self.report.sla.jira_ticket_id, r"^DCO-NET-\d{5}$")

    def test_sla_oncall_team_assigned(self):
        self.assertIn("DCO", self.report.sla.oncall_team)

    # ── Scenario metadata ─────────────────────────────────────────────────────
    def test_report_scenario_name(self):
        self.assertEqual(self.report.scenario, "degraded_fiber")

    def test_report_mode_is_simulate(self):
        self.assertEqual(self.report.mode, "simulate")

    def test_report_interface(self):
        self.assertEqual(self.report.interface, IFACE)


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Scenario: link_down
# ═══════════════════════════════════════════════════════════════════════════════

class TestLinkDownScenario(unittest.TestCase):
    """Tests for the 'link_down' simulation scenario (unplugged cable / failed SFP+)."""

    def setUp(self):
        self.report = seeded_report(simulate_link_down)

    # ── Layer 1 assertions ────────────────────────────────────────────────────
    def test_l1_link_state_is_no_carrier(self):
        self.assertEqual(self.report.layer1.link_state, "NO-CARRIER")

    def test_l1_operational_state_is_down(self):
        self.assertEqual(self.report.layer1.operational_state, "down")

    def test_l1_speed_is_zero(self):
        """No link negotiation when cable is unplugged."""
        self.assertEqual(self.report.layer1.speed_mbps, 0)

    def test_l1_duplex_is_unknown(self):
        self.assertEqual(self.report.layer1.duplex, "unknown")

    def test_l1_no_crc_errors(self):
        """No traffic flows → no CRC errors."""
        self.assertEqual(self.report.layer1.rx_crc_errors, 0)

    def test_l1_transceiver_not_present(self):
        self.assertFalse(self.report.layer1.transceiver_present)

    def test_l1_no_optical_power(self):
        """No transceiver → optical power readings are None."""
        self.assertIsNone(self.report.layer1.optical_rx_power_dbm)
        self.assertIsNone(self.report.layer1.optical_tx_power_dbm)

    def test_l1_media_type_is_copper(self):
        self.assertEqual(self.report.layer1.media_type, "Copper")

    # ── Layer 2 assertions ────────────────────────────────────────────────────
    def test_l2_arp_state_is_failed(self):
        """ARP MUST fail when Layer 1 is down."""
        self.assertEqual(self.report.layer2.arp_neighbor_state, "FAILED")

    def test_l2_up_flag_absent(self):
        """Interface flags must NOT contain UP when link is down."""
        self.assertNotIn("UP", self.report.layer2.interface_flags)

    def test_l2_arp_mac_is_na(self):
        self.assertEqual(self.report.layer2.arp_neighbor_mac, "N/A")

    # ── Layer 3 assertions ────────────────────────────────────────────────────
    def test_l3_packet_loss_is_100_percent(self):
        """Full packet loss when layer 1 is down."""
        self.assertAlmostEqual(self.report.layer3.packet_loss_pct, 100.0)

    def test_l3_zero_packets_received(self):
        self.assertEqual(self.report.layer3.packets_received, 0)

    def test_l3_all_rtt_values_are_zero(self):
        self.assertEqual(self.report.layer3.ping_min_ms, 0.0)
        self.assertEqual(self.report.layer3.ping_avg_ms, 0.0)
        self.assertEqual(self.report.layer3.ping_max_ms, 0.0)

    def test_l3_dns_resolution_fails(self):
        """DNS cannot resolve when link is down."""
        self.assertIsNone(self.report.layer3.dns_hostname)

    def test_l3_no_route_next_hop(self):
        self.assertIsNone(self.report.layer3.route_next_hop)

    # ── SLA assertions ────────────────────────────────────────────────────────
    def test_sla_severity_is_sev2(self):
        """Link down MUST trigger SEV-2 (highest severity for physical failure)."""
        self.assertEqual(self.report.sla.severity, "SEV-2",
                         "Complete link failure must escalate to SEV-2")

    def test_sla_priority_is_high(self):
        self.assertEqual(self.report.sla.jira_priority, "High")

    def test_sla_remediation_timer_is_30_min(self):
        """SEV-2 SLA mandates 30-minute resolution target."""
        self.assertEqual(self.report.sla.remediation_timer_minutes,
                         THRESHOLDS["sev2_remediation_minutes"])

    def test_sla_rca_mentions_physical_failure(self):
        """RCA must reference physical layer concepts."""
        rca_upper = self.report.sla.root_cause_analysis.upper()
        self.assertTrue(
            any(kw in rca_upper for kw in ["PHYSICAL", "CARRIER", "CABLE", "TRANSCEIVER"]),
            "RCA should mention physical layer failure keywords"
        )

    def test_sla_l1_down_rule_triggered(self):
        """L1-LINK-DOWN rule must appear in triggered rules."""
        rules_str = " ".join(self.report.sla.triggered_rules).upper()
        self.assertIn("L1-LINK-DOWN", rules_str)

    def test_sla_remediation_contains_physical_steps(self):
        """Remediation steps should reference physical inspection."""
        steps_joined = " ".join(self.report.sla.remediation_steps).lower()
        self.assertTrue(
            any(kw in steps_joined for kw in ["cable", "patch", "sfp", "fiber", "transceiver", "inspect"]),
            "Remediation steps should reference physical layer actions"
        )

    # ── Scenario metadata ─────────────────────────────────────────────────────
    def test_report_scenario_name(self):
        self.assertEqual(self.report.scenario, "link_down")


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  Scenario: healthy
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthyScenario(unittest.TestCase):
    """Tests for the 'healthy' baseline simulation scenario."""

    def setUp(self):
        self.report = seeded_report(simulate_healthy)

    # ── Layer 1 assertions ────────────────────────────────────────────────────
    def test_l1_link_state_is_up(self):
        self.assertEqual(self.report.layer1.link_state, "UP")

    def test_l1_operational_state_is_up(self):
        self.assertEqual(self.report.layer1.operational_state, "up")

    def test_l1_speed_is_1g(self):
        self.assertEqual(self.report.layer1.speed_mbps, 1000)

    def test_l1_duplex_is_full(self):
        self.assertEqual(self.report.layer1.duplex, "full")

    def test_l1_zero_crc_errors(self):
        """Healthy interface must have ZERO CRC errors."""
        self.assertEqual(self.report.layer1.rx_crc_errors, 0)
        self.assertEqual(self.report.layer1.tx_crc_errors, 0)

    def test_l1_zero_dropped_packets(self):
        self.assertEqual(self.report.layer1.rx_dropped, 0)
        self.assertEqual(self.report.layer1.tx_dropped, 0)

    def test_l1_no_optical_data_on_copper(self):
        """Copper interface should not report optical power."""
        self.assertIsNone(self.report.layer1.optical_rx_power_dbm)

    def test_l1_mtu_is_standard(self):
        self.assertEqual(self.report.layer1.mtu, 1500)

    # ── Layer 2 assertions ────────────────────────────────────────────────────
    def test_l2_arp_state_is_reachable(self):
        """Healthy link must show ARP as REACHABLE."""
        self.assertEqual(self.report.layer2.arp_neighbor_state, "REACHABLE")

    def test_l2_up_flag_present(self):
        self.assertIn("UP", self.report.layer2.interface_flags)

    def test_l2_vlan_assigned(self):
        self.assertEqual(self.report.layer2.vlan_id, 10)

    # ── Layer 3 assertions ────────────────────────────────────────────────────
    def test_l3_zero_packet_loss(self):
        """Healthy link must have exactly 0% packet loss."""
        self.assertAlmostEqual(self.report.layer3.packet_loss_pct, 0.0)

    def test_l3_all_packets_received(self):
        self.assertEqual(self.report.layer3.packets_sent,
                         self.report.layer3.packets_received)

    def test_l3_low_latency(self):
        """Average RTT on healthy link should be < 5 ms."""
        self.assertLess(self.report.layer3.ping_avg_ms, 5.0)

    def test_l3_dns_resolves(self):
        self.assertIsNotNone(self.report.layer3.dns_hostname)

    def test_l3_ttl_is_64(self):
        self.assertEqual(self.report.layer3.ttl, 64)

    # ── SLA assertions ────────────────────────────────────────────────────────
    def test_sla_severity_is_ok(self):
        """Healthy scenario must produce OK severity (no incident)."""
        self.assertEqual(self.report.sla.severity, "OK",
                         "Healthy interface should produce OK, not an alert severity")

    def test_sla_no_remediation_timer(self):
        """No SLA breach on healthy interface."""
        self.assertEqual(self.report.sla.remediation_timer_minutes, 0)

    def test_sla_no_triggered_rules(self):
        """No alert rules should fire on a healthy interface."""
        self.assertEqual(len(self.report.sla.triggered_rules), 0)

    def test_sla_priority_is_low(self):
        self.assertEqual(self.report.sla.jira_priority, "Low")

    def test_sla_rca_mentions_nominal(self):
        """RCA on healthy interface should reference normal operation."""
        rca_lower = self.report.sla.root_cause_analysis.lower()
        self.assertTrue(
            any(kw in rca_lower for kw in ["normal", "healthy", "nominal", "no anomal"]),
            "RCA should indicate no anomalies on healthy interface"
        )

    # ── Scenario metadata ─────────────────────────────────────────────────────
    def test_report_scenario_name(self):
        self.assertEqual(self.report.scenario, "healthy")


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  SLA Engine — Direct Unit Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSLAEvaluationEngine(unittest.TestCase):
    """Tests for the evaluate_sla() function in isolation."""

    def _make_l1(self, **kwargs) -> Layer1Diagnostics:
        defaults = dict(link_state="UP", operational_state="up",
                        speed_mbps=1000, duplex="full",
                        rx_crc_errors=0, tx_crc_errors=0,
                        rx_dropped=0, tx_dropped=0,
                        optical_rx_power_dbm=None, transceiver_present=True,
                        media_type="Copper", mtu=1500)
        defaults.update(kwargs)
        return Layer1Diagnostics(**defaults)

    def _make_l2(self, **kwargs) -> Layer2Diagnostics:
        defaults = dict(mac_address="aa:bb:cc:dd:ee:ff",
                        arp_neighbor_state="REACHABLE",
                        arp_neighbor_mac="aa:bb:cc:dd:ee:00",
                        interface_flags=["UP", "BROADCAST", "MULTICAST"])
        defaults.update(kwargs)
        return Layer2Diagnostics(**defaults)

    def _make_l3(self, **kwargs) -> Layer3Diagnostics:
        defaults = dict(ping_avg_ms=0.5, packet_loss_pct=0.0,
                        packets_sent=10, packets_received=10,
                        target_ip="10.200.1.2")
        defaults.update(kwargs)
        return Layer3Diagnostics(**defaults)

    def test_healthy_produces_ok(self):
        sla = evaluate_sla(self._make_l1(), self._make_l2(), self._make_l3())
        self.assertEqual(sla.severity, "OK")

    def test_link_down_produces_sev2(self):
        l1 = self._make_l1(link_state="NO-CARRIER", operational_state="down",
                           speed_mbps=0, transceiver_present=False)
        l2 = self._make_l2(arp_neighbor_state="FAILED",
                           interface_flags=["BROADCAST", "MULTICAST"])
        l3 = self._make_l3(packet_loss_pct=100.0, packets_received=0,
                           ping_avg_ms=0.0)
        sla = evaluate_sla(l1, l2, l3)
        self.assertEqual(sla.severity, "SEV-2")

    def test_crc_errors_produce_sev3(self):
        l1 = self._make_l1(rx_crc_errors=THRESHOLDS["crc_error_threshold"] + 500)
        sla = evaluate_sla(l1, self._make_l2(), self._make_l3())
        self.assertEqual(sla.severity, "SEV-3")

    def test_low_optical_power_produces_sev3(self):
        l1 = self._make_l1(
            optical_rx_power_dbm=THRESHOLDS["optical_rx_min_dbm"] - 2.0,
            media_type="Fiber (SFP+)"
        )
        sla = evaluate_sla(l1, self._make_l2(), self._make_l3())
        self.assertEqual(sla.severity, "SEV-3")

    def test_packet_loss_above_threshold_produces_sev3(self):
        l3 = self._make_l3(packet_loss_pct=THRESHOLDS["packet_loss_sev3_pct"] + 1.0,
                           packets_received=5)
        sla = evaluate_sla(self._make_l1(), self._make_l2(), l3)
        self.assertEqual(sla.severity, "SEV-3")

    def test_link_down_overrides_sev3(self):
        """SEV-2 (link down) must override SEV-3 from other rules."""
        l1 = self._make_l1(link_state="DOWN", operational_state="down",
                           rx_crc_errors=50_000)   # Also triggers SEV-3 rule
        l2 = self._make_l2(arp_neighbor_state="FAILED",
                           interface_flags=["BROADCAST"])
        l3 = self._make_l3(packet_loss_pct=100.0, packets_received=0)
        sla = evaluate_sla(l1, l2, l3)
        self.assertEqual(sla.severity, "SEV-2",
                         "SEV-2 from link-down must dominate SEV-3 from CRC errors")

    def test_sev2_timer_is_30_minutes(self):
        l1 = self._make_l1(link_state="NO-CARRIER", operational_state="down")
        l2 = self._make_l2(arp_neighbor_state="FAILED", interface_flags=[])
        l3 = self._make_l3(packet_loss_pct=100.0, packets_received=0)
        sla = evaluate_sla(l1, l2, l3)
        self.assertEqual(sla.remediation_timer_minutes,
                         THRESHOLDS["sev2_remediation_minutes"])

    def test_sev3_timer_is_120_minutes(self):
        l1 = self._make_l1(rx_crc_errors=THRESHOLDS["crc_error_threshold"] + 1)
        sla = evaluate_sla(l1, self._make_l2(), self._make_l3())
        self.assertEqual(sla.remediation_timer_minutes,
                         THRESHOLDS["sev3_remediation_minutes"])

    def test_jira_ticket_id_format(self):
        sla = evaluate_sla(self._make_l1(), self._make_l2(), self._make_l3())
        self.assertRegex(sla.jira_ticket_id, r"^DCO-NET-\d{5}$")

    def test_ok_severity_has_zero_remediation_timer(self):
        sla = evaluate_sla(self._make_l1(), self._make_l2(), self._make_l3())
        self.assertEqual(sla.remediation_timer_minutes, 0)

    def test_high_latency_triggers_sev3_alone(self):
        """High latency alone (no other issues) should trigger SEV-3."""
        l3 = self._make_l3(ping_avg_ms=THRESHOLDS["latency_sev3_ms"] + 10.0)
        sla = evaluate_sla(self._make_l1(), self._make_l2(), l3)
        self.assertEqual(sla.severity, "SEV-3")

    def test_stale_arp_does_not_breach_sla_alone(self):
        """STALE ARP with an otherwise healthy link should not trigger a breach alone."""
        l2 = self._make_l2(arp_neighbor_state="STALE")
        sla = evaluate_sla(self._make_l1(), l2, self._make_l3())
        # STALE ARP alone doesn't trigger a rule; FAILED does
        self.assertEqual(sla.severity, "OK")

    def test_arp_failed_adds_to_rca(self):
        """FAILED ARP should be mentioned in the RCA."""
        l2 = self._make_l2(arp_neighbor_state="FAILED",
                           interface_flags=["BROADCAST"])
        l1 = self._make_l1(link_state="NO-CARRIER", operational_state="down")
        l3 = self._make_l3(packet_loss_pct=100.0, packets_received=0)
        sla = evaluate_sla(l1, l2, l3)
        self.assertIn("ARP", sla.root_cause_analysis.upper())


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  Report File Generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportFileGeneration(unittest.TestCase):
    """Tests that Markdown and JSON reports are created correctly."""

    def setUp(self):
        random.seed(SEED)
        self.tmp_dir  = Path(tempfile.mkdtemp())
        self.md_path  = self.tmp_dir / "jira_incident_ticket.md"
        self.json_path= self.tmp_dir / "jira_incident_ticket.json"

    def tearDown(self):
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _generate_all(self, report: DiagnosticReport):
        generate_markdown_ticket(report, self.md_path)
        generate_json_payload(report, self.json_path)

    # ── File existence ────────────────────────────────────────────────────────
    def test_markdown_file_created_degraded_fiber(self):
        self._generate_all(seeded_report(simulate_degraded_fiber))
        self.assertTrue(self.md_path.exists(), "Markdown ticket file must be created")

    def test_json_file_created_degraded_fiber(self):
        self._generate_all(seeded_report(simulate_degraded_fiber))
        self.assertTrue(self.json_path.exists(), "JSON payload file must be created")

    def test_markdown_file_created_link_down(self):
        self._generate_all(seeded_report(simulate_link_down))
        self.assertTrue(self.md_path.exists())

    def test_markdown_file_created_healthy(self):
        self._generate_all(seeded_report(simulate_healthy))
        self.assertTrue(self.md_path.exists())

    # ── Markdown content ──────────────────────────────────────────────────────
    def test_markdown_contains_ticket_id(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        content = self.md_path.read_text(encoding="utf-8")
        self.assertIn(report.sla.jira_ticket_id, content)

    def test_markdown_contains_severity(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        content = self.md_path.read_text(encoding="utf-8")
        self.assertIn("SEV-3", content)

    def test_markdown_contains_layer_sections(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        content = self.md_path.read_text(encoding="utf-8")
        for section_header in ["OSI Layer 1", "OSI Layer 2", "OSI Layer 3",
                                "Root Cause Analysis", "Remediation Steps"]:
            self.assertIn(section_header, content,
                          f"Markdown should contain section: '{section_header}'")

    def test_markdown_link_down_shows_no_carrier(self):
        report = seeded_report(simulate_link_down)
        self._generate_all(report)
        content = self.md_path.read_text(encoding="utf-8")
        self.assertIn("NO-CARRIER", content)

    def test_markdown_healthy_shows_ok(self):
        report = seeded_report(simulate_healthy)
        self._generate_all(report)
        content = self.md_path.read_text(encoding="utf-8")
        self.assertIn("OK", content)

    def test_markdown_contains_remediation_steps(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        content = self.md_path.read_text(encoding="utf-8")
        self.assertIn("Remediation", content)

    # ── JSON content ──────────────────────────────────────────────────────────
    def test_json_is_valid(self):
        """JSON file must be valid JSON."""
        self._generate_all(seeded_report(simulate_degraded_fiber))
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_json_contains_jira_fields(self):
        self._generate_all(seeded_report(simulate_degraded_fiber))
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        for key in ["summary", "priority", "labels", "components", "diagnostic_telemetry"]:
            self.assertIn(key, data, f"JSON must contain field: '{key}'")

    def test_json_contains_all_diagnostic_layers(self):
        self._generate_all(seeded_report(simulate_degraded_fiber))
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        tel = data["diagnostic_telemetry"]
        for layer in ["layer1_physical", "layer2_datalink", "layer3_network", "sla_evaluation"]:
            self.assertIn(layer, tel, f"diagnostic_telemetry must contain '{layer}'")

    def test_json_sla_severity_matches_report(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        json_severity = data["diagnostic_telemetry"]["sla_evaluation"]["severity"]
        self.assertEqual(json_severity, report.sla.severity)

    def test_json_link_down_severity_is_sev2(self):
        self._generate_all(seeded_report(simulate_link_down))
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["diagnostic_telemetry"]["sla_evaluation"]["severity"], "SEV-2")

    def test_json_healthy_severity_is_ok(self):
        self._generate_all(seeded_report(simulate_healthy))
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["diagnostic_telemetry"]["sla_evaluation"]["severity"], "OK")

    def test_json_layer1_crc_errors_in_degraded(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        crc = data["diagnostic_telemetry"]["layer1_physical"]["rx_crc_errors"]
        self.assertGreater(crc, THRESHOLDS["crc_error_threshold"])

    def test_json_metadata_fields(self):
        report = seeded_report(simulate_degraded_fiber)
        self._generate_all(report)
        with self.json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        meta = data["diagnostic_telemetry"]["metadata"]
        self.assertEqual(meta["interface"], IFACE)
        self.assertEqual(meta["scenario"], "degraded_fiber")
        self.assertEqual(meta["mode"], "simulate")

    # ── File size sanity ──────────────────────────────────────────────────────
    def test_markdown_file_non_empty(self):
        self._generate_all(seeded_report(simulate_degraded_fiber))
        self.assertGreater(self.md_path.stat().st_size, 1000,
                           "Markdown report should be substantial (> 1 KB)")

    def test_json_file_non_empty(self):
        self._generate_all(seeded_report(simulate_degraded_fiber))
        self.assertGreater(self.json_path.stat().st_size, 500,
                           "JSON payload should be substantial (> 500 bytes)")


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  Data Model Integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataModelIntegrity(unittest.TestCase):
    """Tests for the dataclass models."""

    def test_diagnostic_report_has_unique_report_id(self):
        """Each report must have a unique ID."""
        ids = {DiagnosticReport().report_id for _ in range(50)}
        self.assertGreater(len(ids), 1, "Report IDs should be unique across instances")

    def test_diagnostic_report_has_timestamp(self):
        r = DiagnosticReport()
        self.assertTrue(r.timestamp.endswith("Z"))

    def test_sla_evaluation_defaults(self):
        sla = SLAEvaluation()
        self.assertEqual(sla.severity, "OK")
        self.assertEqual(sla.triggered_rules, [])
        self.assertEqual(sla.remediation_steps, [])

    def test_layer1_defaults(self):
        l1 = Layer1Diagnostics()
        self.assertEqual(l1.rx_crc_errors, 0)
        self.assertIsNone(l1.optical_rx_power_dbm)

    def test_all_scenarios_produce_diagnostic_report(self):
        """All three simulators must return a DiagnosticReport instance."""
        for fn in [simulate_degraded_fiber, simulate_link_down, simulate_healthy]:
            with self.subTest(scenario=fn.__name__):
                result = seeded_report(fn)
                self.assertIsInstance(result, DiagnosticReport)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
