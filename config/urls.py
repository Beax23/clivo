from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.accounts.urls')),
    path('', include('apps.workspaces.urls')),
    path('', include('apps.console.urls')),
    path('', include('apps.clients.urls')),
    path('', include('apps.documents.urls')),
    #path('', include('apps.references.urls')),
    path('', include('apps.briefings.urls')),
    path('', include('apps.projects.urls')),
    path('', include('apps.timeline.urls')),
    path('', include('apps.intelligence.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)