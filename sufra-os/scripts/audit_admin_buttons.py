"""Audit every SUFRA OS admin page for button layout defects.

Needs a running server on port 8123 and a staff PIN in the environment:

    SUFRA_AUDIT_PIN=<an admin PIN from your seed printout> python3 scripts/audit_admin_buttons.py

Checks each button for three concrete, measurable failures rather than
eyeballing screenshots:
  overflow  - the button extends past its nearest card/section ancestor
  clipped   - the button's own text is wider than the button (scrollWidth)
  overlap   - two buttons' rects intersect
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

PAGES = ["", "operations", "floor", "reservations", "booking-control", "orders",
         "kitchen", "menu", "inventory", "guests", "staff", "hr", "executive",
         "analytics", "finance", "accounting", "qr", "suppliers", "events",
         "copilot", "settings"]

CHECK = """() => {
  const out = [];
  const btns = [...document.querySelectorAll('button, .btn')].filter(b => {
    const r = b.getBoundingClientRect();
    const cs = getComputedStyle(b);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  });
  const label = b => (b.textContent || '').trim().slice(0, 34) || '(icon)';
  for (const b of btns) {
    const r = b.getBoundingClientRect();
    // nearest meaningful container
    let host = b.parentElement;
    while (host && !/card|section|panel|modal|rail|row|head/i.test(host.className || '')
           && host !== document.body) host = host.parentElement;
    if (host && host !== document.body) {
      const hr = host.getBoundingClientRect();
      const over = Math.round(Math.max(r.right - hr.right, hr.left - r.left));
      if (over > 2) out.push({ type: 'overflow', px: over, label: label(b),
                               cls: (b.className||'').slice(0,40), host: (host.className||'').slice(0,40) });
    }
    const absKid = [...b.children].some(c => getComputedStyle(c).position === 'absolute');
    if (!absKid && b.scrollWidth - b.clientWidth > 2)
      out.push({ type: 'clipped', px: b.scrollWidth - b.clientWidth, label: label(b),
                 cls: (b.className||'').slice(0,40) });
  }
  for (let i = 0; i < btns.length; i++) for (let j = i + 1; j < btns.length; j++) {
    const a = btns[i].getBoundingClientRect(), c = btns[j].getBoundingClientRect();
    const ox = Math.min(a.right, c.right) - Math.max(a.left, c.left);
    const oy = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top);
    if (ox > 3 && oy > 3 && !btns[i].contains(btns[j]) && !btns[j].contains(btns[i]))
      out.push({ type: 'overlap', px: Math.round(Math.min(ox, oy)),
                 label: label(btns[i]) + ' vs ' + label(btns[j]),
                 cls: (btns[i].parentElement?.className||'').slice(0,40) });
  }
  return { buttons: btns.length, issues: out };
}"""


def main():
    if "SUFRA_AUDIT_PIN" not in os.environ:
        sys.exit("Set SUFRA_AUDIT_PIN to the PIN of an admin account (see the seed printout).")
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1600
    req = urllib.request.Request("http://127.0.0.1:8123/api/auth/login",
        data=json.dumps({"staff_id": int(os.environ.get("SUFRA_AUDIT_STAFF_ID", "1")),
                         "pin": os.environ["SUFRA_AUDIT_PIN"]}).encode(),
        headers={"Content-Type": "application/json"})
    auth = json.loads(urllib.request.urlopen(req).read())

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": width, "height": 1000})
        page.goto("http://127.0.0.1:8123/admin", wait_until="load", timeout=60000)
        page.evaluate("""(a) => { for (const s of [sessionStorage, localStorage]) {
            s.setItem('nova-admin-token', a.token);
            s.setItem('nova-admin-staff', JSON.stringify(a.staff));
            s.setItem('nova-admin-perms', JSON.stringify(a.permissions)); } }""", auth)
        total = 0
        for p in PAGES:
            try:
                page.goto(f"http://127.0.0.1:8123/admin/{p}", wait_until="load", timeout=45000)
                page.wait_for_timeout(3500)
                r = page.evaluate(CHECK)
            except Exception as e:
                print(f"{p or '(command centre)':18} ERROR {str(e)[:60]}")
                continue
            issues = r["issues"]
            total += len(issues)
            flag = "OK " if not issues else f"{len(issues):2d} "
            print(f"{flag}{p or '(command centre)':18} buttons={r['buttons']:3d}")
            for i in issues[:6]:
                print(f"      {i['type']:8} {i.get('px','')}px  {i['label']}"
                      + (f"  [{i.get('cls','')}]" if i.get('cls') else ""))
        print(f"\nTOTAL ISSUES at {width}px: {total}")
        b.close()


if __name__ == "__main__":
    main()
