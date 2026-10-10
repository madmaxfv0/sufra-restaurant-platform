"""
Role-based access control.

The matrix is the single source of truth. The frontend reads it (via
/api/auth/me) to decide what to show, but that is a convenience, not the
security boundary — every sensitive endpoint depends on require_permission
below, which re-checks the token and the role on every request regardless
of what the client claims.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from .security import IDLE_LOCK_MINUTES
from typing import Optional

from fastapi import Header, HTTPException
from sqlmodel import Session, select

from .database import engine
from .models import AuthSession, Role, Staff

PERMISSIONS = {
    "can_view_reservations", "can_modify_reservations", "can_assign_tables",
    "can_view_orders",
    "can_view_guest_profiles", "can_create_order", "can_edit_order",
    "can_void_item", "can_apply_discount", "can_comp_item", "can_take_payment",
    "can_refund_payment", "can_view_staff", "can_edit_staff",
    "can_view_inventory", "can_edit_inventory", "can_view_analytics",
    "can_view_financials", "can_view_profitability", "can_manage_menu",
    "can_manage_permissions", "can_manage_availability", "can_manage_complaints",
    # Physical table state — seat a party, free a table. Deliberately separate
    # from can_modify_reservations: a waiter must be able to say "these people
    # have left" without also being able to rewrite the book.
    "can_set_table_state",
}

# Every permission defaults to False; only what's listed here is granted.
MATRIX: dict[Role, set[str]] = {
    Role.OWNER: set(PERMISSIONS),  # full access, including permissions themselves

    Role.GENERAL_MANAGER: PERMISSIONS - {"can_manage_permissions"},

    Role.RESTAURANT_MANAGER: {
        "can_view_reservations", "can_modify_reservations", "can_assign_tables",
        "can_view_orders",
        "can_view_guest_profiles", "can_create_order", "can_edit_order",
        "can_void_item", "can_apply_discount", "can_comp_item", "can_take_payment",
        "can_refund_payment", "can_view_staff", "can_edit_staff",
        "can_view_inventory", "can_edit_inventory", "can_view_analytics",
        "can_view_financials", "can_manage_menu", "can_manage_availability", "can_manage_complaints",
        "can_set_table_state",
        # not granted: can_view_profitability, can_manage_permissions
    },

    Role.HOST: {
        "can_view_reservations", "can_modify_reservations", "can_assign_tables",
        "can_view_guest_profiles", "can_set_table_state",
    },

    Role.WAITER: {
        "can_view_reservations", "can_view_guest_profiles",
        "can_create_order", "can_edit_order", "can_take_payment",
        "can_set_table_state",
        # not granted: can_void_item (needs a manager), can_apply_discount,
        # can_comp_item, can_refund_payment
    },

    Role.BARTENDER: {
        "can_create_order", "can_edit_order", "can_take_payment",
        "can_set_table_state",
    },

    Role.KITCHEN: {"can_manage_menu", "can_manage_availability"},

    Role.CASHIER: {
        "can_take_payment", "can_refund_payment",
    },

    Role.INVENTORY_MANAGER: {
        "can_view_inventory", "can_edit_inventory", "can_manage_availability",
    },
}


def permissions_for(role: Role) -> list[str]:
    return sorted(MATRIX.get(role, set()))


def has_permission(role: Role, perm: str) -> bool:
    return perm in MATRIX.get(role, set())


def _load_session(token: str, s: Session) -> Optional[AuthSession]:
    sess = s.get(AuthSession, token)
    if not sess or sess.expires_at <= datetime.now() or sess.last_seen_at + timedelta(minutes=IDLE_LOCK_MINUTES) <= datetime.now():
        return None
    return sess


def current_staff(authorization: str = Header(default="")) -> Staff:
    """Base dependency: any signed-in, unexpired staff member."""
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else authorization.strip()
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    with Session(engine, expire_on_commit=False) as s:
        sess = _load_session(token, s)
        if not sess:
            raise HTTPException(401, "Your session has ended. Please sign in again.")
        staff = s.get(Staff, sess.staff_id)
        if not staff:
            raise HTTPException(401, "That staff account no longer exists.")
        from .enterprise_models import HRProfile
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == staff.id)).first()
        if profile and profile.status in {"leaver", "suspended"}:
            raise HTTPException(401, "This employee account is inactive.")
        s.refresh(staff)
        return staff


def require_permission(perm: str):
    """Dependency factory: 403s unless the signed-in staff member's role
    carries this permission. `perm` must be one of PERMISSIONS."""
    assert perm in PERMISSIONS, f"unknown permission: {perm}"

    def dep(authorization: str = Header(default="")) -> Staff:
        staff = current_staff(authorization)
        if not has_permission(staff.role, perm):
            raise HTTPException(403, "Your role doesn't allow that.")
        return staff

    return dep


def admin_staff(authorization: str = Header(default="")) -> Staff:
    """Allow only roles that use the back-of-house administration app."""
    staff = current_staff(authorization)
    if staff.role in {Role.WAITER, Role.BARTENDER}:
        raise HTTPException(403, "Your role doesn't allow administration access.")
    return staff
