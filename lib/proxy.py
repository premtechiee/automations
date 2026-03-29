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


def _is_on_intel_network(timeout: float = 2.0) -> bool:
    """Return True if the Intel corporate proxy host is reachable."""
    try:
        s = socket.create_connection(("proxy-dmz.intel.com", 912), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def configure_proxy(https_proxy: str = "") -> dict[str, str]:
    """
    Resolve the effective proxy URL and apply it to the process environment.

    Priority:
      1. ``https_proxy`` argument (explicit override)
      2. Auto-detect Intel VPN/LAN via socket probe
      3. No proxy (cloud / home network)

    Returns the ``proxies`` dict suitable for ``requests`` and ``curl_cffi``.
    """
    effective = https_proxy

    if not effective and _is_on_intel_network():
        effective = _INTEL_PROXY_URL
        print(f"[proxy] Intel VPN/LAN detected — proxy auto-configured: {effective}")

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
