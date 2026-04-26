"""
lib/proxy.py
============
Lightweight proxy configuration helper.

Priority order:
  1. ``configure_proxy(https_proxy=...)`` argument
  2. ``HTTPS_PROXY`` / ``https_proxy`` environment variable
  3. Windows system proxy (from IE/GPO registry settings) — handles Intel
     corporate network automatically without hardcoding any proxy URL
  4. PythonAnywhere container auto-detect (``proxy.server:3128``)
  5. No proxy (home / cloud / mobile-hotspot environments)
"""

import os


_PA_PROXY_URL = "http://proxy.server:3128"  # PythonAnywhere outbound proxy


def _is_on_pythonanywhere() -> bool:
    return bool(os.environ.get("PYTHONANYWHERE_SITE"))


def _parse_pac(pac_url: str) -> str:
    """Fetch a PAC/WPAD script and extract the first PROXY host:port.
    Uses urllib (no requests, avoids circular dependency) with a short timeout.
    Only HTTP PAC URLs are tried since HTTPS ones would need the proxy first."""
    import re
    import urllib.request
    try:
        # PAC files are typically served over plain HTTP on the internal network
        req = urllib.request.Request(pac_url, headers={"User-Agent": "WinHTTP"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'\bPROXY\s+([A-Za-z0-9._-]+:\d+)', content)
        if m:
            host = m.group(1)
            return f"http://{host}" if "://" not in host else host
    except Exception:
        pass
    return ""


def _get_windows_system_proxy() -> str:
    """Read the effective HTTPS proxy from Windows registry.
    Handles both direct ProxyServer entries and PAC/WPAD AutoConfigURL."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        # 1. Direct proxy setting
        try:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _  = winreg.QueryValueEx(key, "ProxyServer")
            if enabled and server:
                if "https=" in server:
                    for part in server.split(";"):
                        if part.startswith("https="):
                            server = part[6:]
                            break
                elif "=" in server:
                    server = server.split(";")[0].split("=", 1)[1]
                if server and "://" not in server:
                    server = f"http://{server}"
                return server
        except (OSError, FileNotFoundError):
            pass

        # 2. PAC / WPAD script
        try:
            pac_url, _ = winreg.QueryValueEx(key, "AutoConfigURL")
            if pac_url and pac_url.startswith("http://"):
                return _parse_pac(pac_url)
        except (OSError, FileNotFoundError):
            pass
    except Exception:
        pass
    return ""


def configure_proxy(https_proxy: str = "") -> dict[str, str]:
    """Resolve and apply the effective proxy. Returns a ``proxies`` dict
    suitable for ``requests`` / ``curl_cffi``. Empty dict means no proxy."""
    effective = https_proxy

    if not effective:
        effective = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
        if effective:
            print(f"[proxy] Using proxy from environment: {effective}")

    if not effective:
        effective = _get_windows_system_proxy()
        if effective:
            print(f"[proxy] Windows system proxy detected: {effective}")

    if not effective and _is_on_pythonanywhere():
        effective = _PA_PROXY_URL
        print(f"[proxy] PythonAnywhere detected - proxy auto-configured: {effective}")

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
