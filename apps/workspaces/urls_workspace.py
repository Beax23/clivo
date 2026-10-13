"""
Rotas do padrão /w/<public_id>/...
"""

from django.urls import path

from apps.workspaces.views import MesaView
from apps.briefings.views import BriefingDetailView


urlpatterns = [
    path('mesa/', MesaView.as_view(), name='w-mesa'),
    path(
        'briefings/<uuid:briefing_id>/',
        BriefingDetailView.as_view(),
        name='w-briefing-detail',
    ),
]