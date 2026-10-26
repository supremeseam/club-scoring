import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .auth_config import parse_auth_mode, parse_cognito_pools, split_list
from .base_path import normalize_base_path

BASE_DIR = Path(__file__).resolve().parent.parent
DEV_SECRET = "dev-insecure-secret-key-change-me"


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from the repo-root .env without overriding real environment variables."""
    f = BASE_DIR.parent / ".env"
    if not f.exists():
        return
    values: dict[str, str] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")     # a repeated key: the last one wins
    for k, v in values.items():
        os.environ.setdefault(k, v)                                 # real environment variables still win


_load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, "1" if default else "0").lower() in ("1", "true", "yes")


DEBUG = env_bool("DEBUG", True)
PRODUCTION = not DEBUG        # captured from the environment (test runners flip DEBUG later)
SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET)
REQUIRE_2FA = env_bool("REQUIRE_2FA", False)
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
ADMIN_URL = os.environ.get("ADMIN_URL", "manage-admin/")
# Serve the app under a sub-path of the club's main domain (e.g. /results). The reverse proxy strips the prefix
# before the request reaches Django; this makes redirects, admin links and static URLs include it. "" = site root.
BASE_PATH = normalize_base_path(os.environ.get("BASE_PATH", ""))
FORCE_SCRIPT_NAME = BASE_PATH or None

# How people sign in. "password" (default): accounts and passwords live in this app. "cognito": the club's Amazon
# Cognito user pool(s) sign people in and every API request carries their ID token; this app keeps no passwords.
AUTH_MODE = parse_auth_mode(os.environ.get("AUTH_MODE", ""))
# "userPoolId:appClientId" pairs, comma separated; only ID tokens from these app clients are accepted.
COGNITO_POOLS = parse_cognito_pools(os.environ.get("COGNITO_POOLS", ""))
if AUTH_MODE == "cognito" and not COGNITO_POOLS:
    raise ImproperlyConfigured("AUTH_MODE=cognito needs COGNITO_POOLS (userPoolId:appClientId)")
# Cognito groups whose members are race committee. Everyone else signs in as crew, or skipper once boats are linked.
COGNITO_RC_GROUPS = split_list(os.environ.get("COGNITO_RC_GROUPS", "admins"))
# Where the browser sends a signed-out visitor (the club website's sign-in page), and the browser storage keys
# (JSON {idToken, expiresAt}) under which that page keeps the sign-in tokens.
COGNITO_SIGN_IN_URL = os.environ.get("COGNITO_SIGN_IN_URL", "")
COGNITO_TOKEN_STORAGE_KEYS = split_list(os.environ.get("COGNITO_TOKEN_STORAGE_KEYS", ""))
CLUB_NAME = os.environ.get("CLUB_NAME", "Your Yacht Club")
CLUB_SHORT_NAME = os.environ.get("CLUB_SHORT_NAME", "") or CLUB_NAME
CLUB_TAGLINE = os.environ.get("CLUB_TAGLINE", "")
CLUB_WEBSITE = os.environ.get("CLUB_WEBSITE", "")
# Path or URL of a logo shown in the header (e.g. /logo.png, with the file in frontend/public/).
CLUB_LOGO_URL = os.environ.get("CLUB_LOGO_URL", "")
# One of Mantine's color names: blue, cyan, teal, green, lime, yellow, orange, red, pink, grape, violet, indigo.
BRAND_COLOR = os.environ.get("BRAND_COLOR", "blue")
# Exact brand colour as #rrggbb (overrides BRAND_COLOR): the whole theme is derived from it.
BRAND_COLOR_HEX = os.environ.get("BRAND_COLOR_HEX", "")
# Product name shown in the header and browser tab, e.g. "Harbor Race Hub".
APP_NAME = os.environ.get("APP_NAME", "") or "Race Results"
# The burgee alone, for small spaces (header, tab icon). CLUB_LOGO_URL is the full logo.
CLUB_BURGEE_URL = os.environ.get("CLUB_BURGEE_URL", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:5173")

# Production must not ship with dev settings.
if not DEBUG:
    if SECRET_KEY == DEV_SECRET:
        raise ImproperlyConfigured("DEBUG=0 requires a real SECRET_KEY")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "axes",
    "simple_history",
    "ninja",
    "boats",
    "courses",
    "racing",
    "api",
    "accounts",
    "crew",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "accounts.middleware.AccountSecurityMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
# ---- brute-force protection (django-axes + a per-account backstop in accounts/security.py) ----------------------
# Behind Caddy the client IP comes from the right-most X-Forwarded-For (see accounts/ip.py). Never publish the
# app container's port: that header is only trustworthy because Caddy is the sole way in.
BEHIND_PROXY = env_bool("BEHIND_PROXY", not DEBUG)
AXES_CLIENT_IP_CALLABLE = "accounts.ip.client_ip"
AXES_LOCKOUT_PARAMETERS = ["ip_address"]       # an attacker locks only THEMSELVES out, never a named user
AXES_FAILURE_LIMIT = 10                        # failed logins per IP ...
AXES_COOLOFF_TIME = timedelta(minutes=15)      # ... then that IP waits 15 minutes
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ACCESS_FAILURE_LOG = True          # one row per failure; feeds the per-account backstop
ACCOUNT_FAILURE_LIMIT = 100                    # NIST: at most 100 consecutive failures per account ...
ACCOUNT_FAILURE_WINDOW_MINUTES = 60            # ... counted over a rolling hour, so a lockout never lasts long

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": DATA_DIR / "db.sqlite3",
    "OPTIONS": {"transaction_mode": "IMMEDIATE", "init_command":
                "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;"},
}}

# NIST SP 800-63B: length and a blocklist, no composition rules. (Maximum length 256 is enforced in the API
# schemas so we never hash megabytes; spaces, Unicode and pasting are all allowed.)
PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 256
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "accounts.validators.ContextSpecificValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "America/New_York")
USE_I18N = False
USE_TZ = False  # race times are club-local wall-clock times
STATIC_URL = f"{BASE_PATH}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessions: 12 hours idle (sliding), 7 days absolute (accounts.middleware), stored server-side.
SESSION_COOKIE_AGE = 12 * 3600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_ABSOLUTE_MAX_SECONDS = int(os.environ.get("SESSION_ABSOLUTE_MAX_SECONDS", 7 * 24 * 3600))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it and echoes it in X-CSRFToken
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = False  # Caddy redirects and terminates TLS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

# Authentication audit trail: one line per event on the "auth" logger, to stdout (so `docker logs` has it).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"auth": {"format": "%(asctime)s AUTH %(levelname)s %(message)s"}},
    "handlers": {"auth": {"class": "logging.StreamHandler", "formatter": "auth"}},
    "loggers": {"auth": {"handlers": ["auth"], "level": "INFO", "propagate": False}},
}
