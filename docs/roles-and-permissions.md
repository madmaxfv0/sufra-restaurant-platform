# Roles and permissions

From `sufra-os/app/security.py`, `permissions.py` and `routers/auth_api.py`.

## Signing in

- Staff choose their profile and enter a four-digit PIN, or open their QR badge link and then enter the PIN.
- PINs are stored as `salt$hash` using PBKDF2-HMAC-SHA256 with 200,000 iterations and a per-person random salt. A plain PIN is shown once, when an administrator creates an account or resets a PIN.
- Five wrong attempts lock that profile for 30 seconds; each further block of five doubles the lockout.
- A session token lasts 12 hours and expires after 8 minutes without activity. The idle limit is enforced on the server.
- Guests do not sign in. The table menu and the public booking API are open by design.

QR badges contain an encrypted identifier and a random nonce, never the PIN. See [staff-qr-access.md](staff-qr-access.md).

## Which app each role uses

| Role | Signs in to |
|---|---|
| Owner, general manager, restaurant manager, host, kitchen, cashier, inventory manager | Administration app (`/admin`) |
| Waiter, bartender | Waiter app (`/waiter`) |

Waiters and bartenders are refused by every `/api/admin/*` endpoint (`admin_staff`). What an administration user can see and do is then narrowed by the matrix below.

## Permission matrix

Generated from `MATRIX` in `permissions.py`. Every permission defaults to off.

| Permission | Owner | GM | Manager | Host | Waiter | Bartender | Kitchen | Cashier | Inventory |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `can_apply_discount` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_assign_tables` | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `can_comp_item` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_create_order` | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |  |
| `can_edit_inventory` | ✓ | ✓ | ✓ |  |  |  |  |  | ✓ |
| `can_edit_order` | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |  |
| `can_edit_staff` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_manage_availability` | ✓ | ✓ | ✓ |  |  |  | ✓ |  | ✓ |
| `can_manage_complaints` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_manage_menu` | ✓ | ✓ | ✓ |  |  |  | ✓ |  |  |
| `can_manage_permissions` | ✓ |  |  |  |  |  |  |  |  |
| `can_modify_reservations` | ✓ | ✓ | ✓ | ✓ |  |  |  |  |  |
| `can_refund_payment` | ✓ | ✓ | ✓ |  |  |  |  | ✓ |  |
| `can_set_table_state` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |
| `can_take_payment` | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ |  |
| `can_view_analytics` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_view_financials` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_view_guest_profiles` | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `can_view_inventory` | ✓ | ✓ | ✓ |  |  |  |  |  | ✓ |
| `can_view_orders` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_view_profitability` | ✓ | ✓ |  |  |  |  |  |  |  |
| `can_view_reservations` | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `can_view_staff` | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `can_void_item` | ✓ | ✓ | ✓ |  |  |  |  |  |  |

Sensitive endpoints depend on `require_permission(...)`, which re-checks the token and the role on every request. The interface reads the same matrix to hide controls, but that is a convenience and not the security boundary.

Issuing, viewing and regenerating staff badges is limited to the owner and general manager.

## Known gap

Seven read-only endpoints in `main.py` do not require a token: `/api/floor`, `/api/kitchen`, `/api/reservations`, `/api/inventory`, `/api/snapshot`, `/api/insights` and `/api/forecast`. `/api/reservations` includes guest names, occasion and allergy notes. They should be placed behind `current_staff` before any deployment that holds real data.

## Audit

Sign-ins, lockouts, voided items and badge operations are written to the `auditlog` table.
