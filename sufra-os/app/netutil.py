"""One place to open an outbound HTTPS connection correctly.

python.org's macOS build of Python ships with no root certificate bundle
until "Install Certificates.command" is run once by hand — something a
restaurant's server almost certainly never had done to it. Without it,
every plain `urllib.request.urlopen("https://...")` fails with
`CERTIFICATE_VERIFY_FAILED`, and because it is an exception like any
other, it is trivially easy to catch-and-swallow it into "the provider is
unreachable" — which is exactly what happened here: the menu translator,
the email webhook, the SMS webhook, and the weather feed were all built
against `urlopen()` calls that quietly failed shut on this machine, each
reporting a believable but wrong reason (rate-limited, provider down)
instead of the real one (this Python cannot verify a certificate at all).

certifi ships its own trust bundle independent of the OS, so every outbound
HTTPS call in this codebase should go through the context this module
builds rather than trusting urlopen's default.
"""
from __future__ import annotations

import ssl
import urllib.request
from typing import Optional


def https_context() -> Optional[ssl.SSLContext]:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None


def urlopen(req, timeout: float = 10.0):
    """Drop-in replacement for urllib.request.urlopen with a working
    certificate bundle on https:// requests. http:// is untouched."""
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if url.startswith("https://"):
        return urllib.request.urlopen(req, timeout=timeout, context=https_context())
    return urllib.request.urlopen(req, timeout=timeout)
