"""deploy/Caddyfile: who the app believes the visitor is. Runs the real Caddy in Docker in front of a stub app.

Login lockouts are per visitor address, taken from the X-Forwarded-For header Caddy writes. Behind CloudFront every
request comes from CloudFront, so Caddy may read the visitor's address from CloudFront-Viewer-Address, but only on a
request that carries the shared secret CloudFront adds (X-Origin-Verify = ORIGIN_VERIFY_SECRET). Anything else a
client sends must be ignored. Skipped when Docker is not available.
"""
import http.client
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "deploy" / "Caddyfile"
IMAGE = "caddy:2-alpine"
SECRET = "s3cret-value-from-cloudfront-0123456789"


def _docker(*args, check=True, timeout=120):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def _docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        if _docker("info", check=False, timeout=20).returncode != 0:
            return False
        if _docker("image", "inspect", IMAGE, check=False).returncode != 0:
            return _docker("pull", IMAGE, check=False, timeout=300).returncode == 0
        return True
    except (subprocess.SubprocessError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="Docker (with the caddy image) is not available")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """A stub 'app' that reports what it was sent, on a private network, plus a way to start Caddy in front of it."""
    tag = uuid.uuid4().hex[:8]
    net, names = f"caddytest-{tag}", []
    work = tmp_path_factory.mktemp("caddy")
    (work / "app.Caddyfile").write_text(
        ':8000 {\n\trespond "xff={http.request.header.X-Forwarded-For};cf={http.request.header.CloudFront-Viewer-Address};'
        'ov={http.request.header.X-Origin-Verify};path={http.request.uri.path}"\n}\n', encoding="utf-8")
    (work / "srv").mkdir()
    (work / "srv" / "index.html").write_text("SPA-INDEX", encoding="utf-8")
    (work / "static").mkdir()
    _docker("network", "create", net)
    _docker("run", "-d", "--name", f"app-{tag}", "--network", net, "--network-alias", "app",
            "-v", f"{work / 'app.Caddyfile'}:/etc/caddy/Caddyfile:ro", IMAGE)
    names.append(f"app-{tag}")

    def start(**env) -> int:
        port, name = _free_port(), f"caddy-{tag}-{len(names)}"
        envs = [x for k, v in {"SITE_ADDRESS": ":80", **env}.items() for x in ("-e", f"{k}={v}")]
        _docker("run", "-d", "--name", name, "--network", net, "-p", f"127.0.0.1:{port}:80", *envs,
                "-v", f"{CADDYFILE}:/etc/caddy/Caddyfile:ro", "-v", f"{work / 'srv'}:/srv:ro",
                "-v", f"{work / 'static'}:/static:ro", IMAGE)
        names.append(name)
        for _ in range(50):                                   # up to ~10 s for Caddy to listen
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                return port
            except OSError:
                time.sleep(0.2)
        raise RuntimeError(_docker("logs", name, check=False).stderr)

    yield start
    for name in names:
        _docker("rm", "-f", name, check=False)
    _docker("network", "rm", net, check=False)


def ask(port: int, path: str = "/api/ping", **headers) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={k.replace("_", "-"): v for k, v in headers.items()})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read().decode()
    return dict(part.split("=", 1) for part in body.split(";"))


@pytest.fixture(scope="module")
def with_secret(stack):
    return stack(ORIGIN_VERIFY_SECRET=SECRET)


@pytest.fixture(scope="module")
def without_secret(stack):
    return stack()


def test_a_plain_visitor_is_identified_by_the_connecting_address(with_secret):
    got = ask(with_secret)
    assert got["xff"] and got["cf"] == "" and got["ov"] == ""
    assert got["path"] == "/api/ping"


def test_a_client_cannot_choose_its_own_address(with_secret):
    baseline = ask(with_secret)["xff"]
    got = ask(with_secret, X_Forwarded_For="1.2.3.4", X_Real_IP="5.6.7.8")
    assert got["xff"] == baseline


def test_cloudfront_headers_without_the_secret_are_ignored_and_removed(with_secret):
    baseline = ask(with_secret)["xff"]
    got = ask(with_secret, CloudFront_Viewer_Address="9.9.9.9:4444", X_Origin_Verify="wrong")
    assert got["xff"] == baseline and got["cf"] == "" and got["ov"] == ""


def test_the_right_secret_makes_caddy_use_the_viewer_address(with_secret):
    got = ask(with_secret, CloudFront_Viewer_Address="203.0.113.9:51234", X_Origin_Verify=SECRET)
    assert got["xff"] == "203.0.113.9"
    assert got["cf"] == "" and got["ov"] == ""            # neither header is passed on to the app


def test_viewer_addresses_in_ipv6_form_lose_their_brackets_and_port(with_secret):
    got = ask(with_secret, CloudFront_Viewer_Address="[2001:db8::7]:443", X_Origin_Verify=SECRET)
    assert got["xff"] == "2001:db8::7"


def test_a_spoofed_forwarded_for_is_still_overwritten_with_the_secret(with_secret):
    got = ask(with_secret, X_Forwarded_For="1.2.3.4", CloudFront_Viewer_Address="203.0.113.9:1", X_Origin_Verify=SECRET)
    assert got["xff"] == "203.0.113.9"


@pytest.mark.parametrize("viewer", ["", "not-an-address", "203.0.113.9", "203.0.113.9:80, 1.2.3.4:80", "<script>:1"])
def test_an_unusable_viewer_address_falls_back_to_the_connecting_address(with_secret, viewer):
    baseline = ask(with_secret)["xff"]
    headers = {"X_Origin_Verify": SECRET, **({"CloudFront_Viewer_Address": viewer} if viewer else {})}
    assert ask(with_secret, **headers)["xff"] == baseline


@pytest.mark.parametrize("sent", ["", "anything", "__unset__", "%{env.ORIGIN_VERIFY_SECRET}"])
def test_without_a_configured_secret_nothing_from_cloudfront_is_ever_trusted(without_secret, sent):
    baseline = ask(without_secret)["xff"]
    headers = {"CloudFront_Viewer_Address": "9.9.9.9:4444", **({"X_Origin_Verify": sent} if sent else {})}
    got = ask(without_secret, **headers)
    assert got["xff"] == baseline and got["cf"] == "" and got["ov"] == ""


def test_the_viewer_address_works_together_with_a_base_path(stack):
    port = stack(ORIGIN_VERIFY_SECRET=SECRET, BASE_PATH="/results")
    got = ask(port, "/results/api/ping", CloudFront_Viewer_Address="198.51.100.4:2", X_Origin_Verify=SECRET)
    assert got["xff"] == "198.51.100.4" and got["path"] == "/api/ping"


# ---- old direct links -----------------------------------------------------------------------------------------------
# After the app moves under /results on the club's main site, links and printed QR codes that point at the server's own
# address (/races/12 ...) must forward to the new address instead of breaking. Only when both BASE_PATH and
# LEGACY_REDIRECT_BASE are set; the API, static files, brand files and the Django admin are never redirected.
NEW_HOME = "https://site.example/results"


def raw(port: int, path: str):
    """One request with no redirect following: (status, Location header, body)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    r = conn.getresponse()
    out = (r.status, r.getheader("Location"), r.read().decode())
    conn.close()
    return out


@pytest.fixture(scope="module")
def moved(stack):
    return stack(BASE_PATH="/results", LEGACY_REDIRECT_BASE=NEW_HOME)


@pytest.mark.parametrize("old, new", [
    ("/", f"{NEW_HOME}/"),
    ("/races/12", f"{NEW_HOME}/races/12"),
    ("/series/3?tab=standings", f"{NEW_HOME}/series/3?tab=standings"),
    ("/boats/7", f"{NEW_HOME}/boats/7"),
    ("/crew", f"{NEW_HOME}/crew"),
    ("/login", f"{NEW_HOME}/login"),
])
def test_old_direct_links_forward_to_the_new_address(moved, old, new):
    status, location, _ = raw(moved, old)
    assert status == 308 and location == new


@pytest.mark.parametrize("path", ["/results/", "/results", "/results/races/12", "/results/assets/app.js"])
def test_links_already_under_the_new_path_are_not_redirected(moved, path):
    status, location, _ = raw(moved, path)
    assert status == 200 and location is None


def test_the_api_the_files_and_the_admin_are_never_redirected(moved):
    assert raw(moved, "/api/ping")[0] == 200                      # reaches the app
    assert raw(moved, "/static/admin.css")[0] == 404              # the static handler, not a redirect
    assert raw(moved, "/brand/logo.png")[0] != 308
    assert raw(moved, "/manage-admin/")[0] == 200                 # reaches the app (the Django admin)


def test_nothing_is_redirected_without_a_base_path_or_without_a_target(stack):
    no_target = stack(BASE_PATH="/results")
    no_base = stack(LEGACY_REDIRECT_BASE=NEW_HOME)
    for port in (no_target, no_base):
        assert raw(port, "/races/12")[0] == 200 and raw(port, "/races/12")[1] is None
