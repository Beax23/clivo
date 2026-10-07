"""
Seed inicial do Console.

Ordem:
1. Sync capabilities (descobre dos apps via capabilities.py)
2. Governanças de sistema (superadmin, owner, architect, collaborator)
3. UsageMetric (catálogo técnico de métricas)
4. Providers (OpenAI, Cloudinary, Resend)

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


class Command(BaseCommand):
    help = 'Seed do Console (capabilities, governanças, métricas, providers)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Seed do Console'))
        self.stdout.write('')

        # [1/4] Sync capabilities
        self.stdout.write('📋 [1/4] Sincronizando capabilities...')
        SyncCapabilitiesCommand().handle()
        self.stdout.write('')

        # [2/4] Governanças
        self.stdout.write('📋 [2/4] Criando governanças de sistema...')
        SeedGovernancesCommand().handle()
        self.stdout.write('')

        # [3/4] Métricas
        self.stdout.write('📋 [3/4] Seed de métricas...')
        SeedUsageMetricsCommand().handle()
        self.stdout.write('')

        # [4/4] Providers
        self.stdout.write('📋 [4/4] Seed de providers...')
        SeedProvidersCommand().handle()
        self.stdout.write('')

        self.stdout.write(self.style.SUCCESS('✅ Seed do Console concluído!'))
        self.stdout.write('')
        self.stdout.write('ℹ️  Para criar o primeiro acesso ao Console:')
        self.stdout.write(
            '   python manage.py bootstrap_console --email seu@email.com'
        )