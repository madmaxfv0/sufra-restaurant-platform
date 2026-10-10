# Architecture

Derived from the code in `sufra-os/` and `sufra-360/`.

## Two applications, one restaurant

| | SUFRA OS | SUFRA 360 |
|---|---|---|
| Audience | Staff (and guests at a table, through the QR menu) | Guests choosing and booking a table |
| Default port | 8123 | 8013 |
| Server | FastAPI, `sufra-os/app/main.py` | FastAPI, `sufra-360/app/main.py` |
| State | SQLite database `nova.db` (or PostgreSQL through `DATABASE_URL`) | None. Geometry and artwork on disk only |
| Frontend | Jinja2 templates, plain JavaScript | Static HTML and ES modules, three.js |
| Background work | Reservation scheduler, live-event tail, optional simulator | Polls the OS revision counter |

SUFRA 360 reaches the restaurant only through `sufra-360/app/nova.py`, an HTTP client for the OS's `/api/public/*` endpoints. If the OS cannot be reached, 360 reports that; it does not fall back to local data.

The guest's session cookie (`sufra_sid`) is forwarded by 360 to the OS, so "the table I am holding" means the same thing in both.

## SUFRA OS modules

| Module | Responsibility |
|---|---|
| `app/main.py` | Application start-up, page routes, operational read APIs, translation endpoint, WebSocket endpoint |
| `app/database.py` | Engine set-up: SQLite with WAL, busy timeout and foreign keys; PostgreSQL pooling when `DATABASE_URL` is set |
| `app/models.py`, `anbar_models.py`, `enterprise_models.py` | 67 tables: 42 core, 15 warehouse, 10 HR/accounting |
| `app/canon.py` | Additive schema migration, restaurant settings, and the table registry synchronised from `sufra-360/venue/*.json` |
| `app/bookings.py` | Creating, changing, accepting, declining and cancelling reservations |
| `app/availability.py` | Bookability for a slot, holds, and the live floor state (kept as separate questions) |
| `app/dblock.py` | The cross-process writer lock (`BEGIN IMMEDIATE`) |
| `app/lifecycle.py` | The only scheduler: marks bookings late, applies the no-show grace period, sweeps expired holds every 30 seconds |
| `app/events.py`, `app/live.py` | Append-only live event table, WebSocket hub, optional service simulator |
| `app/security.py`, `permissions.py`, `staff_access.py` | PIN hashing, sessions, lockout, the role matrix, staff QR badges |
| `app/intelligence.py` | Seven statistical models and the rule-based copilot router |
| `app/anbar.py`, `anbar_ai.py` | Warehouse ledger and stock recommendations, each with the inputs that produced it |
| `app/allergens.py` | Allergen vocabulary and order checks against declared allergies |
| `app/rtime.py` | The restaurant's own clock and time zone (`SUFRA_TZ`, default Asia/Baku) |
| `app/seed.py`, `seed_ops.py` | Synthetic demo data |
| `app/routers/auth_api.py` | Roster, sign-in, verify, sign-out |
| `app/routers/service_api.py` | Waiter and guest ordering, bills, payment recording |
| `app/routers/admin_api.py` | Administration APIs (all require a non-waiter staff session) |
| `app/routers/operations_v2.py` | Floor, reservations book and booking control |
| `app/routers/public_v2.py`, `public_booking.py` | The public booking API used by 360, and the OS's own booking page |
| `app/routers/anbar.py` | Warehouse API |
| `app/routers/enterprise.py` | HR, accounting, BI exports, payment page, passkeys, health probes |
| `app/routers/sufra_upgrade.py`, `media_v4.py` | Menu content, uploads, optional image generation |

Route handlers: 215 across `main.py` and the routers.

## SUFRA 360 modules

| Module | Responsibility |
|---|---|
| `app/main.py` | Public API (venue, tables, live state, availability, holds, reservations, waitlist, guide), page routes, WebSocket |
| `app/nova.py` | HTTP bridge to the OS, with a short cache for venue identity and the table registry only |
| `app/booking.py` | Ranking and recommendation of tables for a request |
| `app/weather.py` | Open-Meteo fetch with a 10-minute cache and last-good fallback |
| `static/js/sufra360/Sufra360.js` | Scene orchestration, booking drawer, user interface |
| `static/js/sufra360/SceneManager.js`, `Environment.js` | Renderer, cameras, lighting, time of day, weather |
| `static/js/sufra360/RestaurantBuilder.js`, `GLBVenue.js` | Builds the room from venue data and models |
| `static/js/sufra360/TableManager.js`, `Halos.js`, `TableInsight.js` | Tables, chairs, status lanterns, selection |
| `static/js/sufra360/AssetManager.js` | Model catalogue with licences, instancing, fallbacks |
| `static/js/sufra360/FoliageWaterRain.js` | Wind-driven foliage, water shader, rain |
| `static/js/sufra360/GuestSystem.js`, `ClothedPeopleSystem.js` | Animated figures |
| `static/js/sufra360/DataAdapter.js` | Fetches live state and maps it onto the scene |
| `static/js/sufra360/i18n.js` | English, Azerbaijani, Russian |
| `venue/*.json` | Floor, tables, seats, zones |
| `tools/*.py` | Generators for the venue data, map, panoramas, textures and menu artwork |
| `blender/*.py` | The pipeline that decimates and exports source models to glTF |

## Booking without double booking

The decision that must not race is "is this table free for this slot? then take it".

1. `dblock.immediate()` opens a raw SQLite connection and issues `BEGIN IMMEDIATE`, which takes the database writer lock before anything is read.
2. Inside that lock the code checks for an overlapping reservation or a live hold from another session, and inserts the hold or the reservation.
3. The lock is released on commit.

Because the lock belongs to the database file, it also serialises requests arriving through different processes. Availability is re-checked at confirmation: a hold reserves a table for five minutes, but the reservation insert performs its own conflict test.

A reservation may carry an `idempotency_key`; a repeat with the same key returns the existing booking.

On PostgreSQL the lock is not taken and the code relies on transaction isolation with the same checks. That mode was not tested for this repository.

## Reservation lifecycle

`lifecycle.loop()` runs every 30 seconds inside the OS. Each transition claims its row with a conditional `UPDATE` inside the writer lock, so a second server process could not apply it twice.

| Setting (default) | Effect |
|---|---|
| `hold_seconds` (300) | How long a table hold lasts |
| `slot_minutes` (15) | Booking time granularity |
| `default_duration` (105) | Minutes a booking occupies a table |
| `turnover_buffer` (15) | Minutes kept free after a booking |
| `grace_minutes` (30) | After this, an unseated booking becomes a no-show |
| `max_party` (20) | Largest party bookable online |

Bookings taken through SUFRA 360 or the website arrive with `staff_decision = pending` so a manager can accept or decline them.

## Live updates

Every genuine state change writes a row to the `liveevent` table. The OS tails that table and pushes new rows to its WebSocket clients (`/ws`). No events are generated when nothing happens.

The OS also keeps a monotonic revision number exposed at `/api/public/live`. SUFRA 360 polls it and publishes a `STATE` message to its own `/ws` clients when it changes; browsers fall back to periodic polling if WebSockets are unavailable.

`NOVA_SIMULATE=1` starts a service simulator in the OS for demonstrations. It is off by default.

## Table identity

`sufra-360/venue/tables.json` defines the physical tables. On start-up `canon.sync_table_registry()` reconciles the OS's `diningtable` rows with that file (path from `SUFRA_360_VENUE`, defaulting to the sibling `sufra-360/venue` folder), so each table has one identifier in both applications. Scene areas map to operational zones: garden, lounge and terrace to Terrace; window, east and main to Main; bar to Bar; private to Private.

## Analytics models

All in `sufra-os/app/intelligence.py`; none calls a language model.

| Model | Method |
|---|---|
| Revenue forecast | Ridge regression in closed form over 180 trading days |
| Preparation time | Base time scaled by queue length and a rush-hour factor |
| Station pressure | 20-minute projection per kitchen station, capped at throughput |
| Inventory outlook | Forecast covers → recipe lines → shortfall and order quantity |
| No-show risk | Logistic scoring of booking features |
| Menu engineering | Split on median margin and median sales |
| Service risk | Per-status time limits per table |

`copilot()` routes a typed question to these by keyword and phrases the result.
