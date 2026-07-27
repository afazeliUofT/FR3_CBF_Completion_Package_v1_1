#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DIRECTORY_URL='https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/19.04.00_60/'
PDF_URL='https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/19.04.00_60/tr_138901v190400p.pdf'
OUT='data/external/etsi/tr_138901v190400p.pdf'
EXPECTED_BYTES='2788641'
DOWNLOAD_ROOT='/mnt/c/Users/alifa/Downloads'

mkdir -p "$(dirname "$OUT")"

validate_pdf() {
  local path="$1"
  [[ -f "$path" ]] || return 1
  [[ "$(stat -c '%s' "$path")" == "$EXPECTED_BYTES" ]] || return 1
  [[ "$(head -c 4 "$path")" == '%PDF' ]] || return 1
  tail -c 2048 "$path" | grep -a -q '%%EOF' || return 1
}

copy_first_valid_download() {
  local candidate
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    echo "Checking Windows download candidate:"
    echo "  $candidate"
    if validate_pdf "$candidate"; then
      cp -p "$candidate" "$OUT"
      echo "Copied validated browser download into the repository external-data area."
      return 0
    fi
  done < <(
    find "$DOWNLOAD_ROOT" \
      -maxdepth 4 \
      -type f \
      -iname 'tr_138901v190400p*.pdf' \
      -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr \
    | cut -d' ' -f2-
  )
  return 1
}

try_http_download() {
  local temp="${OUT}.partial"
  local cookie="${OUT}.cookies"
  rm -f "$temp" "$cookie"

  set +e
  curl \
    --silent \
    --show-error \
    --location \
    --retry 3 \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 120 \
    --user-agent 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36' \
    --cookie-jar "$cookie" \
    --output /dev/null \
    "$DIRECTORY_URL"
  local directory_code=$?

  curl \
    --fail \
    --location \
    --retry 3 \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 240 \
    --compressed \
    --user-agent 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36' \
    --referer "$DIRECTORY_URL" \
    --cookie "$cookie" \
    --output "$temp" \
    "$PDF_URL"
  local pdf_code=$?
  set -e

  echo "ETSI directory-request exit code: $directory_code"
  echo "ETSI PDF-request exit code: $pdf_code"

  if [[ "$pdf_code" -eq 0 ]] && validate_pdf "$temp"; then
    mv "$temp" "$OUT"
    rm -f "$cookie"
    echo "ETSI PDF acquired through the browser-like HTTP session."
    return 0
  fi

  rm -f "$temp" "$cookie"
  return 1
}

echo "================================================================="
echo "OFFICIAL ETSI TR 138 901 V19.4.0 SOURCE ACQUISITION"
echo "================================================================="
echo "Expected PDF bytes: $EXPECTED_BYTES"
echo "Destination: $ROOT/$OUT"

if validate_pdf "$OUT"; then
  echo "ETSI TR 138 901 V19.4.0 PDF: VALID EXISTING REPOSITORY COPY"
elif copy_first_valid_download; then
  echo "ETSI TR 138 901 V19.4.0 PDF: VALID WINDOWS DOWNLOAD COPY"
elif try_http_download; then
  echo "ETSI TR 138 901 V19.4.0 PDF: AUTOMATED DOWNLOAD PASS"
else
  echo
  echo "The official ETSI server rejected automated download."
  echo "A browser download is now required; this remains inside the same drop-in."
  echo
  echo "The browser will open the official ETSI directory and PDF."
  echo "Download the file named:"
  echo "  tr_138901v190400p.pdf"
  echo "to your normal Windows Downloads folder."

  if command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$DIRECTORY_URL" >/dev/null 2>&1 || true
    sleep 2
    cmd.exe /c start "" "$PDF_URL" >/dev/null 2>&1 || true
  else
    echo "ERROR: Windows browser launcher cmd.exe is unavailable."
    echo "Open the official ETSI 19.04.00_60 directory manually."
  fi

  while true; do
    echo
    read -r -p \
      "After the official PDF has downloaded, press Enter to continue (or type STOP): " \
      response
    if [[ "$response" == "STOP" ]]; then
      echo "ETSI source acquisition stopped by the user."
      exit 20
    fi
    if copy_first_valid_download; then
      break
    fi
    echo
    echo "No valid 2,788,641-byte ETSI PDF was found under:"
    echo "  $DOWNLOAD_ROOT"
    echo "Keep the browser download filename close to tr_138901v190400p.pdf."
  done
fi

validate_pdf "$OUT" || {
  echo "ERROR: final ETSI PDF validation failed"
  exit 21
}

echo
echo "ETSI TR 138 901 V19.4.0 PDF SOURCE: PASS"
echo "Bytes: $(stat -c '%s' "$OUT")"
echo "SHA-256:"
sha256sum "$OUT"
echo "Local path: $ROOT/$OUT"
echo "WRAPPER 20 ETSI SOURCE: PASS"
