"""Start NOVA on the clean-build port. Prefer: python3 start_all.py"""
import os
from pathlib import Path
import uvicorn
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8123, reload=False)
