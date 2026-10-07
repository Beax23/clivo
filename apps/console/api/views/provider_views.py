from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import (
    Provider,
    ProviderConnection,
    ProviderContract,
)
from apps.console.api.serializers.provider_serializers import (
    ProviderSerializer,
    ProviderCreateSerializer,
    ProviderUpdateSerializer,
    ProviderConnectionSerializer,
    ProviderConnectionWriteSerializer,
    ProviderContractSerializer,
    ProviderContractWriteSerializer,
)
from apps.console.services.cost_service import CostService
from apps.console.permissions.console_permissions import IsConsoleAdmin


class ProviderViewSet(viewsets.ModelViewSet):
    """CRUD de Provider + endpoints de connections, contracts e economics."""

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return ProviderCreateSerializer
        if self.action in ['update', 'partial_update']:
            return ProviderUpdateSerializer
        return ProviderSerializer

    def get_queryset(self):
        return Provider.objects.all().order_by('name')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.save()
        return Response(
            ProviderSerializer(provider).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        provider = self.get_object()
        serializer = self.get_serializer(provider, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        provider = serializer.save()
        return Response(ProviderSerializer(provider).data)

    def destroy(self, request, *args, **kwargs):
        provider = self.get_object()
        if provider.connections.exists() or provider.contracts.exists():
            return Response(
                {'error': 'Provider possui conexões ou contratos vinculados'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        provider.delete()
        return Response(
            {'detail': 'Provider excluído com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )

    # ---------- Connections ----------

    @action(detail=True, methods=['get'], url_path='connections')
    def list_connections(self, request, id=None):
        provider = self.get_object()
        connections = provider.connections.all().order_by('name')
        return Response(ProviderConnectionSerializer(connections, many=True).data)

    @action(detail=True, methods=['post'], url_path='connections')
    def create_connection(self, request, id=None):
        provider = self.get_object()
        data = dict(request.data)
        data['provider'] = str(provider.id)

        serializer = ProviderConnectionWriteSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        connection = serializer.save()
        return Response(
            ProviderConnectionSerializer(connection).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------- Contracts ----------

    @action(detail=True, methods=['get'], url_path='contracts')
    def list_contracts(self, request, id=None):
        provider = self.get_object()
        contracts = provider.contracts.all().order_by('-started_at')
        return Response(ProviderContractSerializer(contracts, many=True).data)

    @action(detail=True, methods=['post'], url_path='contracts')
    def create_contract(self, request, id=None):
        provider = self.get_object()
        data = dict(request.data)
        data['provider'] = str(provider.id)

        serializer = ProviderContractWriteSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        return Response(
            ProviderContractSerializer(contract).data,
            status=status.HTTP_201_CREATED,
        )

    # ---------- Economics ----------

    @action(detail=True, methods=['get'], url_path='economics')
    def economics(self, request, id=None):
        """
        Resumo econômico do provider no período.

        Query params:
            days (default: 30)
        """
        provider = self.get_object()
        period_days = int(request.query_params.get('days', 30))

        data = CostService.get_provider_economics(
            provider=provider,
            period_days=period_days,
        )
        return Response(data)


class ProviderConnectionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'
    queryset = ProviderConnection.objects.all().select_related(
        'provider'
    ).order_by('provider__name', 'name')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProviderConnectionWriteSerializer
        return ProviderConnectionSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        connection = self.get_object()
        serializer = self.get_serializer(connection, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        connection = serializer.save()
        return Response(ProviderConnectionSerializer(connection).data)

    def destroy(self, request, *args, **kwargs):
        connection = self.get_object()
        if connection.contracts.exists():
            return Response(
                {'error': 'Conexão possui contratos vinculados'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        connection.delete()
        return Response(
            {'detail': 'Conexão excluída com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )


class ProviderContractViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'
    queryset = ProviderContract.objects.all().select_related(
        'provider', 'connection'
    ).order_by('provider__name', '-started_at')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProviderContractWriteSerializer
        return ProviderContractSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        contract = self.get_object()
        serializer = self.get_serializer(contract, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        contract = serializer.save()
        return Response(ProviderContractSerializer(contract).data)

    def destroy(self, request, *args, **kwargs):
        contract = self.get_object()
        contract.delete()
        return Response(
            {'detail': 'Contrato excluído com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )