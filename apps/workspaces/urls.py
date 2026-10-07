from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.workspaces.api.views import WorkspaceViewSet
from apps.workspaces.views import (
    WorkspaceEntryView,
    WorkspaceCreateView,
    InvitationEntryView,
    MesaView,
    MesaRedirectView,
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
        MesaView.as_view(),
        name='mesa',
    ),
    path(
        'mesa/',
        MesaRedirectView.as_view(),
        name='mesa-redirect',
    ),
    path('api/', include(router.urls)),
]