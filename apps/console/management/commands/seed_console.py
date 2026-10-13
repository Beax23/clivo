"""
Seed inicial do Console.

Ordem:
1. Sync capabilities (descobre dos apps via capabilities.py)
2. Governanças de sistema (superadmin, owner, architect, collaborator)
3. UsageMetric (catálogo técnico de métricas)
4. Providers (OpenAI, Backblaze B2, Resend)
5. Plan limits (limite de armazenamento por plano)

IMPORTANTE:
    Este seed NÃO cria ConsoleMembership.
    Para criar o primeiro acesso:

        python manage.py bootstrap_console --email seu@email.com
"""

from django.core.management.base import BaseCommand

from apps.console.management.commands.sync_capabilities import (
    Command as SyncCapabilitiesCommand,
)
from apps.console.management.commands.seed_system_governances import (
    Command as SeedGovernancesCommand,
)
from apps.console.management.commands.seed_usage_metrics import (
    Command as SeedUsageMetricsCommand,
)
from apps.console.management.commands.seed_providers import (
    Command as SeedProvidersCommand,
)
from apps.console.management.commands.seed_plan_limits import (
    Command as SeedPlanLimitsCommand,
)


class Command(BaseCommand):
    help = (
        'Seed do Console '
        '(capabilities, governanças, métricas, providers, plan limits)'
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Seed do Console'))
        self.stdout.write('')

        # [1/5] Sync capabilities
        self.stdout.write('📋 [1/5] Sincronizando capabilities...')
        SyncCapabilitiesCommand().handle()
        self.stdout.write('')

        # [2/5] Governanças
        self.stdout.write('📋 [2/5] Criando governanças de sistema...')
        SeedGovernancesCommand().handle()
        self.stdout.write('')

        # [3/5] Métricas
        self.stdout.write('📋 [3/5] Seed de métricas...')
        SeedUsageMetricsCommand().handle()
        self.stdout.write('')

        # [4/5] Providers
        self.stdout.write('📋 [4/5] Seed de providers...')
        SeedProvidersCommand().handle()
        self.stdout.write('')

        # [5/5] Plan limits
        self.stdout.write('📋 [5/5] Seed de limites de armazenamento...')
        SeedPlanLimitsCommand().handle()
        self.stdout.write('')

        self.stdout.write(self.style.SUCCESS('✅ Seed do Console concluído!'))
        self.stdout.write('')
        self.stdout.write('ℹ️  Para criar o primeiro acesso ao Console:')
        self.stdout.write(
            '   python manage.py bootstrap_console --email seu@email.com'
        )