"""
URLs da API do módulo integrations.

Prefixo: `/api/integrations/` (definido em apps.integrations.urls).
"""

from django.urls import path

from apps.integrations.api.views import (
    GoogleFormsSearchView,
    GoogleFormsPreviewView,
    GoogleFormsImportView,
)


urlpatterns = [
    path(
        'google/forms/search/',
        GoogleFormsSearchView.as_view(),
        name='google-forms-search',
    ),
    path(
        'google/forms/preview/',
        GoogleFormsPreviewView.as_view(),
        name='google-forms-preview',
    ),
    path(
        'google/forms/import/',
        GoogleFormsImportView.as_view(),
        name='google-forms-import',
    ),
]