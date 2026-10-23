"""Guard rails for the open-source repo: nothing private or club-specific may be tracked by git.

Runs in CI with the rest of pytest, so a bad commit (by a person or an agent) turns the build red.
Add your own club's words to `club-data/forbidden-terms.txt` (git-ignored, one per line, case-insensitive) and this
test also refuses any tracked file that contains them, without the words themselves ever being committed.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Paths that must never be tracked, whatever they contain.
FORBIDDEN_PATHS = [
    r"(^|/)\.env$", r"(^|/)\.env\.(?!example$)[^/]+$", r"^data/", r"^club-data/", r"\.sqlite3?(-wal|-shm|-journal)?$",
    r"\.tfstate", r"(^|/)terraform\.tfvars$", r"^frontend/public/brand/(?!README\.md$)", r"\.(pem|key|p12|pfx)$",
    r"\.(xlsx|xls)$", r"(^|/)credentials(\.json)?$",
]

# Things that look like secrets or deployment specifics. Test files and docs use placeholders instead.
SECRET_PATTERNS = {
    "AWS access key id": r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
    "private key": r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "AWS account id in an ARN": r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:",
    # 203.0.113.x is the documentation range, fine in examples
    "sslip.io host for a real IP": r"\b(?!203-0-113-)\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}\.sslip\.io\b",
    "GitHub token": r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}",
    "Slack token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "hard-coded secret value": r"(?i)\b(SECRET_KEY|AWS_SECRET_ACCESS_KEY|PASSWORD)\s*=\s*['\"](?!dev-insecure)[A-Za-z0-9+/_\-]{24,}['\"]",
}
# This file names the patterns above, so it is exempt from the scan.
SELF = "backend/tests/test_repo_hygiene.py"
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".yml", ".yaml", ".tf", ".sh", ".toml",
                  ".txt", ".css", ".html", ".example", ".cfg", ".ini", ""}


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [line for line in out.splitlines() if line and (ROOT / line).is_file()]


def read(path: str) -> str:
    p = ROOT / path
    if p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size > 2_000_000:
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def test_no_private_files_are_tracked():
    bad = [f for f in tracked_files() for pat in FORBIDDEN_PATHS if re.search(pat, f)]
    assert not bad, f"private or local-only files are tracked by git: {sorted(set(bad))}"


def test_no_secrets_or_deployment_specifics_in_tracked_files():
    hits = []
    for f in tracked_files():
        if f == SELF or f.endswith(("package-lock.json", "uv.lock", ".terraform.lock.hcl")):
            continue
        text = read(f)
        for label, pat in SECRET_PATTERNS.items():
            if re.search(pat, text):
                hits.append(f"{f}: {label}")
    assert not hits, "possible secrets or deployment-specific values committed:\n" + "\n".join(hits)


def test_no_club_specific_terms_in_tracked_files():
    terms_file = ROOT / "club-data" / "forbidden-terms.txt"
    if not terms_file.exists():
        pytest.skip("no club-data/forbidden-terms.txt on this machine")
    terms = [t.strip().lower() for t in terms_file.read_text(encoding="utf-8").splitlines()
             if t.strip() and not t.startswith("#")]
    hits = []
    for f in tracked_files():
        text = (read(f) + "\n" + f).lower()
        hits += [f"{f}: contains a forbidden term" for t in terms if t in text]
    assert not hits, "club-specific words are in tracked files:\n" + "\n".join(sorted(set(hits)))


def test_env_example_has_no_real_secret():
    text = read(".env.example")
    for line in text.splitlines():
        if line.startswith("SECRET_KEY="):
            assert line.split("=", 1)[1].strip() in ("", "change-me", "dev-insecure-change-me") \
                or "change" in line.lower() or "example" in line.lower(), "a real SECRET_KEY is in .env.example"
