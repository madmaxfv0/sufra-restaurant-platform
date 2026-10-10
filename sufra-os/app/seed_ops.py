"""
Seeds the operations layer on top of the service data in seed.py.

Kept separate because these tables answer a different question. seed.py
builds a restaurant that is open right now; this builds the business
around it — who supplies it, who works there, what it has been charged,
what is booked into the private room next month.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from .models import (
    AnalyticsEvent, Event, Guest, Ingredient, Location, MenuItem, Notification,
    Order, OrderItem, Payment, PriceHistory, PurchaseLine, PurchaseOrder, Role,
    Shift, Staff, Supplier, WaitlistEntry,
)

rng = random.Random(11)

LOCATIONS = [
    ("Waterfront", "Baku", 128, True),
    ("Old City", "Baku", 96, False),
    ("Sea Breeze", "Baku", 154, False),
    ("Ganja", "Ganja", 88, False),
]

SUPPLIERS = [
    ("Cornish Day Boats", "Fish", "orders@cornishdayboats.co.uk", 1, 94, 96),
    ("Billingsgate Prime", "Fish", "trade@billingsgateprime.com", 1, 88, 91),
    ("Turner & Son", "Butchery", "kev@turnerandson.co.uk", 2, 97, 98),
    ("Sapori d'Italia", "Dry & deli", "ciao@saporiditalia.it", 3, 92, 95),
    ("La Fromagerie", "Cheese", "wholesale@lafromagerie.co.uk", 2, 96, 99),
    ("Neal's Yard", "Dairy", "trade@nealsyarddairy.co.uk", 2, 95, 97),
    ("Covent Garden Greens", "Produce", "market@cgreens.co.uk", 1, 85, 88),
    ("Wild Harvest", "Foraged", "hello@wildharvest.co.uk", 2, 79, 94),
    ("Valrhona", "Pastry", "uk@valrhona.com", 4, 99, 99),
    ("Berry Bros", "Cellar", "restaurant@bbr.com", 3, 98, 99),
    ("Clarence Court", "Eggs", "sales@clarencecourt.co.uk", 2, 96, 97),
    ("Asia Foods", "Dry", "orders@asiafoods.co.uk", 3, 83, 86),
    ("Levant Supply", "Dry", "info@levantsupply.co.uk", 4, 81, 90),
    ("Attilus", "Caviar", "concierge@attilus.com", 5, 99, 100),
    ("Shipton Mill", "Flour", "trade@shipton-mill.com", 3, 94, 97),
    ("Tartufi Bianchi", "Truffle", "ordini@tartufibianchi.it", 2, 76, 93),
    ("Assembly Roast", "Coffee", "wholesale@assemblycoffee.co.uk", 2, 97, 96),
    ("Carlingford", "Shellfish", "oysters@carlingford.ie", 2, 90, 95),
    ("In-house", "In-house", "", 0, 100, 100),
]

EVENT_NAMES = [
    ("Farraday wedding rehearsal", "Private dining", 18, 145.0),
    ("Meridian Capital year end", "Private dining", 24, 190.0),
    ("Okonkwo 60th birthday", "Terrace", 32, 120.0),
    ("Vintners' tasting dinner", "Cellar room", 14, 240.0),
    ("Halcyon Films wrap party", "Whole restaurant", 90, 110.0),
    ("Dr Reyes retirement lunch", "Private dining", 20, 95.0),
    ("Byrne christening lunch", "Terrace", 26, 88.0),
]

WAITLIST = [
    ("Delacroix", 2, 15), ("Hoffman", 4, 35), ("Nakamura", 2, 15),
    ("O'Sullivan", 6, 55), ("Petrov", 3, 25),
]


def build_ops(s: Session) -> None:
    today = date.today()
    now = datetime.now()

    # --- locations -------------------------------------------------
    for name, city, seats, home in LOCATIONS:
        s.add(Location(name=name, city=city, seats=seats, is_home=home,
                       currency="₼"))

    # --- suppliers, linked back to the ingredients that name them --
    for name, cat, contact, lead, rel, qual in SUPPLIERS:
        s.add(Supplier(name=name, category=cat, contact=contact,
                       lead_time_days=lead, reliability=rel, quality=qual))
    s.commit()

    sup_by_name = {x.name: x for x in s.exec(select(Supplier)).all()}
    ingredients = s.exec(select(Ingredient)).all()
    for ing in ingredients:
        sup = sup_by_name.get(ing.supplier)
        if sup:
            ing.supplier_id = sup.id
            s.add(ing)
    s.commit()

    # --- six months of ingredient prices ---------------------------
    # Most drift gently. A few move sharply so the supplier screen has
    # something worth flagging.
    volatile = {"Sea bass fillet", "Native lobster", "Black truffle",
                "Avocado", "Butter, cultured", "Ribeye, dry aged"}
    for ing in ingredients:
        price = ing.cost_per_unit * rng.uniform(0.82, 0.95)
        for weeks_back in range(26, -1, -1):
            drift = rng.gauss(0.004, 0.012)
            if ing.name in volatile:
                drift += rng.gauss(0.008, 0.03)
            price = max(0.05, price * (1 + drift))
            s.add(PriceHistory(ingredient_id=ing.id, supplier_id=ing.supplier_id,
                               price=round(price, 3),
                               on_day=today - timedelta(weeks=weeks_back)))
        ing.cost_per_unit = round(price, 2)
        s.add(ing)
    s.commit()

    # --- purchase orders, past and pending -------------------------
    for back in range(21, -1, -3):
        sup = rng.choice([x for x in sup_by_name.values() if x.name != "In-house"])
        theirs = [i for i in ingredients if i.supplier_id == sup.id]
        if not theirs:
            continue
        po = PurchaseOrder(
            supplier_id=sup.id,
            created_at=now - timedelta(days=back),
            deliver_on=today - timedelta(days=back - sup.lead_time_days),
            status="delivered" if back > 2 else rng.choice(["sent", "draft"]),
            raised_by=rng.choice(["SUFRA", "Elena Rossi", "Marcus Bell"]))
        s.add(po)
        s.commit()
        s.refresh(po)
        total = 0.0
        for ing in rng.sample(theirs, min(len(theirs), rng.randint(2, 5))):
            qty = round(max(0.5, ing.par_level * rng.uniform(0.3, 0.9)), 2)
            total += qty * ing.cost_per_unit
            s.add(PurchaseLine(order_id=po.id, ingredient_id=ing.id, qty=qty,
                               unit_price=ing.cost_per_unit))
        po.total = round(total, 2)
        s.add(po)
    s.commit()

    # --- rotas: last week, this week, next week --------------------
    staff = s.exec(select(Staff)).all()
    for i, member in enumerate(staff):
        # PIN and pin_hash are already set in seed.py — this pass only adds
        # the operational detail (rate, rating, tenure) on top.
        member.hourly_rate = {
            Role.OWNER: 0.0, Role.GENERAL_MANAGER: 30.0, Role.RESTAURANT_MANAGER: 24.0,
            Role.HOST: 15.5, Role.WAITER: 14.5, Role.KITCHEN: 18.0,
            Role.BARTENDER: 16.0, Role.CASHIER: 14.0, Role.INVENTORY_MANAGER: 19.0,
        }[member.role]
        member.rating = round(rng.uniform(3.6, 4.9), 1)
        member.started_on = today - timedelta(days=rng.randint(60, 1800))
        s.add(member)

        for offset in range(-7, 8):
            day = today + timedelta(days=offset)
            if day.weekday() == rng.choice([0, 1, 2]):
                continue                                    # everyone gets days off
            if rng.random() < 0.18:
                continue
            lunch = rng.random() < 0.35
            s.add(Shift(
                staff_id=member.id, day=day, role=member.role,
                start_hour=11.5 if lunch else 16.5,
                end_hour=16.0 if lunch else 23.5,
                status=("holiday" if rng.random() < 0.04 else
                        "sick" if rng.random() < 0.03 else
                        "confirmed" if offset <= 0 else "scheduled")))
    s.commit()

    # --- events ----------------------------------------------------
    guests = s.exec(select(Guest)).all()
    for i, (name, room, size, per_head) in enumerate(EVENT_NAMES):
        when = now + timedelta(days=rng.randint(-10, 60),
                               hours=rng.choice([-3, 0, 2, 4]))
        s.add(Event(
            name=name, room=room, party_size=size, per_head=per_head,
            guest_id=rng.choice(guests).id,
            starts_at=when.replace(hour=rng.choice([12, 18, 19]), minute=0,
                                   second=0, microsecond=0),
            deposit=round(size * per_head * 0.3, 2),
            status=("delivered" if when < now else
                    rng.choices(["confirmed", "enquiry"], [4, 1])[0]),
            contact=f"{name.split()[0].lower()}@example.com",
            menu_note=rng.choice([
                "Two vegans, one coeliac. No shellfish on the canapés.",
                "Set menu B, wine flight upgraded to the Burgundy pairing.",
                "Cake brought in, needs plating and candles at 21:30.",
                "Speeches between main and dessert. Hold service twenty minutes.",
            ])))
    s.commit()

    # --- waitlist --------------------------------------------------
    for name, size, quoted in WAITLIST:
        s.add(WaitlistEntry(name=name, party_size=size, quoted_minutes=quoted,
                            phone=f"+44 7{rng.randint(100, 999)} {rng.randint(100000, 999999)}",
                            added_at=now - timedelta(minutes=rng.randint(2, 40))))

    # --- payments against today's closed orders --------------------
    closed = s.exec(select(Order).where(Order.paid == True)).all()  # noqa: E712
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    for o in closed:
        items = s.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
        total = sum(menu[i.menu_item_id].price * i.qty for i in items if i.menu_item_id in menu)
        if not total:
            continue
        kind = rng.choices(["full", "equal", "item", "custom"], [52, 30, 12, 6])[0]
        splits = 1 if kind == "full" else rng.randint(2, 4)
        for n in range(splits):
            share = round(total / splits, 2)
            s.add(Payment(order_id=o.id, amount=share,
                          tip=round(share * rng.uniform(0.05, 0.15), 2),
                          method=rng.choices(["card", "applepay", "googlepay", "cash", "qr"],
                                             [44, 26, 12, 8, 10])[0],
                          kind=kind, payer=f"Guest {n + 1} of {splits}",
                          created_at=o.closed_at or now,
                          reference=f"NV{rng.randint(100000, 999999)}"))
    s.commit()

    # --- notifications ---------------------------------------------
    seeds = [
        ("warning", "Walk-in fridge running warm", "Fish fridge at 6.2°C for eleven minutes. Engineer notified.", "manager"),
        ("note", "New five-star review", "“The turbot was the best thing I ate all year.” — Google", "manager"),
        ("critical", "Card terminal 2 offline", "Reconnect or move that section to terminal 1.", "manager"),
        ("good", "Covers passed 200 before 21:00", "Best Saturday pace in six weeks.", "all"),
        ("note", "Rota published for next week", "Nine people still to confirm.", "waiter"),
        ("warning", "Truffle price up 14% in a fortnight", "Tartufi Bianchi. Worth pricing the tagliatelle again.", "manager"),
    ]
    for i, (level, title, body, aud) in enumerate(seeds):
        s.add(Notification(level=level, title=title, body=body, audience=aud,
                           read=i > 3, created_at=now - timedelta(minutes=i * 27 + 4)))

    for i in range(400):
        s.add(AnalyticsEvent(at=now - timedelta(hours=i * 3),
                             kind=rng.choice(["page_view", "order_sent", "table_seated",
                                              "copilot_query", "menu_scan"]),
                             value=round(rng.uniform(1, 90), 2)))
    s.commit()
    print("Seeded ops: 4 locations, 19 suppliers, 6 months of prices, rotas, "
          "events, payments, waitlist, notifications.")
