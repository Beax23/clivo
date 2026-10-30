"""
URLs do módulo intelligence.

Rotas expostas (montadas em /api/intelligence/ porque o config/urls.py
inclui este módulo com prefixo vazio — as rotas abaixo carregam o
prefixo explícito):

    GET     /api/intelligence/mesa/
    GET     /api/intelligence/clientes/<uuid:client_id>/
    GET     /api/intelligence/briefings/<uuid:briefing_id>/relatorio/
    POST    /api/intelligence/briefings/<uuid:briefing_id>/reanalyze/
    POST    /api/intelligence/clientes/<uuid:client_id>/reanalyze/
    GET     /api/intelligence/tags/
    GET     /api/intelligence/tags/<uuid:tag_id>/
    PATCH   /api/intelligence/tags/<uuid:tag_id>/
    GET     /api/intelligence/jobs/<uuid:job_id>/status/

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
    BriefingReanalyzeView,
    ClientReanalyzeView,
    JobStatusView,
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
        'api/intelligence/clientes/<uuid:client_id>/reanalyze/',
        ClientReanalyzeView.as_view(),
        name='intelligence-client-reanalyze',
    ),
    path(
        'api/intelligence/briefings/<uuid:briefing_id>/relatorio/',
        RelatorioView.as_view(),
        name='intelligence-relatorio',
    ),
    path(
        'api/intelligence/briefings/<uuid:briefing_id>/reanalyze/',
        BriefingReanalyzeView.as_view(),
        name='intelligence-briefing-reanalyze',
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
    path(
        'api/intelligence/jobs/<uuid:job_id>/status/',
        JobStatusView.as_view(),
        name='intelligence-job-status',
    ),
]