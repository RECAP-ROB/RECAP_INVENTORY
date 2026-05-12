import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-%hjisw!0c0)bs&s9m#0e(#(=g54-#f+q2-d3+p%puk)0=5qrp#"

ALLOWED_HOSTS = ["0.0.0.0", "localhost", "127.0.0.1", "0.0.0.0:8000"]

DEBUG = True
# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "api",
    "rest_framework",
    "silk",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    "channels",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "silk.middleware.SilkyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8080",
]

CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = "main.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = 'main.wsgi.application'

ASGI_APPLICATION = 'main.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': ['redis://127.0.0.1:6379'],
        },
    }
}

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_IMPORTS = ('api.celery_tasks',)

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True
CELERY_ACKS_LATE = True

MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "10.15.173.106")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "shelf/status")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "inventory-mqtt-client")
MQTT_KEEPALIVE = int(os.environ.get("MQTT_KEEPALIVE", "60"))

# Task Execution settings
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_TASK_DEFAULT_RATE_LIMIT = '1000/s' # Maximum of 1000 tasks per second
CELERY_TASK_TRACK_STARTED = True # Ability to track the task when it starts
CELERY_TASK_TIME_LIMIT = 30 * 60 # Hard timeout: (30 minutes)
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60 # Soft timeout:(25 minutes)

#Celery Worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 1 # Prefetch 1 task at a time
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000 #Prevent memory leaks

# Broker settings
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "priority_steps": list(range(10)),  # 10 priority levels (0-9)
    "sep": ":",
    "queue_order_strategy": "priority",
    "visibility_timeout": 3600,
}

# Task routing - Directing tasks to specific queues
CELERY_TASK_ROUTES = {
    "api.celery_tasks.validate_restock_task": {
        "queue": "default",
        "priority": 10,  # High priority
    },
    "api.celery_tasks.create_restock_item_task": {
        "queue": "default",
        "priority": 8,  # Medium priority
    },
    "api.celery_tasks.trigger_robot_mission_task": {
        "queue": "robot",
        "priority": 6,  # Robot-specific work queue
    },
    "api.celery_tasks.monitor_mission_task": {
        "queue": "monitoring",
        "priority": 3,  # Low priority
    },
    "api.celery_tasks.execute_restock_workflow": {
        "queue": "default",
        "priority": 9,
    },
}

# Scheduled tasks using Celery Beat
CELERY_BEAT_SCHEDULE = {
    "check-low-stock-daily": {
        "task": "api.celery_tasks.check_low_stock_products",
        "schedule": crontab(hour=6, minute=0),
    },
    "cleanup-old-restocks-daily": {
        "task": "api.celery_tasks.cleanup_old_restocks",
        "schedule": crontab(hour=2, minute=0),
    },
}

# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases
# Support either SQLite (default) or PostgreSQL via environment variables.
if os.environ.get("DATABASE_URL"):
    # Parse DATABASE_URL if provided (e.g. postgres://user:pass@host:port/dbname)
    from urllib.parse import urlparse

    url = urlparse(os.environ["DATABASE_URL"])
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": url.path[1:],
            "USER": url.username or "",
            "PASSWORD": url.password or "",
            "HOST": url.hostname or "",
            "PORT": url.port or "",
            "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", 600)),
        }
    }
elif os.environ.get("POSTGRES_DB"):
    # Individual Postgres environment variables
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "recap"),
            "USER": os.environ.get("POSTGRES_USER", "recap"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "recap_pass"),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", 600)),
        }
    }
else:
    # Default: SQLite for quick local/dev usage
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles/"

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "api.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}


SPECTACULAR_SETTINGS = {
    "TITLE": "RECAP",
    "DESCRIPTION": "An inventory management system designed to keep track and replenish items in a supermarket with the aid of a robot manipulator",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # OTHER SETTINGS
}

MEDIA_ROOT = BASE_DIR / "products/"
