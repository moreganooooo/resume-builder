# 📱 Mobile Transposition & Desktop-Sync Deployment Blueprint

This document details the unified architectural design, deployment roadmap, and automated installation scripts to support running the `resume-builder` codebase across both **Desktop environments** (macOS/Linux/WSL) and **Mobile devices** (Google Pixel 10 running Linux via Termux).

---

## 🎨 1. Mobile-Transposed User Experience & Constraints

Applying the `/transpose` and `/distill` design paradigms, we optimize the command-line user interface to maintain elite visual fidelity and zero-friction execution when running in a high-density, touch-centric mobile terminal interface.

```
+--------------------------------------------------------+
| ✦ 💎 RESUME BUILDER │ SETTINGS ✦                      |  <-- Banner automatically
|                                                        |      collapses into compact
| How would you like to proceed?                         |      mode to fit mobile screen
| > [Recommended] Sync JDs from Desktop                  |
|   ↳ Run Doctor Checks                                  |
|   ↳ Manage Scraping & Keywords                         |
|   Back                                                 |
|                                                        |
+--------------------------------------------------------+
| [ ↑↓ / JK ] navigate  [ ENTER ] select  [ CTRL+C ] exit |  <-- Bottom-docked commands
+--------------------------------------------------------+
| q  w  e  r  t  y  u  i  o  p                           |
|  a  s  d  f  g  h  j  k  l                             |  <-- Mobile Gboard covers
|   z  x  c  v  b  n  m  [del]                           |      50% of the screen
+--------------------------------------------------------+
```

### 🧠 Mobile Interaction & UI Adaptations

1. **Virtual Keyboard Clearance (`rows >= 24`):**
   * *The Problem:* Gboard or SwiftKey consumes 50% of mobile viewports, leaving as few as 12 vertical lines.
   * *The Adaptation:* The program dynamically detects terminal size. On screens under 24 rows, banners automatically collapse into single-line high-contrast gradient formats, preserving full menu item scanning.
2. **Built-in Interactive TUI File Browser:**
   * *The Problem:* Typing directory paths on a mobile virtual keyboard is slow, error-prone, and frustrating.
   * *The Adaptation:* The fallback onboarding wizard utilizes our **Unified File Picker**. Dom can navigate directories (`📁 folder/`) and select documents (`📄 file.pdf`) using simple touch gestures or arrow tapping—making manual file-path typing completely obsolete.
3. **Native PDF Viewer Integration:**
   * *The Problem:* Standard mobile terminals cannot render heavy binary files like PDFs.
   * *The Adaptation:* Once compiled, the program triggers `termux-open <file.pdf>`, which tells the Android OS to slide up his native Google Drive PDF Reader or Adobe Acrobat viewer instantly with high-fidelity formatting.

---

## 📡 2. Decentralized Syncthing Desktop-Sync Architecture

To eliminate file storage bloat and bypass compiling heavy WebKit or Playwright browser instances on his phone, the system uses a **decentralized, peer-to-peer sync engine**.

```mermaid
graph TD
    subgraph Google Pixel 10 (15MB Client)
        A["Termux TUI Engine"] -->|Saves tailored data| B["tailored_resume.json (Text state)"]
        H["Android PDF Viewer"] <---|Instant Sync| G["MorganEscott_Resume.pdf"]
    end

    B -->|Encrypted TLS Sync| C["Desktop profiles/ Folder"]

    subgraph Desktop (Mac/PC Compiler)
        C --> D["Desktop Watcher Daemon"]
        D -->|Compiles HTML to PDF| E["Playwright PDF Compiler"]
        E -->|Writes file| G
    end
```

### The Sync Specs
Syncthing runs encrypted, device-to-device file transfers. It synchronizes **only the four operational directories** of the active profile, keeping compiled code on standard git tracking:

| Synced Directory | Path | Purpose | Size |
| :--- | :--- | :--- | :--- |
| **Profile Config** | `profiles/<name>/` | Syncs target roles, `.env` (Gemini API keys), search parameters, and handwritten signatures. | **~100 KB** |
| **Scanned JDs** | `jds/<name>/` | Syncs active job description raw texts, triage queue listings, and application trackers. | **~2 MB** |
| **Rendered Outputs** | `output/<name>/` | Syncs tailored JSON state outputs and fully rendered, high-resolution PDFs. | **~5 MB** |
| **Operational Tracker** | `data/<name>/` | Syncs local SQLite database (`data.db`), CSV application checkpoints, and pipeline history. | **~10 KB** |

* **Total Synchronization Footprint:** **< 10 MB** (Almost instantaneous, sub-second sync speeds even on spotty cellular connections).

### Syncthing Ignore Patterns (`.stignore`) & WAL Safety
To prevent synchronization collisions and database corruption across distributed nodes, `.stignore` must strictly ignore SQLite journal/WAL files and transient build artifacts while syncing `data.db`:
```gitignore
// SQLite WAL & shared memory temporary files
(?d)*.db-wal
(?d)*.db-shm
(?d)*.db-journal

// Transient Python & Node caches
(?d)__pycache__
(?d)*.pyc
(?d).pytest_cache
(?d)node_modules

// Temporary render files
(?d)output/*/tmp/
(?d).DS_Store
```
> [!IMPORTANT]
> **WAL Flushes Before Sync:** Because `*-wal` files are ignored, `db.checkpoint(profile)` is called to flush all SQLite writes directly into `data.db` prior to file transfer triggers.

---

## 🛠️ 3. The Unified Setup Installer & Termux Automation Scripts

We provide dedicated cross-platform installers and maintenance utilities:

1. **[`scripts/install.sh`](file:///Users/morganescott/resume-builder/scripts/install.sh)**: Multi-platform interactive installer (macOS, Linux, WSL, Android Termux).
2. **[`scripts/termux_install.sh`](file:///Users/morganescott/resume-builder/scripts/termux_install.sh)**: Fully automated, non-interactive one-command bootstrapper optimized for mobile touch terminals.
3. **[`scripts/termux_update.sh`](file:///Users/morganescott/resume-builder/scripts/termux_update.sh)**: One-command repository sync, virtualenv re-hash, and health check runner for mobile.
4. **[`scripts/verify_syncthing.py`](file:///Users/morganescott/resume-builder/scripts/verify_syncthing.py)** (`resume verify-sync`): Verifies directory pairing, `.stignore` rules, WAL flush state, and local Syncthing connectivity.

---

## 📱 4. Step-by-Step Mobile Deployment Plan

If setting up on an Android device (e.g., Google Pixel 10):

### Step A: Provision Android Linux Environment
1. Download and launch **Termux** (recommended from F-Droid).
2. Run the one-command installer:
   ```bash
   pkg update && pkg upgrade -y
   pkg install python nodejs git termux-api -y
   git clone https://github.com/morganescott/resume-builder.git ~/resume-builder
   cd ~/resume-builder
   bash scripts/termux_install.sh
   ```

### Step B: Verification & Syncthing Pairing
1. Download **Syncthing** on Desktop and **Syncthing Android App** on the mobile device.
2. Pair the devices via QR code and share `profiles/`, `jds/`, `output/`, and `data/`.
3. Verify local pairing and folder permissions:
   ```bash
   resume verify-sync
   ```

### Step C: Daily Mobile Workflow & Auto-Update
- Tailor resumes and scan job boards on mobile using `resume menu` or `resume scan`.
- Keep the mobile codebase fresh with a single command:
   ```bash
   bash scripts/termux_update.sh
   ```

When a resume is tailored on mobile, the JSON state syncs back to the desktop compiler in real time, which generates the print-ready PDF and syncs it back to mobile for instant review via `termux-open`.
