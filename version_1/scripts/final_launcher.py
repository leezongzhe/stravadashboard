import argparse
import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# PATH CONFIGURATION
# ============================================================

# final_launcher.py is inside:
#
# StravaDashboard/
# └── scripts/
#     ├── final_launcher.py
#     ├── dashboard.py
#     ├── discover_and_download.py
#     └── track_new_file.py

BASE_DIR = Path(__file__).resolve().parent

WATCHER_SCRIPT = (
    BASE_DIR / "track_new_file.py"
)

DISCOVERY_SCRIPT = (
    BASE_DIR / "discover_and_download.py"
)

DASHBOARD_SCRIPT = (
    BASE_DIR / "dashboard.py"
)


# ============================================================
# MAIN PIPELINE
# ============================================================

def main(retry_unavailable=False):

    print("=" * 60)
    print("STRAVA DASHBOARD MASTER PIPELINE")
    print("=" * 60)


    # ========================================================
    # 1. START WATCHDOG
    # ========================================================

    print(
        "\n[*] 1. Starting Watchdog folder monitor..."
    )

    watcher_process = subprocess.Popen(
        [
            sys.executable,
            str(WATCHER_SCRIPT)
        ],
        cwd=str(BASE_DIR)
    )

    print(
        f"[✓] Watchdog started "
        f"(PID: {watcher_process.pid})"
    )


    # ========================================================
    # 2. WAIT FOR WATCHDOG
    # ========================================================

    print(
        "[*] Waiting for Watchdog to initialize..."
    )

    time.sleep(2)


    # ========================================================
    # 3. DISCOVER AND DOWNLOAD NEW ACTIVITIES
    # ========================================================

    print(
        "\n[*] 2. Starting Discovery & Download..."
    )

    discovery_success = False

    try:

        discovery_command = [
            sys.executable,
            str(DISCOVERY_SCRIPT)
        ]

        if retry_unavailable:
            discovery_command.append("--retry-unavailable")

        subprocess.run(
            discovery_command,
            cwd=str(BASE_DIR),
            check=True
        )

        discovery_success = True

        print(
            "\n[✓] Discovery and download "
            "completed successfully."
        )

    except subprocess.CalledProcessError as e:

        print(
            "\n[X] Discovery script encountered "
            "an error."
        )

        print(
            f"    Error: {e}"
        )


    # ========================================================
    # 4. WAIT FOR TCX PROCESSING
    # ========================================================

    if discovery_success:

        print(
            "\n[*] 3. Waiting for Watchdog "
            "to process downloaded TCX files..."
        )

        time.sleep(5)

        print(
            "[✓] TCX processing period completed."
        )


    # ========================================================
    # 5. STOP WATCHDOG
    # ========================================================

    print(
        "\n[*] 4. Stopping Watchdog..."
    )

    try:

        watcher_process.terminate()

        watcher_process.wait(
            timeout=5
        )

        print(
            "[✓] Watchdog stopped successfully."
        )

    except subprocess.TimeoutExpired:

        print(
            "[!] Watchdog did not stop normally."
        )

        watcher_process.kill()

        watcher_process.wait()

        print(
            "[✓] Watchdog terminated."
        )


    # ========================================================
    # 6. START STREAMLIT DASHBOARD
    # ========================================================

    print(
        "\n" + "=" * 60
    )

    print(
        "STARTING STRAVA DASHBOARD"
    )

    print(
        "=" * 60
    )

    print(
        "\n[*] Executing:"
    )

    print(
        "    streamlit run dashboard.py"
    )

    print(
        "\n[*] Dashboard is starting...\n"
    )


    # --------------------------------------------------------
    # Run Streamlit
    #
    # Equivalent to manually typing:
    #
    # streamlit run dashboard.py
    #
    # --------------------------------------------------------

    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "dashboard.py"
        ],
        cwd=str(BASE_DIR)
    )


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--retry-unavailable",
        action="store_true",
        help="Retry activities previously recorded without TCX data."
    )
    args = parser.parse_args()

    try:

        main(args.retry_unavailable)

    except KeyboardInterrupt:

        print(
            "\n\n[*] Launcher interrupted by user."
        )

        sys.exit(0)
