"""
shared/proxy.py
===============
Intel VPN/LAN auto-detection and proxy configuration.

Import this module early (before any network call) in any automation.
After import, ``PROXIES`` is ready for use with requests/curl_cffi,
and HTTP_PROXY/HTTPS_PROXY env vars are set accordingly.
"""

import os
import socket

_INTEL_PROXY_URL = "http://proxy-dmz.intel.com:912"
_PA_PROXY_URL    = "http://proxy.server:3128"  # PythonAnywhere outbound proxy


def _is_on_intel_network(timeout: float = 2.0) -> bool:
    """Return True if the Intel corporate proxy host is reachable."""
    try:
        s = socket.create_connection(("proxy-dmz.intel.com", 912), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def _is_on_pythonanywhere() -> bool:
    """Return True when running inside a PythonAnywhere container."""
    return bool(os.environ.get("PYTHONANYWHERE_SITE"))


def configure_proxy(https_proxy: str = "") -> dict[str, str]:
    """
    Resolve the effective proxy URL and apply it to the process environment.

    Priority:
      1. ``https_proxy`` argument (explicit override)
      2. HTTPS_PROXY / https_proxy already set in environment (e.g. PythonAnywhere)
      3. Auto-detect Intel VPN/LAN via socket probe
      4. No proxy (cloud / home network)

    Returns the ``proxies`` dict suitable for ``requests`` and ``curl_cffi``.
    """
    effective = https_proxy

    # Respect any proxy already set in the environment (e.g. via .env file)
    if not effective:
        effective = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
        if effective:
            print(f"[proxy] Using proxy from environment: {effective}")

    # Auto-detect PythonAnywhere
    if not effective and _is_on_pythonanywhere():
        effective = _PA_PROXY_URL
        print(f"[proxy] PythonAnywhere detected - proxy auto-configured: {effective}")

    # Auto-detect Intel VPN/LAN
    if not effective and _is_on_intel_network():
        effective = _INTEL_PROXY_URL
        print(f"[proxy] Intel VPN/LAN detected - proxy auto-configured: {effective}")

    if effective:
        proxies: dict[str, str] = {"http": effective, "https": effective}
        os.environ["HTTP_PROXY"]  = effective
        os.environ["HTTPS_PROXY"] = effective
    else:
        proxies = {}
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"):
            os.environ.pop(var, None)

    return proxies


# Module-level resolved proxy — available as ``from lib.proxy import PROXIES``
PROXIES: dict[str, str] = configure_proxy()
