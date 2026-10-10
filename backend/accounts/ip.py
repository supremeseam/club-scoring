"""Which IP address a request really came from.

In production Caddy is the only way in (the app container is never published) and it overwrites
X-Forwarded-For with the real client address, so the RIGHT-most entry is trustworthy. Never publish port
8000 or put another proxy in front without revisiting this. In development there is no proxy and the
header is ignored.
"""
import ipaddress

from django.conf import settings


def client_ip(request) -> str:
    ip = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "BEHIND_PROXY", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded.strip():
            ip = forwarded.split(",")[-1].strip()
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip or "unknown"
    if addr.version == 6:        # one customer typically owns a /64, so don't let one rotate inside it
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address)
    return str(addr)
