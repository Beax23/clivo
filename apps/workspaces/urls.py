from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.workspaces.api.views import (
    WorkspaceViewSet,
    WorkspaceStorageView,
)
from apps.workspaces.views import (
    WorkspaceEntryView,
    WorkspaceCreateView,
    InvitationEntryView,
    MesaView,
    LegacyMesaView,
    MesaRedirectView,
    ConfiguracoesView,
)

router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')

urlpatterns = [
    path(
        'workspaces/entrar/',
        WorkspaceEntryView.as_view(),
        name='workspace-entry',
    ),
    path(
        'workspaces/novo/',
        WorkspaceCreateView.as_view(),
        name='workspace-create',
    ),
    path(
        'convite/<str:token>/',
        InvitationEntryView.as_view(),
        name='workspace-invitation-entry',
    ),
    path(
        'mesa/<str:public_id>/',
        LegacyMesaView.as_view(),
        name='mesa',
    ),
    path(
        'mesa/',
        MesaRedirectView.as_view(),
        name='mesa-redirect',
    ),
    path(
        'configuracoes/',
        ConfiguracoesView.as_view(),
        name='configuracoes',
    ),
    path(
        'api/workspaces/<str:public_id>/storage/',
        WorkspaceStorageView.as_view(),
        name='workspace-storage',
    ),
    path('api/', include(router.urls)),
]