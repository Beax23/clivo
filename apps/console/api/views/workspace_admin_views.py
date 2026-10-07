"""
AdminWorkspaceViewSet — o Console visualiza Workspaces.

REGRA:
    O Console NÃO administra Workspace (isso é da Mesa).
    O Console apenas OBSERVA. Read-only.

    No futuro, se for necessário "suspender um workspace", isso vira
    uma action específica — mas na V1 é só listagem.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.workspaces.models import Workspace
from apps.console.api.serializers.workspace_admin_serializers import (
    AdminWorkspaceSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin


class AdminWorkspaceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only. Lista todos os Workspaces da plataforma.

    Permite filtros por `q` (nome/slug), `is_active` e `city`.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = AdminWorkspaceSerializer
    lookup_field = 'id'

    def get_queryset(self):
        qs = (
            Workspace.objects
            .select_related('subscription__plan')
            .order_by('-created_at')
        )

        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(slug__icontains=q)

        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        elif is_active in ('0', 'false', 'False'):
            qs = qs.filter(is_active=False)

        city = self.request.query_params.get('city')
        if city:
            qs = qs.filter(city__icontains=city)

        return qs