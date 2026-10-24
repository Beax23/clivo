"""
Refresh proativo dos access_tokens do Google.

Uso:
    python manage.py refresh_google_tokens
    python manage.py refresh_google_tokens --dry-run
    python manage.py refresh_google_tokens --limit 50

Objetivo:
    Renovar access_tokens ANTES que expirem, para que o usuário
    não experimente latência em operações que dependem da API do
    Google.

    O refresh lazy (`IntegrationService.get_valid_access_token`)
    já cobre o caso de uso. Este comando é OTIMIZAÇÃO — reduz o
    tempo de resposta percebido pelo usuário.

Agendamento recomendado (cron):
    */30 * * * * python manage.py refresh_google_tokens --limit 100

IDEMPOTÊNCIA:
    Se chamado repetidamente, cada chamada só renova integrações
    que precisam. Não é destrutivo. Não causa efeito colateral no
    provider além do próprio refresh (que é o desejado).

COMPORTAMENTO EM ERRO:
    Se uma integração falhar com RefreshTokenInvalidError, ela
    vira `expired`. Isso é o comportamento correto — o cron
    "descobre" que a integração está quebrada antes que o
    usuário tente usá-la.
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.integrations.exceptions import (
    ConnectionExpiredError,
    IntegrationError,
    RefreshTransientError,
)
from apps.integrations.models import WorkspaceIntegration
from apps.integrations.services.integration_service import (
    IntegrationService,
)

logger = logging.getLogger('integrations')


class Command(BaseCommand):
    help = (
        'Renova access_tokens do Google que estão próximos de expirar.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Máximo de integrações a processar. Default: 100.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Lista as integrações que precisariam de refresh, '
                 'sem renovar.',
        )

    def handle(self, *args, **options):
        limit = max(1, options['limit'])
        dry_run = options['dry_run']

        # Só processa integrações Google ativas.
        qs = (
            WorkspaceIntegration.objects
            .filter(
                provider__key='google',
                status=WorkspaceIntegration.STATUS_ACTIVE,
            )
            .select_related('provider', 'workspace')
            .order_by('last_refresh_at')
            [:limit]
        )

        refreshed = 0
        skipped = 0
        failed = 0
        expired = 0

        for integration in qs:
            # Checa se precisa de refresh (mesma lógica do lazy).
            if not IntegrationService._integration_needs_refresh(
                integration,
            ):
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  [DRY] {integration.id} '
                    f'({integration.workspace.name}) '
                    f'precisa de refresh'
                )
                refreshed += 1
                continue

            try:
                IntegrationService.refresh_credentials(integration)
                refreshed += 1
            except ConnectionExpiredError:
                expired += 1
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️  {integration.id} — credencial revogada, '
                    f'marcada como expired'
                ))
            except RefreshTransientError:
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️  {integration.id} — falha transitória'
                ))
            except IntegrationError as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f'  ❌ {integration.id} — {exc}'
                ))

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Dry-run: {refreshed} precisariam de refresh, '
                f'{skipped} já estão válidos.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Refresh concluído: '
                f'{refreshed} renovadas, '
                f'{skipped} já válidas, '
                f'{expired} expiradas, '
                f'{failed} falharam.'
            ))