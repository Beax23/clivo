"""
Testes de `user_has_capability`.

Cobrem:
    - Usuário sem associação ao workspace.
    - Usuário com associação e governance sem a capability.
    - Usuário com associação e governance com a capability ativa.
    - Usuário com associação e governance com a capability INATIVA.
    - Usuário proprietário (governance key='proprietario').

Não testa DRF. Apenas a função pública.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.console.models import (
    ConsoleCapability,
    ConsoleGovernance,
    ConsoleGovernanceCapability,
)
from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
)
from apps.workspaces.permissions.workspace_permissions import (
    user_has_capability,
)
from apps.workspaces.services.membership_service import (
    WorkspaceMembershipService,
)


User = get_user_model()


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def workspace(db):
    return Workspace.objects.create(name='WS', slug='ws-cap-test')


@pytest.fixture
def user_member(db):
    return User.objects.create_user(
        email='member-cap@example.com', password='x',
    )


@pytest.fixture
def user_outsider(db):
    return User.objects.create_user(
        email='outsider-cap@example.com', password='x',
    )


@pytest.fixture
def gov_proprietario(db):
    return ConsoleGovernance.objects.create(
        key=WorkspaceMembershipService.PROPRIETARIO_KEY,
        name='Proprietário',
        description='',
        scope='workspace',
        is_system=True,
        is_protected=True,
    )


@pytest.fixture
def gov_regular(db):
    return ConsoleGovernance.objects.create(
        key='membro', name='Membro',
        description='', scope='workspace',
    )


@pytest.fixture
def capability_active(db):
    return ConsoleCapability.objects.create(
        code='workspaces.member.invite',
        name='Convidar membro',
        description='',
        source_app='workspaces',
        is_active=True,
    )


@pytest.fixture
def capability_inactive(db):
    return ConsoleCapability.objects.create(
        code='workspaces.member.remove',
        name='Remover membro',
        description='',
        source_app='workspaces',
        is_active=False,
    )


# =========================================================================
# TESTES
# =========================================================================

@pytest.mark.django_db
class TestUserHasCapability:

    def test_anonymous_returns_false(self, workspace):
        """Usuário anônimo → False."""
        assert user_has_capability(workspace, None, 'any.code') is False

    def test_none_user_returns_false(self, workspace):
        """user=None → False."""
        assert user_has_capability(workspace, None, 'any.code') is False

    def test_outsider_returns_false(
        self, workspace, user_outsider, capability_active,
    ):
        """
        Usuário autenticado sem membership → False.
        Nem precisa de capability existente.
        """
        assert user_has_capability(
            workspace, user_outsider, capability_active.code,
        ) is False

    def test_regular_without_capability_returns_false(
        self, workspace, user_member, gov_regular, capability_active,
    ):
        """
        Membro com governance regular, mas SEM ConsoleGovernanceCapability
        atribuída → False.
        """
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member, governance=gov_regular,
        )
        # capability_active existe no catálogo, mas a governance
        # não a tem.
        assert user_has_capability(
            workspace, user_member, capability_active.code,
        ) is False

    def test_regular_with_active_capability_returns_true(
        self, workspace, user_member, gov_regular, capability_active,
    ):
        """Membro com governance regular e capability ativa → True."""
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member, governance=gov_regular,
        )
        ConsoleGovernanceCapability.objects.create(
            governance=gov_regular, capability=capability_active,
        )
        assert user_has_capability(
            workspace, user_member, capability_active.code,
        ) is True

    def test_regular_with_inactive_capability_returns_false(
        self, workspace, user_member, gov_regular, capability_inactive,
    ):
        """
        Membro com governance regular e ConsoleGovernanceCapability
        apontando para uma capability INATIVA → False.

        Regra: capability precisa estar ativa para conceder acesso.
        """
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member, governance=gov_regular,
        )
        ConsoleGovernanceCapability.objects.create(
            governance=gov_regular, capability=capability_inactive,
        )
        assert user_has_capability(
            workspace, user_member, capability_inactive.code,
        ) is False

    def test_owner_returns_true_for_any_code(
        self, workspace, user_member, gov_proprietario,
    ):
        """
        Proprietário → True para QUALQUER código, mesmo sem
        ConsoleGovernanceCapability.
        """
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member,
            governance=gov_proprietario,
        )
        assert user_has_capability(
            workspace, user_member, 'qualquer.coisa.inventada',
        ) is True