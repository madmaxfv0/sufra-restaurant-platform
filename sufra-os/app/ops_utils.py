from sqlmodel import Session, select
from .models import AvailabilityFlag, MenuArchive, MenuSection, RecipeLine

ARCHIVED_ZONE = "__ARCHIVED__"


def archived_menu_ids(s: Session) -> set[int]:
    return {r.menu_item_id for r in s.exec(select(MenuArchive).where(MenuArchive.active == True)).all()}  # noqa: E712


def unavailable_menu_ids(s: Session) -> tuple[set[int], dict[int, str]]:
    blocked = set(archived_menu_ids(s))
    reasons: dict[int, str] = {i: "Removed from menu" for i in blocked}
    flags = s.exec(select(AvailabilityFlag).where(AvailabilityFlag.active == True)).all()  # noqa: E712
    ingredient_ids = set()
    for f in flags:
        if f.kind == "menu_item":
            blocked.add(f.ref_id)
            reasons[f.ref_id] = f.note or f"{f.label} unavailable"
        elif f.kind == "ingredient":
            ingredient_ids.add(f.ref_id)
    if ingredient_ids:
        for line in s.exec(select(RecipeLine).where(RecipeLine.ingredient_id.in_(ingredient_ids))).all():
            blocked.add(line.menu_item_id)
        for f in flags:
            if f.kind != "ingredient":
                continue
            for line in s.exec(select(RecipeLine).where(RecipeLine.ingredient_id == f.ref_id)).all():
                reasons[line.menu_item_id] = f.note or f"Ingredient unavailable: {f.label}"
    return blocked, reasons


def menu_sections(s: Session) -> list[str]:
    rows=s.exec(select(MenuSection).where(MenuSection.active == True).order_by(MenuSection.sort_order, MenuSection.name)).all()  # noqa: E712
    return [r.name for r in rows]
