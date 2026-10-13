"""
Testes do WorkspaceStorageService.

O WorkspaceStorageService envelopa o QuotaService (Console). Os testes
verificam:
    - O payload retornado tem todos os campos esperados.
    - Cada estado (unconfigured / unlimited / ok / warning / blocked)
      é propagado corretamente.
    - Casos-limite do Workspace: sem plano, plano inativo, plano sem
      limite, limite ilimitado.
    - Atalhos `get_usage_bytes` e `get_quota_bytes`.
    - Ambiguidade é absorvida (não levanta em get_storage_state).
"""

from decimal import Decimal

import pytest

from apps.console.models import (
    Feature,
    Plan,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)
from apps.workspaces.models import Workspace, WorkspaceSubscription
from apps.workspaces.services.storage_service import WorkspaceStorageService


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
def plan_active(db):
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


@pytest.fixture
def workspace(db):
    return Workspace.objects.create(
        name='Studio Teste',
        slug='studio-teste',
    )


# =========================================================================
# HELPERS
# =========================================================================

def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=workspace.created_at,
    )


def _give_limit(plan, feature, metric, limit_value,
                period='monthly', behavior='hard_limit'):
    pf = PlanFeature.objects.create(plan=plan, feature=feature)
    return PlanFeatureLimit.objects.create(
        plan_feature=pf,
        metric=metric,
        limit_value=limit_value,
        period=period,
        behavior=behavior,
    )


def _add_document(workspace, size, idx=0):
    from apps.documents.models import Document
    return Document.objects.create(
        workspace=workspace,
        name=f'doc-{idx}',
        file=f'documents/test-{idx}.bin',
        extension='bin',
        mime_type='application/octet-stream',
        size=size,
    )


def _add_reference(workspace, size, idx=0):
    from apps.references.models import Reference
    return Reference.objects.create(
        workspace=workspace,
        title=f'ref-{idx}',
        image=f'references/test-{idx}.jpg',
        extension='jpg',
        size=size,
    )


# =========================================================================
# UNCONFIGURED
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateUnconfigured:

    def test_workspace_without_subscription(self, workspace):
        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['workspace_id'] == str(workspace.pk)
        assert state['workspace_name'] == 'Studio Teste'
        assert state['status'] == 'unconfigured'
        assert state['allowed'] is True
        assert state['quota_bytes'] is None
        assert state['remaining_bytes'] is None
        assert state['plan_key'] is None
        assert state['plan_name'] is None
        assert state['unconfigured_reason'] == 'workspace sem plano ativo'

    def test_workspace_with_inactive_subscription(
        self, workspace, plan_active,
    ):
        _subscribe(workspace, plan_active, is_active=False)
        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'unconfigured'
        assert state['unconfigured_reason'] == 'assinatura inativa'

    def test_workspace_with_inactive_plan(
        self, workspace, plan_inactive,
    ):
        _subscribe(workspace, plan_inactive)
        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'unconfigured'
        assert state['unconfigured_reason'] == 'plano inativo'

    def test_plan_without_storage_limit(
        self, workspace, plan_active,
    ):
        _subscribe(workspace, plan_active)
        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'unconfigured'
        assert state['quota_bytes'] is None
        assert state['plan_key'] == 'pro'
        assert state['unconfigured_reason'] == (
            'plano sem limite configurado para storage.bytes'
        )


# =========================================================================
# UNLIMITED
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateUnlimited:

    def test_unlimited_limit(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(
            plan_active, storage_feature, storage_metric, None,
        )
        _subscribe(workspace, plan_active)
        _add_document(workspace, 1000, idx=1)

        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'unlimited'
        assert state['allowed'] is True
        assert state['quota_bytes'] is None
        assert state['remaining_bytes'] is None
        assert state['used_bytes'] == 1000


# =========================================================================
# OK
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateOk:

    def test_ok_below_80_percent(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(plan_active, storage_feature, storage_metric, 1000)
        _subscribe(workspace, plan_active)
        _add_document(workspace, 500, idx=1)
        _add_reference(workspace, 200, idx=1)

        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'ok'
        assert state['allowed'] is True
        assert state['quota_bytes'] == 1000
        assert state['used_bytes'] == 700
        assert state['remaining_bytes'] == 300
        assert state['percent'] == 70.0
        assert state['behavior'] == 'hard_limit'
        assert state['period'] == 'monthly'
        assert state['feature_key'] == 'armazenamento'
        assert state['plan_key'] == 'pro'
        assert state['plan_name'] == 'Pro'
        assert state['unconfigured_reason'] is None


# =========================================================================
# WARNING
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateWarning:

    def test_warning_at_80_percent(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(plan_active, storage_feature, storage_metric, 1000)
        _subscribe(workspace, plan_active)
        _add_document(workspace, 800, idx=1)

        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'warning'
        assert state['allowed'] is True
        assert state['percent'] == 80.0
        assert state['remaining_bytes'] == 200


# =========================================================================
# BLOCKED
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateBlocked:

    def test_blocked_over_quota_hard_limit(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(
            plan_active, storage_feature, storage_metric, 1000,
            behavior='hard_limit',
        )
        _subscribe(workspace, plan_active)
        _add_document(workspace, 1500, idx=1)

        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'blocked'
        assert state['allowed'] is False
        assert state['remaining_bytes'] == 0
        assert state['percent'] == 150.0


# =========================================================================
# SOFT / OVERAGE
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateSoftAndOverage:

    def test_soft_limit_allows_overage(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(
            plan_active, storage_feature, storage_metric, 1000,
            behavior='soft_limit',
        )
        _subscribe(workspace, plan_active)
        _add_document(workspace, 1500, idx=1)

        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'warning'
        assert state['allowed'] is True
        assert state['behavior'] == 'soft_limit'


# =========================================================================
# AMBIGUIDADE — absorvida
# =========================================================================

@pytest.mark.django_db
class TestGetStorageStateAmbiguous:

    def test_ambiguous_does_not_raise(
        self, workspace, plan_active,
        storage_feature, other_feature, storage_metric,
    ):
        """
        `get_storage_state` NÃO deve levantar em ambiguidade — deve
        devolver um payload explícito com feature_key='__ambiguous__'.
        """
        _give_limit(plan_active, storage_feature, storage_metric, 1000)
        _give_limit(plan_active, other_feature, storage_metric, 2000)
        _subscribe(workspace, plan_active)

        state = WorkspaceStorageService.get_storage_state(workspace)

        assert state['status'] == 'unconfigured'
        assert state['feature_key'] == '__ambiguous__'
        assert 'ambígua' in state['unconfigured_reason']


# =========================================================================
# ATALHOS
# =========================================================================

@pytest.mark.django_db
class TestShortcuts:

    def test_get_usage_bytes(
        self, workspace,
    ):
        _add_document(workspace, 100, idx=1)
        _add_reference(workspace, 500, idx=1)

        assert WorkspaceStorageService.get_usage_bytes(workspace) == 600

    def test_get_quota_bytes_when_configured(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(plan_active, storage_feature, storage_metric, 5000)
        _subscribe(workspace, plan_active)

        assert WorkspaceStorageService.get_quota_bytes(workspace) == 5000

    def test_get_quota_bytes_returns_none_when_no_plan(
        self, workspace,
    ):
        assert WorkspaceStorageService.get_quota_bytes(workspace) is None

    def test_get_quota_bytes_returns_none_when_unlimited(
        self, workspace, plan_active, storage_feature, storage_metric,
    ):
        _give_limit(plan_active, storage_feature, storage_metric, None)
        _subscribe(workspace, plan_active)

        assert WorkspaceStorageService.get_quota_bytes(workspace) is None

    def test_get_quota_bytes_propagates_ambiguous(
        self, workspace, plan_active,
        storage_feature, other_feature, storage_metric,
    ):
        """
        Diferente de `get_storage_state`, o atalho `get_quota_bytes`
        propaga AmbiguousQuotaConfigurationError. É contrato do
        QuotaService, e o atalho apenas repassa.
        """
        from apps.console.exceptions import AmbiguousQuotaConfigurationError

        _give_limit(plan_active, storage_feature, storage_metric, 1000)
        _give_limit(plan_active, other_feature, storage_metric, 2000)
        _subscribe(workspace, plan_active)

        with pytest.raises(AmbiguousQuotaConfigurationError):
            WorkspaceStorageService.get_quota_bytes(workspace)