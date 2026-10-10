"""Paths only.

SUFRA 360 used to keep its own SQLite database of tables, reservations and
holds. It does not any more: SUFRA OS owns all of that, and app/nova.py is
how this application reaches it. What is left here is where the scene's
geometry and artwork live on disk.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENUE = os.path.join(ROOT, "venue")
ASSETS = os.path.join(ROOT, "assets")
