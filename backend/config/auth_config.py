import re

from django.core.exceptions import ImproperlyConfigured

_POOL_ID = re.compile(r"[a-z]{2}(?:-[a-z]+)+-\d_[A-Za-z0-9]+")
_CLIENT_ID = re.compile(r"[A-Za-z0-9]+")


def parse_auth_mode(value: str) -> str:
    mode = (value or "password").strip().lower()
    if mode not in ("password", "cognito"):
        raise ImproperlyConfigured(f"AUTH_MODE must be 'password' or 'cognito', not {value!r}")
    return mode


def parse_cognito_pools(value: str) -> list[tuple[str, str]]:
    """"poolId:clientId, poolId:clientId" -> [(poolId, clientId), ...]. Only these app clients' tokens are accepted."""
    pools = []
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        pool_id, _, client_id = item.partition(":")
        if not _POOL_ID.fullmatch(pool_id) or not _CLIENT_ID.fullmatch(client_id):
            raise ImproperlyConfigured(
                f"COGNITO_POOLS entries look like us-west-2_AbCdEf123:appclientid, not {item!r}")
        pools.append((pool_id, client_id))
    return pools


def split_list(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]
