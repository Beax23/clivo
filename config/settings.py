"""
Django settings for config project.
"""
from pathlib import Path
import os
import sys
import socket
import codecs
import dj_database_url
from dotenv import load_dotenv


if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    else:
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')
        except:
            pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Adiciona a pasta apps ao PYTHONPATH para imports mais limpos
sys.path.insert(0, str(BASE_DIR / "apps"))
sys.path.insert(0, str(BASE_DIR))


def is_production():
    if 'RENDER' in os.environ:
        return True
    try:
        hostname = socket.gethostname()
        if 'render' in hostname.lower():
            return True
    except:
        pass
    if os.getenv("DEBUG", "False") == "False":
        return True
    return False


def _is_running_tests():
    """
    Detecta se o Django está sendo executado em modo de teste.
    """
    if 'test' in sys.argv:
        return True
    if any('pytest' in arg for arg in sys.argv[:2]):
        return True
    if 'pytest' in sys.modules:
        return True
    return False


SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")


if is_production():
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://clivoos.com")
    print("🚀 Ambiente de PRODUÇÃO")
    print(f"   FRONTEND_URL: {FRONTEND_URL}")
else:
    FRONTEND_URL = os.getenv("FRONTEND_URL_DEV", "http://localhost:9000")
    print("🔧 Ambiente de DESENVOLVIMENTO")
    print(f"   FRONTEND_URL: {FRONTEND_URL}")


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Django AllAuth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.pinterest',

    # Django REST Framework
    'rest_framework',
    'rest_framework.authtoken',

    # Utilitarios
    'corsheaders',
    'channels',
    'sslserver',
    'django_extensions',

    # Storage S3-compatible (B2 / R2)
    'storages',

    # Seus apps
    'apps.accounts',
    'apps.console',
    'apps.workspaces',
    'apps.clients',
    'apps.documents',
    'apps.briefings',
    'apps.intelligence',
    'apps.integrations',
]


SITE_ID = int(os.getenv("SITE_ID", 1))


AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]


AUTH_USER_MODEL = 'accounts.User'


# ============ ALLAUTH CONFIGURATIONS ============
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_RATE_LIMITS = {
    'login_failed': '5/300',
}
ACCOUNT_PASSWORD_MIN_LENGTH = 6
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_CONFIRM_EMAIL_ON_GET = True

SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'mandatory'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_STORE_TOKENS = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.social.CustomSocialAccountAdapter'

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
# ============ INTEGRATIONS — GOOGLE (Drive + Forms) ============
# OAuth Client DEDICADO para o app `integrations`.
# Separado do GOOGLE_CLIENT_ID do allauth (que é para login).
# Ver `apps/integrations/providers/google/connector.py` para uso.
INTEGRATIONS_GOOGLE_CLIENT_ID = os.getenv("INTEGRATIONS_GOOGLE_CLIENT_ID")
INTEGRATIONS_GOOGLE_CLIENT_SECRET = os.getenv("INTEGRATIONS_GOOGLE_CLIENT_SECRET")

PINTEREST_CLIENT_ID = os.getenv("PINTEREST_CLIENT_ID", "")
PINTEREST_CLIENT_SECRET = os.getenv("PINTEREST_CLIENT_SECRET", "")

SOCIALACCOUNT_PROVIDERS = {
    # ─────────────────────────────────────────────────────────────────
    # GOOGLE
    #
    # IMPORTANTE: NÃO definimos `APP` aqui.
    #
    # As credenciais do Google vêm EXCLUSIVAMENTE do `SocialApp` no
    # banco de dados (configurado via Django Admin em
    # /admin/socialaccount/socialapp/).
    #
    # Motivo: o AllAuth não permite configurar o mesmo provider em
    # dois lugares ao mesmo tempo (`settings.py` + `SocialApp`).
    # Isso causa `MultipleObjectsReturned` ou `state mismatch` no
    # callback, resultando em 401.
    # ─────────────────────────────────────────────────────────────────
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'offline',
        },
        'OAUTH_PKCE_ENABLED': True,
        'VERIFIED_EMAIL': True,
        'EMAIL_AUTHENTICATION': True,
    },
    'pinterest': {
        'APP': {
            'client_id': PINTEREST_CLIENT_ID,
            'secret': PINTEREST_CLIENT_SECRET,
            'key': ''
        },
        'SCOPE': [
            'pins:read',
            'boards:read',
        ],
        'AUTH_PARAMS': {
            'prompt': 'consent',
        },
        'VERIFIED_EMAIL': False,
        'EMAIL_AUTHENTICATION': False,
    }
}


# ============ REST FRAMEWORK ============
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        'login': '5/minute',
        'reset': '3/hour',
        'register': '10/hour',
    },
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
}


# ============ MIDDLEWARE ============
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'core.middleware.correlation_id.CorrelationIdMiddleware',
    'apps.accounts.middleware.SessionTrackingMiddleware',

    # ▼ ADICIONE ESTA LINHA
    'apps.workspaces.middleware.WorkspaceContextMiddleware',

    'apps.clients.middleware.ClientPortalMiddleware',
]


ROOT_URLCONF = 'config.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'ui' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'apps.workspaces.context.workspace_public_id',
            ],
        },
    },
]


WSGI_APPLICATION = 'config.wsgi.application'


# ============ DATABASE ============
if _is_running_tests():
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
            'TEST': {
                'NAME': ':memory:',
            }
        }
    }
else:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        DATABASES = {
            "default": dj_database_url.parse(
                database_url,
                conn_max_age=600,
                ssl_require=True,
            )
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }


# ============ PASSWORD VALIDATION ============
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 6,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ============ INTERNATIONALIZATION ============
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True


# ============ STATIC & MEDIA ============
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'ui' / 'static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ============ STORAGE S3-COMPATIBLE ============
#
# Dois provedores suportados, em ordem de prioridade:
#
#   1. Backblaze B2  (ativo — usa credenciais B2_*)
#   2. Cloudflare R2 (reservado — usa credenciais CLOUDFLARE_R2_*)
#   3. Local         (fallback de desenvolvimento)

# --- Backblaze B2 ---
B2_KEY_ID = os.getenv('B2_KEY_ID', '')
B2_APPLICATION_KEY = os.getenv('B2_APPLICATION_KEY', '')
B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME', '')
B2_ENDPOINT = os.getenv('B2_ENDPOINT', '')
B2_REGION = os.getenv('B2_REGION', '')

B2_CONFIGURED = all([
    B2_KEY_ID,
    B2_APPLICATION_KEY,
    B2_BUCKET_NAME,
    B2_ENDPOINT,
    B2_REGION,
])

# --- Cloudflare R2 ---
R2_ACCOUNT_ID = os.getenv('CLOUDFLARE_R2_ACCOUNT_ID', '')
R2_ACCESS_KEY_ID = os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY', '')
R2_BUCKET_NAME = os.getenv('CLOUDFLARE_R2_BUCKET_NAME', '')
R2_ENDPOINT = os.getenv('CLOUDFLARE_R2_ENDPOINT', '')
R2_CUSTOM_DOMAIN = os.getenv('CLOUDFLARE_R2_CUSTOM_DOMAIN', '')
R2_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN', '')

R2_CONFIGURED = all([
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_ENDPOINT,
])

# --- Resolução da prioridade ---
if B2_CONFIGURED:
    _active_storage = 'b2'
    AWS_ACCESS_KEY_ID = B2_KEY_ID
    AWS_SECRET_ACCESS_KEY = B2_APPLICATION_KEY
    AWS_STORAGE_BUCKET_NAME = B2_BUCKET_NAME
    AWS_S3_ENDPOINT_URL = B2_ENDPOINT
    AWS_S3_REGION_NAME = B2_REGION
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = 'virtual'
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    _default_storage_backend = 'storages.backends.s3.S3Storage'
    print(f"💾 Backblaze B2 ativo")
    print(f"   bucket: {B2_BUCKET_NAME}")
    print(f"   endpoint: {B2_ENDPOINT}")
    print(f"   região: {B2_REGION}")

elif R2_CONFIGURED:
    _active_storage = 'r2'
    AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
    AWS_S3_ENDPOINT_URL = R2_ENDPOINT
    AWS_S3_REGION_NAME = 'auto'
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = 'virtual'
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    if R2_CUSTOM_DOMAIN:
        AWS_S3_CUSTOM_DOMAIN = R2_CUSTOM_DOMAIN
        AWS_QUERYSTRING_AUTH = False
    _default_storage_backend = 'storages.backends.s3.S3Storage'
    print(f"💾 Cloudflare R2 ativo")
    print(f"   bucket: {R2_BUCKET_NAME}")
    print(f"   endpoint: {R2_ENDPOINT}")
    if R2_CUSTOM_DOMAIN:
        print(f"   custom domain: {R2_CUSTOM_DOMAIN}")
    else:
        print(f"   URLs assinadas (querystring auth)")
else:
    _active_storage = 'local'
    _default_storage_backend = 'django.core.files.storage.FileSystemStorage'
    print("⚠️  Nenhum storage remoto configurado — usando LOCAL")

print(f"   storage backend: {_default_storage_backend}")


# ============ STORAGES (Django 6) ============
STORAGES = {
    "default": {
        "BACKEND": _default_storage_backend,
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Compat: manter em sincronia para codigo legado.
DEFAULT_FILE_STORAGE = _default_storage_backend


# ============ WORKSPACE PUBLIC ID ============
WORKSPACE_PUBLIC_ID_SALT = os.getenv(
    'WORKSPACE_PUBLIC_ID_SALT',
    'dev-only-change-me-in-production',
)


# ============ CELERY ============
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False") == "True"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# ============ ENCRYPTION ============
# Chave de infraestrutura da Clivo (usada por sistemas internos).
INFRASTRUCTURE_ENCRYPTION_KEY = os.getenv("PROVIDER_ENCRYPTION_KEY")

# Chave dedicada ao módulo `integrations`.
#
# Fallback explícito: no V1, reutiliza a chave de infraestrutura para
# evitar duas chaves em dev. Em produção, defina
# INTEGRATIONS_ENCRYPTION_KEY no .env com uma chave Fernet dedicada.
#
# Formato esperado: base64-url de 32 bytes (44 caracteres).
# Gerar com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
INTEGRATIONS_ENCRYPTION_KEY = os.getenv(
    "INTEGRATIONS_ENCRYPTION_KEY",
    INFRASTRUCTURE_ENCRYPTION_KEY,   # ← NOVO: fallback para V1
)


# ============ CACHE ============
if _is_running_tests():
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache',
        }
    }
    print("🧪 Cache: LocMemCache (testes)")
else:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': os.getenv("REDIS_URL", "redis://localhost:6379/1"),
            'TIMEOUT': 300,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'db': 1,
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 20,
                    'retry_on_timeout': True,
                    'retry_on_error': [ConnectionError, TimeoutError],
                },
                'RETRY_ON_TIMEOUT': True,
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
            }
        }
    }
    print("🔴 Cache: Redis (pool 20 conexões)")


# ============ CORS ============
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if os.getenv("CORS_ALLOWED_ORIGINS") else [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://clivoos.com",
    "https://www.clivoos.com",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]


# ============ LOGGING ============
LOG_DIR = BASE_DIR / 'logs'
if not LOG_DIR.exists():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
        'console': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'django.log',
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        'file_error': {
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'errors.log',
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        # ── DEBUG para diagnosticar login Google ────────────────────
        'allauth': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'allauth.socialaccount.providers.oauth2': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'allauth.socialaccount.providers.google': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'socialaccount': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # ────────────────────────────────────────────────────────────
        'console': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'workspaces': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'clients': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'integrations': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'documents': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'references': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # Bibliotecas de storage/S3 — extremamente verbosas em DEBUG
        'botocore': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'boto3': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        's3transfer': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'urllib3': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}


# ============ SESSION & CSRF ============
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = 'clivo_session'
SESSION_SAVE_EVERY_REQUEST = True

CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_USE_SESSIONS = False
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'


# ============ SECURITY ============
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============ EMAIL ============
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

if RESEND_API_KEY and RESEND_API_KEY != '':
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.resend.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = 'resend'
    EMAIL_HOST_PASSWORD = RESEND_API_KEY
    EMAIL_USE_SSL = False
    EMAIL_TIMEOUT = 60
    print("📧 Email: Resend (SMTP)")
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    print("📧 Email: console (sem RESEND_API_KEY)")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Clivo <suporte@clivoos.com>")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "suporte@clivoos.com")


# ============ FEATURE FLAGS ============
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_WORKSPACE_USERS = 100

ENABLE_GOOGLE_LOGIN = True
ENABLE_MICROSOFT_LOGIN = os.getenv("ENABLE_MICROSOFT_LOGIN", "False") == "True"
ENABLE_GITHUB_LOGIN = os.getenv("ENABLE_GITHUB_LOGIN", "False") == "True"
ENABLE_PINTEREST_LOGIN = bool(PINTEREST_CLIENT_ID and PINTEREST_CLIENT_SECRET)


# ============ RESEND INIT ============
try:
    import resend
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    if RESEND_API_KEY:
        resend.api_key = RESEND_API_KEY
except ImportError:
    pass
except Exception as e:
    print(f"⚠️  Erro ao inicializar Resend: {e}")


# ============ ENVIRONMENT OVERRIDES ============
if not os.getenv('RENDER'):
    DEBUG = True
    ALLOWED_HOSTS = [
        '127.0.0.1',
        'localhost',
        'clivoos.com',
        'clivo-mvp.onrender.com',
        'clivo.onrender.com',
        'testserver',
    ]
    # ─────────────────────────────────────────────────────────────
    # CSRF_TRUSTED_ORIGINS — inclui AMBAS as portas 8000 e 9000
    # para evitar problemas durante o desenvolvimento.
    # ─────────────────────────────────────────────────────────────
    CSRF_TRUSTED_ORIGINS = [
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        'http://127.0.0.1:9000',
        'http://localhost:9000',
        'https://clivoos.com',
        'https://clivo-mvp.onrender.com',
        'https://clivo.onrender.com',
    ]
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    FRONTEND_URL = 'http://localhost:8000'
    # ─────────────────────────────────────────────────────────────
    # CORS_ALLOWED_ORIGINS — inclui AMBAS as portas 8000 e 9000
    # ─────────────────────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:3000',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://localhost:9000',
        'http://127.0.0.1:9000',
        'https://clivoos.com',
        'https://www.clivoos.com',
        'https://clivo-mvp.onrender.com',
        'https://clivo.onrender.com',
    ]
    print("🔧 Overrides locais aplicados (DEBUG=True)")


if is_production():
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    # ── Corrige detecção de HTTPS atrás do proxy do Render ────────
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    # ─────────────────────────────────────────────────────────────
    print("🔒 Configurações de produção aplicadas")


# ============ AI & INTEGRATIONS ============
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
UNSPLASH_SECRET_KEY = os.getenv("UNSPLASH_SECRET_KEY", "")
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
LIVEKIT_HOST = os.getenv("LIVEKIT_HOST")

STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

RENDER_API_KEY = os.getenv("RENDER_API_KEY")


# ============ DOCUMENTS ============
DOCUMENTS_STORAGE_QUOTA_BYTES = int(
    os.getenv("DOCUMENTS_STORAGE_QUOTA_BYTES", 5 * 1024 ** 3)  # 5 GB
)


# ============ REFERENCES ============
REFERENCES_STORAGE_QUOTA_BYTES = int(
    os.getenv("REFERENCES_STORAGE_QUOTA_BYTES", 5 * 1024 ** 3)  # 5 GB
)

REFERENCES_REQUIRE_PILLOW = (
    os.getenv("REFERENCES_REQUIRE_PILLOW", "True") == "True"
)

REFERENCES_MAX_IMAGE_SIZE_BYTES = int(
    os.getenv("REFERENCES_MAX_IMAGE_SIZE_BYTES", 25 * 1024 * 1024)
)

REFERENCES_MAX_IMAGE_PIXELS = int(
    os.getenv("REFERENCES_MAX_IMAGE_PIXELS", 100_000_000)
)


# ============ DIAGNÓSTICO FINAL ============
try:
    import PIL
    _pillow_ok = True
    _pillow_version = getattr(PIL, '__version__', '?')
except ImportError:
    _pillow_ok = False
    _pillow_version = None

print("")
print("=" * 60)
print("📋 DIAGNÓSTICO FINAL")
print("=" * 60)

if _is_running_tests():
    print("Modo:                 TESTES (SQLite em memória)")
    print(f"Cache:                LocMemCache")

print(f"Storage ativo:        {_active_storage.upper()}")
print(f"Storage backend:      {_default_storage_backend}")
print(f"B2 configurado:       {'✅' if B2_CONFIGURED else '❌'}")
print(f"R2 configurado:       {'✅' if R2_CONFIGURED else '❌'}")
print(f"OpenAI:               {'✅' if OPENAI_API_KEY else '❌'}")
print(f"Unsplash:             {'✅' if UNSPLASH_ACCESS_KEY else '❌'}")
print(f"Pinterest API:        {'✅' if PINTEREST_ACCESS_TOKEN else '❌'}")
print(f"Google Auth:          {'✅' if GOOGLE_CLIENT_ID else '❌'}")
print(f"Pinterest Auth:       {'✅' if ENABLE_PINTEREST_LOGIN else '❌'}")
print(f"Email Verification:   {ACCOUNT_EMAIL_VERIFICATION}")
print(f"Workspace Public ID:  {'✅ salt configurado' if WORKSPACE_PUBLIC_ID_SALT else '❌ salt ausente'}")
print(f"Encryption (Infra):   {'✅' if INFRASTRUCTURE_ENCRYPTION_KEY else '❌ ausente'}")
print(f"Encryption (Integr):  {'✅' if INTEGRATIONS_ENCRYPTION_KEY else '❌ ausente'}")
print(f"Cota Arquivos:        {DOCUMENTS_STORAGE_QUOTA_BYTES // (1024 ** 3)} GB por workspace")
print(f"Cota Referências:     {REFERENCES_STORAGE_QUOTA_BYTES // (1024 ** 3)} GB por workspace")
print(f"Pillow:               {'✅ v' + _pillow_version if _pillow_ok else '❌ ausente'}")
print(f"Require Pillow:       {'✅' if REFERENCES_REQUIRE_PILLOW else '❌'}")
print(f"Max imagem:           {REFERENCES_MAX_IMAGE_SIZE_BYTES // (1024 ** 2)} MB")
print(f"Max pixels:           {REFERENCES_MAX_IMAGE_PIXELS:,}".replace(',', '.'))
print("=" * 60)
print("")