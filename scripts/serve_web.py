"""Serve the React frontend and its JSON API (same data layer as the Streamlit dashboard).

  python scripts/serve_web.py             # http://localhost:8504   (API + built frontend from web/dist)
  python scripts/serve_web.py --reload    # API only, auto-reload; run `npm run dev` in web/ for the frontend (port 5173)

Build the frontend once with:  cd web && npm install && npm run build
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.environ.get("MCR_WEB_PORT", 8504)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()
    uvicorn.run("mcr.api:app", host=a.host, port=a.port, reload=a.reload)
