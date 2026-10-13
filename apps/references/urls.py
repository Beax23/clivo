"""
URLs do módulo references.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.references.api.views import (
    ReferenceViewSet,
    ReferenceFolderViewSet,
    ReferenceCategoryViewSet,
    WorkspaceStorageView,
    DriveStatusView,
    DriveFilesView,
    DriveImportView,
    PinterestStatusView,
    PinterestPinsView,
    PinterestImportView,
)
from apps.references.views import ReferencesView


references_router = DefaultRouter()
references_router.register(r'references', ReferenceViewSet, basename='reference')

folders_router = DefaultRouter()
folders_router.register(r'reference-folders', ReferenceFolderViewSet, basename='reference-folder')

categories_router = DefaultRouter()
categories_router.register(r'reference-categories', ReferenceCategoryViewSet, basename='reference-category')


urlpatterns = [
    path('references/', ReferencesView.as_view(), name='references-page'),

    path('api/workspace/storage/', WorkspaceStorageView.as_view(), name='workspace-storage'),

    path('api/drive/status/', DriveStatusView.as_view(), name='drive-status'),
    path('api/drive/files/', DriveFilesView.as_view(), name='drive-files'),
    path('api/drive/import/', DriveImportView.as_view(), name='drive-import'),

    path('api/pinterest/status/', PinterestStatusView.as_view(), name='pinterest-status'),
    path('api/pinterest/pins/', PinterestPinsView.as_view(), name='pinterest-pins'),
    path('api/pinterest/import/', PinterestImportView.as_view(), name='pinterest-import'),

    # Ordem: categories antes de folders antes de references,
    # para que "reference-categories" não seja capturado pelo prefixo "references".
    path('api/', include(categories_router.urls)),
    path('api/', include(folders_router.urls)),
    path('api/', include(references_router.urls)),
]