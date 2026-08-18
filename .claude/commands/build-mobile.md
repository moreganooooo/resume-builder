# Build Mobile Binaries Command

Cross-compiles static, zero-dependency Go Charm TUI binaries for Android (Termux) and cross-platform targets.

## Steps to Execute:
1. Run the cross-compilation script:
   ```bash
   ./scripts/build_mobile.sh
   ```
2. Verify binaries generated in `dist/mobile/`:
   - `dashboard-linux-arm64` (Android / Termux 64-bit)
   - `dashboard-linux-arm` (Android / Raspberry Pi 32-bit)
   - `dashboard-linux-amd64` (Linux x86_64)
   - `dashboard-darwin-arm64` (macOS Apple Silicon)
   - `dashboard-darwin-amd64` (macOS Intel)
