"""
URLs do módulo documents.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.documents.api.views import (
    DocumentViewSet,
    DocumentFolderViewSet,
    DocumentPublicPreviewView,
)
from apps.documents.views import DocumentsView


# Router do DocumentViewSet
documents_router = DefaultRouter()
documents_router.register(
    r'documents',
    DocumentViewSet,
    basename='document',
)

# Router do FolderViewSet — registrado com prefixo próprio
folders_router = DefaultRouter()
folders_router.register(
    r'documents/folders',
    DocumentFolderViewSet,
    basename='document-folder',
)


urlpatterns = [
    # ===== PÁGINAS =====
    path(
        'documents/',
        DocumentsView.as_view(),
        name='documents-page',
    ),

    # ===== ROTA PÚBLICA =====
    path(
        'api/documents/public-preview/<str:token>/',
        DocumentPublicPreviewView.as_view(),
        name='document-public-preview',
    ),

    # ===== APIs =====
    # O router de folders PRECISA vir antes do router de documents,
    # senão o padrão `documents/<pk>/` captura `documents/folders/`.
    path('api/', include(folders_router.urls)),
    path('api/', include(documents_router.urls)),
]