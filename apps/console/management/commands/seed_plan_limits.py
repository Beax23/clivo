"""
Seed de limite de armazenamento por plano.

Garante que cada plano ativo tenha:
    - Feature 'armazenamento'
    - PlanFeature ligando essa feature ao plano
    - PlanFeatureLimit de 'storage.bytes' com 5 GiB

IDEMPOTENTE:
    - Não duplica Feature nem PlanFeature.
    - Não sobrescreve PlanFeatureLimit existente — se o operador
      customizou o limite via Console UI, o seed respeita.

Pré-requisito:
    - UsageMetric 'storage.bytes' precisa existir (seed_usage_metrics
      cuida disso; se não existir, este comando FALHA com mensagem clara).

Uso:
    python manage.py seed_plan_limits
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.console.models import (
    Plan,
    Feature,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)


DEFAULT_STORAGE_LIMIT = 5 * 1024 ** 3  # 5 GiB
STORAGE_METRIC_KEY = 'storage.bytes'
STORAGE_FEATURE_KEY = 'armazenamento'
STORAGE_FEATURE_NAME = 'Armazenamento'


class Command(BaseCommand):
    help = 'Seed do limite de armazenamento por plano (5 GiB).'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('💾 Seed de limites de armazenamento...')

        metric = UsageMetric.objects.filter(
            key=STORAGE_METRIC_KEY, is_active=True,
        ).first()
        if metric is None:
            raise CommandError(
                f"Métrica '{STORAGE_METRIC_KEY}' não encontrada ou inativa. "
                f"Rode 'python manage.py seed_usage_metrics' primeiro."
            )

        feature, feature_created = Feature.objects.get_or_create(
            key=STORAGE_FEATURE_KEY,
            defaults={
                'name': STORAGE_FEATURE_NAME,
                'description': 'Armazenamento de arquivos no workspace.',
                'is_active': True,
            },
        )
        if feature_created:
            self.stdout.write(f'   🆕 feature {feature.key}')
        else:
            self.stdout.write(f'   🔄 feature {feature.key}')

        plans = Plan.objects.filter(is_active=True).order_by('key')
        if not plans.exists():
            self.stdout.write(self.style.WARNING(
                '   ⚠️  Nenhum plano ativo — nada a fazer.'
            ))
            return

        pf_created = 0
        limit_created = 0
        limit_skipped = 0

        for plan in plans:
            plan_feature, pf_new = PlanFeature.objects.get_or_create(
                plan=plan,
                feature=feature,
            )
            if pf_new:
                pf_created += 1
                self.stdout.write(f'      🆕 plan_feature {plan.key}/{feature.key}')

            existing = PlanFeatureLimit.objects.filter(
                plan_feature=plan_feature,
                metric=metric,
            ).first()

            if existing is not None:
                limit_skipped += 1
                self.stdout.write(
                    f'      ⏭️  limite já existe para {plan.key} '
                    f'(limit_value={existing.limit_value})'
                )
                continue

            PlanFeatureLimit.objects.create(
                plan_feature=plan_feature,
                metric=metric,
                limit_value=DEFAULT_STORAGE_LIMIT,
                period='monthly',
                behavior='hard_limit',
            )
            limit_created += 1
            self.stdout.write(
                f'      🆕 limite {plan.key} = '
                f'{DEFAULT_STORAGE_LIMIT} bytes (5 GiB)'
            )

        self.stdout.write(self.style.SUCCESS(
            f'   ✅ PlanFeatures criados: {pf_created} · '
            f'Limites criados: {limit_created} · '
            f'Limites preservados: {limit_skipped}'
        ))