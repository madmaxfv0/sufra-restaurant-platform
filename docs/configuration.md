# Configuration

Neither application needs configuration for a local demo. All variables are optional and read from the environment; [`.env.example`](../.env.example) lists them.

## SUFRA OS

| Variable | Default | Effect |
|---|---|---|
| `NOVA_SEED_DEMO` | off | `1` seeds synthetic data, only when no database file exists yet |
| `NOVA_DB_PATH` | `sufra-os/nova.db` | Location of the SQLite file |
| `DATABASE_URL` | — | Use PostgreSQL instead (`postgresql+psycopg://…`). Not tested for this repository |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT` | 10, 20, 1800, 30 | PostgreSQL pool settings |
| `SUFRA_TZ` | `Asia/Baku` | The restaurant's time zone |
| `SUFRA_360_VENUE` | `../sufra-360/venue` | Folder with the room's `tables.json` and related files |
| `SUFRA_360_ORIGIN` | `http://127.0.0.1:8013` | Origin(s) allowed by CORS, comma-separated |
| `SUFRA_PUBLIC_URL`, `SUFRA_STAFF_URL` | derived from the request | Base URL used in QR links |
| `SUFRA_STAFF_QR_KEY` | generated into `.staff-qr.key` | Fernet key that encrypts staff badges. Set it for hosted deployments |
| `NOVA_SIMULATE` | off | `1` runs a service simulator |
| `NOVA_ALLOW_DEMO_RESET` | off | `1` enables the demo reset endpoint |
| `BI_API_KEY` | — | Accepts this key on `/api/bi/*` in place of a staff session |
| `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` | derived from the request | Passkey relying-party settings |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | — | Enables the new-employee account email |
| `OPENAI_API_KEY` | — | Enables generated menu photos |

Restaurant settings such as opening hours, slot length, hold length and the no-show grace period live in the database (`restaurantsetting`) and are edited in Administration → Settings.

## SUFRA 360

| Variable | Default | Effect |
|---|---|---|
| `SUFRA_OS_BASE` | `http://127.0.0.1:8123` | Where SUFRA OS is |
| `SUFRA_OS_TIMEOUT` | `12` | Seconds before a call to the OS gives up |
| `PORT` | `8013` | Port used by `run.py` |

## Secrets

Nothing secret is stored in the repository. The following are created at run time and are git-ignored: the database, `.staff-qr.key`, server logs, uploaded photos and `deploy/seed.db`.

`deploy/prepare.sh` copies the local database into `deploy/seed.db` for the first hosted boot. Whatever is in the local database at that moment, including staff PIN hashes and any stored settings, goes into the image. Seed a clean database and reset the PINs before deploying.
