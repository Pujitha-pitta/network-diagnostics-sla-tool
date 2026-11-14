#!/usr/bin/env bash
# =============================================================================
# setup_veth_lab.sh — Virtual Ethernet Lab Setup
# =============================================================================
# Purpose : Create a veth pair (veth0 <-> veth1), assign IPs, inject netem
#           impairments (80 ms delay, 15% packet loss), and capture traffic.
# Usage   : sudo ./scripts/setup_veth_lab.sh [--cleanup]
# Requires: iproute2, ethtool, tc (iproute2-tc), tcpdump
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
err()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════${RESET}"; \
            echo -e "${BOLD}${CYAN}  $*${RESET}"; \
            echo -e "${BOLD}${CYAN}══════════════════════════════════════════${RESET}"; }

# ── Root privilege check ──────────────────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This script must be run as root (sudo)."
        err "Usage: sudo $0 [--cleanup]"
        exit 1
    fi
}

# ── Dependency check ──────────────────────────────────────────────────────────
check_deps() {
    local missing=()
    for cmd in ip ethtool tc tcpdump; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required tools: ${missing[*]}"
        err "Install with: apt-get install -y iproute2 ethtool tcpdump"
        exit 1
    fi
    ok "All required tools present (ip, ethtool, tc, tcpdump)"
}

# ── Cleanup / teardown ────────────────────────────────────────────────────────
cleanup_lab() {
    header "Tearing Down veth Lab"

    # Remove netem qdisc if present
    if ip link show veth0 &>/dev/null; then
        tc qdisc del dev veth0 root 2>/dev/null && info "Removed netem qdisc from veth0" || true
        tc qdisc del dev veth1 root 2>/dev/null && info "Removed netem qdisc from veth1" || true
    fi

    # Delete the veth pair (deleting one removes both)
    if ip link show veth0 &>/dev/null; then
        ip link delete veth0
        ok "Deleted veth pair (veth0 <-> veth1)"
    else
        warn "veth0 not found — lab may already be clean."
    fi

    info "Cleanup complete."
}

# ── Create and configure veth pair ───────────────────────────────────────────
create_veth_pair() {
    header "Creating Virtual Ethernet Pair"

    # Remove stale interfaces if they exist
    if ip link show veth0 &>/dev/null; then
        warn "veth0 already exists — removing stale pair first."
        ip link delete veth0 2>/dev/null || true
    fi

    ip link add veth0 type veth peer name veth1
    ok "Created veth pair: veth0 <-> veth1"

    # Assign IP addresses
    ip addr add 10.200.1.1/24 dev veth0
    ip addr add 10.200.1.2/24 dev veth1
    ok "Assigned 10.200.1.1/24 → veth0  |  10.200.1.2/24 → veth1"

    # Bring links up
    ip link set veth0 up
    ip link set veth1 up
    ok "Links brought UP"
}

# ── Verify link state ─────────────────────────────────────────────────────────
verify_links() {
    header "Verifying Link State"

    echo -e "\n${BOLD}→ ethtool veth0${RESET}"
    ethtool veth0 2>/dev/null || warn "ethtool output may be limited on veth interfaces"

    echo -e "\n${BOLD}→ ip -s link show veth0${RESET}"
    ip -s link show veth0

    echo -e "\n${BOLD}→ ip -s link show veth1${RESET}"
    ip -s link show veth1

    # Confirm operational state
    local state
    state=$(cat /sys/class/net/veth0/operstate 2>/dev/null || echo "unknown")
    if [[ "$state" == "up" ]]; then
        ok "veth0 operational state: UP ✓"
    else
        warn "veth0 operational state: $state"
    fi
}

# ── Inject netem impairments ──────────────────────────────────────────────────
inject_netem_impairments() {
    header "Injecting Network Impairments (OSI Layer 1/2 Simulation)"

    # 80 ms delay + 15% packet loss on veth0 egress
    tc qdisc add dev veth0 root netem delay 80ms loss 15%
    ok "Injected: 80 ms latency + 15% packet loss on veth0 (tc netem)"

    echo -e "\n${BOLD}→ tc qdisc show dev veth0${RESET}"
    tc qdisc show dev veth0

    info "These impairments simulate degraded fiber / faulty patch cable conditions."
}

# ── Capture ICMP traffic with tcpdump ────────────────────────────────────────
capture_icmp_traffic() {
    header "Capturing ICMP Traffic (10 Packets)"

    local pcap_file="/tmp/veth_icmp_capture.pcap"

    # Start tcpdump in background
    tcpdump -i veth1 -c 10 -w "$pcap_file" icmp &
    local tcpdump_pid=$!

    # Give tcpdump time to start
    sleep 0.5

    # Send 15 pings (accounting for 15% loss, we need enough to get 10 captured)
    info "Sending ICMP pings from 10.200.1.1 → 10.200.1.2 ..."
    ping -c 20 -W 2 -I veth0 10.200.1.2 || true

    # Wait for tcpdump to finish
    wait "$tcpdump_pid" 2>/dev/null || true

    if [[ -f "$pcap_file" ]]; then
        ok "ICMP capture saved → $pcap_file"
        info "Analysing capture with tcpdump:"
        tcpdump -r "$pcap_file" -n 2>/dev/null | head -20 || true
    else
        warn "No pcap file generated — tcpdump may not have captured packets."
    fi
}

# ── Print final lab summary ───────────────────────────────────────────────────
print_summary() {
    header "Lab Setup Complete — Summary"
    echo
    printf "  %-22s %-18s %-10s %-20s\n" "Interface" "IP Address" "State" "Applied Impairments"
    printf "  %-22s %-18s %-10s %-20s\n" "─────────" "──────────" "─────" "───────────────────"
    printf "  %-22s %-18s %-10s %-20s\n" "veth0" "10.200.1.1/24" "UP" "80ms delay, 15% loss"
    printf "  %-22s %-18s %-10s %-20s\n" "veth1" "10.200.1.2/24" "UP" "None (peer)"
    echo
    info "Run the Python diagnostic tool:"
    echo -e "  ${BOLD}python3 src/net_diag_ticket.py --interface veth0 --target-ip 10.200.1.2${RESET}"
    echo
    info "Or use simulation mode (no root required):"
    echo -e "  ${BOLD}python3 src/net_diag_ticket.py --simulate --scenario degraded_fiber${RESET}"
    echo
    info "To clean up:  ${BOLD}sudo $0 --cleanup${RESET}"
    echo
}

# ── Main entrypoint ───────────────────────────────────────────────────────────
main() {
    echo -e "\n${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║  Virtual Ethernet Lab Setup                           ║${RESET}"
    echo -e "${BOLD}${CYAN}║  OSI Layer 1-3 Network Diagnostics & SLA Toolkit     ║${RESET}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${RESET}\n"

    check_root

    if [[ "${1:-}" == "--cleanup" ]]; then
        cleanup_lab
        exit 0
    fi

    check_deps
    create_veth_pair
    verify_links
    inject_netem_impairments
    capture_icmp_traffic
    print_summary
}

main "$@"
