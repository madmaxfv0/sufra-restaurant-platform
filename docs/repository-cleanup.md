# Repository cleanup

What changed when two working folders were combined into this repository.

## Why one repository

SUFRA OS and SUFRA 360 were two folders with separate local git histories. They are one product: 360 has no database and cannot run without the OS; the OS builds its table registry from 360's venue files; they are deployed together by one script. They now sit side by side as `sufra-os/` and `sufra-360/`.

## Why the old git histories are not here

This repository starts from a snapshot of both working trees. The earlier local histories were left untouched in their original folders and were not pushed, because they contain:

- the SUFRA OS database at many points in time, including staff PIN hashes, stored mail settings and a few real-looking guest email addresses entered during testing;
- two complete Python virtual environments (over 10,000 files);
- in SUFRA 360, a 1.2 GB third-party model file, which also exceeds GitHub's file size limit.

## Choosing the baseline

| Copy | State |
|---|---|
| `SUFRA_OS/NOVA_WORKING_BLUE_FIXED_CHECKPOINT` (working tree, including uncommitted changes) | Newest. **Baseline for `sufra-os/`** |
| `NOVA_WORKING_BLUE_FIXED_CHECKPOINT` on the Desktop | Older copy of the same project. Only two things exist there alone: an Events admin screen that was later removed on purpose, and an early copy of twelve SUFRA 360 frontend files whose newer versions are in `sufra-360/` |
| `app_BACKUP_BEFORE_LANGUAGE_RESPONSIVE_FIX/`, 28 `.backup-*` folders and files, `*.before_*` files | Dated backups made before individual changes |
| `SUFRA_360` (working tree) | **Baseline for `sufra-360/`** |
| `SUFRA_360/backups/` | Dated backups of individual files |

## Moved and renamed

| Before | After |
|---|---|
| `NOVA_WORKING_BLUE_FIXED_CHECKPOINT/` | `sufra-os/` |
| `SUFRA_360/` | `sufra-360/` |
| `START_NOVA.command` | `sufra-os/start-sufra-os.command` |
| `import_360_menu.py` | `sufra-os/scripts/import_360_menu.py` |
| `tools_audit_buttons.py` | `sufra-os/scripts/audit_admin_buttons.py` |
| `STAFF_QR_ACCESS.md` | `docs/staff-qr-access.md` |
| `WAREHOUSE_USAGE.md` | `docs/warehouse-usage.md` |
| `SUFRA_ENTERPRISE.md` | `docs/enterprise-modules.md` |
| `SUFRA_360/CAPTURE.md` | `docs/capturing-a-venue.md` |
| `SUFRA_360/deploy/DEPLOY.md` | `docs/deployment.md` |

Identifiers containing "nova" (`nova.db`, `NOVA_DB_PATH`, `nova-core.js`, `nova.css`, browser storage keys) were kept. Renaming them would change environment variables and stored sessions of the deployed instance.

## Left out

| Item | Reason |
|---|---|
| `nova.db` and its `-wal` / `-shm` files, `deploy/seed.db`, `.local-backups/` | Databases. The demo seeds its own |
| `.staff-qr.key` | Signing key |
| `sufra_server_errors.log`, `.runtime/`, empty smoke logs | Logs |
| `.venv/`, `.venv312/`, `__pycache__/` | Environments and generated files |
| `app/static/uploads/staff/*` | Uploaded staff photographs |
| `artifacts/` (172 MB) | Output of the language audit |
| 28 `.backup-*` folders and files, `app_BACKUP_BEFORE_LANGUAGE_RESPONSIVE_FIX/`, `*.before_*`, `backups/` | Superseded backups |
| `APPLY_SUFRA_BETTER_LANGUAGE_LIGHT.command`, `RESTORED_VERSION.txt`, `INSTALL_ON_MAC.txt` | One-off patch script and notes about an earlier checkpoint |
| The earlier `README.md` files | Described earlier builds; one listed every demo PIN |
| `SUFRA_360/assets_src/` (1.8 GB), `blender/*.blend` | Source downloads and Blender scenes, some containing licensed geometry |
| `SUFRA_360/static/3d/models/provis/` | Models derived from a licensed third-party scene |
| `SUFRA_360/static/models/clothed_people/` except six files | Only the six characters the scene loads are kept (CC0), with their licence files |
| `SUFRA_360/captures/` (137 MB) | Development screenshots; already git-ignored |

Nothing was deleted from the original folders.

## Code changes

| File | Change | Why |
|---|---|---|
| `sufra-os/app/bookings.py` | The reservation `INSERT` now names `staff_decision`, `decided_by` and `decline_reason` | **Bug fix.** On a newly created database those columns have no SQL default, so every online booking failed with a `NOT NULL` error. Databases upgraded in place were unaffected, which is why it had not been seen |
| `sufra-os/app/canon.py` | Default venue path is the sibling `sufra-360/venue` | The old default pointed at a folder layout on one machine |
| `sufra-os/deploy/prepare.sh`, `sufra-360/deploy/deploy_fly.sh` | Default paths to the other application | Same reason |
| `sufra-os/scripts/import_360_menu.py` | Menu file path is a command-line argument | It was an absolute path on one machine |
| `sufra-os/scripts/audit_admin_buttons.py` | Reads the PIN from `SUFRA_AUDIT_PIN` | A demo PIN was written in the source |
| `sufra-os/start-sufra-os.command` | Installs from `deploy/requirements.lock` | A fresh resolve of `requirements.txt` installs an unsupported SQLModel release |
| `sufra-os/app/seed.py` | Seed message no longer refers to a PIN list in the README | The README no longer has one |
| `sufra-360/static/js/sufra360/AssetManager.js` | A catalogue entry may name a `fallback` model | So the scene still has chairs and tables without the licensed models |

## Added

- `README.md`, `docs/architecture.md`, `features.md`, `api-reference.md`, `roles-and-permissions.md`, `demo-guide.md`, `configuration.md`, `testing.md`.
- `docs/screenshots/` — 21 screenshots from a local run on seeded data.
- `scripts/start_demo.sh` — starts both applications on a seeded database.
- `sufra-os/tests/http_double_booking.py` — the booking race check.
- `.env.example`, `.gitignore`, `.github/workflows/ci.yml`.
