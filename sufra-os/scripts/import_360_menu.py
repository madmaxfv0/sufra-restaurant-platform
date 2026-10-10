"""Import SUFRA 360's menu into NOVA, so the OS owns one menu.

SUFRA 360 shipped its own venue/menu.json. NOVA is the source of truth for
operational data, and the kitchen rail, menu admin, guest ordering and menu
engineering all read MenuItem - so the 360 dishes have to become real
MenuItem rows rather than live in a second file.

Idempotent: matches on dish name, updates in place if present, inserts if
not. Existing NOVA dishes are left alone; open orders reference them by
foreign key, so deleting them would break live tickets.

    python3 scripts/import_360_menu.py path/to/menu.json
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.database import engine
from app.models import MenuItem, Station

MENU_360 = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None

# 360 section id -> NOVA course
COURSE = {"starters": "Starter", "mains": "Main", "desserts": "Dessert",
          "sides": "Side", "drinks": "Drink", "snacks": "Snack"}

# 360's "hero" (what the dish is built around) is the best signal available
# for which section actually cooks it.
STATION = {"veg": Station.COLD, "fish": Station.HOT, "meat": Station.GRILL,
           "lamb": Station.GRILL, "beef": Station.GRILL, "chicken": Station.GRILL,
           "pastry": Station.PASTRY, "sweet": Station.PASTRY, "drink": Station.BAR}


def main():
    if MENU_360 is None:
        print("usage: python3 scripts/import_360_menu.py path/to/menu.json", file=sys.stderr)
        return 2
    if not MENU_360.exists():
        print(f"!! {MENU_360} not found", file=sys.stderr)
        return 1
    data = json.loads(MENU_360.read_text())

    added = updated = 0
    with Session(engine) as s:
        for section in data.get("sections", []):
            course = COURSE.get(section.get("id"), "Main")
            for d in section.get("dishes", []):
                name = d["name"]
                # tags carries diet and allergens together - that is exactly
                # what NOVA's comma-separated tags field is documented to hold,
                # and what the kitchen rail surfaces as allergen warnings.
                tags = sorted(set(d.get("diet", []) + d.get("allergens", []) + d.get("tags", [])))
                station = STATION.get(d.get("hero", ""), Station.HOT)
                if course == "Dessert":
                    station = Station.PASTRY

                row = s.exec(select(MenuItem).where(MenuItem.name == name)).first()
                if row:
                    row.course, row.price = course, float(d.get("price", 0))
                    row.blurb, row.tags, row.station = d.get("blurb", ""), ",".join(tags), station
                    s.add(row)
                    updated += 1
                else:
                    s.add(MenuItem(
                        name=name, course=course, station=station,
                        price=float(d.get("price", 0)),
                        food_cost=round(float(d.get("price", 0)) * 0.30, 2),
                        blurb=d.get("blurb", ""), tags=",".join(tags),
                        available=True, base_minutes=14 if course == "Main" else 9,
                        hue={"Starter": 96, "Main": 18, "Dessert": 320}.get(course, 150),
                    ))
                    added += 1
        s.commit()

    print(f"SUFRA 360 menu imported into NOVA: {added} added, {updated} updated")
    with Session(engine) as s:
        total = len(s.exec(select(MenuItem)).all())
    print(f"NOVA now carries {total} dishes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
