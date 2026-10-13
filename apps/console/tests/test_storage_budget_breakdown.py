"""
Testes do endpoint `/api/console/storage/budget/breakdown/`.

Cobrem:
    - Orçamento ausente → 404 (o breakdown depende do orçamento existir? NÃO)
      → na prática, o breakdown NÃO exige orçamento. Só lê planos e
        workspaces. Testa isso.
    - Sem planos elegíveis → lista vazia, totais zerados.
    - Um plano com quota → linha com quota, workspaces_count, committed.
    - Múltiplos planos → cada linha correta, total somado.
    - Plano sem quota → has_quota=False, quota_bytes=None, committed=0.
    - Plano ilimitado → 409.
    - Configuração ambígua → 409.
    - Autorização (IsConsoleAdmin).
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

BREAKDOWN_URL = '/api/console/storage/budget/breakdown/'

GIB = 1024 ** 3


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def admin_client(db):
    from rest_framework.test import APIClient
    user = User.objects.create_user(
        email='admin-breakdown@example.com',
        password='x',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def plain_client(db):
    from rest_framework.test import APIClient
    user = User.objects.create_user(
        email='plain-breakdown@example.com',
        password='x',
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


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
def plan_basic(db):
    return Plan.objects.create(
        key='basic',
        name='Basic',
        price=Decimal('49.00'),
        is_active=True,
    )


@pytest.fixture
def plan_pro(db):
    return Plan.objects.create(
        key='pro',
        name='Pro',
        price=Decimal('99.00'),
        is_active=True,
    )


def _make_ws(slug):
    return Workspace.objects.create(name=f'WS {slug}', slug=slug)


def _subscribe(ws, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=ws,
        plan=plan,
        is_active=is_active,
        started_at=ws.created_at,
    )


def _set_quota(plan, feature, metric, limit_value):
    pf = PlanFeature.objects.create(plan=plan, feature=feature)
    return PlanFeatureLimit.objects.create(
        plan_feature=pf,
        metric=metric,
        limit_value=limit_value,
        period='monthly',
        behavior='hard_limit',
    )


# =========================================================================
# AUTORIZAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestBreakdownAuth:

    def test_anonymous_gets_401_or_403(self, api_client):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.get(BREAKDOWN_URL)
        assert resp.status_code in (401, 403)

    def test_non_console_user_gets_403(self, plain_client):
        resp = plain_client.get(BREAKDOWN_URL)
        assert resp.status_code == 403

    def test_admin_gets_200(self, admin_client):
        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 200


# =========================================================================
# SEM DADOS
# =========================================================================

@pytest.mark.django_db
class TestBreakdownEmpty:

    def test_empty_returns_zero_totals(self, admin_client):
        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 200
        assert resp.data['plans'] == []
        assert resp.data['totals']['committed_bytes'] == 0
        assert resp.data['totals']['workspaces_count'] == 0
        assert resp.data['unconfigured_plans_count'] == 0

    def test_breakdown_does_not_require_budget(self, admin_client):
        """
        O breakdown lê planos e workspaces. Não lê o orçamento.
        Se o orçamento não existe, o breakdown ainda funciona.
        """
        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 200


# =========================================================================
# PLANOS ELEGÍVEIS
# =========================================================================

@pytest.mark.django_db
class TestBreakdownPlans:

    def test_plan_without_workspaces_not_in_breakdown(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 200
        assert resp.data['plans'] == []

    def test_plan_with_one_workspace(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        ws = _make_ws('one')
        _subscribe(ws, plan_basic, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 200
        assert len(resp.data['plans']) == 1

        row = resp.data['plans'][0]
        assert row['plan_key'] == 'basic'
        assert row['plan_name'] == 'Basic'
        assert row['quota_bytes'] == 5 * GIB
        assert row['has_quota'] is True
        assert row['is_unlimited'] is False
        assert row['workspaces_count'] == 1
        assert row['committed_bytes'] == 5 * GIB

        assert resp.data['totals']['committed_bytes'] == 5 * GIB
        assert resp.data['totals']['workspaces_count'] == 1

    def test_plan_with_three_workspaces(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        for i in range(3):
            ws = _make_ws(f'w{i}')
            _subscribe(ws, plan_basic, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        row = resp.data['plans'][0]
        assert row['workspaces_count'] == 3
        assert row['committed_bytes'] == 15 * GIB

        assert resp.data['totals']['committed_bytes'] == 15 * GIB
        assert resp.data['totals']['workspaces_count'] == 3

    def test_two_plans(
        self, admin_client, storage_metric, storage_feature,
        plan_basic, plan_pro,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        _set_quota(plan_pro, storage_feature, storage_metric, 10 * GIB)

        ws1 = _make_ws('b1')
        _subscribe(ws1, plan_basic, is_active=True)
        ws2 = _make_ws('b2')
        _subscribe(ws2, plan_basic, is_active=True)
        ws3 = _make_ws('p1')
        _subscribe(ws3, plan_pro, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        assert len(resp.data['plans']) == 2

        by_key = {p['plan_key']: p for p in resp.data['plans']}
        assert by_key['basic']['workspaces_count'] == 2
        assert by_key['basic']['committed_bytes'] == 10 * GIB
        assert by_key['pro']['workspaces_count'] == 1
        assert by_key['pro']['committed_bytes'] == 10 * GIB

        assert resp.data['totals']['committed_bytes'] == 20 * GIB
        assert resp.data['totals']['workspaces_count'] == 3

    def test_plan_without_quota_shows_unconfigured(
        self, admin_client, plan_basic,
    ):
        ws = _make_ws('nq')
        _subscribe(ws, plan_basic, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        row = resp.data['plans'][0]
        assert row['plan_key'] == 'basic'
        assert row['has_quota'] is False
        assert row['quota_bytes'] is None
        assert row['is_unlimited'] is False
        assert row['committed_bytes'] == 0

        assert resp.data['unconfigured_plans_count'] == 1

    def test_inactive_workspace_not_counted(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        ws_active = _make_ws('active')
        _subscribe(ws_active, plan_basic, is_active=True)
        ws_inactive = Workspace.objects.create(
            name='Inactive', slug='inactive', is_active=False,
        )
        _subscribe(ws_inactive, plan_basic, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        row = resp.data['plans'][0]
        assert row['workspaces_count'] == 1

    def test_inactive_subscription_not_counted(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        ws = _make_ws('inactive-sub')
        _subscribe(ws, plan_basic, is_active=False)

        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.data['plans'] == []


# =========================================================================
# ERROS
# =========================================================================

@pytest.mark.django_db
class TestBreakdownErrors:

    def test_unlimited_quota_returns_409(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        _set_quota(plan_basic, storage_feature, storage_metric, None)
        ws = _make_ws('unl')
        _subscribe(ws, plan_basic, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 409
        assert resp.data['code'] == 'unlimited_quota'

    def test_ambiguous_quota_returns_409(
        self, admin_client, storage_metric, storage_feature, plan_basic,
    ):
        from apps.console.models import Feature
        other_feature = Feature.objects.create(
            key='intelligence', name='Intelligence', is_active=True,
        )
        _set_quota(plan_basic, storage_feature, storage_metric, 5 * GIB)
        _set_quota(plan_basic, other_feature, storage_metric, 10 * GIB)
        ws = _make_ws('amb')
        _subscribe(ws, plan_basic, is_active=True)

        resp = admin_client.get(BREAKDOWN_URL)
        assert resp.status_code == 409
        assert resp.data['code'] == 'ambiguous_quota'