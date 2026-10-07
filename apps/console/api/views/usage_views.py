from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.console.models import UsageMetric
from apps.console.api.serializers.usage_serializers import UsageMetricSerializer
from apps.console.permissions.console_permissions import IsConsoleAdmin


class UsageMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet read-only do catálogo de métricas.

    As métricas são populadas via seed e não são editáveis pela API.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = UsageMetricSerializer
    lookup_field = 'id'
    queryset = UsageMetric.objects.all().order_by('key')