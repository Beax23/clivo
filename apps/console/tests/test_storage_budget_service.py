"""
Testes do StorageBudgetService.

Cobrem:
    - Criação via seed (idempotência).
    - Cálculo de allocatable_bytes com reserva.
    - Cálculo de committed_bytes em todos os cenários:
        * Workspace sem assinatura → 0
        * Workspace com assinatura inativa → 0
        * Workspace inativo → 0
        * Plano sem limite → 0
        * Plano com limite → soma
        * Plano ilimitado → bloqueia
        * Configuração ambígua → bloqueia
    - Atualização transacional com select_for_update.
    - Bloqueio de redução abaixo do comprometido (política estrita).
    - Permissão de redução abaixo do comprometido (política controlada).
    - Gravação de histórico com valores anteriores e novos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from io import StringIO

from apps.console.models import (
    Plan,
    Feature,
    PlanFeature,
    PlanFeatureLimit,
    StorageBudget,
    StorageBudgetChange,
    UsageMetric,
)
from apps.console.services import StorageBudgetService
from apps.console.exceptions import (
    StorageBudgetNotFoundError,
    StorageBudgetBelowCommittedError,
    StorageBudgetUnlimitedQuotaError,
    StorageBudgetAmbiguousQuotaError,
)
from apps.workspaces.models import Workspace, WorkspaceSubscription


GIB = 1024 ** 3


# =========================================================================
# FIXTURES
# =========================================================================

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
def storage_feature(db):
    return Feature.objects.create(
        key='armazenamento',
        name='Armazenamento',
        is_active=True,
    )


@pytest.fixture
def other_feature(db):
    return Feature.objects.create(
        key='intelligence',
        name='Intelligence',
        is_active=True,
    )


@pytest.fixture
def plan_a(db):
    return Plan.objects.create(
        key='plan-a',
        name='Plan A',
        price=Decimal('10.00'),
        is_active=True,
    )


@pytest.fixture
def plan_b(db):
    return Plan.objects.create(
        key='plan-b',
        name='Plan B',
        price=Decimal('20.00'),
        is_active=True,
    )


def _make_workspace(slug, is_active=True):
    return Workspace.objects.create(
        name=f'WS {slug}',
        slug=slug,
        is_active=is_active,
    )


def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=workspace.created_at,
    )


def _set_storage_limit(plan, feature, metric, limit_value):
    pf = PlanFeature.objects.create(plan=plan, feature=feature)
    return PlanFeatureLimit.objects.create(
        plan_feature=pf,
        metric=metric,
        limit_value=limit_value,
        period='monthly',
        behavior='hard_limit',
    )


@pytest.fixture
def budget(db):
    """Orçamento configurado com valores explícitos."""
    return StorageBudget.objects.create(
        singleton_key=StorageBudget.SINGLETON_KEY,
        total_budget_bytes=50 * GIB,
        reserve_percent=20,
        allocation_policy=StorageBudget.POLICY_STRICT,
    )


# =========================================================================
# SINGLETON
# =========================================================================

@pytest.mark.django_db
class TestSingleton:

    def test_second_budget_via_save_raises_validation_error(self, budget):
        """
        `StorageBudget.save()` chama `full_clean()`, que valida
        `unique=True` do `singleton_key` em Python.

        Portanto, criar um segundo orçamento via `.save()` levanta
        `ValidationError` — o INSERT nem chega a ser emitido.
        """
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            StorageBudget.objects.create(
                singleton_key=StorageBudget.SINGLETON_KEY,
                total_budget_bytes=100 * GIB,
                reserve_percent=20,
                allocation_policy=StorageBudget.POLICY_STRICT,
            )

    def test_second_budget_via_bulk_create_raises_integrity_error(self, budget):
        """
        Prova que a constraint `unique=True` existe NO BANCO.

        `bulk_create()` pula o `full_clean()` do modelo. O INSERT vai
        direto para o banco, e o `IntegrityError` vem do banco, não
        do Python.

        Isso é o invariante real: sob concorrência (dois processos
        tentando criar o singleton ao mesmo tempo), quem garante é a
        constraint do banco, não a validação em Python.
        """
        duplicate = StorageBudget(
            singleton_key=StorageBudget.SINGLETON_KEY,
            total_budget_bytes=100 * GIB,
            reserve_percent=20,
            allocation_policy=StorageBudget.POLICY_STRICT,
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                StorageBudget.objects.bulk_create([duplicate])


# =========================================================================
# ALLOCATABLE
# =========================================================================

@pytest.mark.django_db
class TestAllocatableBytes:

    def test_20_percent_reserve(self, budget):
        """50 GiB total, 20% reserva → 40 GiB alocável."""
        assert budget.allocatable_bytes == 40 * GIB

    def test_zero_reserve(self):
        b = StorageBudget(
            total_budget_bytes=100 * GIB,
            reserve_percent=0,
            allocation_policy=StorageBudget.POLICY_STRICT,
        )
        assert b.allocatable_bytes == 100 * GIB

    def test_100_percent_reserve(self):
        b = StorageBudget(
            total_budget_bytes=100 * GIB,
            reserve_percent=100,
            allocation_policy=StorageBudget.POLICY_STRICT,
        )
        assert b.allocatable_bytes == 0

    def test_rounding_down(self):
        """Cálculo inteiro, arredondando para baixo."""
        b = StorageBudget(
            total_budget_bytes=101,
            reserve_percent=20,
            allocation_policy=StorageBudget.POLICY_STRICT,
        )
        # 101 * 80 // 100 = 80
        assert b.allocatable_bytes == 80


# =========================================================================
# COMMITTED — cenários
# =========================================================================

@pytest.mark.django_db
class TestCommittedBytes:

    def test_no_workspaces(self, budget):
        assert StorageBudgetService.calculate_committed_bytes() == 0

    def test_workspace_without_subscription(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 10 * GIB)
        _make_workspace('no-sub')

        assert StorageBudgetService.calculate_committed_bytes() == 0

    def test_workspace_with_inactive_subscription(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 10 * GIB)
        ws = _make_workspace('inactive-sub')
        _subscribe(ws, plan_a, is_active=False)

        assert StorageBudgetService.calculate_committed_bytes() == 0

    def test_inactive_workspace_does_not_count(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 10 * GIB)
        ws = _make_workspace('inactive-ws', is_active=False)
        _subscribe(ws, plan_a, is_active=True)

        assert StorageBudgetService.calculate_committed_bytes() == 0

    def test_plan_without_limit_does_not_count(
        self, budget, plan_a,
    ):
        ws = _make_workspace('no-limit')
        _subscribe(ws, plan_a, is_active=True)

        assert StorageBudgetService.calculate_committed_bytes() == 0

    def test_single_workspace_with_limit(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 5 * GIB)
        ws = _make_workspace('one')
        _subscribe(ws, plan_a, is_active=True)

        assert StorageBudgetService.calculate_committed_bytes() == 5 * GIB

    def test_multiple_workspaces_same_plan(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 5 * GIB)
        for i in range(3):
            ws = _make_workspace(f'multi-{i}')
            _subscribe(ws, plan_a, is_active=True)

        assert StorageBudgetService.calculate_committed_bytes() == 15 * GIB

    def test_different_plans(
        self, budget, storage_metric, storage_feature, plan_a, plan_b,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 5 * GIB)
        _set_storage_limit(plan_b, storage_feature, storage_metric, 10 * GIB)

        ws_a1 = _make_workspace('a1')
        _subscribe(ws_a1, plan_a, is_active=True)
        ws_a2 = _make_workspace('a2')
        _subscribe(ws_a2, plan_a, is_active=True)
        ws_b1 = _make_workspace('b1')
        _subscribe(ws_b1, plan_b, is_active=True)

        assert StorageBudgetService.calculate_committed_bytes() == (
            2 * 5 * GIB + 1 * 10 * GIB
        )

    def test_unlimited_quota_raises(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(
            plan_a, storage_feature, storage_metric, None,
        )
        ws = _make_workspace('unlimited')
        _subscribe(ws, plan_a, is_active=True)

        with pytest.raises(StorageBudgetUnlimitedQuotaError):
            StorageBudgetService.calculate_committed_bytes()

    def test_ambiguous_quota_raises(
        self, budget, storage_metric,
        storage_feature, other_feature, plan_a,
    ):
        _set_storage_limit(
            plan_a, storage_feature, storage_metric, 5 * GIB,
        )
        _set_storage_limit(
            plan_a, other_feature, storage_metric, 10 * GIB,
        )
        ws = _make_workspace('ambiguous')
        _subscribe(ws, plan_a, is_active=True)

        with pytest.raises(StorageBudgetAmbiguousQuotaError):
            StorageBudgetService.calculate_committed_bytes()

    def test_inactive_plan_does_not_count(
        self, budget, storage_metric, storage_feature,
    ):
        inactive_plan = Plan.objects.create(
            key='old',
            name='Old',
            price=Decimal('0.00'),
            is_active=False,
        )
        _set_storage_limit(
            inactive_plan, storage_feature, storage_metric, 10 * GIB,
        )
        ws = _make_workspace('inactive-plan')
        _subscribe(ws, inactive_plan, is_active=True)

        assert StorageBudgetService.calculate_committed_bytes() == 0


# =========================================================================
# UPDATE
# =========================================================================

@pytest.mark.django_db
class TestUpdateBudget:

    def test_update_total(self, budget):
        StorageBudgetService.update_budget(
            total_budget_bytes=100 * GIB,
            reason='Aumento',
        )
        budget.refresh_from_db()
        assert budget.total_budget_bytes == 100 * GIB

    def test_update_reserve(self, budget):
        StorageBudgetService.update_budget(
            reserve_percent=30,
            reason='Aumento de reserva',
        )
        budget.refresh_from_db()
        assert budget.reserve_percent == 30

    def test_update_policy(self, budget):
        StorageBudgetService.update_budget(
            allocation_policy=StorageBudget.POLICY_CONTROLLED,
            reason='Flexibilização',
        )
        budget.refresh_from_db()
        assert budget.allocation_policy == StorageBudget.POLICY_CONTROLLED

    def test_update_raises_when_not_configured(self, db):
        with pytest.raises(StorageBudgetNotFoundError):
            StorageBudgetService.update_budget(total_budget_bytes=100 * GIB)

    def test_update_below_committed_strict_raises(
        self, budget, storage_metric, storage_feature, plan_a,
    ):
        _set_storage_limit(plan_a, storage_feature, storage_metric, 30 * GIB)
        ws = _make_workspace('one')
        _subscribe(ws, plan_a, is_active=True)

        # 50 GiB total, 20% reserva → 40 GiB alocável
        # Tentar reduzir total para 30 GiB → 24 GiB alocável < 30 GiB comprometido
        with pytest.raises(StorageBudgetBelowCommittedError):
            StorageBudgetService.update_budget(
                total_budget_bytes=30 * GIB,
                reason='Redução que não cabe',
            )

    def test_update_below_committed_controlled_allows(
        self, storage_metric, storage_feature, plan_a,
    ):
        budget = StorageBudget.objects.create(
            singleton_key=StorageBudget.SINGLETON_KEY,
            total_budget_bytes=50 * GIB,
            reserve_percent=20,
            allocation_policy=StorageBudget.POLICY_CONTROLLED,
        )
        _set_storage_limit(plan_a, storage_feature, storage_metric, 30 * GIB)
        ws = _make_workspace('one')
        _subscribe(ws, plan_a, is_active=True)

        StorageBudgetService.update_budget(
            total_budget_bytes=30 * GIB,
            reason='Sobrealocação intencional',
        )
        budget.refresh_from_db()
        assert budget.total_budget_bytes == 30 * GIB

    def test_update_with_no_change_does_not_create_history(self, budget):
        StorageBudgetService.update_budget(
            total_budget_bytes=budget.total_budget_bytes,
            reserve_percent=budget.reserve_percent,
        )
        assert StorageBudgetChange.objects.filter(budget=budget).count() == 0

    def test_update_writes_history(
        self, budget, django_user_model,
    ):
        user = django_user_model.objects.create_user(
            email='admin-budget@example.com',
            password='x',
        )

        StorageBudgetService.update_budget(
            total_budget_bytes=100 * GIB,
            reserve_percent=30,
            reason='Duplicando orçamento',
            changed_by=user,
        )

        changes = StorageBudgetChange.objects.filter(budget=budget)
        assert changes.count() == 1
        change = changes.first()
        assert change.previous_total_bytes == 50 * GIB
        assert change.new_total_bytes == 100 * GIB
        assert change.previous_reserve_percent == 20
        assert change.new_reserve_percent == 30
        assert change.changed_by == user
        assert change.reason == 'Duplicando orçamento'


# =========================================================================
# SEED
# =========================================================================

@pytest.mark.django_db
class TestSeedStorageBudget:

    def test_seed_creates_budget(self):
        call_command('seed_storage_budget', stdout=StringIO())
        budget = StorageBudget.objects.first()
        assert budget is not None
        assert budget.total_budget_bytes == 50 * GIB
        assert budget.reserve_percent == 20
        assert budget.allocation_policy == StorageBudget.POLICY_STRICT

    def test_seed_is_idempotent(self):
        call_command('seed_storage_budget', stdout=StringIO())
        call_command('seed_storage_budget', stdout=StringIO())
        assert StorageBudget.objects.count() == 1

    def test_seed_does_not_overwrite_existing(self):
        StorageBudget.objects.create(
            singleton_key=StorageBudget.SINGLETON_KEY,
            total_budget_bytes=100 * GIB,
            reserve_percent=10,
            allocation_policy=StorageBudget.POLICY_CONTROLLED,
        )
        call_command('seed_storage_budget', stdout=StringIO())
        budget = StorageBudget.objects.first()
        assert budget.total_budget_bytes == 100 * GIB
        assert budget.reserve_percent == 10
        assert budget.allocation_policy == StorageBudget.POLICY_CONTROLLED

    def test_seed_force_overwrites(self):
        StorageBudget.objects.create(
            singleton_key=StorageBudget.SINGLETON_KEY,
            total_budget_bytes=100 * GIB,
            reserve_percent=10,
            allocation_policy=StorageBudget.POLICY_CONTROLLED,
        )
        call_command(
            'seed_storage_budget',
            '--force',
            '--total', '200GiB',
            '--reserve', '25',
            '--policy', 'strict',
            stdout=StringIO(),
        )
        budget = StorageBudget.objects.first()
        assert budget.total_budget_bytes == 200 * GIB
        assert budget.reserve_percent == 25
        assert budget.allocation_policy == StorageBudget.POLICY_STRICT

    def test_seed_creates_history(self):
        call_command('seed_storage_budget', stdout=StringIO())
        assert StorageBudgetChange.objects.count() == 1
        change = StorageBudgetChange.objects.first()
        assert change.new_total_bytes == 50 * GIB
        assert 'seed' in change.reason.lower()