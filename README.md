# Strava Dashboard

This repository contains the published original version of the local Strava
training dashboard in a self-contained `version_1/` folder.

Clone the repository and begin inside `version_1`:

```powershell
git clone https://github.com/leezongzhe/stravadashboard.git
cd stravadashboard\version_1
py -m venv SDBvenv
.\SDBvenv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts\final_launcher.py
```

See the [complete Version 1 instructions](version_1/README.md) for login,
troubleshooting, retry behavior, and privacy guidance.

The locally developed `version_2` and `app_version` editions are intentionally
not published by this repository update.

## Private data

Browser profiles, downloaded TCX files, SQLite databases, virtual environments,
and environment files are local data and are excluded from future commits by the
repository `.gitignore`. Never publish a saved browser profile because it may
contain authenticated session cookies.
