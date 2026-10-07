"""
Seed das governanças estruturais do Console.

Cria as governanças que são PRÉ-REQUISITO do sistema.

REGRA ARQUITETURAL:
    Este seed cria apenas governanças que o backend REQUER para
    funcionar. Governanças comerciais ou de administração são
    criadas pelo operador via Console, NÃO por seed.

    ConsoleMembership já é o mecanismo de acesso administrativo ao
    Console. Não existe governança "superadmin" de Console.
"""

from django.core.management.base import BaseCommand

from apps.console.services.governance_service import ConsoleGovernanceService
from apps.console.services.capability_service import ConsoleCapabilityService


class Command(BaseCommand):
    help = 'Cria as governanças estruturais do Console'

    GOVERNANCES = [
        {
            'key': 'proprietario',
            'name': 'Proprietário',
            'description': (
                'Proprietário do Workspace. '
                'Atribuído automaticamente a quem cria o Workspace.'
            ),
            'scope': 'workspace',
            'is_system': True,
            'is_protected': True,
            'capabilities': [],
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write('📋 Sincronizando catálogo de capabilities...')
        stats = ConsoleCapabilityService.sync_capabilities()
        self.stdout.write(
            f"   Descobertas={stats['discovered']} "
            f"Criadas={stats['created']} "
            f"Atualizadas={stats['updated']} "
            f"Desativadas={stats['deactivated']}"
        )

        service = ConsoleGovernanceService()

        created = updated = 0
        for gov_data in self.GOVERNANCES:
            existing = service.get_governance_by_key(gov_data['key'])

            if existing:
                service.update_governance(
                    governance=existing,
                    name=gov_data['name'],
                    description=gov_data['description'],
                )
                # Garante o scope correto mesmo em registros antigos
                if existing.scope != gov_data['scope']:
                    existing.scope = gov_data['scope']
                    existing.save(update_fields=['scope', 'updated_at'])

                updated += 1
                self.stdout.write(f'   ✅ {gov_data["key"]} — atualizado')
            else:
                service.create_governance(
                    key=gov_data['key'],
                    name=gov_data['name'],
                    description=gov_data['description'],
                    created_by=None,
                    scope=gov_data['scope'],
                    is_system=gov_data['is_system'],
                    is_protected=gov_data['is_protected'],
                )
                created += 1
                self.stdout.write(f'   🆕 {gov_data["key"]} — criado')

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Seed concluído. Criadas={created} Atualizadas={updated}'
        ))