"""
Seed do catálogo de Provider.

Inicialmente apenas os providers reais da infraestrutura do Clivo.
"""

from datetime import date

from django.core.management.base import BaseCommand

from apps.console.models import Provider, ProviderConnection, ProviderContract


class Command(BaseCommand):
    help = 'Seed do catálogo de providers'

    PROVIDERS = [
        {
            'key': 'openai',
            'name': 'OpenAI',
            'category': 'ai',
            'description': 'Provedor de modelos de linguagem.',
        },
        {
            'key': 'cloudinary',
            'name': 'Cloudinary',
            'category': 'storage',
            'description': 'Armazenamento e transformação de mídia.',
        },
        {
            'key': 'resend',
            'name': 'Resend',
            'category': 'email',
            'description': 'Envio de e-mails transacionais.',
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write('🏢 Seed de Providers...')

        created = 0
        updated = 0

        for data in self.PROVIDERS:
            provider, was_created = Provider.objects.update_or_create(
                key=data['key'],
                defaults={
                    'name': data['name'],
                    'category': data['category'],
                    'description': data['description'],
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f'   🆕 {provider.key}')
            else:
                updated += 1
                self.stdout.write(f'   🔄 {provider.key}')

        self.stdout.write(self.style.SUCCESS(
            f'   ✅ Providers: {created} criado(s), {updated} atualizado(s)'
        ))