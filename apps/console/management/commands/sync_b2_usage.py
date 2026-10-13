"""
Sincroniza o snapshot físico do bucket Backblaze B2.

Uso:
    python manage.py sync_b2_usage
    python manage.py sync_b2_usage --quiet
    python manage.py sync_b2_usage --json

Este comando NÃO agenda nada. Ele executa uma vez e termina. O
agendamento operacional (cron do Render, ou Celery futuro) é decisão
de infraestrutura, fora do escopo deste módulo.

Sempre retorna código de saída 0, mesmo em falha da API — para não
poluir logs de cron com alertas falsos. O erro fica registrado no
snapshot e no logger. Se quiser alertar sobre falhas, faça o
monitoramento olhar o `status` do snapshot mais recente.

SOBRE O NÚMERO DE "USO"
-----------------------
O valor exibido é o TAMANHO FÍSICO COBRADO pelo B2: soma de TODAS as
versões de TODOS os objetos do bucket (não só a versão ativa).

Isso corresponde ao que o painel do B2 mostra em "Storage" no resumo
da conta. É o número que a B2 efetivamente cobra — um arquivo
sobrescrito N vezes ocupa (N+1) × tamanho na cobrança.
"""

import json

from django.core.management.base import BaseCommand

from apps.console.models import StorageProviderSnapshot
from apps.console.services.b2_usage_service import (
    BackblazeB2UsageService,
)


class Command(BaseCommand):
    help = (
        'Sincroniza o snapshot físico do bucket Backblaze B2 '
        '(soma de todas as versões).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Não imprime saída normal — só erros.',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Imprime o snapshot como JSON (útil para automação).',
        )

    def handle(self, *args, **options):
        quiet = options['quiet']
        as_json = options['json']

        snapshot = BackblazeB2UsageService.sync()

        if as_json:
            self.stdout.write(json.dumps(
                self._snapshot_to_dict(snapshot),
                indent=2,
                default=str,
            ))
            return

        if quiet:
            return

        self._print_human(snapshot)

    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_to_dict(snapshot: StorageProviderSnapshot) -> dict:
        payload = snapshot.raw_payload or {}
        return {
            'id': str(snapshot.id),
            'provider_key': snapshot.provider_key,
            'status': snapshot.status,
            'fetched_at': snapshot.fetched_at.isoformat(),
            'storage_usage_bytes': snapshot.storage_usage_bytes,
            'bucket_name': payload.get('bucket_name'),
            'file_count': payload.get('file_count'),
            'active_versions_count': payload.get('active_versions_count'),
            'total_versions_count': payload.get('total_versions_count'),
            'delete_markers_count': payload.get('delete_markers_count'),
            'truncated': payload.get('truncated'),
            'payload_version': payload.get('payload_version'),
            'error_message': snapshot.error_message,
        }

    def _print_human(self, snapshot: StorageProviderSnapshot) -> None:
        style = self.style

        if snapshot.status == StorageProviderSnapshot.STATUS_UNAVAILABLE:
            self.stdout.write(style.WARNING(
                '⚠️  B2 não configurado neste ambiente.'
            ))
            self.stdout.write(f'   {snapshot.error_message}')
            return

        if snapshot.status == StorageProviderSnapshot.STATUS_ERROR:
            self.stdout.write(style.ERROR(
                '❌ Falha ao consultar o B2.'
            ))
            self.stdout.write(f'   {snapshot.error_message}')
            self.stdout.write('')
            self.stdout.write(
                '   O snapshot anterior (se válido) continua sendo '
                'usado como referência pelo Console.'
            )
            return

        # status == ok
        self.stdout.write(style.SUCCESS('✅ B2 sincronizado.'))
        self.stdout.write('')

        payload = snapshot.raw_payload or {}
        bucket = payload.get('bucket_name')
        active = payload.get('active_versions_count')
        total = payload.get('total_versions_count')
        markers = payload.get('delete_markers_count')

        if bucket:
            self.stdout.write(f'   Bucket: {bucket}')

        if snapshot.storage_usage_bytes is not None:
            self.stdout.write(
                f'   Total físico: {self._humanize_bytes(snapshot.storage_usage_bytes)} '
                f'({snapshot.storage_usage_bytes} bytes)'
            )

        if active is not None and total is not None:
            self.stdout.write(
                f'   Versões ativas: {active} · '
                f'total de versões: {total}'
            )
            if total > active:
                self.stdout.write(style.WARNING(
                    f'   ℹ️  Existem {total - active} versões antigas '
                    f'contabilizadas no uso (a B2 cobra por todas).'
                ))

        if markers:
            self.stdout.write(f'   Delete markers: {markers}')

        if payload.get('truncated'):
            self.stdout.write(style.WARNING(
                '   ⚠️  Paginação interrompida — snapshot incompleto.'
            ))

        self.stdout.write('')
        self.stdout.write(f'   Snapshot: {snapshot.id}')

    @staticmethod
    def _humanize_bytes(num_bytes: int) -> str:
        size = float(num_bytes)
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1
        return f'{size:.2f} {units[i]}'