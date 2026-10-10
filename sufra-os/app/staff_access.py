"""Encrypted, revocable staff badges. No PINs or bearer badges in storage."""
import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path

import qrcode
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlmodel import select

from .models import StaffBadgeCopy, StaffQR, AuthSession, AuditLog, Role
from .security import new_token


def cipher():
    key = os.getenv("SUFRA_STAFF_QR_KEY", "").strip()
    if not key:
        path = Path(__file__).resolve().parent.parent / ".staff-qr.key"
        # Atomic publication: another worker never sees a partially written key.
        if not path.exists():
            import tempfile
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".staff-qr-key-")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(Fernet.generate_key())
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    pass
            finally:
                os.unlink(tmp)
        key = path.read_bytes().strip()
    return Fernet(key)


def revoke_sessions(s, staff_id, preserve_token=None):
    for session in s.exec(select(AuthSession).where(AuthSession.staff_id == staff_id)).all():
        if session.token != preserve_token:
            s.delete(session)


def issue_badge(s, member, actor_id, base_url, preserve_session=None):
    token = cipher().encrypt(json.dumps({"staff_id": member.id, "nonce": new_token()}).encode()).decode()
    badge = s.get(StaffQR, member.id)
    if badge:
        s.delete(badge)
        s.flush()
    s.add(StaffQR(staff_id=member.id, token_hash=hashlib.sha256(token.encode()).hexdigest()))
    copy = s.get(StaffBadgeCopy, member.id) or StaffBadgeCopy(staff_id=member.id, encrypted_token="")
    copy.encrypted_token = cipher().encrypt(token.encode()).decode()
    s.add(copy)
    revoke_sessions(s, member.id, preserve_session if member.id == actor_id else None)
    s.add(AuditLog(staff_id=actor_id, action="staff_qr_issued", entity_type="staff", entity_id=member.id))
    return badge_card(member, token, base_url)


def local_staff_host():
    """Primary LAN interface; connecting UDP selects a route without sending data."""
    import socket
    import ipaddress
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            if not ipaddress.ip_address(host).is_loopback and host != "0.0.0.0":
                return host
        except OSError:
            pass
    return None


def staff_base_url(request):
    from urllib.parse import urlsplit, urlunsplit
    configured = (os.getenv("SUFRA_STAFF_URL") or os.getenv("SUFRA_PUBLIC_URL") or "").strip()
    parts = urlsplit(configured or str(request.base_url))
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise HTTPException(503, "Set SUFRA_STAFF_URL to this staff application's HTTP or HTTPS address.")
    if parts.hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        host = local_staff_host()
        if not host:
            raise HTTPException(503, "Connect this Mac to the restaurant network or set SUFRA_STAFF_URL before generating a phone QR.")
        authority = host + (f":{parts.port}" if parts.port else "")
    else:
        authority = parts.netloc
    return urlunsplit((parts.scheme, authority, "", "", ""))


def badge_card(member, token, base_url):
    path = "/waiter" if member.role in {Role.WAITER, Role.BARTENDER} else "/admin"
    url = base_url.rstrip("/") + path + "#staff_qr=" + token
    png = io.BytesIO()
    qrcode.make(url).save(png, format="PNG")
    return {"staff_id": member.id, "name": member.name, "qr_url": url,
            "app_path": path, "qr_image": "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()}


def badge_staff(s, token):
    if not isinstance(token, str) or not 40 <= len(token) <= 1024:
        raise HTTPException(401, "Invalid or revoked employee QR code.")
    try:
        data = json.loads(cipher().decrypt(token.encode()))
        staff_id = int(data["staff_id"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Invalid or revoked employee QR code.")
    badge = s.get(StaffQR, staff_id)
    if not badge or not hmac.compare_digest(badge.token_hash, hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(401, "Invalid or revoked employee QR code.")
    return staff_id
