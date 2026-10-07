from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import ConsoleCapability
from apps.console.api.serializers.capability_serializers import CapabilitySerializer
from apps.console.permissions.console_permissions import IsConsoleAdmin


class CapabilityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para consulta de capabilities.

    Read-only. A criação/atualização acontece via `sync_capabilities`.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = CapabilitySerializer
    lookup_field = 'id'

    def get_queryset(self):
        include_inactive = self.request.query_params.get('include_inactive') == '1'
        qs = ConsoleCapability.objects.all()
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return qs.order_by('source_app', 'name')

    @action(detail=False, methods=['get'], url_path='by-app')
    def by_app(self, request):
        """Lista capabilities agrupadas por app."""
        capabilities = self.get_queryset()

        grouped = {}
        for cap in capabilities:
            grouped.setdefault(cap.source_app, []).append(
                CapabilitySerializer(cap).data
            )

        return Response(grouped)

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        query = request.query_params.get('q', '').strip()

        if not query:
            return Response(
                {'error': 'Parâmetro "q" é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        capabilities = self.get_queryset().filter(
            code__icontains=query
        ) | self.get_queryset().filter(
            name__icontains=query
        )

        serializer = CapabilitySerializer(capabilities, many=True)
        return Response(serializer.data)