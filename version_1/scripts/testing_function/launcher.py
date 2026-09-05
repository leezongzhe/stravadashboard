import subprocess
import sys
import time
from pathlib import Path

# Setup paths (Ensure these match your actual file names)
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"

WATCHER_SCRIPT = SCRIPTS_DIR / "track_new_file.py"
DISCOVERY_SCRIPT = SCRIPTS_DIR / "discover_and_download.py" # Update if you named it differently

def main():
    print("🚀 Starting Strava Dashboard Master Pipeline...")

    # 1. Start the Watcher in the background
    print("\n[*] 1. Booting up Watchdog folder monitor...")
    # Popen starts the process in the background and continues the script
    watcher_process = subprocess.Popen([sys.executable, str(WATCHER_SCRIPT)])

    # Give Watchdog 2 seconds to initialize the database and bind to the folder
    time.sleep(2)

    # 2. Run the Discovery & Download script in the foreground
    print("\n[*] 2. Starting Discovery & Download automation...")
    try:
        # subprocess.run blocks and waits for the discovery script to finish
        subprocess.run([sys.executable, str(DISCOVERY_SCRIPT)], check=True)
        print("\n[✓] Discovery and download phase completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Discovery script encountered an error: {e}")

    # 3. Keep the pipeline alive
    print("\n" + "="*50)
    print("📡 PIPELINE ACTIVE")
    print("The folder watcher is still running in the background.")
    print("Any TCX files dropped into 'incoming/' will be instantly processed.")
    print("Press Ctrl+C to safely shut down all services.")
    print("="*50 + "\n")

    try:
        # Keep the main script alive so Watchdog can do its job
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[*] Shutting down Master Launcher...")
        # Safely kill the background Watchdog process
        watcher_process.terminate()
        watcher_process.wait()
        print("[✓] All background processes terminated gracefully. Goodbye!")

if __name__ == "__main__":
    main()