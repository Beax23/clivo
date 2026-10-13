"""
StorageViewSet — exposição read-only do snapshot de armazenamento
e do teto operacional do provider.

Endpoints:
    GET /api/console/storage/provider-snapshot/
        Snapshot atual (último 'ok') e último snapshot (qualquer status).

    GET /api/console/storage/provider-snapshot/history/
        N snapshots mais recentes.

    GET /api/console/storage/provider-cap/
        Agrega numa resposta só: identidade do provider, teto
        operacional do contrato ativo mais recente, uso físico do
        snapshot 'ok', e status do último snapshot.
"""

import logging

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.console.models import (
    Provider,
    ProviderContract,
    StorageProviderSnapshot,
)
from apps.console.api.serializers import (
    StorageProviderSnapshotSerializer,
    StorageProviderSnapshotCurrentSerializer,
    StorageProviderCapSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin

logger = logging.getLogger('console')


PROVIDER_KEY_B2 = 'backblaze_b2'


class StorageViewSet(viewsets.ViewSet):
    """
    ViewSet agregado de leitura do armazenamento do Console.

    Não expõe CRUD — o snapshot é histórico e só é escrito pelo
    serviço de sincronização. O teto operacional é escrito pelo
    Console via `ProviderContract`. Este ViewSet só lê.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]

    # ------------------------------------------------------------------
    # SNAPSHOT ATUAL
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['get'],
        url_path='provider-snapshot',
        url_name='provider-snapshot',
    )
    def provider_snapshot(self, request):
        """
        Devolve o snapshot atual e o último snapshot do provider
        de armazenamento.
        """
        provider_key = request.query_params.get(
            'provider_key', PROVIDER_KEY_B2,
        )

        latest = (
            StorageProviderSnapshot.objects
            .filter(provider_key=provider_key)
            .order_by('-fetched_at')
            .first()
        )

        current = (
            StorageProviderSnapshot.objects
            .filter(
                provider_key=provider_key,
                status=StorageProviderSnapshot.STATUS_OK,
            )
            .order_by('-fetched_at')
            .first()
        )

        serializer = StorageProviderSnapshotCurrentSerializer({
            'current': current,
            'latest': latest,
        })
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # HISTÓRICO RECENTE
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['get'],
        url_path='provider-snapshot/history',
        url_name='provider-snapshot-history',
    )
    def provider_snapshot_history(self, request):
        """
        Devolve os N snapshots mais recentes (default: 20, máx: 100).
        """
        provider_key = request.query_params.get(
            'provider_key', PROVIDER_KEY_B2,
        )

        try:
            limit = int(request.query_params.get('limit', 20))
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(100, limit))

        snapshots = (
            StorageProviderSnapshot.objects
            .filter(provider_key=provider_key)
            .order_by('-fetched_at')[:limit]
        )

        serializer = StorageProviderSnapshotSerializer(snapshots, many=True)
        return Response({
            'provider_key': provider_key,
            'count': len(serializer.data),
            'results': serializer.data,
        })

    # ------------------------------------------------------------------
    # PROVIDER CAP — agregado
    # ------------------------------------------------------------------

    @action(
        detail=False,
        methods=['get'],
        url_path='provider-cap',
        url_name='provider-cap',
    )
    def provider_cap(self, request):
        """
        Agrega numa resposta só:

            - Provider (nome, key, is_active)
            - Contrato ativo mais recente (com teto cadastrado ou não)
            - Snapshot 'ok' mais recente (uso físico)
            - Último snapshot, qualquer status (para detectar falha)

        Query params:
            provider_key (default: "backblaze_b2")

        Semântica:
            - Se o provider não existe → devolve payload com
              `provider_key`, `provider_name=''` e tudo mais null.
            - Se o provider existe mas sem contrato ativo → devolve
              `contract_id=null`, `is_configured=False`.
            - Se contrato ativo sem teto → `included_storage_bytes=null`,
              `is_configured=False`.
            - Se contrato ativo com teto → `is_configured=True`.
            - `usage_bytes` vem do snapshot 'ok' mais recente.
              Se nenhum, null.
        """
        provider_key = request.query_params.get(
            'provider_key', PROVIDER_KEY_B2,
        )

        provider = (
            Provider.objects
            .filter(key=provider_key)
            .first()
        )

        # Se o provider não existe, devolve payload mínimo.
        if provider is None:
            return Response({
                'provider_key': provider_key,
                'provider_name': '',
                'provider_is_active': False,
                'contract_id': None,
                'contract_name': None,
                'contract_is_active': False,
                'included_storage_bytes': None,
                'is_configured': False,
                'usage_bytes': None,
                'usage_fetched_at': None,
                'usage_is_stale': False,
                'snapshot_status': '',
                'last_snapshot_status': '',
                'last_snapshot_error': '',
                'last_snapshot_fetched_at': None,
            })

        # Contrato ativo mais recente para este provider.
        contract = (
            ProviderContract.objects
            .filter(provider=provider, is_active=True)
            .order_by('-started_at')
            .first()
        )

        # Snapshot 'ok' mais recente (uso físico).
        current_snapshot = (
            StorageProviderSnapshot.objects
            .filter(
                provider_key=provider_key,
                status=StorageProviderSnapshot.STATUS_OK,
            )
            .order_by('-fetched_at')
            .first()
        )

        # Último snapshot (qualquer status) — para detectar falha.
        latest_snapshot = (
            StorageProviderSnapshot.objects
            .filter(provider_key=provider_key)
            .order_by('-fetched_at')
            .first()
        )

        # `usage_is_stale` — mesma regra do serializer do snapshot.
        from datetime import timedelta
        from django.conf import settings
        from django.utils import timezone
        stale_hours = getattr(settings, 'STORAGE_SNAPSHOT_STALE_HOURS', 25)
        stale_threshold = timezone.now() - timedelta(hours=stale_hours)

        usage_is_stale = False
        if current_snapshot is not None:
            usage_is_stale = current_snapshot.fetched_at < stale_threshold

        included_storage_bytes = (
            contract.included_storage_bytes if contract else None
        )

        is_configured = (
            contract is not None
            and included_storage_bytes is not None
        )

        payload = {
            'provider_key': provider.key,
            'provider_name': provider.name,
            'provider_is_active': provider.is_active,

            'contract_id': contract.id if contract else None,
            'contract_name': contract.name if contract else None,
            'contract_is_active': contract.is_active if contract else False,

            'included_storage_bytes': included_storage_bytes,
            'is_configured': is_configured,

            'usage_bytes': (
                current_snapshot.storage_usage_bytes
                if current_snapshot else None
            ),
            'usage_fetched_at': (
                current_snapshot.fetched_at
                if current_snapshot else None
            ),
            'usage_is_stale': usage_is_stale,

            'snapshot_status': (
                current_snapshot.status if current_snapshot else ''
            ),
            'last_snapshot_status': (
                latest_snapshot.status if latest_snapshot else ''
            ),
            'last_snapshot_error': (
                latest_snapshot.error_message if latest_snapshot else ''
            ),
            'last_snapshot_fetched_at': (
                latest_snapshot.fetched_at if latest_snapshot else None
            ),
        }

        serializer = StorageProviderCapSerializer(payload)
        return Response(serializer.data)