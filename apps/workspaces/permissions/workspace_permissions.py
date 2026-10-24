"""
Permissões do Workspace.

REGRA ARQUITETURAL:
    O Workspace NÃO conhece nomes de Governance como regra geral.
    A exceção é "proprietario", que é uma INVARIANTE ESTRUTURAL do
    tenant (todo Workspace precisa ter pelo menos um proprietário).

    Toda outra autorização passa por:
        WorkspaceMembership
            → ConsoleGovernance
                → ConsoleGovernanceCapability
                    → ConsoleCapability

    Este é o ÚNICO ponto do módulo `workspaces` que consulta
    ConsoleGovernanceCapability. Apps de domínio (integrations,
    clients, briefings) consomem esta interface pública e NÃO
    importam `apps.console` diretamente.

API PÚBLICA:
    user_has_capability(workspace, user, code) → bool
        Fonte única de verdade da pergunta
        "esse usuário tem essa capability nesse workspace?".

    RequireCapability
        Permission class do DRF. Delega para `user_has_capability`.

    IsWorkspaceMember / IsWorkspaceOwner
        Permissions estruturais. `IsWorkspaceOwner` verifica a
        invariante do tenant (última pessoa com governance
        `proprietario` não pode sair).
"""

from rest_framework.permissions import BasePermission

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.workspaces.services.membership_service import (
    WorkspaceMembershipService,
)


# Reexporta a constante para uso interno do módulo, evitando que
# outros pontos do projeto a dupliquem. A FONTE continua sendo
# `WorkspaceMembershipService.PROPRIETARIO_KEY`.
OWNER_KEY = WorkspaceMembershipService.PROPRIETARIO_KEY


# =========================================================================
# API PÚBLICA — AUTORIZAÇÃO POR CAPABILITY
# =========================================================================

def user_has_capability(workspace, user, code: str) -> bool:
    """
    Verifica se o usuário tem a capability `code` no workspace.

    Regras (nesta ordem):
        1. Usuário anônimo ou None      → False
        2. Sem membership               → False
        3. Governance == proprietario   → True (tem todas)
        4. ConsoleGovernanceCapability com is_active=True → True / False

    Nunca levanta. Único ponto do módulo que consulta
    `ConsoleGovernanceCapability`.

    Contrato público: apps externos podem depender desta função.
    """
    if not user or not user.is_authenticated:
        return False

    membership = (
        WorkspaceMembership.objects
        .filter(workspace=workspace, user=user)
        .select_related('governance')
        .first()
    )
    if membership is None:
        return False

    if membership.governance.key == OWNER_KEY:
        return True

    # Import local — único ponto do módulo que toca o Console.
    # Mantido aqui para deixar explícito que esta é a fronteira.
    from apps.console.models import ConsoleGovernanceCapability

    return ConsoleGovernanceCapability.objects.filter(
        governance=membership.governance,
        capability__code=code,
        capability__is_active=True,
    ).exists()


# =========================================================================
# HELPERS INTERNOS
# =========================================================================

def _extract_workspace(obj):
    """Extrai o Workspace de um objeto do domínio."""
    if isinstance(obj, Workspace):
        return obj
    if isinstance(obj, WorkspaceMembership):
        return obj.workspace
    return getattr(obj, 'workspace', None)


# =========================================================================
# PERMISSIONS
# =========================================================================

class IsWorkspaceMember(BasePermission):
    """Requer que o usuário seja membro do Workspace."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = _extract_workspace(obj)
        if workspace is None:
            return False
        return WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
        ).exists()


class IsWorkspaceOwner(BasePermission):
    """
    Requer que o usuário seja proprietário do Workspace.

    "proprietario" é a invariante estrutural do tenant. É a única
    exceção documentada ao princípio "o Workspace não conhece
    governanças pelo nome".
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = _extract_workspace(obj)
        if workspace is None:
            return False
        return WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
            governance__key=OWNER_KEY,
        ).exists()


class RequireCapability(BasePermission):
    """
    Autorização baseada em capability do Console.

    Uso:
        class MinhaView(APIView):
            permission_classes = [IsAuthenticated, RequireCapability]
            required_capability = 'workspaces.member.invite'

    Delega toda a verificação para `user_has_capability`. Não
    duplica regra alguma.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        capability_code = getattr(view, 'required_capability', None)
        if not capability_code:
            # Se a view não declarou capability, deixa passar —
            # contrato preservado do arquivo original.
            return True

        workspace = _extract_workspace(obj)
        if workspace is None:
            return False

        return user_has_capability(workspace, request.user, capability_code)