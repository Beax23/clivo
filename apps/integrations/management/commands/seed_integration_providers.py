"""
Seed idempotente do catálogo de providers e resources de integrations.

Popula:
    - IntegrationProvider(key='google') com recursos de Drive e Forms.
    - IntegrationResource para cada recurso suportado pelo GoogleConnector.

IDEMPOTENTE:
    - Usa `update_or_create` por `key` / `(provider, slug)`.
    - NÃO sobrescreve `is_active` se o operador alterou.
    - NÃO apaga providers que não estão no seed.

Uso:
    python manage.py seed_integration_providers
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.integrations.models import (
    IntegrationProvider,
    IntegrationResource,
)


PROVIDERS = [
    {
        'key': 'google',
        'name': 'Google',
        'category': 'productivity',
        'description': (
            'Ferramentas Google: Drive e Forms. '
            'Permite consultar arquivos e formulários do escritório.'
        ),
        'resources': [
            {
                'slug': 'drive.file.read',
                'name': 'Ler arquivos do Drive',
                'description': (
                    'Ler arquivos e metadados do Google Drive.'
                ),
            },
            {
                'slug': 'forms.body.read',
                'name': 'Ler formulários do Forms',
                'description': (
                    'Ler formulários e respostas do Google Forms.'
                ),
            },
        ],
    },
]


class Command(BaseCommand):
    help = (
        'Seed idempotente de IntegrationProvider + IntegrationResource.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('🌱 Seed de IntegrationProvider...')
        self.stdout.write('')

        for spec in PROVIDERS:
            provider, created = (
                IntegrationProvider.objects.update_or_create(
                    key=spec['key'],
                    defaults={
                        'name': spec['name'],
                        'category': spec['category'],
                        'description': spec['description'],
                        # `is_active` deliberadamente NÃO incluso:
                        # preserva decisão operacional.
                    },
                )
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'   🆕 provider {provider.key} — {provider.name}'
                ))
            else:
                self.stdout.write(
                    f'   🔄 provider {provider.key} — {provider.name}'
                )

            for res_spec in spec['resources']:
                resource, res_created = (
                    IntegrationResource.objects.update_or_create(
                        provider=provider,
                        slug=res_spec['slug'],
                        defaults={
                            'name': res_spec['name'],
                            'description': res_spec['description'],
                        },
                    )
                )
                if res_created:
                    self.stdout.write(
                        f'      🆕 resource {resource.slug}'
                    )
                else:
                    self.stdout.write(
                        f'      🔄 resource {resource.slug}'
                    )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Seed concluído.'))