"""Settings for iglc.net. Everything that differs between machines comes from environment variables.

A `.env` file in the project root is read at start-up (see `.env.example`).
"""

import os
import sys
from email.utils import parseaddr
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
_DEV_KEY = "dev-only-insecure-key"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _DEV_KEY)
if SECRET_KEY == _DEV_KEY and not DEBUG:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY, or DJANGO_DEBUG=1 for local development.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "apps.archive",
    "apps.pages",
    "apps.governance",
    "apps.core",
    "apps.production",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
]

MIDDLEWARE = [
    "apps.core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.HostRedirectMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.archive.legacy.LegacyUrlMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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
                "apps.archive.context_processors.navigation",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    # Papers in production: never public, only downloaded through the site by their editors.
    "private": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": os.environ.get("PRIVATE_FILES_ROOT", str(BASE_DIR / "private"))}},
}
# In production, uploaded images and documents go to a blob container (App Service does not
# keep files written in the container). The container allows anonymous read of blobs, like
# the ones holding the papers.
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
if AZURE_STORAGE_CONNECTION_STRING:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.azure_storage.AzureStorage",
        "OPTIONS": {
            "connection_string": AZURE_STORAGE_CONNECTION_STRING,
            "azure_container": os.environ.get("AZURE_MEDIA_CONTAINER", "media"),
            "expiration_secs": None,
            "overwrite_files": False,
        },
    }
    STORAGES["private"] = {
        "BACKEND": "storages.backends.azure_storage.AzureStorage",
        "OPTIONS": {
            "connection_string": AZURE_STORAGE_CONNECTION_STRING,
            "azure_container": os.environ.get("AZURE_PRIVATE_CONTAINER", "production"),  # no public access
            "overwrite_files": False,
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

WAGTAIL_SITE_NAME = "IGLC"
# Logging out of the archive admin or the CMS returns to the front page; logging out from a
# page on the site returns to that page (the form sends it as "next").
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "wagtailadmin_login"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "apps.production.auth.ProductionRoleBackend",  # production roles give access to the back office
]
WAGTAILADMIN_BASE_URL = SITE_URL

# IGLC specifics
# A preview or test copy tells search engines not to index it.
SITE_NOINDEX = env_bool("SITE_NOINDEX", False)
# Serve uploaded files from Django when no separate file server is set up (previews).
SERVE_MEDIA = env_bool("SERVE_MEDIA", False)
# Times New Roman (times.ttf, timesi.ttf) for the running heads on published papers. The fonts
# are licensed and not in the repository: if they are not here, they are read from the
# private files under fonts/.
PRODUCTION_FONTS_DIR = Path(os.environ.get("PRODUCTION_FONTS_DIR", str(BASE_DIR / "_fonts")))

IGLC_DOI_PREFIX = "10.24928"
# Website of the current conference (menu link "Conference website" and the old ConferenceWebsite URL).
CONFERENCE_WEBSITE = os.environ.get("CONFERENCE_WEBSITE", "https://www.iglc35.com/")
# Files the old site served from /Content/ (full proceedings, standards, templates, images)
# now live in blob storage; /Content/<path> redirects to <LEGACY_CONTENT_URL>/<path>.
LEGACY_CONTENT_URL = os.environ.get(
    "LEGACY_CONTENT_URL", "https://iglcstorage.blob.core.windows.net/content"
).rstrip("/")

# Whole host names to redirect, e.g. "iglc.net=www.iglc.net".
HOST_REDIRECTS = dict(item.split("=", 1) for item in env_list("HOST_REDIRECTS"))

# Errors and warnings go to the console, which App Service and Docker keep as the log.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django.request": {"handlers": ["console", "mail_admins"], "level": "ERROR", "propagate": False},
    },
}

# Email (password resets, error reports). Without EMAIL_HOST, email is printed to the log.
if os.environ.get("EMAIL_HOST"):
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "IGLC website <webmaster@iglc.net>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Who gets error reports: "Name <email>, Name <email>"
ADMINS = [parseaddr(item) for item in env_list("DJANGO_ADMINS")]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Not while running the tests, whose client talks plain http.
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True) and sys.argv[1:2] != ["test"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
