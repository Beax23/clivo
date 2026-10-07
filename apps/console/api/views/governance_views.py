from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import ConsoleGovernance
from apps.console.api.serializers.governance_serializers import (
    GovernanceSerializer,
    GovernanceCreateSerializer,
    GovernanceUpdateSerializer,
)
from apps.console.api.serializers.capability_serializers import CapabilitySerializer
from apps.console.services.governance_service import ConsoleGovernanceService
from apps.console.permissions.console_permissions import IsConsoleAdmin


class GovernanceViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de governanças do Console."""

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return GovernanceCreateSerializer
        if self.action in ['update', 'partial_update']:
            return GovernanceUpdateSerializer
        return GovernanceSerializer

    def get_queryset(self):
        qs = ConsoleGovernance.objects.all()

        scope = self.request.query_params.get('scope')
        if scope in ('console', 'workspace'):
            qs = qs.filter(scope=scope)

        return qs.order_by('name')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = ConsoleGovernanceService()
        governance = service.create_governance(
            key=serializer.validated_data['key'],
            name=serializer.validated_data['name'],
            description=serializer.validated_data.get('description', ''),
            created_by=request.user,
            scope=serializer.validated_data.get('scope', 'workspace'),
            is_system=serializer.validated_data.get('is_system', False),
            is_protected=serializer.validated_data.get('is_protected', False),
        )

        return Response(
            GovernanceSerializer(governance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        governance = self.get_object()
        serializer = self.get_serializer(
            governance, data=request.data, partial=False
        )
        serializer.is_valid(raise_exception=True)

        service = ConsoleGovernanceService()
        updated = service.update_governance(
            governance=governance,
            name=serializer.validated_data['name'],
            description=serializer.validated_data.get('description', ''),
            updated_by=request.user,
        )

        return Response(GovernanceSerializer(updated).data)

    def partial_update(self, request, *args, **kwargs):
        governance = self.get_object()
        serializer = self.get_serializer(
            governance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        service = ConsoleGovernanceService()
        updated = service.update_governance(
            governance=governance,
            name=serializer.validated_data.get('name'),
            description=serializer.validated_data.get('description', ''),
            updated_by=request.user,
        )

        return Response(GovernanceSerializer(updated).data)

    def destroy(self, request, *args, **kwargs):
        governance = self.get_object()

        service = ConsoleGovernanceService()
        service.delete_governance(governance)

        return Response(
            {'detail': 'Governança excluída com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )

    @action(
        detail=True,
        methods=['get', 'patch'],
        url_path='capabilities',
        url_name='governance-capabilities',
    )
    def capabilities(self, request, id=None):
        """
        GET  → lista capabilities da governança
        PATCH → substitui a lista de capabilities atribuídas

        Body do PATCH:
            {"capability_codes": ["workspaces.member.view", ...]}
        """
        governance = self.get_object()
        service = ConsoleGovernanceService()

        if request.method == 'GET':
            capabilities = service.get_governance_capabilities(governance)
            serializer = CapabilitySerializer(capabilities, many=True)
            return Response(serializer.data)

        # PATCH
        capability_codes = request.data.get('capability_codes', [])
        if not isinstance(capability_codes, list):
            return Response(
                {'error': 'capability_codes deve ser uma lista'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service.set_governance_capabilities(
            governance=governance,
            capability_codes=capability_codes,
            updated_by=request.user,
        )

        capabilities = service.get_governance_capabilities(governance)
        serializer = CapabilitySerializer(capabilities, many=True)
        return Response(serializer.data)