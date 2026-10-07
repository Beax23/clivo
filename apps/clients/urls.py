from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.clients.api.views import ClientViewSet, ClientPortalViewSet
from apps.clients.views import ClientesView

router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')

portal_router = DefaultRouter()
portal_router.register(r'portal', ClientPortalViewSet, basename='portal')

urlpatterns = [
    # ===== PÁGINAS HTML =====
    path(
        'clientes/',
        ClientesView.as_view(),
        name='clientes-page',
    ),

    # ===== APIs =====
    path('api/', include(router.urls)),
    path('api/', include(portal_router.urls)),
]