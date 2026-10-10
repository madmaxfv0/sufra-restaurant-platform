"""Allergen inspection: what a guest declared, and what is on the plate.

Two halves that have to meet in the middle.

A guest writes free text — "walnuts", "Nuts", "no shellfish please", and in
a booking note as often as in the allergy field. The kitchen labels dishes
with a fixed vocabulary of tags, and recipes name real ingredients
("Scallops", "Double cream"). This module maps the first onto the second so
that ordering a pistachio cannolo for a table that said "nuts" is caught
before the ticket reaches the pass.

Two rules it will not bend:

  * an allergy this vocabulary cannot parse is reported as UNRECOGNISED,
    never silently passed as clear. "Soy" and "fv" both fail to match; the
    first is a real allergy we do not model and the second is a typo, and
    the only safe thing either can do is put it in front of a person.
  * a dish is screened on its tags AND on its recipe. Tags are the label;
    ingredients are the truth. A dish containing scallops is flagged as
    shellfish whether or not anybody remembered to tag it.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from sqlmodel import Session, select

from .models import (DiningTable, Guest, Ingredient, MenuItem, RecipeLine,
                     Reservation, TableNote)

# Canonical allergens. The keys are exactly the tags the kitchen already puts
# on MenuItem.tags, so a match here is a match on the real menu. Synonyms
# cover how guests actually write it, in the three languages the restaurant
# takes bookings in.
ALLERGENS: dict[str, dict] = {
    "nuts": {
        "label": "nuts",
        "words": ["nut", "nuts", "peanut", "peanuts", "almond", "almonds",
                  "walnut", "walnuts", "pistachio", "pistachios", "cashew",
                  "cashews", "hazelnut", "hazelnuts", "pecan", "pecans",
                  "macadamia", "praline", "marzipan", "nutty",
                  "qoz", "fındıq", "badam", "püstə",
                  "орех", "орехи", "орехов", "арахис", "фундук", "миндаль", "фисташки"],
    },
    "gluten": {
        "label": "gluten",
        "words": ["gluten", "wheat", "flour", "barley", "rye", "bread",
                  "pasta", "celiac", "coeliac", "breadcrumb", "breadcrumbs",
                  "qlüten", "buğda", "un",
                  "глютен", "пшеница", "мука", "клейковина"],
    },
    "dairy": {
        "label": "dairy",
        "words": ["dairy", "milk", "lactose", "cream", "butter", "yoghurt",
                  "yogurt", "creme", "crème", "mascarpone",
                  "süd", "laktoza", "qaymaq", "kərə",
                  "молоко", "молочное", "лактоза", "сливки", "масло", "сливочное"],
    },
    "cheese": {
        "label": "cheese",
        "words": ["cheese", "parmesan", "burrata", "mozzarella", "comté",
                  "comte", "pecorino", "gorgonzola", "feta",
                  "pendir", "сыр", "сыра", "пармезан"],
    },
    "egg": {
        "label": "egg",
        "words": ["egg", "eggs", "yolk", "albumen", "mayonnaise",
                  "yumurta", "яйцо", "яйца", "яиц", "яичный"],
    },
    "fish": {
        "label": "fish",
        "words": ["fish", "salmon", "tuna", "anchovy", "anchovies", "cod",
                  "bass", "sole", "turbot", "mackerel", "sardine", "caviar",
                  "balıq", "nərə", "рыба", "рыбу", "лосось", "тунец", "икра"],
    },
    "shellfish": {
        "label": "shellfish",
        "words": ["shellfish", "seafood", "shrimp", "shrimps", "prawn",
                  "prawns", "crab", "lobster", "scallop", "scallops",
                  "oyster", "oysters", "mussel", "mussels", "clam", "clams",
                  "squid", "octopus", "calamari", "crustacean", "crustaceans",
                  "karides", "xərçəng", "istiridyə",
                  "морепродукты", "креветки", "краб", "омар", "мидии", "устрицы", "гребешки"],
    },
    "sesame": {
        "label": "sesame",
        "words": ["sesame", "tahini", "küncüt", "kunjut",
                  "кунжут", "кунжута", "тахини"],
    },
    "citrus": {
        "label": "citrus",
        "words": ["citrus", "lemon", "lime", "orange", "grapefruit",
                  "sitrus", "limon", "portağal",
                  "цитрус", "цитрусовые", "лимон", "апельсин", "лайм"],
    },
}

# Written where an allergy field is offered, meaning "I have none".
NOTHING = {"", "-", "--", "n/a", "na", "no", "none", "nil", "nothing",
           "no allergies", "yox", "yoxdur", "нет", "нету", "никаких", "ничего"}

# Words that mark free text as being ABOUT an allergy, used when scanning a
# booking's notes rather than its allergy field.
ALLERGY_CUES = ["allerg", "intoleran", "coeliac", "celiac", "anaphyla",
                "allergiya", "dözümsüzlük", "аллерг", "непереносим"]

_WORD_CACHE: dict[str, re.Pattern] = {}


def _pattern(word: str) -> re.Pattern:
    if word not in _WORD_CACHE:
        # Word boundaries keep "coconut" out of "nut" and "limonade" out of
        # "limon"; \w covers the Cyrillic and Azerbaijani letters too.
        _WORD_CACHE[word] = re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)",
                                       re.IGNORECASE | re.UNICODE)
    return _WORD_CACHE[word]


def parse(text: str) -> tuple[set[str], list[str]]:
    """Free text in; canonical allergens out, plus anything unrecognised.

    The second half matters as much as the first: a term we cannot map is
    an allergy we cannot screen for, and the caller has to say so.
    """
    raw = (text or "").strip()
    if not raw or raw.lower() in NOTHING:
        return set(), []

    found: set[str] = set()
    for key, spec in ALLERGENS.items():
        if any(_pattern(w).search(raw) for w in spec["words"]):
            found.add(key)

    # Anything left that looks like a word a guest meant, and that we did
    # not match, is reported rather than dropped.
    leftovers = []
    for term in re.split(r"[,;/•\n]+|\band\b|\bor\b", raw):
        term = term.strip(" .!-()")
        if not term or term.lower() in NOTHING or len(term) < 2:
            continue
        if any(_pattern(w).search(term) for key in found for w in ALLERGENS[key]["words"]):
            continue
        if any(cue in term.lower() for cue in ALLERGY_CUES) and len(term.split()) <= 2:
            continue                       # "allergy:" style labels, not a term
        leftovers.append(term)
    return found, leftovers


def looks_like_allergy(text: str) -> bool:
    """Does this free-text note appear to be declaring an allergy at all?"""
    low = (text or "").lower()
    return any(cue in low for cue in ALLERGY_CUES)


# ----------------------------------------------------------- what the guest said

def declared_for_table(s: Session, table_id: int) -> dict:
    """Every allergy attached to this table right now, and where it came from.

    Sources, in the order a waiter would trust them: what a member of staff
    wrote on the table during service, what the guest put on the booking,
    and what the CRM remembers about that guest.
    """
    entries: list[dict] = []
    seen: set[tuple] = set()

    def add(term: str, source: str, who: str, note_id: Optional[int] = None,
            acknowledged: bool = True) -> None:
        allergens, unknown = parse(term)
        if not allergens and not unknown:
            return
        key = (term.strip().lower(), source)
        if key in seen:
            return
        seen.add(key)
        entries.append({"term": term.strip(), "allergens": sorted(allergens),
                        "unrecognised": unknown, "source": source, "who": who,
                        "note_id": note_id, "acknowledged": acknowledged})

    for n in s.exec(select(TableNote).where(
            TableNote.table_id == table_id, TableNote.kind == "allergy")).all():
        add(n.message, "table note", n.author_name or "Staff", n.id, n.acknowledged)

    from .bookings import seated_reservation_on
    r = seated_reservation_on(s, table_id)
    if r is None:
        from .rtime import now as _now
        from datetime import timedelta
        rows = s.exec(select(Reservation).where(
            Reservation.table_id == table_id,
            Reservation.starts_at >= _now() - timedelta(hours=4),
            Reservation.starts_at <= _now() + timedelta(hours=2))).all()
        live = [x for x in rows if (x.status or "") in ("confirmed", "late", "seated")]
        r = live[0] if live else None

    guest_name = ""
    if r is not None:
        guest_name = (" ".join(x for x in [r.first_name, r.last_name] if x)).strip() or "Guest"
        add(r.allergies or "", "booking", guest_name)
        # A guest as often writes it in the notes as in the allergy field.
        for free in (r.special_request or "", r.note or "", r.dietary or ""):
            if looks_like_allergy(free):
                add(free, "booking note", guest_name)

    table = s.get(DiningTable, table_id)
    guest = s.get(Guest, table.guest_id) if table and table.guest_id else None
    if guest is None and r is not None and r.guest_id:
        guest = s.get(Guest, r.guest_id)
    if guest is not None:
        add(guest.allergies or "", "guest profile", guest.name or guest_name or "Guest")

    allergens = sorted({a for e in entries for a in e["allergens"]})
    unrecognised = sorted({u for e in entries for u in e["unrecognised"]})
    return {
        "entries": entries,
        "allergens": allergens,
        "unrecognised": unrecognised,
        "unacknowledged": [e for e in entries if not e["acknowledged"]],
        "guest": guest_name,
        "any": bool(entries),
    }


# -------------------------------------------------------- what is on the plate

def dish_allergens(s: Session, item: MenuItem,
                   recipes: Optional[dict[int, list[str]]] = None) -> dict:
    """What this dish contains, from its tags and from its actual recipe."""
    tags = {t.strip().lower() for t in (item.tags or "").split(",") if t.strip()}
    from_tags = {t for t in tags if t in ALLERGENS}

    names = recipes.get(item.id, []) if recipes is not None else _recipe_names(s, item.id)
    from_recipe: dict[str, list[str]] = {}
    for name in names:
        hits, _ = parse(name)
        for key in hits:
            from_recipe.setdefault(key, []).append(name)

    return {"tags": sorted(from_tags), "recipe": from_recipe,
            "all": sorted(from_tags | set(from_recipe))}


def _recipe_names(s: Session, menu_item_id: int) -> list[str]:
    lines = s.exec(select(RecipeLine).where(RecipeLine.menu_item_id == menu_item_id)).all()
    if not lines:
        return []
    ids = [l.ingredient_id for l in lines]
    return [i.name for i in s.exec(select(Ingredient).where(Ingredient.id.in_(ids))).all()]


def recipe_index(s: Session) -> dict[int, list[str]]:
    """Every dish's ingredient names in one pass, for screening a whole order."""
    names = {i.id: i.name for i in s.exec(select(Ingredient)).all()}
    out: dict[int, list[str]] = {}
    for line in s.exec(select(RecipeLine)).all():
        if line.ingredient_id in names:
            out.setdefault(line.menu_item_id, []).append(names[line.ingredient_id])
    return out


# ------------------------------------------------------------------ the check

def screen(s: Session, table_id: int, item_ids: Iterable[int]) -> dict:
    """Check a set of dishes against everything this table has declared."""
    declared = declared_for_table(s, table_id)
    ids = [int(i) for i in item_ids if i]
    if not ids:
        return {"conflicts": [], "declared": declared, "blocked": False,
                "unrecognised": declared["unrecognised"]}

    items = {m.id: m for m in s.exec(select(MenuItem).where(MenuItem.id.in_(ids))).all()}
    recipes = recipe_index(s)
    wanted = set(declared["allergens"])

    conflicts = []
    for item_id in dict.fromkeys(ids):            # preserve order, drop repeats
        item = items.get(item_id)
        if not item:
            continue
        found = dish_allergens(s, item, recipes)
        clash = wanted & set(found["all"])
        if not clash:
            continue
        for allergen in sorted(clash):
            why = found["recipe"].get(allergen)
            # Attribute it to the shortest declaration that names this
            # allergen — "sesame" reads better than the whole note it was
            # copied into, and the full text is kept alongside.
            who = sorted((e for e in declared["entries"] if allergen in e["allergens"]),
                         key=lambda e: len(e["term"]))
            said = who[0] if who else None
            conflicts.append({
                "menu_item_id": item.id, "dish": item.name,
                "allergen": ALLERGENS[allergen]["label"],
                "evidence": ("contains " + ", ".join(why)) if why else "labelled on the menu",
                "declared_as": ALLERGENS[allergen]["label"],
                "declared_note": said["term"] if said else "",
                "declared_by": said["who"] if said else declared["guest"],
                "source": said["source"] if said else "booking",
            })
    return {"conflicts": conflicts, "declared": declared,
            "blocked": bool(conflicts),
            "unrecognised": declared["unrecognised"]}


def sentence(conflicts: list[dict]) -> str:
    """One line a waiter can read at a glance."""
    if not conflicts:
        return ""
    first = conflicts[0]
    head = "%s contains %s — %s declared %s" % (
        first["dish"], first["allergen"],
        first["declared_by"] or "this table", first["allergen"])
    if len(conflicts) > 1:
        head += " (and %d other clash%s)" % (len(conflicts) - 1,
                                             "" if len(conflicts) == 2 else "es")
    return head + "."
