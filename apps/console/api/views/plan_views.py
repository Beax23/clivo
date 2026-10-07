from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import Plan, PlanFeature, Feature
from apps.console.api.serializers.plan_serializers import (
    PlanSerializer,
    PlanCreateSerializer,
    PlanUpdateSerializer,
    PlanFeatureLimitSerializer,
    PlanFeatureLimitWriteSerializer,
)
from apps.console.api.serializers.plan_feature_serializers import (
    PlanFeatureSerializer,
    PlanFeatureWriteSerializer,
)
from apps.console.services.plan_service import PlanService
from apps.console.permissions.console_permissions import IsConsoleAdmin


class PlanViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de planos do Console.

    CRUD completo + endpoints para associar Features e definir
    limites de métricas por Feature.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return PlanCreateSerializer
        if self.action in ['update', 'partial_update']:
            return PlanUpdateSerializer
        return PlanSerializer

    def get_queryset(self):
        return (
            Plan.objects.all()
            .prefetch_related(
                'plan_features__feature',
                'plan_features__limits__metric',
            )
            .order_by('price', 'name')
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save(created_by=request.user)
        return Response(
            PlanSerializer(plan).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        plan = self.get_object()
        serializer = self.get_serializer(plan, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        return Response(PlanSerializer(plan).data)

    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()

        if plan.is_default:
            return Response(
                {'error': 'O plano padrão não pode ser excluído'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan.delete()
        return Response(
            {'detail': 'Plano excluído com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )

    # ------------------------------------------------------------------
    # FEATURES DO PLANO
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='features')
    def list_features(self, request, id=None):
        """Lista as features associadas ao plano."""
        plan = self.get_object()
        plan_features = PlanService.get_plan_features(plan)
        serializer = PlanFeatureSerializer(plan_features, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='features')
    def add_feature(self, request, id=None):
        """
        Associa uma Feature ao plano.

        Body:
            {"feature": "<feature_id>"}
        """
        plan = self.get_object()
        feature_id = request.data.get('feature')

        if not feature_id:
            return Response(
                {'error': 'O campo "feature" é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            feature = Feature.objects.get(id=feature_id)
        except (Feature.DoesNotExist, ValueError):
            return Response(
                {'error': 'Feature não encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        plan_feature = PlanService.add_feature(
            plan=plan,
            feature=feature,
            created_by=request.user,
        )
        return Response(
            PlanFeatureSerializer(plan_feature).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['delete'],
        url_path=r'features/(?P<feature_id>[^/.]+)',
    )
    def remove_feature(self, request, id=None, feature_id=None):
        """Remove a associação entre o plano e uma Feature."""
        plan = self.get_object()

        try:
            feature = Feature.objects.get(id=feature_id)
        except (Feature.DoesNotExist, ValueError):
            return Response(
                {'error': 'Feature não encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        PlanService.remove_feature(plan, feature)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # LIMITES DE UMA FEATURE DO PLANO
    # ------------------------------------------------------------------

    def _get_plan_feature(self, plan, plan_feature_id):
        try:
            return PlanFeature.objects.get(id=plan_feature_id, plan=plan)
        except (PlanFeature.DoesNotExist, ValueError):
            return None

    @action(
        detail=True,
        methods=['get'],
        url_path=r'features/(?P<plan_feature_id>[^/.]+)/limits',
    )
    def get_limits(self, request, id=None, plan_feature_id=None):
        """Lista os limites de uma Feature dentro do plano."""
        plan = self.get_object()
        pf = self._get_plan_feature(plan, plan_feature_id)
        if pf is None:
            return Response(
                {'error': 'Feature do plano não encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        limits = PlanService.get_limits(pf)
        serializer = PlanFeatureLimitSerializer(limits, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['put', 'patch'],
        url_path=r'features/(?P<plan_feature_id>[^/.]+)/limits',
    )
    def set_limits(self, request, id=None, plan_feature_id=None):
        """
        Define os limites de uma Feature dentro do plano em lote.

        Body esperado:
            {"limits": [
                {"metric_key": "ai.credits", "limit_value": 1000,
                 "period": "monthly", "behavior": "hard_limit"},
                ...
            ]}
        """
        plan = self.get_object()
        pf = self._get_plan_feature(plan, plan_feature_id)
        if pf is None:
            return Response(
                {'error': 'Feature do plano não encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        limits_data = request.data.get('limits', [])
        if not isinstance(limits_data, list):
            return Response(
                {'error': 'limits deve ser uma lista'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PlanFeatureLimitWriteSerializer(
            data=limits_data, many=True
        )
        serializer.is_valid(raise_exception=True)

        created = PlanService.replace_limits(
            plan_feature=pf,
            limits_data=serializer.validated_data,
        )

        return Response(
            PlanFeatureLimitSerializer(created, many=True).data,
            status=status.HTTP_200_OK,
        )