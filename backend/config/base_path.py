import re


def normalize_base_path(value: str) -> str:
    """"" for the site root, otherwise "/some/path" with no trailing slash. Anything but a plain path is refused."""
    v = (value or "").strip()
    if v in ("", "/"):
        return ""
    if not v.startswith("/"):
        v = "/" + v
    v = v.rstrip("/")
    if not re.fullmatch(r"(/[A-Za-z0-9._~-]+)+", v) or any(part in (".", "..") for part in v.split("/")):
        raise ValueError(f"BASE_PATH must be a plain path such as /results, not {value!r}")
    return v
