from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),

    # ============================================================
    # Service Worker na RAIZ (necessário para o PWA funcionar
    # com escopo global /). Servido como template para poder usar
    # {% static %} no conteúdo e respeitar o STATIC_URL.
    # ============================================================
    path(
        'sw.js',
        TemplateView.as_view(
            template_name='sw.js',
            content_type='application/javascript',
        ),
        name='service-worker',
    ),

    # ============================================================
    # Padrão novo: /w/<public_id>/...
    # ============================================================
    path('w/<str:public_id>/', include('apps.workspaces.urls_workspace')),

    # ============================================================
    # Rotas antigas — mantidas durante a migração.
    # ============================================================
    path('', include('apps.accounts.urls')),
    path('', include('apps.workspaces.urls')),
    path('', include('apps.console.urls')),
    path('', include('apps.clients.urls')),
    path('', include('apps.documents.urls')),
    path('', include('apps.references.urls')),
    path('', include('apps.briefings.urls')),
    path('', include('apps.projects.urls')),
    path('', include('apps.timeline.urls')),
    path('', include('apps.intelligence.urls')),
    path('', include('apps.integrations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)