"""
Testes do QuotaService.

Cobrem:
    - get_quota_info: resolução via plano, casos ausentes, ambiguidade
    - get_usage_bytes: soma de Document.size + Reference.size
    - get_remaining_bytes: subtração segura, ilimitado, ausente
    - check: máquina de estados completa

Nenhuma chamada de rede. Usa SQLite em memória (pytest-django).

As fixtures de documentos/referências são criadas diretamente via ORM,
porque o QuotaService só olha para `size` — não precisa do ciclo de
upload/storage real.
"""

from decimal import Decimal

import pytest

from apps.console.exceptions import AmbiguousQuotaConfigurationError
from apps.console.models import (
    Plan,
    Feature,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)
from apps.console.services.quota_service import (
    QuotaService,
    QuotaInfo,
    QuotaCheckResult,
    STORAGE_METRIC_KEY,
    WARNING_THRESHOLD,
)
from apps.workspaces.models import Workspace, WorkspaceSubscription


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def storage_metric(db):
    return UsageMetric.objects.create(
        key=STORAGE_METRIC_KEY,
        name='Armazenamento',
        unit='byte',
        kind='gauge',
        origin='derived',
        is_active=True,
    )


@pytest.fixture
def other_metric(db):
    return UsageMetric.objects.create(
        key='ai.credits',
        name='Créditos de IA',
        unit='credit',
        kind='counter',
        origin='recorded',
        is_active=True,
    )


@pytest.fixture
def feature_storage(db):
    return Feature.objects.create(
        key='armazenamento',
        name='Armazenamento',
        is_active=True,
    )


@pytest.fixture
def feature_other(db):
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
        is_public=True,
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
def workspace_with_plan(db, plan_active):
    """
    Workspace com subscription ativa e plano ativo, SEM limite
    configurado. Serve para testar o caso 'plano sem limite'.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(email='ws@example.com', password='x')
    ws = Workspace.objects.create(name='WS Test', slug='ws-test')
    WorkspaceSubscription.objects.create(
        workspace=ws,
        plan=plan_active,
        is_active=True,
        started_at=ws.created_at,
    )
    return ws


# =========================================================================
# HELPERS — DOCUMENTOS E REFERENCES
# =========================================================================

def _make_document(workspace, size: int, idx: int = 0):
    """
    Cria um Document mínimo do ponto de vista do QuotaService:
    workspace + size. Não sobe arquivo físico.
    """
    from apps.documents.models import Document
    return Document.objects.create(
        workspace=workspace,
        name=f'doc-{idx}',
        file=f'documents/test-{idx}.bin',  # caminho fictício
        extension='bin',
        mime_type='application/octet-stream',
        size=size,
    )


def _make_reference(workspace, size: int, idx: int = 0):
    """
    Cria uma Reference mínima do ponto de vista do QuotaService:
    workspace + size. Não sobe imagem física.
    """
    from apps.references.models import Reference
    return Reference.objects.create(
        workspace=workspace,
        title=f'ref-{idx}',
        image=f'references/test-{idx}.jpg',
        extension='jpg',
        size=size,
    )


def _set_storage_limit(
    plan, feature, metric,
    limit_value,
    period='monthly',
    behavior='hard_limit',
):
    pf = PlanFeature.objects.create(plan=plan, feature=feature)
    return PlanFeatureLimit.objects.create(
        plan_feature=pf,
        metric=metric,
        limit_value=limit_value,
        period=period,
        behavior=behavior,
    )


# =========================================================================
# GET_QUOTA_INFO
# =========================================================================

@pytest.mark.django_db
class TestGetQuotaInfo:

    def test_returns_none_when_no_subscription(self):
        """Workspace sem subscription → None."""
        ws = Workspace.objects.create(name='Sem plano', slug='sem-plano')
        assert QuotaService.get_quota_info(ws) is None

    def test_returns_none_when_subscription_inactive(
        self, plan_active,
    ):
        ws = Workspace.objects.create(name='WS', slug='ws-inactive')
        WorkspaceSubscription.objects.create(
            workspace=ws,
            plan=plan_active,
            is_active=False,
            started_at=ws.created_at,
            ended_at=ws.created_at,
        )
        assert QuotaService.get_quota_info(ws) is None

    def test_returns_none_when_plan_inactive(
        self, plan_inactive,
    ):
        ws = Workspace.objects.create(name='WS', slug='ws-plan-inactive')
        WorkspaceSubscription.objects.create(
            workspace=ws,
            plan=plan_inactive,
            is_active=True,
            started_at=ws.created_at,
        )
        assert QuotaService.get_quota_info(ws) is None

    def test_returns_none_when_plan_has_no_storage_limit(
        self, plan_active, feature_other, other_metric,
    ):
        # Limite existe, mas é de outra métrica — não deve contar.
        _set_storage_limit(
            plan_active, feature_other, other_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-other-limit')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        assert QuotaService.get_quota_info(ws) is None

    def test_returns_quota_info_when_single_limit_exists(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=5 * 1024 ** 3,
            period='monthly',
            behavior='hard_limit',
        )
        ws = Workspace.objects.create(name='WS', slug='ws-ok')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )

        info = QuotaService.get_quota_info(ws)

        assert info is not None
        assert isinstance(info, QuotaInfo)
        assert info.limit_value == 5 * 1024 ** 3
        assert info.period == 'monthly'
        assert info.behavior == 'hard_limit'
        assert info.feature_key == 'armazenamento'
        assert info.plan_key == 'pro'

    def test_returns_quota_info_with_unlimited_limit(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=None,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-unlim')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )

        info = QuotaService.get_quota_info(ws)
        assert info is not None
        assert info.limit_value is None

    def test_raises_ambiguous_when_multiple_limits(
        self, plan_active, feature_storage, feature_other,
        storage_metric,
    ):
        """
        Mesmo plano, DUAS features diferentes com limite da MESMA métrica.
        Deve levantar AmbiguousQuotaConfigurationError — não somar,
        não escolher.
        """
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        _set_storage_limit(
            plan_active, feature_other, storage_metric, 2000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-ambiguous')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )

        with pytest.raises(AmbiguousQuotaConfigurationError) as exc:
            QuotaService.get_quota_info(ws)

        # Mensagem deve citar as features conflitantes
        assert 'armazenamento' in str(exc.value)
        assert 'intelligence' in str(exc.value)

    def test_ignores_inactive_metric(
        self, plan_active, feature_storage, storage_metric,
    ):
        """
        Limite cuja métrica está inativa não conta.
        Se for o único, o resultado é None.
        """
        storage_metric.is_active = False
        storage_metric.save(update_fields=['is_active'])

        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-inactive-metric')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )

        assert QuotaService.get_quota_info(ws) is None


# =========================================================================
# GET_USAGE_BYTES
# =========================================================================

@pytest.mark.django_db
class TestGetUsageBytes:

    def test_empty_workspace_returns_zero(self):
        ws = Workspace.objects.create(name='WS', slug='ws-empty')
        assert QuotaService.get_usage_bytes(ws) == 0

    def test_documents_only(self):
        ws = Workspace.objects.create(name='WS', slug='ws-docs')
        _make_document(ws, 100, idx=1)
        _make_document(ws, 250, idx=2)
        assert QuotaService.get_usage_bytes(ws) == 350

    def test_references_only(self):
        ws = Workspace.objects.create(name='WS', slug='ws-refs')
        _make_reference(ws, 500, idx=1)
        _make_reference(ws, 750, idx=2)
        assert QuotaService.get_usage_bytes(ws) == 1250

    def test_documents_plus_references(self):
        ws = Workspace.objects.create(name='WS', slug='ws-both')
        _make_document(ws, 100, idx=1)
        _make_reference(ws, 500, idx=1)
        assert QuotaService.get_usage_bytes(ws) == 600

    def test_isolated_between_workspaces(self):
        ws_a = Workspace.objects.create(name='A', slug='ws-a')
        ws_b = Workspace.objects.create(name='B', slug='ws-b')
        _make_document(ws_a, 1000, idx=1)
        _make_reference(ws_a, 2000, idx=1)
        _make_document(ws_b, 9999, idx=1)

        assert QuotaService.get_usage_bytes(ws_a) == 3000
        assert QuotaService.get_usage_bytes(ws_b) == 9999

    def test_zero_size_documents_are_ignored_in_sum(self):
        ws = Workspace.objects.create(name='WS', slug='ws-zeros')
        _make_document(ws, 0, idx=1)
        _make_document(ws, 0, idx=2)
        _make_reference(ws, 100, idx=1)
        assert QuotaService.get_usage_bytes(ws) == 100


# =========================================================================
# GET_REMAINING_BYTES
# =========================================================================

@pytest.mark.django_db
class TestGetRemainingBytes:

    def test_returns_none_without_quota(self):
        ws = Workspace.objects.create(name='WS', slug='ws-no-quota')
        assert QuotaService.get_remaining_bytes(ws) is None

    def test_returns_none_when_unlimited(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=None,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-unlim-rem')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        assert QuotaService.get_remaining_bytes(ws) is None

    def test_returns_difference(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-diff')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 400, idx=1)

        assert QuotaService.get_remaining_bytes(ws) == 600

    def test_returns_zero_when_used_equals_quota(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-full')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 1000, idx=1)

        assert QuotaService.get_remaining_bytes(ws) == 0

    def test_returns_zero_when_used_exceeds_quota(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-over')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 5000, idx=1)

        assert QuotaService.get_remaining_bytes(ws) == 0

    def test_propagates_ambiguous_error(
        self, plan_active, feature_storage, feature_other, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        _set_storage_limit(
            plan_active, feature_other, storage_metric, 2000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-amb-rem')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )

        with pytest.raises(AmbiguousQuotaConfigurationError):
            QuotaService.get_remaining_bytes(ws)


# =========================================================================
# CHECK — MÁQUINA DE ESTADOS
# =========================================================================

@pytest.mark.django_db
class TestCheck:

    # ------------------------------------------------------------------
    # UNCONFIGURED
    # ------------------------------------------------------------------

    def test_unconfigured_no_plan(self):
        ws = Workspace.objects.create(name='WS', slug='ws-nc-1')
        result = QuotaService.check(ws)

        assert isinstance(result, QuotaCheckResult)
        assert result.status == 'unconfigured'
        assert result.allowed is True
        assert result.quota_bytes is None
        assert result.remaining_bytes is None
        assert result.used_bytes == 0

    def test_unconfigured_plan_without_limit(
        self, plan_active,
    ):
        ws = Workspace.objects.create(name='WS', slug='ws-nc-2')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        result = QuotaService.check(ws)

        assert result.status == 'unconfigured'
        assert result.allowed is True
        assert result.quota_bytes is None

    def test_unconfigured_does_not_raise_on_ambiguous(
        self, plan_active, feature_storage, feature_other, storage_metric,
    ):
        """
        `check()` NÃO deve levantar — deve retornar 'unconfigured'
        com feature_key='__ambiguous__' para o endpoint administrativo
        detectar e responder 500 se quiser.
        """
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        _set_storage_limit(
            plan_active, feature_other, storage_metric, 2000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-nc-amb')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        result = QuotaService.check(ws)

        assert result.status == 'unconfigured'
        assert result.allowed is True
        assert result.feature_key == '__ambiguous__'

    # ------------------------------------------------------------------
    # UNLIMITED
    # ------------------------------------------------------------------

    def test_unlimited(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=None,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-unl')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 999_999_999, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'unlimited'
        assert result.allowed is True
        assert result.quota_bytes is None
        assert result.remaining_bytes is None
        assert result.used_bytes == 999_999_999

    # ------------------------------------------------------------------
    # OK — uso < 80%
    # ------------------------------------------------------------------

    def test_ok_at_zero_usage(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-ok-zero')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        result = QuotaService.check(ws)

        assert result.status == 'ok'
        assert result.allowed is True
        assert result.quota_bytes == 1000
        assert result.used_bytes == 0
        assert result.remaining_bytes == 1000
        assert result.percent == 0.0

    def test_ok_below_warning_threshold(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-ok-79')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 790, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'ok'
        assert result.allowed is True
        assert result.remaining_bytes == 210
        assert result.percent == 79.0

    # ------------------------------------------------------------------
    # WARNING — 80% ≤ uso < 100%
    # ------------------------------------------------------------------

    def test_warning_at_exactly_80_percent(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-warn-80')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 800, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'warning'
        assert result.allowed is True
        assert result.remaining_bytes == 200
        assert result.percent == 80.0

    def test_warning_just_below_full(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric, 1000,
        )
        ws = Workspace.objects.create(name='WS', slug='ws-warn-99')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 999, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'warning'
        assert result.allowed is True
        assert result.remaining_bytes == 1

    # ------------------------------------------------------------------
    # BLOCKED — uso ≥ 100% E hard_limit
    # ------------------------------------------------------------------

    def test_blocked_exactly_at_quota_hard_limit(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=1000, behavior='hard_limit',
        )
        ws = Workspace.objects.create(name='WS', slug='ws-blocked-100')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 1000, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'blocked'
        assert result.allowed is False
        assert result.remaining_bytes == 0
        assert result.percent == 100.0
        assert result.behavior == 'hard_limit'

    def test_blocked_above_quota_hard_limit(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=1000, behavior='hard_limit',
        )
        ws = Workspace.objects.create(name='WS', slug='ws-blocked-120')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 1200, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'blocked'
        assert result.allowed is False
        assert result.remaining_bytes == 0
        assert result.percent == 120.0

    # ------------------------------------------------------------------
    # WARNING acima da quota — soft_limit / overage_allowed
    # ------------------------------------------------------------------

    def test_warning_above_quota_soft_limit(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=1000, behavior='soft_limit',
        )
        ws = Workspace.objects.create(name='WS', slug='ws-soft-over')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 1200, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'warning'
        assert result.allowed is True
        assert result.remaining_bytes == 0

    def test_warning_above_quota_overage_allowed(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=1000, behavior='overage_allowed',
        )
        ws = Workspace.objects.create(name='WS', slug='ws-overage')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        _make_document(ws, 1200, idx=1)

        result = QuotaService.check(ws)

        assert result.status == 'warning'
        assert result.allowed is True
        assert result.remaining_bytes == 0

    # ------------------------------------------------------------------
    # METADADOS PROPAGADOS
    # ------------------------------------------------------------------

    def test_check_propagates_behavior_and_period(
        self, plan_active, feature_storage, storage_metric,
    ):
        _set_storage_limit(
            plan_active, feature_storage, storage_metric,
            limit_value=5000,
            period='lifetime',
            behavior='soft_limit',
        )
        ws = Workspace.objects.create(name='WS', slug='ws-meta')
        WorkspaceSubscription.objects.create(
            workspace=ws, plan=plan_active, is_active=True,
            started_at=ws.created_at,
        )
        result = QuotaService.check(ws)

        assert result.behavior == 'soft_limit'
        assert result.period == 'lifetime'
        assert result.feature_key == 'armazenamento'
        assert result.plan_key == 'pro' 