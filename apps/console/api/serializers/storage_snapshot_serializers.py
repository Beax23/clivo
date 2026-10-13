"""
Serializer de leitura do StorageProviderSnapshot.

Expõe SOMENTE os campos normalizados. O `raw_payload` fica no admin —
no endpoint seria vazamento desnecessário de detalhes internos.

`is_stale` é derivado do `fetched_at` — não é persistido. O limiar é
configurável via `settings.STORAGE_SNAPSHOT_STALE_HOURS` (default: 25h,
que é 1 hora a mais que o ciclo diário típico de sincronização do
provider de armazenamento).
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.console.models import StorageProviderSnapshot


DEFAULT_STALE_HOURS = 25


class StorageProviderSnapshotSerializer(serializers.ModelSerializer):

    is_stale = serializers.SerializerMethodField()
    is_failed = serializers.SerializerMethodField()

    class Meta:
        model = StorageProviderSnapshot
        fields = [
            'id',
            'provider_key',
            'status',
            'plan_name',
            'fetched_at',
            'is_stale',
            'is_failed',
            'storage_usage_bytes',
            'storage_credits_usage',
            'bandwidth_usage_bytes',
            'bandwidth_credits_usage',
            'transformations_usage',
            'transformations_credits_usage',
            'credits_usage',
            'credits_limit',
            'credits_used_percent',
            'objects_count',
            'resources_count',
            'derived_resources_count',
            'media_limits',
            'rate_limit_remaining',
            'rate_limit_reset_at',
            'error_message',
            'created_at',
        ]
        read_only_fields = fields

    def get_is_stale(self, obj) -> bool:
        """
        Um snapshot é considerado stale se:
            - é um snapshot válido (status='ok'), E
            - foi coletado há mais que o limiar configurado.

        Snapshots com status='error' ou 'unavailable' NÃO são stale —
        eles são falhas, o que é outro estado.
        """
        if obj.status != StorageProviderSnapshot.STATUS_OK:
            return False

        hours = getattr(
            settings, 'STORAGE_SNAPSHOT_STALE_HOURS', DEFAULT_STALE_HOURS,
        )
        threshold = timezone.now() - timedelta(hours=hours)
        return obj.fetched_at < threshold

    def get_is_failed(self, obj) -> bool:
        """
        Conveniência para o frontend: True quando o snapshot em si
        é de falha. Evita o frontend ter que comparar strings de status.
        """
        return obj.status in (
            StorageProviderSnapshot.STATUS_ERROR,
            StorageProviderSnapshot.STATUS_UNAVAILABLE,
        )


class StorageProviderSnapshotCurrentSerializer(serializers.Serializer):
    """
    Envelope do endpoint `/api/console/storage/provider-snapshot/`.

    Devolve:
        - current  → último snapshot 'ok' (ou null se nunca houve)
        - latest   → último snapshot, seja qual for o status

    O frontend escolhe o que mostrar:
        - Se `latest.status == 'ok'` → mostra os dados de `current`.
        - Se `latest.status == 'error'` e `current` existe →
          mostra `current` com badge de "última tentativa falhou".
        - Se ambos são vazios → mostra "nunca sincronizado".
    """

    current = serializers.SerializerMethodField()
    latest = serializers.SerializerMethodField()

    def get_current(self, obj):
        snapshot = obj.get('current')
        if snapshot is None:
            return None
        return StorageProviderSnapshotSerializer(snapshot).data

    def get_latest(self, obj):
        snapshot = obj.get('latest')
        if snapshot is None:
            return None
        return StorageProviderSnapshotSerializer(snapshot).data