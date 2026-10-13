"""
Testes do endpoint administrativo de quota do Console.

Endpoint:
    GET /api/console/quota/workspaces/<workspace_id>/

Requer:
    - autenticação
    - ConsoleMembership (IsConsoleAdmin)
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.console.models import (
    ConsoleMembership,
    Plan,
    Feature,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)
from apps.workspaces.models import Workspace, WorkspaceSubscription


User = get_user_model()

QUOTA_URL_TEMPLATE = '/api/console/quota/workspaces/{workspace_id}/'


# =========================================================================
# HELPERS
# =========================================================================

@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email='admin-quota@example.com',
        password='x',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    return user


@pytest.fixture
def admin_client_quota(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


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
def plan(db):
    return Plan.objects.create(
        key='pro',
        name='Pro',
        price=Decimal('99.00'),
        is_active=True,
    )


def _make_workspace(name_suffix):
    return Workspace.objects.create(
        name=f'WS {name_suffix}',
        slug=f'ws-{name_suffix}',
    )


def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=workspace.created_at,
    )


def _give_limit(plan, feature, metric, limit_value, behavior='hard_limit'):
    pf = PlanFeature.objects.create(plan=plan, feature=feature)
    PlanFeatureLimit.objects.create(
        plan_feature=pf,
        metric=metric,
        limit_value=limit_value,
        period='monthly',
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


# =========================================================================
# AUTENTICAÇÃO / AUTORIZAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewAuth:

    def test_anonymous_gets_401_or_403(self, api_client, plan):
        ws = _make_workspace('anon')
        _subscribe(ws, plan)
        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = api_client.get(url)
        assert response.status_code in (401, 403)

    def test_non_console_user_gets_403(self, api_client, plan):
        user = User.objects.create_user(email='plain-quota@example.com', password='x')
        api_client.force_authenticate(user=user)
        ws = _make_workspace('plain')
        _subscribe(ws, plan)
        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = api_client.get(url)
        assert response.status_code == 403

    def test_console_admin_gets_200(self, admin_client_quota, plan):
        ws = _make_workspace('admin')
        _subscribe(ws, plan)
        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)
        assert response.status_code == 200


# =========================================================================
# WORKSPACE INVÁLIDO
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewWorkspaceNotFound:

    def test_inexistent_workspace_returns_404(self, admin_client_quota):
        url = QUOTA_URL_TEMPLATE.format(
            workspace_id='00000000-0000-0000-0000-000000000000',
        )
        response = admin_client_quota.get(url)
        assert response.status_code == 404

    def test_invalid_uuid_returns_404(self, admin_client_quota):
        url = QUOTA_URL_TEMPLATE.format(workspace_id='not-a-uuid')
        response = admin_client_quota.get(url)
        assert response.status_code == 404


# =========================================================================
# UNCONFIGURED
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewUnconfigured:

    def test_workspace_without_subscription(
        self, admin_client_quota,
    ):
        ws = _make_workspace('no-sub')
        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        assert response.data['status'] == 'unconfigured'
        assert response.data['allowed'] is True
        assert response.data['quota_bytes'] is None
        assert response.data['plan_key'] is None
        assert response.data['unconfigured_reason'] == 'workspace sem plano ativo'

    def test_workspace_with_inactive_subscription(
        self, admin_client_quota, plan,
    ):
        ws = _make_workspace('inactive-sub')
        _subscribe(ws, plan, is_active=False)
        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        assert response.data['status'] == 'unconfigured'
        assert response.data['unconfigured_reason'] == 'assinatura inativa'

    def test_plan_without_storage_limit(
        self, admin_client_quota, plan,
    ):
        ws = _make_workspace('no-limit')
        _subscribe(ws, plan)
        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        assert response.data['status'] == 'unconfigured'
        assert response.data['quota_bytes'] is None
        assert response.data['plan_key'] == 'pro'
        assert response.data['unconfigured_reason'] == (
            'plano sem limite configurado para storage.bytes'
        )


# =========================================================================
# OK
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewOk:

    def test_ok_below_80_percent(
        self, admin_client_quota, plan, storage_feature, storage_metric,
    ):
        _give_limit(plan, storage_feature, storage_metric, 1000)
        ws = _make_workspace('ok')
        _subscribe(ws, plan)
        _add_document(ws, 500, idx=1)

        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        data = response.data
        assert data['status'] == 'ok'
        assert data['allowed'] is True
        assert data['quota_bytes'] == 1000
        assert data['used_bytes'] == 500
        assert data['remaining_bytes'] == 500
        assert data['percent'] == 50.0
        assert data['behavior'] == 'hard_limit'
        assert data['period'] == 'monthly'
        assert data['feature_key'] == 'armazenamento'
        assert data['plan_key'] == 'pro'
        assert data['plan_name'] == 'Pro'
        assert data['unconfigured_reason'] is None


# =========================================================================
# WARNING
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewWarning:

    def test_warning_at_80_percent(
        self, admin_client_quota, plan, storage_feature, storage_metric,
    ):
        _give_limit(plan, storage_feature, storage_metric, 1000)
        ws = _make_workspace('warn')
        _subscribe(ws, plan)
        _add_document(ws, 800, idx=1)

        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        assert response.data['status'] == 'warning'
        assert response.data['allowed'] is True
        assert response.data['percent'] == 80.0


# =========================================================================
# BLOCKED
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewBlocked:

    def test_blocked_when_over_quota_hard_limit(
        self, admin_client_quota, plan, storage_feature, storage_metric,
    ):
        _give_limit(
            plan, storage_feature, storage_metric, 1000,
            behavior='hard_limit',
        )
        ws = _make_workspace('blocked')
        _subscribe(ws, plan)
        _add_document(ws, 1500, idx=1)

        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        assert response.data['status'] == 'blocked'
        assert response.data['allowed'] is False
        assert response.data['remaining_bytes'] == 0


# =========================================================================
# UNLIMITED
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewUnlimited:

    def test_unlimited_limit_value_none(
        self, admin_client_quota, plan, storage_feature, storage_metric,
    ):
        _give_limit(plan, storage_feature, storage_metric, None)
        ws = _make_workspace('unlimited')
        _subscribe(ws, plan)
        _add_document(ws, 999_999_999, idx=1)

        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 200
        assert response.data['status'] == 'unlimited'
        assert response.data['allowed'] is True
        assert response.data['quota_bytes'] is None
        assert response.data['remaining_bytes'] is None


# =========================================================================
# AMBÍGUO
# =========================================================================

@pytest.mark.django_db
class TestQuotaViewAmbiguous:

    def test_ambiguous_returns_500(
        self, admin_client_quota, plan, storage_feature, storage_metric,
    ):
        feature_other = Feature.objects.create(
            key='intelligence', name='Intelligence', is_active=True,
        )
        _give_limit(plan, storage_feature, storage_metric, 1000)
        _give_limit(plan, feature_other, storage_metric, 2000)

        ws = _make_workspace('ambiguous')
        _subscribe(ws, plan)

        url = QUOTA_URL_TEMPLATE.format(workspace_id=ws.id)
        response = admin_client_quota.get(url)

        assert response.status_code == 500
        assert response.data['code'] == 'ambiguous_quota_configuration'
        assert 'armazenamento' in response.data['error']
        assert 'intelligence' in response.data['error']