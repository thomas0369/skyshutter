#!/usr/bin/env bash
# check-secrets: fail if tracked content carries real rig identifiers.
#
# The measured values (AP SSID with serial derivative, AP PSK, rig MACs)
# live in docs/secrets.local.md -- gitignored, like *.pcap. This guard is
# the net that catches a slip BEFORE it is committed or pushed (release
# plan R5). Exit 0 = clean, 1 = leak found (paths printed).
set -uo pipefail
cd "$(dirname "$0")/.."

PATTERNS_FILE="tools/secret-patterns.txt"
[ -r "$PATTERNS_FILE" ] || { echo "check-secrets: $PATTERNS_FILE fehlt"; exit 2; }

status=0
while IFS= read -r pat; do
  case "$pat" in ""|\#*) continue ;; esac
  hits=$(git grep -n -I -e "$pat" -- ':!docs/release-plan.md' ':!tools/secret-patterns.txt' 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "LECK für Muster '$pat':"
    echo "$hits"
    status=1
  fi
done < "$PATTERNS_FILE"

if [ "$status" -eq 0 ]; then
  echo "check-secrets: sauber ($(git rev-parse --short HEAD))"
fi
exit $status
