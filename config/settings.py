from pathlib import Path
import os
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
PRODUCTION = os.getenv('VERCEL') == '1' or os.getenv('VERITY_PRODUCTION') == '1'
USE_SUPABASE = PRODUCTION or os.getenv('VERITY_USE_SUPABASE') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'local-demo-only-verity-secret' if not PRODUCTION else '')
DEBUG = not PRODUCTION
VERITY_JUDGE_PASSWORD = os.getenv('VERITY_JUDGE_PASSWORD', '') if PRODUCTION or os.getenv('VERITY_REQUIRE_JUDGE_ACCESS') == '1' else ''
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
SUPABASE_STORAGE_BUCKET = os.getenv('SUPABASE_STORAGE_BUCKET', 'resumes')
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver'] + [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]
if os.getenv('VERCEL_URL'): ALLOWED_HOSTS.append(os.environ['VERCEL_URL'])
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
if PRODUCTION:
    from django.core.exceptions import ImproperlyConfigured
    if not SECRET_KEY or not VERITY_JUDGE_PASSWORD:
        raise ImproperlyConfigured('Production requires DJANGO_SECRET_KEY and VERITY_JUDGE_PASSWORD.')
    if not os.getenv('DATABASE_URL', '').startswith(('postgres://', 'postgresql://')) or not SUPABASE_URL.startswith('https://') or not SUPABASE_SERVICE_ROLE_KEY:
        raise ImproperlyConfigured('Production requires PostgreSQL and private Supabase Storage settings.')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
WSGI_APPLICATION = 'config.wsgi.application'
INSTALLED_APPS = ['django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'recruitment']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware', 'recruitment.access.WorkspaceAccessMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.messages.context_processors.messages']}}]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20}}}
if USE_SUPABASE:
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(os.environ['DATABASE_URL'], conn_max_age=0, ssl_require=True)}
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
    DATABASES['default']['OPTIONS'].update({'prepare_threshold': None, 'connect_timeout': 10})
    STORAGES = {'default': {'BACKEND': 'recruitment.storage.SupabaseStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'Asia/Kolkata'
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024
X_FRAME_OPTIONS = 'DENY' if PRODUCTION else 'SAMEORIGIN'
