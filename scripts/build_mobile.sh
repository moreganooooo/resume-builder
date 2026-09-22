#!/usr/bin/env bash
# ==============================================================================
# build_mobile.sh — Cross-compiles Charm TUI Go binaries for Android / Termux
# and multiple architectures.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DASHBOARD_DIR="${PROJECT_ROOT}/dashboard"
DIST_DIR="${PROJECT_ROOT}/dist/mobile"

mkdir -p "${DIST_DIR}"

# ------------------------------------------------------------------------------
# Presentation
#
# This script sits next to a TUI that is styled to the last glyph and had no
# styling of its own. Gum is the sanctioned way to give a shell script the same
# look, so it is used when it is present -- and only when it is present. Gum is
# not a dependency of this project and is not installed on every machine that
# can cross-compile Go, so every helper below falls back to a plain `echo`,
# exactly like scripts/dashboard.py falling back when Go is missing. A build
# script that refuses to build because a cosmetic tool is absent would be a
# worse script than the unstyled one it replaced.
#
# The hex values are this project's palette, kept here as literals because a
# bash script cannot import dashboard/internal/theme. Their source of truth is
# scripts/theme.py (BRAND, SUCCESS, MUTED); change them there first.
# ------------------------------------------------------------------------------
BRAND="#a47bff"
SUCCESS="#9ab63f"
MUTED="#A3A3A3"

if command -v gum >/dev/null 2>&1; then
  HAVE_GUM=1
else
  HAVE_GUM=0
fi

ui_header() {
  if [[ "${HAVE_GUM}" == "1" ]]; then
    gum style --border rounded --border-foreground "${BRAND}" \
      --foreground "${BRAND}" --padding "0 2" --margin "1 0" "$1"
  else
    echo "✦ $1 ✧"
  fi
}

ui_note() {
  if [[ "${HAVE_GUM}" == "1" ]]; then
    gum style --foreground "${MUTED}" "  $1"
  else
    echo "  $1"
  fi
}

ui_ok() {
  if [[ "${HAVE_GUM}" == "1" ]]; then
    gum style --foreground "${SUCCESS}" "     ✔ $1"
  else
    echo "     ✔ $1"
  fi
}

# ui_run keeps the command's own exit status, so `set -e` still stops the
# build on a failed compile whether or not gum is doing the waiting.
ui_run() {
  local title="$1"
  shift
  if [[ "${HAVE_GUM}" == "1" ]]; then
    gum spin --spinner dot --title "${title}" --show-error -- "$@"
  else
    echo "  ⚒ ${title}"
    "$@"
  fi
}

ui_header "Building Charm TUI Binaries for Mobile & Cross-Platform Deployments"
ui_note "Source directory: ${DASHBOARD_DIR}"
ui_note "Output directory: ${DIST_DIR}"
if [[ "${HAVE_GUM}" == "0" ]]; then
  ui_note "(install charmbracelet/gum for styled output -- optional)"
fi
echo ""

TARGETS=(
  "linux/arm64/dashboard-linux-arm64 (Android / Termux 64-bit)"
  "linux/arm/dashboard-linux-arm (Android / Raspberry Pi 32-bit)"
  "linux/amd64/dashboard-linux-amd64 (Linux x86_64)"
  "darwin/arm64/dashboard-darwin-arm64 (macOS Apple Silicon)"
  "darwin/amd64/dashboard-darwin-amd64 (macOS Intel)"
)

cd "${DASHBOARD_DIR}"

# Build dashboard and helper binaries
for target in "${TARGETS[@]}"; do
  os_arch="${target%%/*}"
  rest="${target#*/}"
  arch="${rest%%/*}"
  rest2="${rest#*/}"
  binary_name="${rest2%% *}"
  desc="${target#* (}"
  desc="${desc%)}"

  # Strip debug symbols (-s -w) for smallest binary size. The environment is
  # set through `env` rather than as a prefix, because ui_run is a shell
  # function and a variable prefix on a function call does not reliably stay
  # scoped to it.
  ui_run "Compiling for ${os_arch}/${arch} [${desc}]" \
    env CGO_ENABLED=0 GOOS="${os_arch}" GOARCH="${arch}" \
    go build -ldflags="-s -w" -o "${DIST_DIR}/${binary_name}" .

  # Build prompt utility
  ui_run "Compiling prompt for ${os_arch}/${arch}" \
    env CGO_ENABLED=0 GOOS="${os_arch}" GOARCH="${arch}" \
    go build -ldflags="-s -w" -o "${DIST_DIR}/prompt-${os_arch}-${arch}" ./cmd/prompt

  size=$(ls -lh "${DIST_DIR}/${binary_name}" | awk '{print $5}')
  ui_ok "Generated ${binary_name} (${size})"
done

echo ""
ui_header "Build Complete! All binaries ready in ${DIST_DIR}"
echo "To run on Android (Termux):"
echo "  1. Copy dist/mobile/dashboard-linux-arm64 to your Android device."
echo "  2. In Termux, run: chmod +x dashboard-linux-arm64"
echo "  3. Execute: ./dashboard-linux-arm64"
echo "=============================================================================="
