"""
Local settings for autotimelapse project.
Tự động nạp cấu hình từ biến môi trường (SITE_DOMAIN, SECRET_KEY, DB_*, MQTT_*, SEAWEED_*).
"""

import os
from pathlib import Path

# Thử load .env / site.env nếu python-dotenv khả dụng
try:
    from dotenv import load_dotenv
    current_dir = Path(__file__).resolve().parent
    search_paths = [
        current_dir.parent.parent.parent / 'environment' / 'site.env',
        current_dir.parent.parent.parent / '.env',
        Path('/app/environment/site.env'),
        Path('/app/.env'),
    ]
    for p in search_paths:
        if p.exists():
            load_dotenv(p)
            break
except ImportError:
    pass

# Site Domain & Base Configs
SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "localhost").strip()
SITE_SCHEME = os.environ.get("SITE_SCHEME", "http").strip()
SITE_NAME = os.environ.get("SITE_NAME", "AutoTimelapse Cloud").strip()

# Core Security & Hosts
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-u_am=8by79nhqo9p@msu21tm5v_nwlrvau@d3(z)qx-fog_%a!")
DEBUG = os.environ.get("DEBUG", "0") == "1"

_allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "*").strip()
_hosts_list = [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()]
if "*" in _hosts_list:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = _hosts_list

_csrf_origins_env = os.environ.get("CSRF_TRUSTED_ORIGINS", f"{SITE_SCHEME}://{SITE_DOMAIN},http://localhost,http://127.0.0.1").strip()
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([o.strip() for o in _csrf_origins_env.split(",") if o.strip()]))

# Database Configuration
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "autotimelapse"),
        "USER": os.environ.get("DB_USER", "atl_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "atl_pass_2026"),
        "HOST": os.environ.get("DB_HOST", "postgres"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Redis & Cache & Celery
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/1",
        "TIMEOUT": 300,
    }
}

CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/2"

# MQTT Broker Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "admin")
MQTT_PASS = os.environ.get("MQTT_PASS", "Admin@Mqtt2026")
MQTT_SKIP_ACL_SETUP = os.environ.get("MQTT_SKIP_ACL_SETUP", "0") == "1"
MQTT_ENABLED = os.environ.get("MQTT_ENABLED", "1") == "1"

# SeaweedFS / Storage Configuration
SEAWEED = {
    "ENDPOINT_URL": os.environ.get("SEAWEED_ENDPOINT_URL", "http://seaweed-filer:8333"),
    "PUBLIC_ENDPOINT_URL": os.environ.get("SEAWEED_PUBLIC_ENDPOINT_URL", f"{SITE_SCHEME}://{SITE_DOMAIN}:8333"),
    "ACCESS_KEY": os.environ.get("SEAWEED_ACCESS_KEY", "atl_api_f47b8b69ca6e"),
    "SECRET_KEY": os.environ.get("SEAWEED_SECRET_KEY", "RuknSq0JJM6RsIt3DnFf0ZcHUfTlsAN1qDWCtLIankM"),
    "BUCKET": os.environ.get("SEAWEED_BUCKET", "media"),
    "REGION": "us-east-1",
    "PRESIGN_EXPIRE": 3600,
    "ADDRESSING_STYLE": "path",
}

# Reverse proxy SSL header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
