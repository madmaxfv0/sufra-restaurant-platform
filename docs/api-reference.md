# API reference

SUFRA OS has 215 route handlers; this document covers the public booking API in detail, because it is the contract between the two applications, and lists the other groups. FastAPI serves interactive OpenAPI documentation at `/docs` on a running instance of either application.

Examples were captured from a local run on the seeded demo and shortened.

## Authentication

- **Public endpoints** (`/api/public/*`, the guest table menu) need no credentials. A guest is identified by the `sufra_sid` cookie, issued on first contact.
- **Staff endpoints** need `Authorization: Bearer <token>`. A token comes from `POST /api/auth/login` with a staff id and PIN.
- A missing or expired token returns `401`; a role without the required permission returns `403`.

## Public booking API (SUFRA OS)

Defined in `sufra-os/app/routers/public_v2.py`. SUFRA 360 exposes the same paths and forwards them.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/public/venue` | Restaurant identity, time zone, service hours and booking rules |
| GET | `/api/public/tables` | The table registry |
| GET | `/api/public/live` | What is happening at each table now, plus a revision counter |
| GET | `/api/public/availability?date&time&party_size&duration` | Which tables can be booked for a slot |
| POST | `/api/public/holds` | Hold a table for five minutes |
| DELETE | `/api/public/holds/{hold_id}` | Release a hold |
| POST | `/api/public/reservations` | Create a reservation |
| GET | `/api/public/reservations/{code}` | Look up a reservation |
| POST | `/api/public/reservations/{code}/cancel` | Cancel |
| GET | `/api/public/reservations/{code}/calendar.ics` | Calendar file |
| POST | `/api/public/waitlist` | Join the waitlist |
| GET | `/api/public/menu` | The menu |

### Availability

`GET /api/public/availability?date=2026-10-12&time=19:00&party_size=2`

```json
{
  "date": "2026-10-12",
  "time": "19:00",
  "party_size": 2,
  "duration": 90,
  "is_past": false,
  "is_closed": false,
  "tables": [
    {
      "table_id": "t01", "number": 1, "zone": "garden", "seats": 4,
      "state": "AVAILABLE", "bookable": true, "reason": "",
      "until": null, "next_available": null
    }
  ]
}
```

Availability never looks at current occupancy; it is decided by reservations, live holds, capacity and whether the table is in service.

### Hold a table

`POST /api/public/holds`

```json
{ "table_id": "t07", "date": "2026-10-14", "time": "20:00", "party_size": 2 }
```

```json
{
  "ok": true,
  "hold": {
    "id": "da289c8bf5b5a498", "table_id": "t07", "number": 7,
    "date": "2026-10-14", "time": "20:00", "duration": 90, "party_size": 2,
    "expires_at": "2026-10-10T20:08:28", "seconds_remaining": 300
  }
}
```

A second session asking for the same table and slot receives `409`.

### Create a reservation

`POST /api/public/reservations`

```json
{
  "table_id": "t10", "date": "2026-10-16", "time": "19:30", "party_size": 6,
  "first_name": "Demo", "last_name": "Guest",
  "email": "demo.guest@example.com", "phone": "+994 50 000 00 02",
  "occasion": "birthday", "allergies": "nuts"
}
```

```json
{
  "ok": true,
  "reservation": {
    "code": "SF00153", "status": "confirmed",
    "table_id": "t10", "table_number": 10, "zone": "window",
    "party_size": 6, "date": "2026-10-16", "time": "19:30", "duration": 120,
    "occasion": "birthday", "allergies": "nuts"
  },
  "calendar": { "ics": "/api/public/reservations/SF00153/calendar.ics", "google": "…" }
}
```

Optional fields: `dietary`, `accessibility`, `high_chairs`, `special_request`, `preference`, `language` (`en`, `az`, `ru`), `marketing_opt_in`, `duration`, `idempotency_key`.

Errors use one shape:

```json
{ "ok": false, "error": "capacity", "message": "Table 10 seats 6–8." }
```

| `error` | Status | Meaning |
|---|---|---|
| `missing_fields`, `bad_email`, `party`, `bad_date` | 400 | The request is incomplete or malformed |
| `capacity` | 400 | The party does not fit the table |
| `conflict` | 409 | The table is booked or held by someone else for that slot |
| `blocked` | 409 | The table is out of service |

### Live state

`GET /api/public/live`

```json
{
  "at": "2026-10-10T20:09:47", "service": "dinner", "revision": 27,
  "counts": { "tables": 30, "occupied": 0, "available": 30, "reserved_soon": 0, "held": 0, "guests": 0, "load_pct": 0 },
  "tables": [
    { "table_id": "t01", "number": 1, "zone": "garden", "state": "AVAILABLE",
      "guests": 0, "since": null, "until": null, "until_next": "free all evening" }
  ]
}
```

`revision` changes only when something in the restaurant changes; SUFRA 360 uses it to decide when to notify its clients.

## SUFRA 360 additions

Defined in `sufra-360/app/main.py`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Build, and whether the OS is reachable |
| GET | `/api/weather` | Cached conditions for the venue |
| GET | `/api/public/tables/{table_id}`, `/seats` | Table and seat geometry for the scene |
| POST | `/api/public/recommend-tables` | Rank tables for a date, time, party and preference |
| POST | `/api/public/guide` | Free-text table request |
| GET | `/api/public/google`, `/api/public/real-venue` | Optional embed configuration |
| WS | `/ws` | State-change notifications |

## Other SUFRA OS route groups

| Prefix or file | Handlers | Access | Covers |
|---|---|---|---|
| `/api/auth/*` (`auth_api.py`) | 7 | Open for roster and sign-in | Roster, sign-in, verify, sign-out, current user |
| `service_api.py` | 16 | Staff with ordering or payment permissions; guest table actions open | Orders, courses, bills, payment recording |
| `/api/admin/*` (`admin_api.py`) | 28 | Non-waiter staff | Administration data and actions |
| `operations_v2.py` | 26 | Staff | Floor, reservations book, booking control |
| `/api/anbar/*` (`anbar.py`) | 41 | Staff with inventory permissions | Warehouse |
| `enterprise.py` | 42 | Managers; owner and general manager for badges | HR, accounting, BI, passkeys, health probes |
| `/api/sufra/*`, `media_v4.py` | 6 | Staff | Menu content and media |
| `main.py` | 30 | Mixed; see the known gap in [roles-and-permissions.md](roles-and-permissions.md) | Pages, operational reads, translation, copilot, WebSocket |

Health probes: `GET /health/live`, `GET /health/ready`, `GET /api/build`.
