# Project Nexus — Prototype Dashboard

Correlates wearable biometrics (Oura, Whoop, Apple Health) with manual
lifestyle inputs (caffeine, alcohol, social stress, light exposure) using
research-based impact window models and cross-correlation analysis.

---

## Deploy in 10 minutes (Streamlit Community Cloud)

### Step 1 — Get the code onto GitHub

1. Go to **github.com** and sign in (or create a free account).
2. Click the **+** button (top right) → **New repository**.
3. Name it `nexus-dashboard`, set it to **Public**, click **Create repository**.
4. On your computer, open **Terminal** (Mac/Linux) or **Command Prompt** (Windows).
5. Run these commands one at a time:

```bash
# Install Git if you don't have it: https://git-scm.com/downloads
git config --global user.email "your@email.com"
git config --global user.name "Your Name"

# Navigate to this folder (replace the path with wherever you saved it)
cd /path/to/nexus-deploy

# Push to GitHub
git init
git add .
git commit -m "Initial Nexus dashboard"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/nexus-dashboard.git
git push -u origin main
```

> Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username.

---

### Step 2 — Deploy on Streamlit Community Cloud

1. Go to **share.streamlit.io** and sign in with your GitHub account.
2. Click **New app**.
3. Fill in:
   - **Repository**: `YOUR_GITHUB_USERNAME/nexus-dashboard`
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. Click **Deploy**. It takes about 2 minutes.
5. You'll get a public URL like `https://your-app-name.streamlit.app`.

---

### Step 3 — Add Whoop credentials (when you have them)

1. In Streamlit Cloud, go to your app → **⋮ menu** → **Settings** → **Secrets**.
2. Paste:
   ```toml
   WHOOP_CLIENT_ID = "your_client_id_here"
   WHOOP_CLIENT_SECRET = "your_client_secret_here"
   ```
3. Click **Save**. The app restarts and pulls live Whoop data automatically.

> Apply for Whoop API access at: https://developer.whoop.com

---

## Run locally (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501 in your browser.

---

## What the dashboard shows

| Section | Description |
|---|---|
| **KPI cards** | Mean metric value, best correlation r, optimal lag, impact window length |
| **Insight card** | Plain-English summary: "Data shows X correlates with Y with a lag of Z hours" |
| **Time-series chart** | Biometric trend with context events overlaid as bars |
| **CCF chart** | Pearson r at every tested lag — peak bar is highlighted |
| **Decay curve** | The biological impact model for the selected context input |
| **Summary table** | All context inputs ranked by correlation strength against the selected metric |

## File structure

```
nexus-deploy/
├── app.py                      ← Main dashboard (Streamlit entry point)
├── requirements.txt            ← Python dependencies
├── .streamlit/
│   ├── config.toml             ← Dark theme settings
│   └── secrets.toml            ← LOCAL ONLY — not committed to GitHub
├── core/
│   └── impact_windows.py       ← Decay models (EXPONENTIAL, LINEAR, LOG, ZEITGEBER)
├── analysis/
│   └── correlator.py           ← CCF engine
└── data/
    ├── synthetic.py            ← 90-day realistic synthetic dataset
    └── whoop_client.py         ← Whoop API integration (falls back to synthetic)
```
