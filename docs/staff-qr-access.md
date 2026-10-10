# Staff access

Restart the running server with `sufra-os/start-sufra-os.command` after updating. It installs missing dependencies and creates new tables automatically. Reload the browser.

All PIN inputs and backend validation now accept exactly **four numeric digits**. New accounts and PIN resets generate four-digit PINs. Existing PIN hashes are preserved. If an account was reset to six digits using the previous version, an administrator must reset it to four digits in Settings.

Only the owner or general manager can issue, view, or regenerate employee badges through **Admin → HR → Employees**. Staff and unauthenticated requests are rejected by the backend.

- **Generate QR** creates a badge for an existing employee and keeps their PIN.
- **View QR** reopens a generated badge for download or printing.
- **Regenerate QR** invalidates the old badge and sessions while keeping the PIN.
- Adding an employee creates a badge and shows their new four-digit PIN once.
- Settings → Reset employee PIN changes the PIN and revokes sessions.

Employees open their admin-issued QR link with a phone camera and enter four digits. The large scan button and guest reservation banner have been removed from the staff profile screen. Employees can also choose Use QR instead to scan with a camera, upload an image, or paste a badge link. Profile + four-digit PIN sign-in remains available for every active employee, including after badge generation or regeneration. QR sign-in identifies the employee and then asks for their PIN.

QR badges contain an encrypted identifier and random nonce, never a PIN. A digest validates the badge, and a separately encrypted copy lets administrators reprint it. PINs remain salted hashes. Credential responses cannot be cached. Inactivity expires sessions after eight minutes; normal polling does not count as user activity.

Set `SUFRA_PUBLIC_URL` to the reachable HTTPS origin of this staff application before distributing badges. Camera access requires HTTPS or localhost. For hosted deployments set `SUFRA_STAFF_QR_KEY` to a persistent Fernet key shared by all workers. Local installations automatically create the owner-readable `.staff-qr.key` file. Preserve this file securely across restarts. Changing or losing it requires replacing badges.

Tests: `python -m unittest discover -s tests -v` and `PYTHONPATH=. python tests/browser_staff_qr.py`. Test dependencies are `httpx` and `playwright`; install Chromium with `python -m playwright install chromium`.


## QR recovery and phone access

Waiter/bartender badges open `/waiter`; other staff badges open `/admin`. The badge dialog includes an Open app link, regeneration status, PNG download, printing without the PIN, and clipboard/manual link copying. Old QR images are invalid after regeneration.

Generating your own badge preserves the authenticated session issuing it and revokes your other sessions. Generating a waiter badge revokes the waiter's sessions, not the administrator's. Expired sessions return to sign-in instead of leaving a broken HR screen. Scrolling and pointer activity count as activity; background polling does not.

Use `SUFRA_STAFF_URL` for the staff server's externally reachable origin. If no specific staff URL is configured, `SUFRA_PUBLIC_URL` remains the fallback. Localhost/127.0.0.1 origins are replaced with the Mac's current LAN address so phones on the same network can open the badge. If the Mac's LAN address changes, re-download or print badges using View QR. A phone must be able to reach the staff server on its configured port.

Run `PYTHONPATH=. python tests/browser_qr_full_app.py` for a real HTTP check of regeneration, old-token rejection, download, print, copy, actual waiter-app sign-in and expired admin-session recovery. It uses a temporary copy of the restaurant database.
