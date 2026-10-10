"""Language-code normalization.

The automatic guest-messaging system (confirmation/reminder/late-note
emails and SMS) that used to live in this module has been removed
entirely, at the restaurant's request — no email or SMS is sent to
guests anywhere in SUFRA. A booking is confirmed the moment it is made;
the only "confirmation" now is what the guest sees on screen.

_lang() survives because a few unrelated screens (the guest booking
confirmation page, admin reservation views) still need to normalize a
free-form language code down to one of the three the product supports.
"""
from __future__ import annotations

LANGS = ("en", "az", "ru")


def _lang(code: str) -> str:
    code = (code or "en").lower()[:2]
    return code if code in LANGS else "en"
