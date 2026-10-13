"""
Testes do seed `seed_plan_limits`.

Cobrem:
    - Criação em base vazia (com planos ativos).
    - Idempotência: rodar 2x não duplica.
    - Preservação: NÃO sobrescreve PlanFeatureLimit existente.
    - Falha clara quando 'storage.bytes' não existe no catálogo.
    - Não cria nada quando não há plano ativo.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.console.models import (
    Plan,
    Feature,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)


@pytest.fixture
def storage_metric(db):
    return UsageMetric.objects.create(
        key='storage.bytes',
        name='Armazenamento',
        unit='byte',
        kind='gauge',
        origin='derived',
        is_active=True,
    )


@pytest.fixture
def plan_a(db):
    return Plan.objects.create(
        key='starter',
        name='Starter',
        price=Decimal('49.00'),
        is_active=True,
    )


@pytest.fixture
def plan_b(db):
    return Plan.objects.create(
        key='pro',
        name='Pro',
        price=Decimal('99.00'),
        is_active=True,
    )


@pytest.fixture
def plan_inactive(db):
    return Plan.objects.create(
        key='old',
        name='Old',
        price=Decimal('0.00'),
        is_active=False,
    )


@pytest.mark.django_db
class TestSeedPlanLimits:

    def test_fails_without_storage_metric(self):
        Plan.objects.create(
            key='starter', name='Starter',
            price=Decimal('49.00'), is_active=True,
        )
        with pytest.raises(CommandError) as exc:
            call_command('seed_plan_limits')
        assert 'storage.bytes' in str(exc.value)

    def test_creates_feature_and_limits(
        self, storage_metric, plan_a, plan_b,
    ):
        out = StringIO()
        call_command('seed_plan_limits', stdout=out)

        feature = Feature.objects.get(key='armazenamento')
        assert feature.name == 'Armazenamento'
        assert feature.is_active is True

        pf_a = PlanFeature.objects.get(plan=plan_a, feature=feature)
        pf_b = PlanFeature.objects.get(plan=plan_b, feature=feature)

        lim_a = PlanFeatureLimit.objects.get(
            plan_feature=pf_a, metric=storage_metric,
        )
        lim_b = PlanFeatureLimit.objects.get(
            plan_feature=pf_b, metric=storage_metric,
        )

        assert lim_a.limit_value == 5 * 1024 ** 3
        assert lim_a.period == 'monthly'
        assert lim_a.behavior == 'hard_limit'

        assert lim_b.limit_value == 5 * 1024 ** 3
        assert lim_b.behavior == 'hard_limit'

    def test_ignores_inactive_plans(
        self, storage_metric, plan_a, plan_inactive,
    ):
        call_command('seed_plan_limits', stdout=StringIO())

        feature = Feature.objects.get(key='armazenamento')
        # Plano ativo tem PlanFeature
        assert PlanFeature.objects.filter(
            plan=plan_a, feature=feature,
        ).exists()
        # Plano inativo NÃO tem
        assert not PlanFeature.objects.filter(
            plan=plan_inactive, feature=feature,
        ).exists()

    def test_idempotent(self, storage_metric, plan_a):
        call_command('seed_plan_limits', stdout=StringIO())
        call_command('seed_plan_limits', stdout=StringIO())

        assert Feature.objects.filter(key='armazenamento').count() == 1
        feature = Feature.objects.get(key='armazenamento')
        assert PlanFeature.objects.filter(
            plan=plan_a, feature=feature,
        ).count() == 1
        assert PlanFeatureLimit.objects.filter(
            plan_feature__plan=plan_a,
            metric=storage_metric,
        ).count() == 1

    def test_does_not_overwrite_existing_limit(
        self, storage_metric, plan_a,
    ):
        """
        Pré-cria um limite customizado e confirma que o seed
        NÃO sobrescreve.
        """
        feature = Feature.objects.create(
            key='armazenamento',
            name='Armazenamento',
            is_active=True,
        )
        pf = PlanFeature.objects.create(plan=plan_a, feature=feature)
        PlanFeatureLimit.objects.create(
            plan_feature=pf,
            metric=storage_metric,
            limit_value=100,
            period='lifetime',
            behavior='soft_limit',
        )

        call_command('seed_plan_limits', stdout=StringIO())

        lim = PlanFeatureLimit.objects.get(
            plan_feature=pf, metric=storage_metric,
        )
        # Permanece o valor customizado.
        assert lim.limit_value == 100
        assert lim.period == 'lifetime'
        assert lim.behavior == 'soft_limit'

    def test_no_active_plans_does_nothing(
        self, storage_metric, plan_inactive,
    ):
        out = StringIO()
        call_command('seed_plan_limits', stdout=out)

        # Feature 'armazenamento' é criada de qualquer forma.
        assert Feature.objects.filter(key='armazenamento').exists()
        # Mas nenhum PlanFeatureLimit é criado.
        assert PlanFeatureLimit.objects.count() == 0

    def test_reuses_existing_feature(
        self, storage_metric, plan_a,
    ):
        pre = Feature.objects.create(
            key='armazenamento',
            name='Armazenamento (custom)',
            is_active=True,
        )
        call_command('seed_plan_limits', stdout=StringIO())

        # Não duplica.
        assert Feature.objects.filter(key='armazenamento').count() == 1
        # Preserva o registro existente (não atualiza name).
        pre.refresh_from_db()
        assert pre.name == 'Armazenamento (custom)'