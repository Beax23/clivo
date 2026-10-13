from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.clients.api.views import ClientViewSet, ClientPortalViewSet
from apps.clients.views import (
    ClientesView,
    PortalLoginView,
    PortalHomeView,
    PortalChatView,
)


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
    path(
        'portal/',
        PortalLoginView.as_view(),
        name='portal-login',
    ),
    path(
        'portal/home/',
        PortalHomeView.as_view(),
        name='portal-home',
    ),
    path(
        'portal/briefings/<uuid:briefing_id>/',
        PortalChatView.as_view(),
        name='portal-chat',
    ),

    # ===== APIs =====
    path('api/', include(router.urls)),
    path('api/', include(portal_router.urls)),
]