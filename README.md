# Strava Dashboard — Original Version

A local Streamlit dashboard that signs in to Strava through a persistent browser
profile, discovers activities, downloads available TCX exports, imports their
trackpoints into SQLite, and displays running analytics.

This README covers the **original version** in the repository root. The newer
implementations are kept separately in `version_2/` and `app_version/`.

## How it works

The normal entry point is `scripts/final_launcher.py`. One command runs the
complete pipeline:

1. Start `track_new_file.py` to watch `incoming/` for TCX files.
2. Run `discover_and_download.py` using a persistent browser session.
3. Import newly downloaded trackpoints into `strava_dashboard.db`.
4. Stop the folder watcher.
5. Start the Streamlit dashboard.

Activities entered manually on Strava may not have a TCX export. These are
recorded in the `activity_import_status` table and skipped on later runs, so a
missing export does not fail repeatedly.

## Requirements

- Windows 10 or 11 is the currently tested platform
- Python 3.10 or newer (64-bit recommended)
- Internet access
- A Strava account
- Google Chrome, or Playwright Chromium as a fallback

Do **not** download or copy somebody else's virtual environment. A Python venv
contains machine-specific executable paths and must be created locally.

## Install on Windows (PowerShell)

Clone the repository and enter its root folder:

```powershell
git clone https://github.com/leezongzhe/stravadashboard.git
cd stravadashboard
```

Create a fresh virtual environment named `SDBvenv`:

```powershell
py -m venv SDBvenv
```

If `py` is unavailable, use `python -m venv SDBvenv` instead.

Activate it and install the Python dependencies:

```powershell
.\SDBvenv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

If PowerShell prevents activation, activation is optional. Run the environment's
Python directly instead:

```powershell
.\SDBvenv\Scripts\python.exe -m pip install -r requirements.txt
.\SDBvenv\Scripts\python.exe -m playwright install chromium
```

## Run the dashboard

With the venv activated:

```powershell
python scripts\final_launcher.py
```

Without activation:

```powershell
.\SDBvenv\Scripts\python.exe scripts\final_launcher.py
```

On the first run, a browser window opens for Strava login. Complete the login
manually, including any password or two-factor-authentication prompt. The
authenticated session is stored locally in `browser_data/`; later runs reuse it.
The launcher continues automatically once it detects a successful login.

After synchronization, Streamlit normally opens the dashboard automatically. If
it does not, open the local address printed in the terminal (usually
`http://localhost:8501`). Keep the terminal open while using the dashboard and
press `Ctrl+C` to stop it.

### Retry activities without a TCX export

Unavailable/manual activities are skipped by default. To deliberately check all
of them again:

```powershell
python scripts\final_launcher.py --retry-unavailable
```

Use this option only if an activity was later updated with downloadable data.

## Project structure

```text
stravadashboard/
├── scripts/
│   ├── final_launcher.py          # Recommended entry point
│   ├── discover_and_download.py   # Login, discovery, and TCX download
│   ├── track_new_file.py          # TCX-to-SQLite importer/watcher
│   ├── dashboard.py               # Original Streamlit dashboard
│   ├── login.py                   # Legacy standalone login helper
│   ├── browser.py                 # Browser testing helper
│   └── testing_function/          # Development utilities; not required
├── incoming/                      # Downloaded TCX files (local user data)
├── browser_data/                  # Saved browser/login profile (private)
├── strava_dashboard.db            # Local SQLite activity database
├── requirements.txt
└── README.md
```

`login.py` is retained for compatibility, but ordinary users should launch
`final_launcher.py`; login handling is already integrated into its synchronization
step.

## Privacy and backup

The following contain personal or authenticated data and should not be committed
to a public repository:

- `browser_data/`
- `incoming/*.tcx`
- `strava_dashboard.db`
- any `.env` file

At minimum, never share `browser_data/`. It may contain reusable authentication
cookies. To sign out locally, close the program and remove that folder; the next
run will request login again.

## Troubleshooting

### The saved `SDBvenv` does not start

Delete or rename that local venv and create it again using the installation steps
above. Virtual environments are not portable between computers or Python
installations.

### Browser executable cannot be found

Install the fallback browser inside the active venv:

```powershell
python -m playwright install chromium
```

The normal launcher first attempts installed Google Chrome and then Playwright
Chromium. The legacy `login.py` has a hard-coded Chrome path and is not the
recommended entry point.

### Login is requested again

Do not use private/incognito mode and do not delete `browser_data/`. If Strava or
Google expires the session, complete login once more in the visible browser. The
new session will replace the saved one.

### No activities appear

Check the terminal for download/import errors. Confirm that TCX files exist in
`incoming/` and that `strava_dashboard.db` contains a `trackpoints` table. Manual
activities without GPS/TCX data cannot provide route or trackpoint analytics.

### Port 8501 is already in use

Stop the other Streamlit process, or start the dashboard alone on another port:

```powershell
python -m streamlit run scripts\dashboard.py --server.port 8502
```

## Notes

- This project reads the Strava website and its TCX export endpoints rather than
  using the official Strava API. Website changes may require maintenance.
- Use the project only with an account and data you are authorized to access.
- Strava and its trademarks belong to their respective owner; this is an
  independent personal project.
