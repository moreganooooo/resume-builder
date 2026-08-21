# 🚀 Unified Setup & Installation Guide

Setting up your job-search pipeline should feel like magic. We have built an automated, interactive setup wizard ([`scripts/install.sh`](../scripts/install.sh)) that handles dependencies, virtual environments, shell aliases, and mobile power-user configurations in seconds.

---

## 💻 1. Desktop & Laptop Installation (macOS, Linux, WSL)

For standard laptops and desktops, this installs the full Python backend and compiles the headless browser engine used to render pixel-perfect vector PDFs.

### Prerequisites:
* Python `3.10+` installed on your system.
* Go `1.21+` (Go `1.25` recommended) for compiling native Charm TUI binaries (`dashboard/bin/dashboard` and `dashboard/bin/prompt`).
* Node.js & `npm` (for HTML/CSS PDF rendering via Playwright) or Typst CLI (for instant native vector PDF rendering).

### Automated Setup:
Simply navigate to your repository and execute our installation wizard:
```bash
./scripts/install.sh
```
Choose **`1` (Full Desktop Suite)**. The installer will:
1. Provision a clean, isolated virtual environment in `.venv/`.
2. Install all required Python packages (Pandas, Pydantic, GenAI, Rich, JobSpy, ddgs, etc.).
3. Compile Node dependencies and download Playwright's Chromium browser binary.
4. Pre-compile the Go Charm dashboard and prompt binaries for sub-millisecond keyboard reactions.
5. Register the global shell alias so you can use the `resume` command from anywhere!

### 🔑 Optional Job-Source API Keys

All of these are optional and free, and every one lives in the **active profile's** own `.env` (`profiles/<name>/.env`) — never a shared project-root file. The scanner works without any of them; each one just adds a source.

| Key | Source | What it adds |
| --- | --- | --- |
| *(none needed)* | **Indeed** (via JobSpy) | The best free source of full local job descriptions. Works out of the box. |
| *(none needed)* | **DuckDuckGo** | Backs the `scan_method: websearch` sweeps. Replaced Brave, whose free tier became metered. |
| `USAJOBS_APP_KEY` + `USAJOBS_EMAIL` | [developer.usajobs.gov](https://developer.usajobs.gov/) | Federal roles with complete descriptions. **Both are required** — USAJOBS authenticates on the registered email sent as the `User-Agent` header, so a key alone fails. |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | [developer.adzuna.com](https://developer.adzuna.com) | Broad local coverage. Descriptions are truncated to exactly 500 characters, so treat it as discovery, not tailoring input. |
| `JOOBLE_API_KEY` | [jooble.org/api/about](https://jooble.org/api/about) | Local aggregation. Descriptions are ~275-character teasers; discovery only. |
| `BRAVE_API_KEY` | [api.search.brave.com](https://api.search.brave.com) | Optional. If set, the websearch sweeps use Brave instead of DuckDuckGo. |

```bash
# Example — add to profiles/<your-profile>/.env
echo 'USAJOBS_APP_KEY=your-key' >> profiles/Morgan/.env
echo 'USAJOBS_EMAIL=you@example.com' >> profiles/Morgan/.env
```

> **Note:** `.env` is gitignored but is deliberately **not** excluded from Syncthing, so a second machine picks up your keys without you retyping them. See the Multi-Device section below.

### 📍 Setting Your Location & Commute Radius

Distance filtering is **off until you configure it**. From the main menu, choose **Settings & Upkeep → Location & Commute Radius**, then set:

* **Origin** — a ZIP code (most precise) or a city and state. Validated against the offline index as you enter it, so an unresolvable origin is rejected immediately rather than silently disabling every later distance check.
* **Radius** — 5, 10, 15, 20, or 25 miles. This is straight-line distance; a real drive in a US metro runs roughly 1.2–1.4× that, so 25 miles is about a 30-mile commute.
* **Workplace types** — a checkbox, so you can combine them. Selecting Remote + On-site (but not Hybrid) is a real, common answer that a single-choice setting cannot express.

Turning this on also relaxes the keyword filter that otherwise rejects every "Onsite"/"Hybrid" posting outright — the same switch does both, so they can never disagree.

### Post-Install Verification:
Run the self-healing diagnostic suite to verify all tools, fonts, keys, and test suites:
```bash
resume doctor
```

### Environment Customization Flags:
You can configure UI accessibility and aesthetics in your shell rc file (`~/.zshrc` or `~/.bashrc`):
```bash
# Fallback to standard Unicode symbols if your terminal lacks Nerd Fonts
export RESUME_BUILDER_ICONS=unicode

# Disable spring micro-animations for motion/vestibular sensitivities
export RESUME_BUILDER_MOTION=reduced

# Force dark or light mode theme
export RESUME_BUILDER_THEME=dark
```

---

## 📱 2. Mobile Linux Installation (Android Termux)

Run your career operations directly from your pocket! To avoid mobile storage bloat, we built a highly distilled **Mobile-Lite Mode** that compiles down to **just ~15 MB**.

### Prerequisites:
1. Download **Termux** on your phone (F-Droid release recommended).
2. Upgrade packages and install requirements:
   ```bash
   pkg update && pkg upgrade -y
   pkg install python nodejs git termux-api -y
   ```

### Automated Setup:
Clone the repository and run our installer directly inside Termux:
```bash
git clone https://github.com/morganescott/resume-builder.git
cd resume-builder
./scripts/install.sh
```
1. Choose **`1` (Mobile Lite Mode)**. This skips downloading heavy compiled binaries (Pandas/NumPy) and browser engines, keeping your virtual environment exceptionally tiny and fast!
2. Press **`Y`** to apply the **Linux Mobile Power-User Optimizations**. The script will automatically:
   * ✨ Download and configure **Fira Code Nerd Fonts** (making all sparkles and icons render beautifully).
   * 🎨 Inject a gorgeous, dark **Catppuccin Macchiato** TrueColor theme.
   * 📋 Configure the **Termux:API** clipboard integration.
   * ⌨️ Install specialized touch keys (ESC, CTRL, Arrow keys) right above your keyboard.
   * 🚀 Build a One-Tap Home Screen Launcher script.

3. To place the launcher button on your phone's Home Screen, install **Termux:Widget** from F-Droid, long-press your home screen, add the widget, and select **`ResumeBuilder`**!

---

## 📡 3. Setting Up Multi-Device Syncthing Sync

By utilizing direct device-to-device encrypted synchronization, your profiles, API keys, JDs, and output resumes sync continuously in the background without needing a public cloud or a third-party server.

```mermaid
graph LR
    A["Pixel 10 Client (~15MB)"] <===>|Direct Encrypted Sync| B["Desktop Compiler"]
```

### Folder Sharing Guide:
1. Download and run **Syncthing** on your Desktop, and the **Syncthing App** on your phone.
2. Pair the devices securely via QR code.
3. Share the four operational folders of your active profile from your Desktop, and map them in Termux on your phone:
   * `profiles/morgan/` (Syncs your `.env` API keys, customized search queries, and signatures)
   * `jds/morgan/` (Syncs scanned job postings and tracking lists)
   * `output/morgan/` (Syncs resume text states and compiled PDFs)
   * `data/morgan/` (Syncs application statistics and history tables)

Now, whenever you run a scan or tailor on your phone, the state JSON instantly syncs back to your desktop, which compiles the high-res PDF and syncs it right back to your phone's Google PDF viewer inside of a single second!
