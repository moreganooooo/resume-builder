# 🚀 Unified Setup & Installation Guide

Setting up your job-search pipeline should feel like magic. We have built an automated, interactive setup wizard ([`scripts/install.sh`](../scripts/install.sh)) that handles dependencies, virtual environments, shell aliases, and mobile power-user configurations in seconds.

---

## 💻 1. Desktop & Laptop Installation (macOS, Linux, WSL)

For standard laptops and desktops, this installs the full Python backend and compiles the headless browser engine used to render pixel-perfect vector PDFs.

### Prerequisites:
* Python `3.10+` installed on your system.
* Node.js & `npm` (for PDF rendering via Playwright).

### Automated Setup:
Simply navigate to your repository and execute our installation wizard:
```bash
./scripts/install.sh
```
Choose **`1` (Full Desktop Suite)**. The installer will:
1. Provision a clean, isolated virtual environment in `.venv/`.
2. Install all required Python packages (Pandas, Pydantic, GenAI, Rich, etc.).
3. Compile Node dependencies and download Playwright's Chromium browser binary.
4. Register the global shell alias so you can use the `resume` command from anywhere!

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
