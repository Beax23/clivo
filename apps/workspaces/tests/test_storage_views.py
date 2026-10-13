"""
Testes do endpoint WorkspaceStorageView.

Rota:
    GET /api/workspaces/<public_id>/storage/

Cobrem:
    - Autenticação e autorização (membro vs não membro).
    - public_id inválido.
    - public_id válido mas workspace inexistente.
    - Isolamento entre workspaces (membro de A não acessa B).
    - Payload completo por estado (unconfigured, ok, warning, blocked).
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.console.models import (
    Feature,
    Plan,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)
from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceSubscription,
)
from apps.workspaces.public_id import encode_workspace_id


User = get_user_model()


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def governance_proprietario(db):
    from apps.console.models import ConsoleGovernance
    return ConsoleGovernance.objects.create(
        key='proprietario',
        name='Proprietário',
        description='',
        scope='workspace',
        is_system=True,
        is_protected=True,
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
def storage_feature(db):
    return Feature.objects.create(
        key='armazenamento',
        name='Armazenamento',
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
def member_workspace(db, user_member, governance_proprietario, plan_active):
    ws = Workspace.objects.create(name='WS A', slug='ws-a')
    WorkspaceSubscription.objects.create(
        workspace=ws,
        plan=plan_active,
        is_active=True,
        started_at=ws.created_at,
    )
    WorkspaceMembership.objects.create(
        workspace=ws,
        user=user_member,
        governance=governance_proprietario,
    )
    return ws


# =========================================================================
# HELPERS
# =========================================================================

def _url_for(ws):
    return f"/api/workspaces/{encode_workspace_id(ws.id)}/storage/"


def _give_limit(plan, feature, metric, limit_value,
                behavior='hard_limit'):
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
class TestWorkspaceStorageAuth:

    def test_anonymous_gets_401_or_403(
        self, api_client, member_workspace,
    ):
        response = api_client.get(_url_for(member_workspace))
        assert response.status_code in (401, 403)

    def test_outsider_gets_404(
        self, outsider_client, member_workspace,
    ):
        """
        Não-membro recebe 404 (não 403), para não vazar existência
        do workspace.
        """
        response = outsider_client.get(_url_for(member_workspace))
        assert response.status_code == 404

    def test_member_gets_200(
        self, member_client, member_workspace,
    ):
        response = member_client.get(_url_for(member_workspace))
        assert response.status_code == 200


# =========================================================================
# PUBLIC_ID INVÁLIDO
# =========================================================================

@pytest.mark.django_db
class TestWorkspaceStorageInvalidPublicId:

    def test_invalid_public_id_returns_404(self, member_client):
        response = member_client.get(
            '/api/workspaces/not-a-valid-token/storage/'
        )
        assert response.status_code == 404


# =========================================================================
# ISOLAMENTO ENTRE WORKSPACES
# =========================================================================

@pytest.mark.django_db
class TestWorkspaceStorageIsolation:

    def test_member_of_a_cannot_access_b(
        self, member_client, user_member,
        governance_proprietario, plan_active,
    ):
        """
        Usuário é membro de A, mas não de B. Acessar B → 404.
        """
        ws_a = Workspace.objects.create(name='WS A', slug='ws-iso-a')
        ws_b = Workspace.objects.create(name='WS B', slug='ws-iso-b')

        for ws in (ws_a, ws_b):
            WorkspaceSubscription.objects.create(
                workspace=ws, plan=plan_active, is_active=True,
                started_at=ws.created_at,
            )
        WorkspaceMembership.objects.create(
            workspace=ws_a, user=user_member,
            governance=governance_proprietario,
        )

        response = member_client.get(_url_for(ws_b))
        assert response.status_code == 404


# =========================================================================
# UNCONFIGURED
# =========================================================================

@pytest.mark.django_db
class TestWorkspaceStorageUnconfigured:

    def test_workspace_without_limit(
        self, member_client, member_workspace,
    ):
        response = member_client.get(_url_for(member_workspace))

        assert response.status_code == 200
        data = response.data
        assert data['status'] == 'unconfigured'
        assert data['allowed'] is True
        assert data['quota_bytes'] is None
        assert data['plan_key'] == 'pro'
        assert data['unconfigured_reason'] == (
            'plano sem limite configurado para storage.bytes'
        )


# =========================================================================
# OK
# =========================================================================

@pytest.mark.django_db
class TestWorkspaceStorageOk:

    def test_ok_payload(
        self, member_client, member_workspace,
        plan_active, storage_feature, storage_metric,
    ):
        _give_limit(plan_active, storage_feature, storage_metric, 1000)
        _add_document(member_workspace, 500, idx=1)

        response = member_client.get(_url_for(member_workspace))

        assert response.status_code == 200
        data = response.data
        assert data['workspace_id'] == str(member_workspace.pk)
        assert data['workspace_name'] == 'WS A'
        assert data['plan_key'] == 'pro'
        assert data['plan_name'] == 'Pro'
        assert data['status'] == 'ok'
        assert data['allowed'] is True
        assert data['quota_bytes'] == 1000
        assert data['used_bytes'] == 500
        assert data['remaining_bytes'] == 500
        assert data['percent'] == 50.0
        assert data['behavior'] == 'hard_limit'
        assert data['period'] == 'monthly'
        assert data['feature_key'] == 'armazenamento'
        assert data['unconfigured_reason'] is None


# =========================================================================
# WARNING
# =========================================================================

@pytest.mark.django_db
class TestWorkspaceStorageWarning:

    def test_warning_at_80(
        self, member_client, member_workspace,
        plan_active, storage_feature, storage_metric,
    ):
        _give_limit(plan_active, storage_feature, storage_metric, 1000)
        _add_document(member_workspace, 800, idx=1)

        response = member_client.get(_url_for(member_workspace))

        assert response.status_code == 200
        assert response.data['status'] == 'warning'
        assert response.data['allowed'] is True
        assert response.data['percent'] == 80.0


# =========================================================================
# BLOCKED
# =========================================================================

@pytest.mark.django_db
class TestWorkspaceStorageBlocked:

    def test_blocked_over_quota(
        self, member_client, member_workspace,
        plan_active, storage_feature, storage_metric,
    ):
        _give_limit(
            plan_active, storage_feature, storage_metric, 1000,
            behavior='hard_limit',
        )
        _add_document(member_workspace, 1500, idx=1)

        response = member_client.get(_url_for(member_workspace))

        assert response.status_code == 200
        assert response.data['status'] == 'blocked'
        assert response.data['allowed'] is False
        assert response.data['remaining_bytes'] == 0