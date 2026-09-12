#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -ne 9 ]]; then
  echo "Interner Fehler: Es wurden $# statt 9 Action-Argumente übergeben." >&2
  exit 2
fi

csv=$1
banner=$2
logos=$3
output=$4
qr_text=$5
qr_label=$6
no_qr=$7
no_rotate_back=$8
fo=$9

set -- "$csv" --banner "$banner" --logos "$logos" --output "$output" --qr-label "$qr_label"

if [[ -n "$qr_text" ]]; then
  set -- "$@" --qr-text "$qr_text"
fi
if [[ "$no_qr" == "true" ]]; then
  set -- "$@" --no-qr
fi
if [[ "$no_rotate_back" == "true" ]]; then
  set -- "$@" --no-rotate-back
fi
if [[ -n "$fo" ]]; then
  set -- "$@" --fo "$fo"
fi

python /action/namensschilder.py "$@"

# Relative paths remain valid for subsequent host-side actions.
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "pdf=$output" >> "$GITHUB_OUTPUT"
fi
