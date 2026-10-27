"""
URLs do módulo intelligence.

Rotas expostas (montadas em /api/intelligence/ porque o config/urls.py
inclui este módulo com prefixo vazio — as rotas abaixo carregam o
prefixo explícito):

    GET     /api/intelligence/mesa/
    GET     /api/intelligence/clientes/<uuid:client_id>/
    GET     /api/intelligence/briefings/<uuid:briefing_id>/relatorio/
    GET     /api/intelligence/tags/
    GET     /api/intelligence/tags/<uuid:tag_id>/
    PATCH   /api/intelligence/tags/<uuid:tag_id>/

Sem este prefixo, as rotas colidiriam com:
    - /mesa/        (apps.workspaces.urls → MesaRedirectView)
    - /clientes/    (apps.clients.urls → página HTML de clientes do arquiteto)
    - /tags/...     (inexistente hoje, mas reservado)

Por isso o prefixo é obrigatório.
"""

from django.urls import path

from apps.intelligence.api.views import (
    MesaView,
    ClienteView,
    RelatorioView,
    TagListView,
    TagDetailView,
)


urlpatterns = [
    path(
        'api/intelligence/mesa/',
        MesaView.as_view(),
        name='intelligence-mesa',
    ),
    path(
        'api/intelligence/clientes/<uuid:client_id>/',
        ClienteView.as_view(),
        name='intelligence-cliente',
    ),
    path(
        'api/intelligence/briefings/<uuid:briefing_id>/relatorio/',
        RelatorioView.as_view(),
        name='intelligence-relatorio',
    ),
    path(
        'api/intelligence/tags/',
        TagListView.as_view(),
        name='intelligence-tags',
    ),
    path(
        'api/intelligence/tags/<uuid:tag_id>/',
        TagDetailView.as_view(),
        name='intelligence-tag-detail',
    ),
]