from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import ProtectedError

from apps.console.models import Feature
from apps.console.api.serializers.feature_serializers import (
    FeatureSerializer,
    FeatureCreateSerializer,
    FeatureUpdateSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin


class FeatureViewSet(viewsets.ModelViewSet):
    """CRUD de Feature."""

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return FeatureCreateSerializer
        if self.action in ['update', 'partial_update']:
            return FeatureUpdateSerializer
        return FeatureSerializer

    def get_queryset(self):
        return Feature.objects.all().order_by('name')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feature = serializer.save()
        return Response(
            FeatureSerializer(feature).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        feature = self.get_object()
        serializer = self.get_serializer(feature, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        feature = serializer.save()
        return Response(FeatureSerializer(feature).data)

    def destroy(self, request, *args, **kwargs):
        """
        Exclui uma Feature.

        Se a Feature estiver associada a algum Plan (via PlanFeature),
        o `PROTECT` da FK impede a exclusão. Retornamos 409 com
        mensagem clara.
        """
        feature = self.get_object()
        try:
            feature.delete()
        except ProtectedError:
            return Response(
                {
                    'error': (
                        'Esta feature está associada a um ou mais planos '
                        'e não pode ser excluída. Remova as associações '
                        'primeiro.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {'detail': 'Feature excluída com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )