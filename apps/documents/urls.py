"""
URLs do módulo documents.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.documents.api.views import DocumentViewSet
from apps.documents.api.views.document_views import DocumentPublicPreviewView
from apps.documents.views import DocumentsView


router = DefaultRouter()
router.register(
    r'documents',
    DocumentViewSet,
    basename='document',
)


urlpatterns = [
    # ===== PÁGINAS =====
    path(
        'documents/',
        DocumentsView.as_view(),
        name='documents-page',
    ),

    # ===== ROTA PÚBLICA (token assinado, para Office Viewer) =====
    path(
        'api/documents/public-preview/<str:token>/',
        DocumentPublicPreviewView.as_view(),
        name='document-public-preview',
    ),

    # ===== APIs =====
    path('api/', include(router.urls)),
]