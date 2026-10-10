"""
NOVA Restaurant OS — data model.

One file, one job: describe the restaurant as tables in a database.
SQLModel gives us a Python class and a SQL table from the same definition,
so `Table.status` is both a column and an attribute you can type-check.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------- enums
# Enums instead of loose strings. If a typo can't compile, it can't ship.


class Role(str, Enum):
    OWNER = "owner"
    GENERAL_MANAGER = "general_manager"
    RESTAURANT_MANAGER = "restaurant_manager"
    HOST = "host"
    WAITER = "waiter"
    BARTENDER = "bartender"
    KITCHEN = "kitchen"
    CASHIER = "cashier"
    INVENTORY_MANAGER = "inventory_manager"


class TableStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SEATED = "seated"
    ORDERING = "ordering"
    COOKING = "cooking"
    READY = "ready"          # food is at the pass, nobody has carried it
    DINING = "dining"
    NEEDS_WAITER = "needs_waiter"
    BILL = "bill"
    CLEANING = "cleaning"


class Station(str, Enum):
    GRILL = "grill"
    HOT = "hot"
    COLD = "cold"
    PASTRY = "pastry"
    BAR = "bar"


class ItemState(str, Enum):
    QUEUED = "queued"
    COOKING = "cooking"
    READY = "ready"
    SERVED = "served"


class TaskKind(str, Enum):
    CALL = "call"            # guest pressed "call waiter"
    WATER = "water"
    CUTLERY = "cutlery"
    BILL = "bill"
    RUNNER = "runner"        # food ready, needs carrying
    CLEAR = "clear"
    CHECKIN = "checkin"      # nobody has spoken to this table in a while


# ---------------------------------------------------------------- people & rooms


class Staff(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    role: Role = Role.WAITER
    avatar: str = "🙂"
    on_shift: bool = True
    section: str = ""            # "A", "Front Desk", "Bar" — where relevant
    covers_served: int = 0
    avg_service_seconds: int = 0
    hourly_rate: float = 14.5
    rating: float = 4.5
    started_on: Optional[date] = None

    # ---- authentication -------------------------------------------
    # The PIN itself is never stored. pin_hash is "salt$hash" from
    # security.hash_pin(). Provisioning responses reveal new PINs once;
    # ordinary profile responses never include credentials.
    pin_hash: str = ""
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None
    last_login: Optional[datetime] = None


class StaffBadgeCopy(SQLModel, table=True):
    """Encrypted badge copy that an administrator can reopen or print."""
    staff_id: int = Field(primary_key=True, foreign_key="staff.id")
    encrypted_token: str


class StaffQR(SQLModel, table=True):
    """Only a digest of the encrypted badge is retained; rotation revokes it."""
    staff_id: int = Field(primary_key=True, foreign_key="staff.id")
    token_hash: str = Field(index=True, unique=True)
    issued_at: datetime = Field(default_factory=datetime.now)


class AuthSession(SQLModel, table=True):
    """A signed-in device. The token is the primary key and doubles as
    the bearer credential the frontend sends back on every request."""

    token: str = Field(primary_key=True)
    staff_id: int = Field(foreign_key="staff.id")
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(default_factory=datetime.now)
    last_seen_at: datetime = Field(default_factory=datetime.now)


class AuditLog(SQLModel, table=True):
    """Anything a sensitive action touches gets a row here: who, what,
    on what, and when. Read by nobody yet in this build — the viewer
    screen is a later phase — but every action logs correctly from day one."""

    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now)
    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    action: str = ""              # "login", "login_failed", "void_item", ...
    entity_type: str = ""         # "order_item", "reservation", ...
    entity_id: Optional[int] = None
    detail: str = ""              # short human-readable note, not raw JSON


class DiningTable(SQLModel, table=True):
    """`table` is a reserved word in SQL, hence DiningTable."""

    id: Optional[int] = Field(default=None, primary_key=True)
    number: int
    seats: int = 2
    zone: str = "Main"       # Main | Terrace | Bar | Private
    x: float = 0.5           # 0..1 position on the floor plan
    y: float = 0.5
    shape: str = "round"     # round | square | banquette
    status: TableStatus = TableStatus.AVAILABLE
    party_size: int = 0
    waiter_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    seated_at: Optional[datetime] = None
    last_touched_at: Optional[datetime] = None   # last time a waiter interacted
    guest_id: Optional[int] = Field(default=None, foreign_key="guest.id")


class Guest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    visits: int = 1
    vip: bool = False
    allergies: str = ""
    likes: str = ""
    seating_pref: str = ""
    avg_spend: float = 0.0
    note: str = ""


class Reservation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    guest_id: Optional[int] = Field(default=None, foreign_key="guest.id")
    table_id: Optional[int] = Field(default=None, foreign_key="diningtable.id")
    party_size: int = 2
    starts_at: datetime
    status: str = "confirmed"    # confirmed | seated | cancelled | no_show
    occasion: str = ""
    note: str = ""
    deposit: float = 0.0
    source: str = "website"      # website | phone | walk-in | instagram | concierge
    created_at: datetime = Field(default_factory=datetime.now)
    no_show_risk: float = 0.0    # filled in by intelligence.py
    duration_minutes: int = 105   # booking slot incl. dining time, before turnover buffer
    left_at: Optional[datetime] = None

    # ---- the guest's own booking, whichever surface took it ---------
    # Guest carries the standing CRM profile; these are the details of
    # THIS booking, so editing a reservation never rewrites a guest's
    # history and two bookings by the same person can differ.
    code: str = Field(default="", index=True)   # SF00042 — the booking reference
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    allergies: str = ""
    dietary: str = ""
    accessibility: str = ""
    high_chairs: int = 0
    special_request: str = ""
    preference: str = ""
    language: str = "en"          # en | az | ru, for confirmations and reminders
    marketing_opt_in: bool = False

    # ---- lifecycle stamps -------------------------------------------
    guest_confirmation_status: str = "pending"   # pending | confirmed
    guest_confirmed_at: Optional[datetime] = None
    confirm_token: str = ""
    reminder_sent_at: Optional[datetime] = None
    late_notified_at: Optional[datetime] = None
    seated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    no_show_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    idempotency_key: str = ""

    # ---- the restaurant's own answer to a booking it did not take ----
    # A table booked through SUFRA 360 or the website arrives without anybody
    # on the floor having seen it. "pending" means it is confirmed to the
    # guest but nobody here has looked at it yet; the book surfaces those
    # first so a manager can accept it or decline it while there is still
    # time to tell the guest.
    staff_decision: str = ""          # "" (taken by us) | pending | accepted | declined
    decided_at: Optional[datetime] = None
    decided_by: str = ""
    decline_reason: str = ""


# ---------------------------------------------------------------- menu & stock


class MenuItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    course: str = "Main"         # Snack | Starter | Main | Side | Dessert | Drink
    station: Station = Station.HOT
    price: float = 0.0
    food_cost: float = 0.0
    base_minutes: int = 12       # prep time on an empty kitchen
    blurb: str = ""
    tags: str = ""               # comma separated: vegan, gf, halal, nuts...
    protein_g: int = 0
    kcal: int = 0
    available: bool = True
    sold_30d: int = 0            # popularity, used by menu engineering
    hue: int = 150               # each dish gets a plate colour, generated not photographed
    spice: int = 0               # 0-3 chillies
    signature: bool = False


class Ingredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    name_ru: str = ""
    unit: str = "kg"
    in_stock: float = 0.0
    par_level: float = 0.0       # the level you never want to drop below
    cost_per_unit: float = 0.0
    supplier: str = ""
    supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id")
    store: str = "Dry store"
    expires_on: Optional[date] = None


class RecipeLine(SQLModel, table=True):
    """Per-portion ingredient quantity in Ingredient.unit (kg/l/count), never display grams."""

    id: Optional[int] = Field(default=None, primary_key=True)
    menu_item_id: int = Field(foreign_key="menuitem.id")
    ingredient_id: int = Field(foreign_key="ingredient.id")
    qty_per_portion: float = 0.0


# ---------------------------------------------------------------- service


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id")
    waiter_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    opened_at: datetime = Field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    paid: bool = False
    tip: float = 0.0


class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    menu_item_id: int = Field(foreign_key="menuitem.id")
    qty: int = 1
    note: str = ""
    seat: int = 0                # 0 = shared/unassigned, else 1..party_size
    course_no: int = 1           # groups items into course 1, course 2...
    state: ItemState = ItemState.QUEUED
    station: Station = Station.HOT
    fired_at: datetime = Field(default_factory=datetime.now)
    ready_at: Optional[datetime] = None
    promised_minutes: int = 12   # what the prediction model said when it fired
    void_reason: str = ""        # set if this line was cancelled after sending


class TableNote(SQLModel, table=True):
    """A note left on a table during service. Distinct from Guest.note,
    which is the guest's standing profile note — this is per-visit, and
    an allergy note here has to be acknowledged before an order can go
    out for that table."""

    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id")
    author_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    author_name: str = ""
    kind: str = "service"        # preference | allergy | kitchen | service | internal
    message: str = ""
    acknowledged: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id")
    kind: TaskKind = TaskKind.CALL
    message: str = ""
    priority: int = 2            # 1 high, 2 medium, 3 low
    created_at: datetime = Field(default_factory=datetime.now)
    done: bool = False
    claimed_by: Optional[int] = Field(default=None, foreign_key="staff.id")


class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    food: int = 5
    service: int = 5
    atmosphere: int = 5
    speed: int = 5
    comment: str = ""


class WasteLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    qty: float = 0.0
    reason: str = "overproduction"
    logged_on: date = Field(default_factory=date.today)
    # Added by SUFRA ANBAR. A waste figure nobody can attribute is a number,
    # not evidence — these turn the log into something a manager can act on.
    at: Optional[datetime] = None
    location_id: Optional[int] = None
    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    staff_name: str = ""
    unit_cost: float = 0.0
    cost_value: float = 0.0
    note: str = ""


class DayStat(SQLModel, table=True):
    """One row per past trading day. This is the training set for forecasting."""

    id: Optional[int] = Field(default=None, primary_key=True)
    day: date
    weekday: int = 0             # 0 = Monday
    covers: int = 0
    revenue: float = 0.0
    reservations: int = 0
    rain_mm: float = 0.0
    temp_c: float = 18.0
    is_holiday: bool = False
    local_event: bool = False


# ==================================================================== 
# Operations layer: everything the three apps need beyond service itself.
# Added as separate tables rather than columns so each has its own history.


class Location(SQLModel, table=True):
    """Multi-location. Owners switch between branches."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str = ""
    currency: str = "£"
    seats: int = 0
    is_home: bool = False


class Supplier(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category: str = "Produce"
    contact: str = ""
    lead_time_days: int = 1
    reliability: int = 90          # % of deliveries on time
    quality: int = 90              # % accepted without complaint
    notes: str = ""
    # Added by SUFRA ANBAR: the rest of a real supplier record.
    legal_name: str = ""
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    payment_terms: str = ""
    delivery_days: str = ""        # "Mon, Wed, Fri"
    min_order_value: float = 0.0
    preferred: bool = False
    active: bool = True


class PriceHistory(SQLModel, table=True):
    """Lets the app say 'salmon is up 11% over six weeks' with evidence."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id")
    price: float = 0.0
    on_day: date = Field(default_factory=date.today)


class PurchaseOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id")
    created_at: datetime = Field(default_factory=datetime.now)
    deliver_on: Optional[date] = None
    # draft | pending | approved | sent | partial | delivered | cancelled
    status: str = "draft"
    total: float = 0.0
    raised_by: str = "SUFRA"
    # Added by SUFRA ANBAR: approval trail and totals breakdown.
    code: str = ""                 # PO00042
    expected_on: Optional[date] = None
    subtotal: float = 0.0
    tax: float = 0.0
    note: str = ""
    created_by_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    approved_by: str = ""
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None


class PurchaseLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="purchaseorder.id")
    ingredient_id: int = Field(foreign_key="ingredient.id")
    qty: float = 0.0
    unit_price: float = 0.0
    # Added by SUFRA ANBAR. qty is in purchase_unit; qty_base is the same
    # amount normalised into the item's stock unit, which is what receiving
    # compares against so a case never gets subtracted from a kilogram.
    purchase_unit: str = ""
    qty_base: float = 0.0
    received_qty: float = 0.0
    note: str = ""


class Shift(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_id: int = Field(foreign_key="staff.id")
    day: date
    start_hour: float = 17.0
    end_hour: float = 23.5
    role: Role = Role.WAITER
    status: str = "scheduled"      # scheduled | confirmed | sick | holiday
    note: str = ""


class Event(SQLModel, table=True):
    """Private dining and functions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    guest_id: Optional[int] = Field(default=None, foreign_key="guest.id")
    starts_at: datetime
    party_size: int = 10
    room: str = "Private dining"
    deposit: float = 0.0
    per_head: float = 0.0
    status: str = "confirmed"      # enquiry | confirmed | delivered | cancelled
    menu_note: str = ""
    contact: str = ""


class Notification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    level: str = "note"            # critical | warning | note | good
    title: str = ""
    body: str = ""
    audience: str = "manager"      # manager | waiter | kitchen | all
    read: bool = False


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    amount: float = 0.0
    tip: float = 0.0
    method: str = "card"           # card | applepay | googlepay | cash | qr
    kind: str = "full"             # full | equal | item | custom
    payer: str = ""                # "Guest 2 of 4"
    created_at: datetime = Field(default_factory=datetime.now)
    reference: str = ""


class WaitlistEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    party_size: int = 2
    phone: str = ""
    added_at: datetime = Field(default_factory=datetime.now)
    quoted_minutes: int = 20
    status: str = "waiting"        # waiting | seated | left | called
    note: str = ""
    # A guest joining from SUFRA 360 lands in this same list — there is no
    # second waitlist — so it has to carry what that form collects.
    email: str = ""
    desired_at: Optional[datetime] = None
    area_pref: str = ""
    source: str = "walk-in"        # walk-in | sufra_360 | phone
    language: str = "en"
    converted_reservation_id: Optional[int] = None


class AnalyticsEvent(SQLModel, table=True):
    """Append-only log. Anything worth charting later gets written here."""

    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now)
    kind: str = ""
    ref: str = ""
    value: float = 0.0

# ====================================================================
# NOVA operations V10 — additive tables only. Existing tables/columns are
# deliberately untouched so this upgrade is safe against the current nova.db.

class OrderChange(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_item_id: int = Field(foreign_key="orderitem.id")
    table_id: int = Field(foreign_key="diningtable.id")
    requested_by: Optional[int] = Field(default=None, foreign_key="staff.id")
    kind: str = "modify"          # modify | void
    old_value: str = ""
    new_value: str = ""
    reason: str = ""
    status: str = "open"          # open | acknowledged
    created_at: datetime = Field(default_factory=datetime.now)
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = Field(default=None, foreign_key="staff.id")


class Complaint(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id")
    source: str = "guest"          # guest | waiter | admin
    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    category: str = "service"
    severity: str = "normal"       # normal | urgent
    message: str = ""
    status: str = "open"           # open | resolved
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = Field(default=None, foreign_key="staff.id")


class AvailabilityFlag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = "menu_item"        # menu_item | ingredient
    ref_id: int
    label: str = ""
    note: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: Optional[int] = Field(default=None, foreign_key="staff.id")


class TableArchive(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id")
    original_zone: str = "Main"
    archived_at: datetime = Field(default_factory=datetime.now)
    archived_by: Optional[int] = Field(default=None, foreign_key="staff.id")
    active: bool = True
    restored_at: Optional[datetime] = None


class MenuArchive(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    menu_item_id: int = Field(foreign_key="menuitem.id")
    archived_at: datetime = Field(default_factory=datetime.now)
    archived_by: Optional[int] = Field(default=None, foreign_key="staff.id")
    active: bool = True
    restored_at: Optional[datetime] = None


class MenuSection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sort_order: int = 50
    active: bool = True
    # A section a manager adds ("Business Lunch") needs a name in the
    # guest's own language same as any dish does. Blank means: no
    # translation on file yet, fall back to the English name.
    name_az: str = ""
    name_ru: str = ""


class TranslationCache(SQLModel, table=True):
    """Every phrase this restaurant has ever asked MyMemory/Google to
    translate, kept forever. The free translation APIs have small daily
    quotas shared across every SUFRA install calling from this network —
    burn through it once on a phrase and it is gone for the day. Once a
    phrase is translated here, it is never sent to either service again,
    so quota only gets spent on genuinely new text (a new dish, a new
    section name) rather than re-translating the same UI labels and
    menu items on every page load, for every browser, all day."""
    id: Optional[int] = Field(default=None, primary_key=True)
    source_lang: str
    target_lang: str
    source_text: str = Field(index=True)
    translated_text: str
    created_at: datetime = Field(default_factory=datetime.now)


class MenuContent(SQLModel, table=True):
    """Optional localized copy + photograph for a menu item.

    Kept in its own additive table so existing MenuItem rows and the current
    database schema never need a destructive migration.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    menu_item_id: int = Field(foreign_key="menuitem.id", index=True)
    image_url: str = ""
    image_source: str = "auto"       # auto | url | upload
    name_az: str = ""
    name_ru: str = ""
    blurb_az: str = ""
    blurb_ru: str = ""
    updated_at: datetime = Field(default_factory=datetime.now)


# ====================================================================
# SUFRA OS ↔ SUFRA 360 canonical layer. Additive only: nothing above is
# altered, so an existing nova.db upgrades in place. These tables are the
# single source of truth both applications read and write.


class TableProfile(SQLModel, table=True):
    """The 3D/scene description of a physical table.

    DiningTable stays the canonical operational record (id, number, seats,
    status). This row hangs the room's own geometry and character off that
    same id, so SUFRA 360 and SUFRA OS cannot disagree about what Table 12
    is. `scene_id` ("t12") is only a rendering handle — the canonical
    identifier is always DiningTable.number.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id", index=True, unique=True)
    scene_id: str = ""            # t01..t30, the 3D scene's own handle
    label: str = ""               # what the guest sees painted on the table
    area: str = ""                # garden | lounge | window | bar | east | private | terrace | main
    area_name: str = ""           # "Garden Court"
    area_blurb: str = ""
    outdoor: bool = False
    min_party: int = 1
    max_party: int = 2
    accessible: bool = True
    premium_view: bool = False
    blocked: bool = False         # taken out of service by a manager
    blocked_reason: str = ""
    shape: str = "round"
    map_x: float = 0.0
    map_y: float = 0.0
    map_w: float = 0.0
    map_h: float = 0.0
    rotation: float = 0.0
    world_x: float = 0.0
    world_y: float = 0.0
    world_z: float = 0.0
    tags: str = ""                # csv
    combinable: str = ""          # csv of scene ids
    scores: str = "{}"            # json
    distances: str = "{}"         # json
    bearings: str = "{}"          # json
    verification: str = "PLACEHOLDER"
    updated_at: datetime = Field(default_factory=datetime.now)


class TableHold(SQLModel, table=True):
    """A short courtesy hold while a guest fills in the booking form.

    A hold is never a guarantee: create_reservation re-checks inside the
    write transaction. Shared by both applications so two guests in two
    different front ends cannot both win the same table.
    """

    id: Optional[str] = Field(default=None, primary_key=True)
    table_id: int = Field(foreign_key="diningtable.id", index=True)
    starts_at: datetime
    duration_minutes: int = 105
    party_size: int = 2
    session_id: str = ""
    status: str = "held"          # held | released | expired | converted
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)
    source: str = "sufra_360"


class LiveEvent(SQLModel, table=True):
    """The one operational activity stream.

    Every real state change appends a row here — from either application,
    from any process. Each server tails the table and pushes new rows to
    its own websocket clients, which is what makes SUFRA OS and SUFRA 360
    live with each other across process boundaries. Nothing writes a row
    unless something actually happened.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)
    kind: str = ""                # reservation_created | guest_seated | table_free | ...
    title: str = ""               # already-composed English line
    title_az: str = ""
    title_ru: str = ""
    detail: str = ""
    table_id: Optional[int] = None
    table_number: Optional[int] = None
    reservation_id: Optional[int] = None
    waitlist_id: Optional[int] = None
    actor: str = ""               # staff name, or "SUFRA 360", or "SUFRA"
    source: str = "sufra_os"      # sufra_os | sufra_360 | automation
    audience: str = "staff"       # staff | manager | all
    severity: str = "note"        # note | good | warning | critical


class NotifyLog(SQLModel, table=True):
    """Every message the system tried to send, and what really happened.

    `status` is never "sent" unless a provider accepted it. When no
    provider is configured the row says so explicitly, and the API surfaces
    that instead of pretending.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now)
    channel: str = "email"        # email | sms
    address: str = ""
    template: str = ""            # confirmation | reminder | late | updated
    language: str = "en"
    reservation_id: Optional[int] = None
    status: str = "queued"        # sent | failed | not_configured
    detail: str = ""


class RestaurantSetting(SQLModel, table=True):
    """Small key/value store for venue identity and service policy.

    Keeps the restaurant name, contact details, timezone and the grace/
    reminder policy in the database rather than scattered through
    templates, so emails, calendar files and the UI all read one value.
    """

    key: Optional[str] = Field(default=None, primary_key=True)
    value: str = ""
