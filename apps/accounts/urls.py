from django.urls import path

from apps.accounts.api.authentication import (
    LoginView as APILoginView,
    GoogleLoginView,
    LogoutView,
    SessionView,
    CsrfView,
)
from apps.accounts.api.password import (
    PasswordChangeView,
    PasswordResetView,
    PasswordResetConfirmView,
)
from apps.accounts.api.user import UserCreateView, UserMeView
from apps.accounts.api.entry import EntryTargetView
from apps.accounts.views import (
    LoginView,
    GoogleOAuthEntryView,
    PostLoginRedirectView,
    ConsoleView,
)

urlpatterns = [
    # ===== PÁGINAS =====
    path('', PostLoginRedirectView.as_view(), name='home'),
    path('login/', LoginView.as_view(), name='login-page'),
    path('console/', ConsoleView.as_view(), name='console'),

    # ===== GOOGLE OAUTH ENTRY =====
    path('auth/google/', GoogleOAuthEntryView.as_view(), name='google-oauth-entry'),

    # ===== CSRF =====
    path('api/auth/csrf/', CsrfView.as_view(), name='csrf'),

    # ===== API - Autenticação =====
    path('api/auth/login/', APILoginView.as_view(), name='login'),
    path('api/auth/login/google/', GoogleLoginView.as_view(), name='google-login'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
    path('api/auth/session/', SessionView.as_view(), name='session'),

    # ===== API - Resolução de entrada =====
    path('api/auth/entry/', EntryTargetView.as_view(), name='entry-target'),

    # ===== API - Senha =====
    path('api/auth/password/change/', PasswordChangeView.as_view(), name='password-change'),
    path('api/auth/password/reset/', PasswordResetView.as_view(), name='password-reset'),
    path('api/auth/password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # ===== API - Usuário =====
    path('api/users/', UserCreateView.as_view(), name='user-create'),
    path('api/users/me/', UserMeView.as_view(), name='user-me'),
]