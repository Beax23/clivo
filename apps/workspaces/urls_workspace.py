"""
Rotas do padrão /w/<public_id>/...

Cada view resolve o workspace via `public_id` da URL + `request.user`.
A URL vence a sessão.

CONVENÇÕES:
    - O prefixo `/w/<public_id>/` é montado em config/urls.py.
    - Este arquivo registra as rotas RELATIVAS ao prefixo.
    - `integrations` NÃO tem mais página HTML nesse padrão.
      A integração é acionada por botões (ex: Importar Forms no Fluxo).
"""

from django.urls import path

from apps.workspaces.views import MesaView
from apps.briefings.views import BriefingDetailView


urlpatterns = [
    path('mesa/', MesaView.as_view(), name='w-mesa'),
    path(
        'briefings/<uuid:briefing_id>/',
        BriefingDetailView.as_view(),
        name='w-briefing-detail',
    ),
]