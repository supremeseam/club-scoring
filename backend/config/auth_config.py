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


_LINK_TARGET = re.compile(r"(/(?!/)[A-Za-z0-9._~/%?=&#:+-]*|https://[A-Za-z0-9.-]+(?::\d+)?(/[A-Za-z0-9._~/%?=&#:+-]*)?)")


def parse_sign_in_links(value: str) -> list[tuple[str, str]]:
    """"Label|address, Label|address" -> [(label, address), ...]. An address is a path on this site or an https address."""
    links = []
    for item in split_list(value):
        label, sep, target = item.partition("|")
        label, target = label.strip(), target.strip()
        if not sep or not label or len(label) > 60 or not _LINK_TARGET.fullmatch(target):
            raise ImproperlyConfigured(f"COGNITO_SIGN_IN_LINKS entries look like 'Race committee|/manage/', not {item!r}")
        links.append((label, target))
    return links
