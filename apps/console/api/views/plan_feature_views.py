from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import PlanFeature
from apps.console.api.serializers.plan_feature_serializers import (
    PlanFeatureSerializer,
    PlanFeatureWriteSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin


class PlanFeatureViewSet(viewsets.ModelViewSet):
    """CRUD de PlanFeature."""

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'
    queryset = PlanFeature.objects.all().select_related(
        'plan', 'feature'
    ).order_by('plan__name', 'feature__name')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PlanFeatureWriteSerializer
        return PlanFeatureSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pf = serializer.save(created_by=request.user)
        return Response(
            PlanFeatureSerializer(pf).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        pf = self.get_object()
        serializer = self.get_serializer(pf, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        pf = serializer.save()
        return Response(PlanFeatureSerializer(pf).data)