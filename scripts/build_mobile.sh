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

echo "✦ Building Charm TUI Binaries for Mobile & Cross-Platform Deployments ✧"
echo "  Source directory: ${DASHBOARD_DIR}"
echo "  Output directory: ${DIST_DIR}"
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

  echo "  ⚒ Compiling for ${os_arch}/${arch} [${desc}]..."

  # Strip debug symbols (-s -w) for smallest binary size
  CGO_ENABLED=0 GOOS="${os_arch}" GOARCH="${arch}" go build -ldflags="-s -w" -o "${DIST_DIR}/${binary_name}" .

  # Build prompt utility
  CGO_ENABLED=0 GOOS="${os_arch}" GOARCH="${arch}" go build -ldflags="-s -w" -o "${DIST_DIR}/prompt-${os_arch}-${arch}" ./cmd/prompt

  size=$(ls -lh "${DIST_DIR}/${binary_name}" | awk '{print $5}')
  echo "     ✔ Generated ${binary_name} (${size})"
done

echo ""
echo "=============================================================================="
echo "✦ Build Complete! All binaries ready in ${DIST_DIR} ✧"
echo "=============================================================================="
echo "To run on Android (Termux):"
echo "  1. Copy dist/mobile/dashboard-linux-arm64 to your Android device."
echo "  2. In Termux, run: chmod +x dashboard-linux-arm64"
echo "  3. Execute: ./dashboard-linux-arm64"
echo "=============================================================================="
