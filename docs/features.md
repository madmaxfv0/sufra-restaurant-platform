# Features

What exists, where it lives, and what it does not do. "Verified" means it was exercised on the seeded demo when this repository was prepared; "present" means the code and screens exist but were not exercised then.

## SUFRA OS

| Area | What it does | Code | State |
|---|---|---|---|
| Reservations | Availability per slot, holds, create / change / cancel, accept or decline bookings that arrived online, waitlist, calendar file | `app/bookings.py`, `app/availability.py`, `app/routers/operations_v2.py`, `public_v2.py` | Verified: availability, hold, reserve, cancel, concurrency |
| Reservation automation | Marks bookings late, applies the no-show grace period, expires holds | `app/lifecycle.py` | Present |
| Floor | Table states set by staff; seat, free, move | `app/routers/operations_v2.py`, `templates/admin/floor.html` | Verified: page renders |
| Waiter app | Home, tables, order pad by seat, courses with hold / send / fire, table notes, bill with split and tip | `app/routers/service_api.py`, `templates/waiter/app.html`, `static/js/waiter.js` | Verified: PIN sign-in (browser test). Ordering flow present |
| Kitchen display | Tickets by station and state; allergen check of each order against declared allergies | `templates/admin/kitchen.html`, `app/allergens.py` | Verified: page renders |
| Menu administration | Sections, dishes, prices, availability, photos, translations | `app/routers/sufra_upgrade.py`, `templates/admin/menu_admin.html` | Verified: page renders |
| Guest table menu | Menu for a table from its QR code; call-waiter requests; feedback | `/t/{table}`, `templates/guest/app.html`, `static/js/guest.js` | Verified: page renders |
| Table QR codes | Printable QR grid, one code per table | `templates/admin/qr.html` | Verified: page renders |
| Payment screen | Records a payment against a table with a method and amount; split bills | `POST /api/pay/{table_id}` in `service_api.py`, `templates/payment.html` | Present. **No payment provider; nothing is charged** |
| Warehouse | Items, categories, locations, batches, purchase orders, goods receipts, transfers, stocktakes, waste, recipes and costing, usage per dish, alerts, reports | `app/anbar.py`, `app/routers/anbar.py`, `templates/admin/anbar.html` | Verified: unit and browser tests |
| Stock intelligence | Reorder suggestions, price changes, waste patterns, each with its inputs and a confidence level | `app/anbar_ai.py` | Present |
| Analytics | Seven models (see architecture) and dashboards | `app/intelligence.py`, `templates/admin/analytics.html`, `executive.html`, `command.html` | Verified: pages render. Accuracy not evaluated on real data |
| Copilot | Routes a typed question to the models and phrases the answer | `intelligence.copilot`, `POST /api/copilot` | Present. **Rule-based; not a language model** |
| HR | Employees, profile photos, attendance, leave, training, gross payroll estimate | `app/routers/enterprise.py`, `templates/admin/hr.html` | Verified: badge flows (browser test) |
| Accounting | Chart of accounts, journals, trial balance, P&L from sales, cost of goods, payroll and waste | `app/routers/enterprise.py`, `templates/admin/accounting.html` | Verified: page renders. An operational estimate, not a ledger of record |
| BI exports | Read-only JSON and CSV under `/api/bi/*`, with an optional API key | `app/routers/enterprise.py` | Present |
| Staff access | PIN sign-in, lockout, idle lock, QR badges, optional passkeys | `app/security.py`, `permissions.py`, `staff_access.py` | Verified: unit and browser tests. Passkeys present |
| Localisation | English, Azerbaijani, Russian; dictionaries plus cached machine translation for free text | `static/js/sufra-translations.js`, `sufra-final-i18n.js`, `POST /api/i18n/translate` | Verified: Russian warehouse screens (browser test) |
| Live updates | WebSocket stream of real state changes | `app/events.py`, `app/live.py` | Present |

## SUFRA 360

| Area | What it does | Code | State |
|---|---|---|---|
| 3D venue | Rooms, furniture, tableware, trees, water, lighting, animated figures | `static/js/sufra360/*` | Verified: loads and renders in headless Chromium |
| Live table status | Lantern colour per table from the OS's live state | `DataAdapter.js`, `TableManager.js`, `GET /api/public/live` | Verified: status feed. Colour change on seating present |
| Booking | Date, time, party size → bookable tables → hold → reservation with booking code | `Sufra360.js`, `app/main.py`, `app/nova.py` | Verified through the API |
| Table guide ("Ask AI") | Ranks tables for a free-text request using table attributes | `POST /api/public/guide`, `app/booking.py` | Present. **Keyword matching and scoring; not a language model** |
| Weather | Real conditions for the venue's coordinates drive the scene | `app/weather.py`, `Environment.js` | Verified: live reading shown |
| Menu | Browse-only menu read from the OS | `GET /api/public/menu` | Verified: page renders |
| Languages | English, Azerbaijani, Russian | `static/js/sufra360/i18n.js` | Present |
| Earlier 2D application | Illustrated map, panorama viewer, real-venue embeds | `static/index.html`, `static/js/app.js`, `map.js`, `pano.js` | Present; superseded by the 3D scene |

## Integrations

| Service | Used for | Key needed | Without it |
|---|---|---|---|
| Open-Meteo | Weather in SUFRA 360 | No | Last good reading, then a default |
| MyMemory, Google Translate (public endpoints) | Translating free text such as dish descriptions; results cached in the database | No | Text stays in its original language |
| Google Maps embed | Arrival and street views in the 2D application | Optional | Views are hidden |
| OpenAI Images | Generating a menu photo when none was uploaded | `OPENAI_API_KEY` | A placeholder image is used |
| SMTP | Emailing a new employee their account details | `SMTP_*` | The email is skipped |

The translation endpoint sends the text it is asked to translate to those services. Account emails, when enabled, go to the employee's own address.
