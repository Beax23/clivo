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

    Este módulo expõe:
        IsWorkspaceMember   — qualquer membro
        IsWorkspaceOwner    — invariante estrutural (proprietário)
        RequireCapability   — autorização baseada em capability do Console
"""

from rest_framework.permissions import BasePermission

from apps.workspaces.models import Workspace, WorkspaceMembership


def _extract_workspace(obj):
    """Extrai o Workspace de um objeto do domínio."""
    if isinstance(obj, Workspace):
        return obj
    if isinstance(obj, WorkspaceMembership):
        return obj.workspace
    return getattr(obj, 'workspace', None)


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

    Este é o ÚNICO lugar em que o Workspace referencia uma Governance
    por nome. "proprietario" é uma invariante estrutural do tenant,
    não uma regra de autorização configurável.
    """

    OWNER_KEY = 'proprietario'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = _extract_workspace(obj)
        if workspace is None:
            return False
        return WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
            governance__key=self.OWNER_KEY,
        ).exists()


class RequireCapability(BasePermission):
    """
    Autorização baseada em capability do Console.

    Uso:
        class MinhaView(APIView):
            permission_classes = [IsAuthenticated, RequireCapability]
            required_capability = 'workspaces.member.invite'

    Este permission classe NÃO define capabilities aqui — apenas
    verifica se a governança da membership do usuário possui a
    capability requerida pela view.

    A cadeia é:
        user → WorkspaceMembership → ConsoleGovernance
             → ConsoleGovernanceCapability → ConsoleCapability
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        capability_code = getattr(view, 'required_capability', None)
        if not capability_code:
            # Se a view não declarou capability, deixa passar —
            # quem configurou a view é responsável por declarar.
            return True

        workspace = _extract_workspace(obj)
        if workspace is None:
            return False

        membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
        ).select_related('governance').first()

        if membership is None:
            return False

        # Consulta ConsoleGovernanceCapability → ConsoleCapability
        from apps.console.models import ConsoleGovernanceCapability
        return ConsoleGovernanceCapability.objects.filter(
            governance=membership.governance,
            capability__code=capability_code,
            capability__is_active=True,
        ).exists()