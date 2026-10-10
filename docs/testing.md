# Testing

## What runs where

| Check | Command (from `sufra-os/`) | Needs | Result when this repository was prepared |
|---|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | Pinned dependencies, `httpx` | 18 passed |
| Double-booking race | `python tests/http_double_booking.py` | A running demo OS | Passed: 1 of 12 holds, 1 of 12 reservations |
| Staff QR in a browser | `PYTHONPATH=. python tests/browser_staff_qr.py` | Playwright, a seeded `nova.db` | Passed |
| Warehouse in a browser | `PYTHONPATH=. python tests/browser_warehouse.py` | Playwright, a seeded `nova.db` | Passed |
| QR badges end to end | `PYTHONPATH=. python tests/browser_qr_full_app.py` | Playwright, a seeded `nova.db` | Passed |
| Language audit | `PYTHONPATH=. python tests/browser_i18n_audit.py --langs ru az en` | Playwright, a seeded `nova.db` | Not run |
| Admin button layout audit | `SUFRA_AUDIT_PIN=… python scripts/audit_admin_buttons.py` | Playwright, a running OS | Not run |

The browser tests copy the database to a temporary folder and start their own server, so they do not change the demo data.

Continuous integration runs the unit tests, compiles every Python file in both applications, starts both on a seeded database, checks their health endpoints and runs the double-booking race.

## What the unit tests cover

`tests/test_staff_qr.py`: four-digit PIN rules; PINs preserved when a badge is generated; old badges and sessions revoked on regeneration; badge issue restricted to owner and general manager; badge links built for LAN access.

`tests/test_warehouse_usage.py`: recipe quantities stored in base units and displayed in grams or millilitres; one-time conversion of older recipes; consumption posted once per kitchen ticket; planning previews that do not change stock.

## Also verified by hand

- A fresh install from `deploy/requirements.lock`, seeding, and start-up of both applications with `scripts/start_demo.sh`.
- Owner sign-in and rendering of thirteen administration pages, the guest table menu and the booking page.
- A booking made through SUFRA 360's API arriving in SUFRA OS.
- The 3D scene loading in headless Chromium, including the fallback for models that are not in the repository.

## Not tested

- Waiter ordering, course firing, bill splitting and payment recording, beyond the pages loading.
- Kitchen display state changes and the stock postings they trigger in a live run.
- HR, attendance, payroll estimate and accounting calculations.
- Accuracy of the forecasting and risk models.
- PostgreSQL mode, the Docker images, Fly.io and Kubernetes deployments (no Docker runtime was available).
- Passkey registration and sign-in.
- Mobile browsers and real devices.
