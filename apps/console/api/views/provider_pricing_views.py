from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import ProviderPricing
from apps.console.api.serializers.provider_pricing_serializers import (
    ProviderPricingSerializer,
    ProviderPricingWriteSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin


class ProviderPricingViewSet(viewsets.ModelViewSet):
    """CRUD de ProviderPricing."""

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'
    queryset = ProviderPricing.objects.all().select_related(
        'provider', 'contract', 'metric'
    ).order_by('provider__name', 'metric__key')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProviderPricingWriteSerializer
        return ProviderPricingSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pricing = serializer.save()
        return Response(
            ProviderPricingSerializer(pricing).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        pricing = self.get_object()
        serializer = self.get_serializer(pricing, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        pricing = serializer.save()
        return Response(ProviderPricingSerializer(pricing).data)