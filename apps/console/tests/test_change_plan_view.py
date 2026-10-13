"""
Testes da action `change_plan` no AdminWorkspaceViewSet.

Cobre:
    - Auth / autorização.
    - Plano inexistente.
    - Plano inativo (H2).
    - Mesmo plano (H1).
    - Troca com sucesso: encerra antiga, cria nova, preenche auditoria.
    - Sem assinatura ativa: cria nova com reason=manual (H3).
    - Constraint de uma única ativa por workspace.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.console.models import ConsoleMembership, Plan
from apps.workspaces.models import Workspace, WorkspaceSubscription


User = get_user_model()


def _url(ws):
    return f'/api/console/workspaces/{ws.id}/change-plan/'


@pytest.fixture
def console_admin(db):
    user = User.objects.create_user(
        email='admin-change-plan@example.com',
        password='x',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    return user


@pytest.fixture
def admin_client(api_client, console_admin):
    api_client.force_authenticate(user=console_admin)
    return api_client


@pytest.fixture
def plan_pro(db):
    return Plan.objects.create(
        key='pro', name='Pro', price=Decimal('99.00'), is_active=True,
    )


@pytest.fixture
def plan_basic(db):
    return Plan.objects.create(
        key='basic', name='Basic', price=Decimal('49.00'), is_active=True,
    )


@pytest.fixture
def plan_inactive(db):
    return Plan.objects.create(
        key='old', name='Old', price=Decimal('0.00'), is_active=False,
    )


@pytest.fixture
def workspace(db):
    return Workspace.objects.create(name='WS Change', slug='ws-change')


def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace, plan=plan, is_active=is_active,
        started_at=workspace.created_at,
    )


# =========================================================================
# AUTENTICAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestChangePlanAuth:

    def test_anonymous_gets_401_or_403(self, api_client, workspace, plan_basic):
        response = api_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key},
            format='json',
        )
        assert response.status_code in (401, 403)


# =========================================================================
# ERROS DE VALIDAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestChangePlanValidation:

    def test_missing_plan_key_returns_400(self, admin_client, workspace):
        response = admin_client.post(_url(workspace), {}, format='json')
        assert response.status_code == 400
        assert 'plan_key' in response.data['error']

    def test_unknown_plan_returns_404(self, admin_client, workspace):
        response = admin_client.post(
            _url(workspace),
            {'plan_key': 'nonexistent'},
            format='json',
        )
        assert response.status_code == 404

    def test_inactive_plan_returns_400(
        self, admin_client, workspace, plan_inactive,
    ):
        response = admin_client.post(
            _url(workspace),
            {'plan_key': plan_inactive.key},
            format='json',
        )
        assert response.status_code == 400
        assert 'inativo' in response.data['error'].lower()

    def test_same_plan_returns_400(
        self, admin_client, workspace, plan_pro,
    ):
        _subscribe(workspace, plan_pro, is_active=True)

        response = admin_client.post(
            _url(workspace),
            {'plan_key': plan_pro.key},
            format='json',
        )
        assert response.status_code == 400
        assert 'já está no plano' in response.data['error']


# =========================================================================
# TROCA COM SUCESSO
# =========================================================================

@pytest.mark.django_db
class TestChangePlanSuccess:

    def test_creates_new_active_subscription(
        self, admin_client, workspace, plan_pro, plan_basic,
    ):
        old = _subscribe(workspace, plan_pro, is_active=True)

        response = admin_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key},
            format='json',
        )

        assert response.status_code == 200
        data = response.data
        assert data['plan_key'] == 'basic'
        assert data['is_active'] is True
        assert data['reason'] == 'manual'
        assert str(data['changed_from_id']) == str(old.id)

        # A antiga foi encerrada
        old.refresh_from_db()
        assert old.is_active is False
        assert old.ended_at is not None

    def test_workspace_without_active_subscription_creates_new(
        self, admin_client, workspace, plan_basic,
    ):
        response = admin_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key},
            format='json',
        )

        assert response.status_code == 200
        assert response.data['plan_key'] == 'basic'
        assert response.data['changed_from_id'] is None

    def test_only_one_active_subscription_remains(
        self, admin_client, workspace, plan_pro, plan_basic,
    ):
        _subscribe(workspace, plan_pro, is_active=True)

        admin_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key},
            format='json',
        )

        active_count = WorkspaceSubscription.objects.filter(
            workspace=workspace, is_active=True,
        ).count()
        assert active_count == 1

    def test_history_is_preserved(
        self, admin_client, workspace, plan_pro, plan_basic,
    ):
        _subscribe(workspace, plan_pro, is_active=True)

        admin_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key},
            format='json',
        )

        # 2 assinaturas totais: a antiga (inativa) + a nova (ativa)
        assert WorkspaceSubscription.objects.filter(
            workspace=workspace,
        ).count() == 2

    def test_custom_reason_is_persisted(
        self, admin_client, workspace, plan_pro, plan_basic,
    ):
        _subscribe(workspace, plan_pro, is_active=True)

        response = admin_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key, 'reason': 'downgrade'},
            format='json',
        )
        assert response.status_code == 200
        assert response.data['reason'] == 'downgrade'

    def test_invalid_reason_returns_400(
        self, admin_client, workspace, plan_pro, plan_basic,
    ):
        _subscribe(workspace, plan_pro, is_active=True)

        response = admin_client.post(
            _url(workspace),
            {'plan_key': plan_basic.key, 'reason': 'weird'},
            format='json',
        )
        assert response.status_code == 400