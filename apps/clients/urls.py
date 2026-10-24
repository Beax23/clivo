from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.clients.api.views import (
    ClientViewSet,
    ClientPortalViewSet,
    ClientPortalLoginView,
)
from apps.clients.views import (
    ClientesView,
    PortalLoginView,
    PortalHomeView,
    PortalChatView,
)


# =========================================================================
# ROUTERS
# =========================================================================
router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')

portal_router = DefaultRouter()
portal_router.register(r'portal', ClientPortalViewSet, basename='portal')


urlpatterns = [
    # ===== PÁGINAS DO ARQUITETO =====
    path(
        'clientes/',
        ClientesView.as_view(),
        name='clientes-page',
    ),

    # ===== PORTAL DO CLIENTE =====
    # Login por código público
    path(
        'portal/',
        PortalLoginView.as_view(),
        name='portal-login',
    ),
    # Lista de briefings
    path(
        'portal/home/',
        PortalHomeView.as_view(),
        name='portal-home',
    ),
    # Chat de perguntas de um briefing
    path(
        'portal/briefings/<uuid:briefing_id>/',
        PortalChatView.as_view(),
        name='portal-chat',
    ),

    # ===== APIs DO ARQUITETO =====
    path('api/', include(router.urls)),

    # ===== APIs DO PORTAL =====
    # Ordem importa: rotas explícitas ANTES do router,
    # para `login` não ser capturado por `portal/<pk>/`
    path(
        'api/portal/login/',
        ClientPortalLoginView.as_view(),
        name='portal-login-api',
    ),
    path('api/', include(portal_router.urls)),
]