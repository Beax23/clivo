from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.console.models import UsageRecord
from apps.console.api.serializers.usage_record_serializers import UsageRecordSerializer
from apps.console.permissions.console_permissions import IsConsoleAdmin


class UsageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet read-only de UsageRecord.

    A criação NÃO é exposta via API. Só o UsageRecordService cria.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = UsageRecordSerializer
    lookup_field = 'id'

    def get_queryset(self):
        qs = UsageRecord.objects.all().select_related('provider', 'metric', 'connection')

        provider_id = self.request.query_params.get('provider')
        workspace_id = self.request.query_params.get('workspace')
        metric_key = self.request.query_params.get('metric')
        operation = self.request.query_params.get('operation')

        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)
        if metric_key:
            qs = qs.filter(metric__key=metric_key)
        if operation:
            qs = qs.filter(operation=operation)

        return qs.order_by('-occurred_at')