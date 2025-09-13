#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage:"
  echo "  $0 apply <iface> <profile.conf>"
  echo "  $0 clear <iface>"
  echo
  echo "Profiles are simple key=value configs: LOSS, DELAY_MS, JITTER_MS, RATE_KBIT (optional)"
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1"; exit 1; }
}

[[ $# -lt 2 ]] && usage

CMD="$1"
IFACE="$2"
PROFILE="${3:-}"

need tc

if [[ "$CMD" == "apply" ]]; then
  [[ -z "$PROFILE" ]] && usage
  if [[ ! -f "$PROFILE" ]]; then
    echo "Profile not found: $PROFILE"
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$PROFILE"
  echo "[netem] applying on $IFACE: loss=${LOSS:-0}% delay=${DELAY_MS:-0}ms jitter=${JITTER_MS:-0}ms rate=${RATE_KBIT:-0}kbit"
  sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
  if [[ "${RATE_KBIT:-0}" -gt 0 ]]; then
    # ограничение скорости: root HTB + класс 1:10 + дочерний netem
    sudo modprobe sch_htb sch_netem 2>/dev/null || true
    sudo tc qdisc add dev "$IFACE" root handle 1: htb default 10
    sudo tc class add dev "$IFACE" parent 1: classid 1:1  htb rate "${RATE_KBIT}kbit" ceil "${RATE_KBIT}kbit"
    sudo tc class add dev "$IFACE" parent 1:1 classid 1:10 htb rate "${RATE_KBIT}kbit" ceil "${RATE_KBIT}kbit"
    sudo tc qdisc add dev "$IFACE" parent 1:10 handle 10: netem \
      loss "${LOSS:-0}%" delay "${DELAY_MS:-0}ms" "${JITTER_MS:-0}ms"
  else
    # без ограничения скорости: netem сразу в root
    sudo modprobe sch_netem 2>/dev/null || true
    sudo tc qdisc replace dev "$IFACE" root netem \
      loss "${LOSS:-0}%" delay "${DELAY_MS:-0}ms" "${JITTER_MS:-0}ms"
  fi
  echo "[netem] applied."
elif [[ "$CMD" == "clear" ]]; then
  sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
  echo "[netem] cleared on $IFACE"
else
  usage
fi
