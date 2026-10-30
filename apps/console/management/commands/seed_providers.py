"""
Seed do catálogo de Provider.

Inicialmente apenas os providers reais da infraestrutura do Clivo.

Idempotente: usa `update_or_create` por `key`. Rodar várias vezes
não duplica. Não apaga providers que não estão nesta lista.
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
            'key': 'gemini',
            'name': 'Google Gemini',
            'category': 'ai',
            'description': 'Modelos Gemini do Google (Flash, Pro).',
        },
        {
            'key': 'anthropic',
            'name': 'Anthropic',
            'category': 'ai',
            'description': 'Modelos Claude da Anthropic.',
        },
        {
            'key': 'backblaze_b2',
            'name': 'Backblaze B2',
            'category': 'storage',
            'description': 'Armazenamento de objetos S3-compatible.',
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