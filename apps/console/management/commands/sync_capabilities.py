from django.core.management.base import BaseCommand

from apps.console.services.capability_service import ConsoleCapabilityService


class Command(BaseCommand):
    help = 'Sincroniza o catálogo de capabilities a partir dos apps instalados.'

    def handle(self, *args, **options):
        self.stdout.write('🔍 Descobrindo capabilities declaradas pelos apps...')

        stats = ConsoleCapabilityService.sync_capabilities()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"✅ Descobertas: {stats['discovered']}"
        ))
        self.stdout.write(f"   Criadas:       {stats['created']}")
        self.stdout.write(f"   Atualizadas:   {stats['updated']}")
        self.stdout.write(f"   Inalteradas:   {stats['unchanged']}")
        self.stdout.write(f"   Reativadas:    {stats['reactivated']}")
        self.stdout.write(f"   Desativadas:   {stats['deactivated']}")
        self.stdout.write('')

        if stats['deactivated']:
            self.stdout.write(self.style.WARNING(
                f"⚠️  {stats['deactivated']} capability(ies) não são mais "
                f"declaradas e foram marcadas como inativas (não deletadas)."
            ))