"""Two guests cannot take the same table: an HTTP-level check.

Fires simultaneous requests for one table and one time slot from separate
guest sessions and asserts that exactly one hold, and exactly one
reservation, is granted. Needs a running SUFRA OS:

    SUFRA_OS_URL=http://127.0.0.1:8123 python tests/http_double_booking.py

Only writes synthetic bookings (example.com addresses). Point it at a demo
database, not a real one.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = os.environ.get("SUFRA_OS_URL", "http://127.0.0.1:8123").rstrip("/")
GUESTS = int(os.environ.get("GUESTS", "12"))
DAY = (date.today() + timedelta(days=3)).isoformat()
SLOT = "19:00"


def call(method, path, body=None):
    """One request with no cookie, so every call is a new guest session."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def race(make_request):
    """Release GUESTS threads at the same moment; return every (status, body)."""
    gate, results = threading.Barrier(GUESTS), []

    def guest(n):
        gate.wait()
        results.append(make_request(n))

    threads = [threading.Thread(target=guest, args=(n,)) for n in range(GUESTS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def free_tables():
    _, slot = call("GET", "/api/public/availability?date=%s&time=%s&party_size=2" % (DAY, SLOT))
    return [t["table_id"] for t in slot["tables"] if t["bookable"]]


def main():
    tables = free_tables()
    if len(tables) < 2:
        sys.exit("Need two free tables on %s at %s to run this check." % (DAY, SLOT))
    hold_table, booking_table = tables[0], tables[1]

    holds = race(lambda n: call("POST", "/api/public/holds", {
        "table_id": hold_table, "date": DAY, "time": SLOT, "party_size": 2}))
    granted = [body for status, body in holds if status == 200 and body.get("ok")]
    refused = [status for status, body in holds if status == 409]
    print("holds:        %d granted, %d refused with 409, of %d simultaneous"
          % (len(granted), len(refused), GUESTS))

    bookings = race(lambda n: call("POST", "/api/public/reservations", {
        "table_id": booking_table, "date": DAY, "time": SLOT, "party_size": 2,
        "first_name": "Guest%d" % n, "last_name": "Concurrency",
        "email": "guest%d@example.com" % n, "phone": "+994 50 000 00 %02d" % n}))
    created = [body for status, body in bookings if status == 200 and body.get("ok")]
    print("reservations: %d created, %d refused, of %d simultaneous"
          % (len(created), GUESTS - len(created), GUESTS))

    # tidy up so the check can be run again against the same database
    for body in created:
        call("POST", "/api/public/reservations/%s/cancel" % body["reservation"]["code"], {})

    if len(granted) != 1 or len(created) != 1 or len(refused) != GUESTS - 1:
        sys.exit("FAIL: more than one guest was given the same table")
    print("PASS: exactly one hold and exactly one reservation")


if __name__ == "__main__":
    main()
