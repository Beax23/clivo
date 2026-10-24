"""
URLs do módulo integrations.

Rotas HTML (views):
    /integrations/google/start/      → inicia OAuth
    /integrations/google/callback/   → recebe retorno do Google

Rotas de API (DRF):
    /api/integrations/google/forms/search/   → busca formulários
    /api/integrations/google/forms/import/   → importa um formulário

Não existe página HTML `/w/<public_id>/integracoes/`.
A integração é uma capacidade acionada por botões em outras telas.
"""

from django.urls import path, include

from apps.integrations.views import (
    GoogleOAuthCallbackView,
    GoogleOAuthStartView,
)

app_name = 'integrations'

urlpatterns = [
    path(
        'integrations/google/start/',
        GoogleOAuthStartView.as_view(),
        name='google-start',
    ),
    path(
        'integrations/google/callback/',
        GoogleOAuthCallbackView.as_view(),
        name='google-callback',
    ),
    path('api/integrations/', include('apps.integrations.api.urls')),
]