"""BASE_PATH: the app can live under a sub-path (e.g. /results) on a club's main domain; default is the site root."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import Client, override_settings

from config.base_path import normalize_base_path

pytestmark = pytest.mark.django_db
BACKEND = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("raw, expected", [
    ("", ""), ("/", ""), ("  ", ""), ("results", "/results"), ("/results", "/results"),
    ("/results/", "/results"), (" /results/ ", "/results"), ("/club/results/", "/club/results"),
])
def test_normalize_base_path(raw, expected):
    assert normalize_base_path(raw) == expected


@pytest.mark.parametrize("bad", ["//evil.example", "/a//b", "/a b", "/results?x=1", "/results#top", "https://x.example/r",
                                 "/../etc", "/results/./x"])
def test_normalize_base_path_rejects_anything_that_is_not_a_plain_path(bad):
    with pytest.raises(ValueError):
        normalize_base_path(bad)


@override_settings(BASE_PATH="", CLUB_BURGEE_URL="/brand/burgee.png", CLUB_LOGO_URL="/brand/logo.png")
def test_config_brand_urls_are_untouched_at_the_site_root():
    cfg = Client().get("/api/config").json()
    assert cfg["burgee_url"] == "/brand/burgee.png" and cfg["logo_url"] == "/brand/logo.png"


@override_settings(BASE_PATH="/results", CLUB_BURGEE_URL="/brand/burgee.png", CLUB_LOGO_URL="https://cdn.example/logo.png")
def test_config_brand_urls_follow_the_base_path_but_absolute_urls_do_not():
    cfg = Client().get("/api/config").json()
    assert cfg["burgee_url"] == "/results/brand/burgee.png"
    assert cfg["logo_url"] == "https://cdn.example/logo.png"
    assert cfg["base_path"] == "/results"


def _settings_with(base_path: str) -> dict:
    env = {**os.environ, "BASE_PATH": base_path, "DJANGO_SETTINGS_MODULE": "config.settings"}
    code = "from django.conf import settings as s; import json; print(json.dumps([s.BASE_PATH, s.FORCE_SCRIPT_NAME, s.STATIC_URL]))"
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=BACKEND, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_settings_wire_the_base_path_into_script_name_and_static_url():
    assert _settings_with("/results/") == ["/results", "/results", "/results/static/"]
    assert _settings_with("") == ["", None, "/static/"]


def test_settings_refuse_a_base_path_that_is_not_a_plain_path():
    with pytest.raises(subprocess.CalledProcessError):
        _settings_with("//evil.example")
