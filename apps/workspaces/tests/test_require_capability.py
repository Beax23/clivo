"""
Testes de `RequireCapability`.

Confirma que a permission class do DRF delega corretamente para
`user_has_capability`. Especificamente, confirma que agora TRATA
proprietário como "tem todas as capabilities" — comportamento que
antes divergia entre `RequireCapability` e `workspace_views._has_capability`.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.console.models import (
    ConsoleCapability,
    ConsoleGovernance,
    ConsoleGovernanceCapability,
)
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.workspaces.permissions.workspace_permissions import (
    RequireCapability,
)
from apps.workspaces.services.membership_service import (
    WorkspaceMembershipService,
)


User = get_user_model()


@pytest.fixture
def workspace(db):
    return Workspace.objects.create(name='WS', slug='ws-req-cap')


@pytest.fixture
def user_member(db):
    return User.objects.create_user(
        email='member-req@example.com', password='x',
    )


@pytest.fixture
def gov_proprietario(db):
    return ConsoleGovernance.objects.create(
        key=WorkspaceMembershipService.PROPRIETARIO_KEY,
        name='Proprietário', description='',
        scope='workspace', is_system=True, is_protected=True,
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
        name='Convidar',
        description='',
        source_app='workspaces',
        is_active=True,
    )


def _make_request(user):
    """Cria um mock de request com `user` autenticado."""
    return SimpleNamespace(user=user)


def _make_view(required_capability=None):
    """Cria um mock de view com `required_capability` opcional."""
    return SimpleNamespace(required_capability=required_capability)


@pytest.mark.django_db
class TestRequireCapability:

    def test_has_permission_anonymous_returns_false(self, workspace):
        perm = RequireCapability()
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        assert perm.has_permission(request, _make_view()) is False

    def test_no_required_capability_returns_true(
        self, workspace, user_member,
    ):
        """
        Sem `required_capability` declarada na view, a permission
        deixa passar. Contrato preservado do arquivo original.
        """
        perm = RequireCapability()
        request = _make_request(user_member)
        assert perm.has_object_permission(
            request, _make_view(), workspace,
        ) is True

    def test_outsider_returns_false(
        self, workspace, user_member, capability_active,
    ):
        """Sem membership → False."""
        perm = RequireCapability()
        request = _make_request(user_member)
        view = _make_view(capability_active.code)
        assert perm.has_object_permission(
            request, view, workspace,
        ) is False

    def test_regular_without_capability_returns_false(
        self, workspace, user_member, gov_regular, capability_active,
    ):
        """Membro regular sem ConsoleGovernanceCapability → False."""
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member, governance=gov_regular,
        )
        perm = RequireCapability()
        request = _make_request(user_member)
        view = _make_view(capability_active.code)
        assert perm.has_object_permission(
            request, view, workspace,
        ) is False

    def test_regular_with_capability_returns_true(
        self, workspace, user_member, gov_regular, capability_active,
    ):
        """Membro regular com capability ativa → True."""
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member, governance=gov_regular,
        )
        ConsoleGovernanceCapability.objects.create(
            governance=gov_regular, capability=capability_active,
        )
        perm = RequireCapability()
        request = _make_request(user_member)
        view = _make_view(capability_active.code)
        assert perm.has_object_permission(
            request, view, workspace,
        ) is True

    def test_owner_returns_true_without_explicit_capability(
        self, workspace, user_member, gov_proprietario,
    ):
        """
        CORREÇÃO-CHAVE: proprietário tem todas as capabilities
        mesmo SEM ConsoleGovernanceCapability atribuída.

        Antes da refatoração, `RequireCapability` rejeitaria o
        proprietário neste cenário. Agora aceita.
        """
        WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member,
            governance=gov_proprietario,
        )
        perm = RequireCapability()
        request = _make_request(user_member)
        # Código arbitrário — não precisa existir no catálogo.
        view = _make_view('qualquer.coisa.inventada')
        assert perm.has_object_permission(
            request, view, workspace,
        ) is True

    def test_workspace_extracted_from_membership(
        self, workspace, user_member, gov_proprietario,
    ):
        """
        Confirma que `_extract_workspace` funciona quando o objeto
        é uma WorkspaceMembership (não um Workspace direto).
        """
        membership = WorkspaceMembership.objects.create(
            workspace=workspace, user=user_member,
            governance=gov_proprietario,
        )
        perm = RequireCapability()
        request = _make_request(user_member)
        view = _make_view('qualquer.coisa')
        # Passa o objeto membership, não o workspace.
        assert perm.has_object_permission(
            request, view, membership,
        ) is True