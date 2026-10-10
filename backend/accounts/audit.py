"""Authentication audit trail: one line per event on the 'auth' logger (stdout, so `docker logs` has it).

Never pass passwords, tokens or one-time codes here. User-supplied strings are repr()'d and truncated so a
crafted username can't forge extra log lines.
"""
import logging

from .ip import client_ip

log = logging.getLogger("auth")


def _clean(value, limit=80) -> str:
    return repr(str(value)[:limit])


def log_event(event: str, request=None, username=None, level=logging.INFO, **extra) -> None:
    parts = [f"event={event}"]
    if username:
        parts.append(f"user={_clean(username, 150)}")
    if request is not None:
        parts.append(f"ip={client_ip(request)}")
        parts.append(f"ua={_clean(request.META.get('HTTP_USER_AGENT', ''), 60)}")
    parts += [f"{k}={_clean(v)}" for k, v in extra.items()]
    log.log(level, " ".join(parts))
