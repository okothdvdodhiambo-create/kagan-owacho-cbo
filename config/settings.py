"""
Django settings for the KAGAN OWACHO CBO community web system.

All secrets and third-party credentials come from the .env file
(python-decouple) - nothing sensitive is hard-coded here.
"""

from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ core ----
SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-only-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,[::1]", cast=Csv())
CSRF_TRUSTED_ORIGINS = [o for o in config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv()) if o]

# Render injects the public hostname of the service it just built. Honouring it here
# means a deploy works without editing ALLOWED_HOSTS by hand, and a rename on Render
# needs no code change.
RENDER_EXTERNAL_HOSTNAME = config("RENDER_EXTERNAL_HOSTNAME", default="").strip()
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    _render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # project apps
    "apps.core",
    "apps.accounts",
    "apps.membership",
    "apps.communications",
    "apps.events",
    "apps.contributions",
    "apps.incidents",
    "apps.admin_panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_settings",
                "apps.core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------- database ----
DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    # Zero-setup local default.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ auth ----
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "apps.accounts.validators.PasswordCompositionValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# --------------------------------------------------------- static & media ----
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Where uploaded photos and receipts live. Render free instances (and any instance
# without a persistent disk) lose MEDIA_ROOT on the next restart, so production uses
# "database": uploads become rows in the same PostgreSQL database that Render already
# backs up. Keep "filesystem" for local work so media/ stays browsable.
MEDIA_STORAGE = config("MEDIA_STORAGE", default="filesystem").strip().lower()

STORAGES = {
    "default": {
        "BACKEND": "apps.core.storage.DatabaseStorage"
        if MEDIA_STORAGE == "database"
        else "django.core.files.storage.FileSystemStorage"
    },
    "staticfiles": {
        # Manifest hashing only in production so `runserver` works before collectstatic.
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=5, cast=int)
IMAGE_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif"]

# ------------------------------------------------- i18n / time / money -------
LANGUAGE_CODE = "en-ke"
TIME_ZONE = "Africa/Nairobi"  # East Africa Time (EAT, UTC+3)
USE_I18N = True
USE_TZ = True
CURRENCY_SYMBOL = "KSh"
CURRENCY_CODE = "KES"

# ------------------------------------------------------------------ email ----
EMAIL_HOST = config("EMAIL_HOST", default="")
if config("EMAIL_BACKEND", default=""):
    EMAIL_BACKEND = config("EMAIL_BACKEND")
elif EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

EMAIL_HOST = EMAIL_HOST or "localhost"
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Kagan Owacho CBO <no-reply@kaganowacho.org>")
ADMIN_INBOX_EMAIL = config("ADMIN_INBOX_EMAIL", default="admin1@kaganowacho.org")

# A registration page must not sit waiting on a slow or unreachable mail server.
# Django's SMTP backend reads this directly and gives up after the timeout.
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)

# ------------------------------------------------------ project constants ----
ORGANIZATION_NAME = config("ORGANIZATION_NAME", default="KAGAN OWACHO CBO")
MEMBERSHIP_PREFIX = config("MEMBERSHIP_PREFIX", default="KOC")

# Fixed administrator accounts bootstrapped by apps.core.signals -> bootstrap_site.
# The two passwords below are development placeholders only: bootstrap_site refuses to
# create an account that still uses one once DEBUG is off, so a live site cannot be
# reachable through the credentials printed in the README.
DEMO_ADMIN_PASSWORDS = ["AdminOne#2026", "AdminTwo#2026"]
ADMIN_ACCOUNTS = [
    (config("ADMIN1_EMAIL", default="admin1@kaganowacho.org"), config("ADMIN1_PASSWORD", default=DEMO_ADMIN_PASSWORDS[0])),
    (config("ADMIN2_EMAIL", default="admin2@kaganowacho.org"), config("ADMIN2_PASSWORD", default=DEMO_ADMIN_PASSWORDS[1])),
]

SMS_PROVIDER = config("SMS_PROVIDER", default="console")
AFRICASTALKING_USERNAME = config("AFRICASTALKING_USERNAME", default="")
AFRICASTALKING_API_KEY = config("AFRICASTALKING_API_KEY", default="")
AFRICASTALKING_SENDER_ID = config("AFRICASTALKING_SENDER_ID", default="KAGANOWACHO")

MPESA_ENV = config("MPESA_ENV", default="sandbox")
MPESA_CONSUMER_KEY = config("MPESA_CONSUMER_KEY", default="")
MPESA_CONSUMER_SECRET = config("MPESA_CONSUMER_SECRET", default="")
MPESA_SHORTCODE = config("MPESA_SHORTCODE", default="")
MPESA_PASSKEY = config("MPESA_PASSKEY", default="")
MPESA_CALLBACK_URL = config("MPESA_CALLBACK_URL", default="http://localhost:8000/contributions/mpesa/callback/")
MPESA_TRANSACTION_TYPE = config("MPESA_TRANSACTION_TYPE", default="CustomerPayBillOnline")

LOGIN_MAX_ATTEMPTS = config("LOGIN_MAX_ATTEMPTS", default=5, cast=int)
LOGIN_LOCKOUT_MINUTES = config("LOGIN_LOCKOUT_MINUTES", default=15, cast=int)
VERIFICATION_TTL_MINUTES = config("VERIFICATION_TTL_MINUTES", default=10, cast=int)
VERIFICATION_MAX_ATTEMPTS = config("VERIFICATION_MAX_ATTEMPTS", default=5, cast=int)
VERIFICATION_RESEND_COOLDOWN_SECONDS = config("VERIFICATION_RESEND_COOLDOWN_SECONDS", default=60, cast=int)

# ------------------------------------------------------------- production ----
if not DEBUG:
    # Render terminates TLS and forwards plain HTTP to gunicorn. Without trusting that
    # header, SECURE_SSL_REDIRECT sees every request as insecure and loops forever.
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

SECURE_REFERRER_POLICY = "same-origin"
APPEND_SLASH = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
