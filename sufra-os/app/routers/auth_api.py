"""
Staff authentication.

Nothing here ever returns a PIN or a pin_hash. The roster endpoint is the
one thing an unauthenticated device can call — it has to be, since it's
what draws the "who is using NOVA?" cards — and it deliberately carries
no PIN, no hash, and nothing sensitive.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re

from fastapi import APIRouter, Body, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..database import engine
from ..models import AuditLog, AuthSession, Staff
from ..staff_access import badge_staff
from ..permissions import current_staff, permissions_for
from ..security import (
    hash_pin, lockout_seconds_for, new_token, session_expiry, verify_pin,
    MAX_ATTEMPTS,
)

router = APIRouter(prefix="/api/auth")


def db() -> Session:
    return Session(engine, expire_on_commit=False)


def staff_card(p: Staff) -> dict:
    return {"id": p.id, "name": p.name, "role": p.role.value, "avatar": p.avatar,
            "section": p.section, "on_shift": p.on_shift}


@router.get("/roster")
def roster():
    with db() as s:
        try:
            from ..enterprise_models import HRProfile
        except Exception:
            from ..enterprise_local_models import HRProfile
        removed = {p.staff_id for p in
                  s.exec(select(HRProfile).where(HRProfile.status == "leaver")).all()}
        people = s.exec(select(Staff).order_by(Staff.role, Staff.name)).all()
        return {"staff": [staff_card(p) for p in people if p.id not in removed]}


@router.post("/login")
async def login(response: Response, body: dict = Body(...)):
    response.headers["Cache-Control"] = "no-store"
    staff_id = body.get("staff_id")
    pin = str(body.get("pin", ""))
    with db() as s:
        qr_token = body.get("qr_token")
        if qr_token:
            staff_id = badge_staff(s, qr_token)
        try:
            staff_id_int = int(staff_id or 0)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Choose a profile to continue."}, 400)
        if not re.fullmatch(r"[0-9]{4}", pin):
            return JSONResponse({"error": "Enter a valid PIN."}, 400)
        person = s.get(Staff, staff_id_int)
        if not person:
            return JSONResponse({"error": "Choose a profile to continue."}, 400)

        # A removed employee is hidden from the sign-in roster, but that is
        # a UI courtesy, not the security boundary — this blocks the PIN
        # itself, so a device that still remembers their staff_id (or a
        # crafted request) cannot sign back in as someone HR removed.
        try:
            from ..enterprise_models import HRProfile
        except Exception:
            from ..enterprise_local_models import HRProfile
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == person.id)).first()
        if profile and profile.status in {"leaver", "suspended"}:
            return JSONResponse({"error": "This account has been removed."}, 403)


        now = datetime.now()
        if person.locked_until and person.locked_until > now:
            wait = round((person.locked_until - now).total_seconds())
            return JSONResponse(
                {"error": f"Too many attempts. Try again in {wait} seconds.",
                 "locked_seconds": wait}, 429)

        if not verify_pin(pin, person.pin_hash):
            person.failed_attempts += 1
            if person.failed_attempts % MAX_ATTEMPTS == 0:
                wait = lockout_seconds_for(person.failed_attempts)
                person.locked_until = now + timedelta(seconds=wait)
                s.add(person)
                s.add(AuditLog(staff_id=person.id, action="login_locked",
                               entity_type="staff", entity_id=person.id,
                               detail=f"Locked for {wait}s after repeated failed PINs."))
                s.commit()
                return JSONResponse(
                    {"error": f"Too many attempts. Try again in {wait} seconds.",
                     "locked_seconds": wait}, 429)
            s.add(person)
            s.add(AuditLog(staff_id=person.id, action="login_failed",
                           entity_type="staff", entity_id=person.id,
                           detail="Incorrect PIN."))
            s.commit()
            left = MAX_ATTEMPTS - (person.failed_attempts % MAX_ATTEMPTS)
            return JSONResponse(
                {"error": f"Incorrect PIN. {left} attempt{'s' if left != 1 else ''} left."}, 401)

        # success
        person.failed_attempts = 0
        person.locked_until = None
        person.last_login = now
        s.add(person)
        token = new_token()
        s.add(AuthSession(token=token, staff_id=person.id, expires_at=session_expiry()))
        s.add(AuditLog(staff_id=person.id, action="login", entity_type="staff",
                       entity_id=person.id, detail="Signed in."))
        s.commit()
        return {"ok": True, "token": token, "staff": staff_card(person),
                "permissions": permissions_for(person.role)}


@router.post("/verify")
async def verify(body: dict = Body(...), authorization: str = Header(default="")):
    """Re-check the PIN for whoever is already signed in — used to clear
    the idle-lock overlay without minting a new session or losing state."""
    staff = current_staff(authorization)
    with db() as s:
        person = s.get(Staff, staff.id)
        now = datetime.now()
        if person.locked_until and person.locked_until > now:
            wait = round((person.locked_until - now).total_seconds())
            return JSONResponse({"error": f"Locked. Try again in {wait} seconds."}, 429)
        pin = str(body.get("pin", ""))
        if not re.fullmatch(r"[0-9]{4}", pin) or not verify_pin(pin, person.pin_hash):
            person.failed_attempts += 1
            if person.failed_attempts % MAX_ATTEMPTS == 0:
                person.locked_until = now + timedelta(seconds=lockout_seconds_for(person.failed_attempts))
            s.add(person)
            s.commit()
            return JSONResponse({"error": "Incorrect PIN."}, 401)
        person.failed_attempts = 0
        s.add(person)
        s.commit()
        return {"ok": True}


@router.post("/logout")
async def logout(authorization: str = Header(default="")):
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else authorization.strip()
    with db() as s:
        sess = s.get(AuthSession, token)
        if sess:
            s.add(AuditLog(staff_id=sess.staff_id, action="logout",
                           entity_type="staff", entity_id=sess.staff_id, detail="Signed out."))
            s.delete(sess)
            s.commit()
    return {"ok": True}


@router.get("/me")
def me(authorization: str = Header(default="")):
    staff = current_staff(authorization)
    return {"staff": staff_card(staff), "permissions": permissions_for(staff.role)}


@router.post("/qr/identify")
def identify_qr(response: Response, body: dict = Body(...)):
    response.headers["Cache-Control"] = "no-store"
    from ..enterprise_models import HRProfile
    with db() as s:
        person = s.get(Staff, badge_staff(s, body.get("qr_token")))
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == person.id)).first() if person else None
        if not person or (profile and profile.status in {"leaver", "suspended"}):
            raise HTTPException(403, "This employee account is inactive.")
        return {"staff": staff_card(person)}


@router.post("/activity")
def activity(authorization: str = Header(default="")):
    staff = current_staff(authorization)
    token = authorization.removeprefix("Bearer ").strip()
    with db() as s:
        sess = s.get(AuthSession, token)
        sess.last_seen_at = datetime.now()
        s.add(sess)
        s.commit()
    return {"ok": True}
