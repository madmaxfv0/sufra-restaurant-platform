"""Start the clean NOVA build and open all three apps.

Uses a fresh local port so an older NOVA process on :8000 cannot be mistaken
for this build. It waits until the server actually answers before opening tabs.
"""
from pathlib import Path
import os
import socket
import threading
import time
import urllib.request
import webbrowser
import uvicorn

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
BUILD = "20260902-sufra-enterprise-1"

def choose_port(start=8123):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit("SUFRA could not find a free local port.")

PORT = choose_port()
BASE = f"http://127.0.0.1:{PORT}"

def open_when_ready():
    for _ in range(100):
        try:
            with urllib.request.urlopen(BASE + "/api/build", timeout=0.25) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.15)
    else:
        print("\nSUFRA did not become ready. Read the error printed above.")
        return
    print("\nSUFRA is ready. Opening fresh browser tabs...")
    for path in ("/", "/admin?fresh=1", "/waiter?fresh=1", "/guest/13"):
        webbrowser.open_new_tab(BASE + path + ('&' if '?' in path else '?') + f"build={BUILD}")

if __name__ == "__main__":
    if not (ROOT / "app" / "main.py").exists():
        raise SystemExit("SUFRA cannot start: app/main.py is missing from this folder.")
    # Preflight database registration/creation before the HTTP server starts.
    # This guarantees new additive operation tables exist even on an old nova.db.
    import app.models  # noqa: F401
    from app.database import create_db
    create_db()
    print("Database schema checked.")
    print("=" * 64)
    print("SUFRA CLEAN BUILD")
    print("Folder:", ROOT)
    print("Build:", BUILD)
    print("Port:", PORT, "(intentionally not 8000)")
    print("Admin:", BASE + "/admin")
    print("Waiter:", BASE + "/waiter")
    print("Guest:", BASE + "/guest/13")
    print("=" * 64)
    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=False, log_level="info")
