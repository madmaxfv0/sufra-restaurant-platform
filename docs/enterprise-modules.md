> Written when these modules were added (September 2026). For the current state of each feature see [features.md](features.md).

# SUFRA Enterprise Upgrade

This upgrade is additive and keeps the existing restaurant service workflow.

## New modules
- Universal dark/light mode across Admin, Waiter, Guest, payment and enterprise pages.
- Larger, labelled controls with visible action icons.
- Per-table QR ordering (`/t/{table}`) with printable QR grid and direct kitchen routing.
- Owner Intelligence: 7-day demand/revenue, station pressure, stock risk, satisfaction, waste and scenario planning.
- HR & People: employee accounts/profile photos, attendance, leave, gross-payroll estimate, training and device biometrics/passkeys.
- Accounting: Chart of Accounts, journals, Trial Balance and P&L generated from operational sales/COGS/payroll/waste entries.
- Read-only BI endpoints under `/api/bi/*` with optional `BI_API_KEY`.
- Separate payment terminal window at `/pay/{table_id}`.
- Menu-photo failure fallback is local; external random photo loading is removed.
- AI menu-image generation controls are removed and the previous generation route is disabled.

## Security
Device biometrics use WebAuthn/passkeys. Face ID/Touch ID/Windows Hello stays on the employee device. SUFRA stores a public credential, **not a face image or facial template**. Biometrics authenticate access only; they are not used for hiring, firing, attendance scoring, discipline or performance ranking.

## Reliability and scale
Local mode remains SQLite, now with WAL + busy timeout. Set `DATABASE_URL` for PostgreSQL in production. PostgreSQL mode uses pre-ping and connection pooling.

Useful production environment variables:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@db-host/sufra'
export DB_POOL_SIZE='20'
export DB_MAX_OVERFLOW='40'
export SUFRA_PUBLIC_URL='https://restaurant.example.com'
export BI_API_KEY='replace-with-a-long-random-secret'
export WEBAUTHN_RP_ID='restaurant.example.com'
export WEBAUTHN_ORIGIN='https://restaurant.example.com'
```

Health probes:
- `/health/live`
- `/health/ready`

**High availability is a deployment property.** For production HA, run multiple FastAPI replicas behind a load balancer with managed PostgreSQL failover. The current in-process WebSocket hub is suitable for one app instance; multi-instance real-time fan-out should use Redis/pub-sub before horizontally scaling WebSocket traffic.

## Accounting note
The included payroll calculation is a gross operational estimate from attendance/rota data. Statutory payroll taxes, pensions and filings should be exported to a payroll provider/accounting system rather than treated as a legal payroll engine.
