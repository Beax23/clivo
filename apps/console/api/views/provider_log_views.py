from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.console.models import ProviderLog
from apps.console.api.serializers.provider_log_serializers import ProviderLogSerializer
from apps.console.permissions.console_permissions import IsConsoleAdmin


class ProviderLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet read-only de ProviderLog.

    A criação NÃO é exposta via API. Só o ProviderLogService cria.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = ProviderLogSerializer
    lookup_field = 'id'

    def get_queryset(self):
        qs = ProviderLog.objects.all().select_related('provider', 'connection')

        provider_id = self.request.query_params.get('provider')
        workspace_id = self.request.query_params.get('workspace')
        status_filter = self.request.query_params.get('status')
        operation = self.request.query_params.get('operation')

        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if operation:
            qs = qs.filter(operation=operation)

        return qs.order_by('-occurred_at')