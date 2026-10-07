"""
Permissões do módulo clients.

SEPARAÇÃO:
    1. TENANT ISOLATION — recurso pertence ao Workspace do usuário
    2. AUTHORIZATION    — Governance possui a capability necessária

Nunca fazer Client.objects.get(id=...) e considerar isso autorização.
"""

from rest_framework.permissions import BasePermission

from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability


def _workspace_of(obj):
    """Extrai o Workspace de um objeto do domínio clients."""
    from apps.clients.models import Client

    if obj is None:
        return None
    if hasattr(obj, 'workspace'):
        return obj.workspace
    if hasattr(obj, 'client'):
        return getattr(obj.client, 'workspace', None)
    if isinstance(obj, Client):
        return obj.workspace
    return None


class IsClientWorkspaceMember(BasePermission):
    """Garante apenas tenant isolation."""

    def has_object_permission(self, request, view, obj):
        workspace = _workspace_of(obj)
        if workspace is None:
            return False
        return WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
        ).exists()


class RequireClientCapability(BasePermission):
    """
    Combina tenant isolation + capability.

    Uso:
        class MinhaView(APIView):
            permission_classes = [IsAuthenticated, RequireClientCapability]
            required_capability = 'clients.client.update'
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        code = getattr(view, 'required_capability', None)
        if not code:
            return True

        workspace = _workspace_of(obj)
        if workspace is None:
            return False

        membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
        ).select_related('governance').first()

        if membership is None:
            return False

        if membership.governance.key == 'proprietario':
            return True

        return ConsoleGovernanceCapability.objects.filter(
            governance=membership.governance,
            capability__code=code,
            capability__is_active=True,
        ).exists()


class IsPortalSessionAuthenticated(BasePermission):
    """
    Autoriza requisições do Portal do Cliente.

    O cliente NÃO tem login de Workspace. Ele é autenticado pela
    ClientPortalSession (cookie/header setado após abrir o link do email).

    Esta permission verifica que `request.portal_session` existe e é
    válida. O middleware `ClientPortalMiddleware` a popula.
    """

    def has_permission(self, request, view):
        session = getattr(request, 'portal_session', None)
        if session is None:
            return False
        return session.is_valid()