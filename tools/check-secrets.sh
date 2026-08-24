#!/usr/bin/env bash
# check-secrets: fail if tracked content carries real rig identifiers.
#
# The pattern list lives in .secret-patterns (gitignored -- the patterns ARE
# the secrets, so they must never be committed; the committed template
# tools/secret-patterns.example.txt documents the format). The measured
# values also live in docs/secrets.local.md. Exit 0 = clean, 1 = leak.
set -uo pipefail
cd "$(dirname "$0")/.."

PATTERNS_FILE=".secret-patterns"
TEMPLATE="tools/secret-patterns.example.txt"
# The pattern list is gitignored BY DESIGN (the patterns ARE the secrets).
# A fresh checkout -- like CI -- simply has no rig secrets to guard; that is
# not an error. The template documents how to add them locally.
if [ ! -r "$PATTERNS_FILE" ]; then
  echo "check-secrets: keine Muster-Datei ($PATTERNS_FILE) -- nichts zu pruefen (Vorlage: $TEMPLATE)"
  exit 0
fi

status=0
while IFS= read -r pat; do
  case "$pat" in ""|\#*) continue ;; esac
  hits=$(git grep -n -I -e "$pat" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "LECK fuer Muster '$pat':"
    echo "$hits"
    status=1
  fi
done < "$PATTERNS_FILE"

if [ "$status" -eq 0 ]; then
  echo "check-secrets: sauber ($(git rev-parse --short HEAD))"
fi
exit $status
