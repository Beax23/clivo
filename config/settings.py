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


SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")


if is_production():
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://clivoos.com")
    print(f"🚀 AMBIENTE DE PRODUCAO DETECTADO")
    print(f"📍 FRONTEND_URL: {FRONTEND_URL}")
else:
    FRONTEND_URL = os.getenv("FRONTEND_URL_DEV", "http://localhost:9000")
    print(f"💻 AMBIENTE DE DESENVOLVIMENTO DETECTADO")
    print(f"📍 FRONTEND_URL: {FRONTEND_URL}")


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

    # Django REST Framework
    'rest_framework',
    'rest_framework.authtoken',

    # Utilitários
    'corsheaders',
    'channels',
    'sslserver',
    'django_extensions',

    # Armazenamento
    'cloudinary',
    'cloudinary_storage',

    # Seus apps
    'apps.accounts',
    'apps.console',
    'apps.workspaces',
    'apps.clients',
    'apps.documents',
    #'apps.references',
    'apps.briefings',
    'apps.projects',
    'apps.timeline',
    'apps.intelligence',
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

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': GOOGLE_CLIENT_ID,
            'secret': GOOGLE_CLIENT_SECRET,
            'key': ''
        },
        'SCOPE': [
            'profile',
            'email',
            'openid',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
            'prompt': 'select_account',
        },
        'OAUTH_PKCE_ENABLED': True,
        'VERIFIED_EMAIL': True,
        'EMAIL_AUTHENTICATION': True,
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
# Nota: o middleware 'core.middleware.security.SecurityMiddleware' foi
# removido. Ele sobrescrevia X-Frame-Options: DENY em todas as respostas,
# quebrando o preview inline de PDF e o iframe do Office Viewer.
# O XFrameOptionsMiddleware do Django + @xframe_options_sameorigin na view
# de preview cobrem o caso corretamente.
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
]


ROOT_URLCONF = 'config.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'Ui' / 'templates',
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
            ],
        },
    },
]


WSGI_APPLICATION = 'config.wsgi.application'


# ============ DATABASE ============
if 'test' in sys.argv:
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
    BASE_DIR / 'Ui' / 'static',
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ============ CLOUDINARY ============
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}


SITE_NAME = os.getenv("SITE_NAME", "Clivo")


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
INFRASTRUCTURE_ENCRYPTION_KEY = os.getenv("PROVIDER_ENCRYPTION_KEY")


# ============ CACHE ============
if 'test' in sys.argv:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache',
        }
    }
    print("🧪 Usando LocMemCache para testes")
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
    print(f"🔴 Redis configurado com pool de conexões (max: 20)")


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
        'allauth': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
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
# SAMEORIGIN permite que nossos próprios templates embutam PDFs
# via <embed>/<iframe> de /api/documents/<id>/preview/.
# Views específicas que precisam bloquear usam @xframe_options_deny.
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============ EMAIL ============
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

if RESEND_API_KEY and RESEND_API_KEY != '':
    print(f"✉️ Usando Resend como provedor de email")
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.resend.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = 'resend'
    EMAIL_HOST_PASSWORD = RESEND_API_KEY
    EMAIL_USE_SSL = False
    EMAIL_TIMEOUT = 60
else:
    print(f"📝 RESEND_API_KEY nao configurada. Usando console para email.")
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Clivo <suporte@clivoos.com>")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "suporte@clivoos.com")


# ============ FEATURE FLAGS ============
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_WORKSPACE_USERS = 100

ENABLE_GOOGLE_LOGIN = True
ENABLE_MICROSOFT_LOGIN = os.getenv("ENABLE_MICROSOFT_LOGIN", "False") == "True"
ENABLE_GITHUB_LOGIN = os.getenv("ENABLE_GITHUB_LOGIN", "False") == "True"


print(f"✉️ EMAIL_BACKEND: {EMAIL_BACKEND}")
print(f"✉️ DEFAULT_FROM_EMAIL: {DEFAULT_FROM_EMAIL}")
print(f"📍 FRONTEND_URL FINAL: {FRONTEND_URL}")
print(f"🌍 AMBIENTE: {'PRODUCAO' if not DEBUG else 'DESENVOLVIMENTO'}")


# ============ RESEND INIT ============
try:
    import resend
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    if RESEND_API_KEY:
        resend.api_key = RESEND_API_KEY
        print("✅ Resend API inicializada com sucesso")
    else:
        print("⚠️ RESEND_API_KEY nao configurada para API")
except ImportError:
    print("ℹ️ Módulo resend não disponível")
except Exception as e:
    print(f"❌ Erro ao inicializar Resend: {e}")


# ============ ENVIRONMENT OVERRIDES ============
if not os.getenv('RENDER'):
    DEBUG = True
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'clivoos.com', 'clivo-mvp.onrender.com', 'clivo.onrender.com', 'testserver']
    CSRF_TRUSTED_ORIGINS = [
        'http://127.0.0.1:9000',
        'http://localhost:9000',
        'https://clivoos.com',
        'https://clivo-mvp.onrender.com',
        'https://clivo.onrender.com'
    ]
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    FRONTEND_URL = 'http://localhost:9000'
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:3000',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://localhost:9000',
        'http://127.0.0.1:9000',
        'https://clivoos.com',
        'https://www.clivoos.com',
        'https://clivo-mvp.onrender.com',
        'https://clivo.onrender.com'
    ]
    print("💻 FORCANDO AMBIENTE DE DESENVOLVIMENTO LOCAL")
    print(f"🐛 DEBUG: {DEBUG}")
    print(f"🌐 ALLOWED_HOSTS: {ALLOWED_HOSTS}")


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
    print("🔒 CONFIGURACOES DE PRODUCAO APLICADAS")
    print(f"🔒 CSRF_COOKIE_SECURE: {CSRF_COOKIE_SECURE}")
    print(f"🔒 CSRF_COOKIE_HTTPONLY: {CSRF_COOKIE_HTTPONLY}")
    print(f"🔒 SESSION_COOKIE_SECURE: {SESSION_COOKIE_SECURE}")


# ============ CLOUDINARY STORAGE ============
# IMPORTANTE: usamos SmartMediaCloudinaryStorage em vez do
# MediaCloudinaryStorage padrão. A versão padrão envia TUDO como
# `resource_type='image'`, o que faz o Cloudinary transformar `.docx`,
# `.xlsx`, `.pptx` e `.zip` em JPEG, corrompendo o arquivo original.
#
# A nossa subclasse decide o resource_type pela extensão: `raw` para
# documentos/binários, `image` para imagens/PDFs.
CLOUDINARY_CONFIGURED = all([
    os.getenv('CLOUDINARY_CLOUD_NAME'),
    os.getenv('CLOUDINARY_API_KEY'),
    os.getenv('CLOUDINARY_API_SECRET'),
])

if CLOUDINARY_CONFIGURED:
    DEFAULT_FILE_STORAGE = 'core.storage.SmartMediaCloudinaryStorage'
    print(f"☁️ Cloudinary configurado: {os.getenv('CLOUDINARY_CLOUD_NAME')}")
    print(f"   🔑 API Key: {os.getenv('CLOUDINARY_API_KEY')}")
    print(f"   📁 DEFAULT_FILE_STORAGE: core.storage.SmartMediaCloudinaryStorage")
    print(f"   🗂️  Documentos (.docx/.xlsx/etc) → resource_type='raw'")
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    print("💻 Usando armazenamento LOCAL")
    print(f"   📁 DEFAULT_FILE_STORAGE: django.core.files.storage.FileSystemStorage")


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


print("=" * 60)
print("✅ SETTINGS CARREGADOS COM SUCESSO")
print(f"☁️ Cloudinary: {'✅ CONFIGURADO' if CLOUDINARY_CONFIGURED else '❌ NÃO CONFIGURADO'}")
print(f"📁 Storage: {DEFAULT_FILE_STORAGE}")
print(f"🤖 OpenAI: {'✅ CONFIGURADO' if OPENAI_API_KEY else '❌ NÃO CONFIGURADO'}")
print(f"🖼️ Unsplash: {'✅ CONFIGURADO' if UNSPLASH_ACCESS_KEY else '❌ NÃO CONFIGURADO'}")
print(f"📌 Pinterest: {'✅ CONFIGURADO' if PINTEREST_ACCESS_TOKEN else '❌ NÃO CONFIGURADO'}")
print(f"🔑 Google Auth: {'✅ CONFIGURADO' if GOOGLE_CLIENT_ID else '❌ NÃO CONFIGURADO'}")
print(f"🔐 Email Verification: {'🔒 MANDATORY' if ACCOUNT_EMAIL_VERIFICATION == 'mandatory' else '📝 OPTIONAL'}")
print(f"🔗 Workspace Public ID: {'✅ Salt configurado' if WORKSPACE_PUBLIC_ID_SALT else '❌ Salt ausente'}")
print(f"🔒 Encryption Key: {'✅ Configurada' if INFRASTRUCTURE_ENCRYPTION_KEY else '❌ AUSENTE — gere PROVIDER_ENCRYPTION_KEY no .env'}")
print("=" * 60)