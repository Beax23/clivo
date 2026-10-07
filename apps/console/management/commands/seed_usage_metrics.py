"""
Seed do catálogo de UsageMetric.

Cria as métricas iniciais do Clivo. Idempotente.
"""

from django.core.management.base import BaseCommand

from apps.console.models import UsageMetric


class Command(BaseCommand):
    help = 'Seed do catálogo de métricas de uso'

    METRICS = [
        {
            'key': 'members.count',
            'name': 'Membros',
            'unit': 'member',
            'kind': 'gauge',
            'origin': 'derived',
            'description': 'Número de membros no workspace.',
        },
        {
            'key': 'clients.count',
            'name': 'Clientes',
            'unit': 'client',
            'kind': 'gauge',
            'origin': 'derived',
            'description': 'Número de clientes cadastrados.',
        },
        {
            'key': 'storage.bytes',
            'name': 'Armazenamento',
            'unit': 'byte',
            'kind': 'gauge',
            'origin': 'derived',
            'description': 'Armazenamento utilizado em bytes.',
        },
        {
            'key': 'documents.count',
            'name': 'Documentos',
            'unit': 'document',
            'kind': 'gauge',
            'origin': 'derived',
            'description': 'Número de documentos armazenados.',
        },
        {
            'key': 'briefings.created',
            'name': 'Briefings criados',
            'unit': 'briefing',
            'kind': 'counter',
            'origin': 'recorded',
            'description': 'Briefings criados ao longo do tempo.',
        },
        {
            'key': 'bandwidth.bytes',
            'name': 'Banda',
            'unit': 'byte',
            'kind': 'counter',
            'origin': 'recorded',
            'description': 'Bytes trafegados.',
        },
        {
            'key': 'email.sent',
            'name': 'E-mails enviados',
            'unit': 'email',
            'kind': 'counter',
            'origin': 'recorded',
            'description': 'E-mails enviados pelo Clivo.',
        },
        {
            'key': 'ai.credits',
            'name': 'Créditos de IA',
            'unit': 'credit',
            'kind': 'counter',
            'origin': 'recorded',
            'description': 'Créditos de IA consumidos.',
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write('📊 Seed de UsageMetric...')

        created = 0
        updated = 0

        for data in self.METRICS:
            metric, was_created = UsageMetric.objects.update_or_create(
                key=data['key'],
                defaults={
                    'name': data['name'],
                    'unit': data['unit'],
                    'kind': data['kind'],
                    'origin': data['origin'],
                    'description': data['description'],
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f'   🆕 {metric.key}')
            else:
                updated += 1
                self.stdout.write(f'   🔄 {metric.key}')

        self.stdout.write(self.style.SUCCESS(
            f'   ✅ Métricas: {created} criada(s), {updated} atualizada(s)'
        ))