"""
Views HTML do módulo Workspace.

FLUXO DE URL:
    /mesa/<public_id>/
        │
        ├── decode public_id → UUID
        ├── valida membership do request.user nesse workspace
        ├── grava request.session['current_workspace_id']
        └── renderiza mesa.html

    /mesa/ (sem public_id)
        └── redireciona para /workspaces/entrar/
"""

from django.shortcuts import redirect, render
from django.views import View
import logging

from apps.workspaces.public_id import (
    encode_workspace_id,
    decode_workspace_id,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.services import (
    WorkspaceService,
    WorkspaceMembershipService,
    WorkspaceInvitationService,
)

logger = logging.getLogger('workspaces')


def _is_clivo_admin(user) -> bool:
    try:
        from apps.accounts.api.entry import resolve_entry_target
        return resolve_entry_target(user) == 'console'
    except Exception as e:
        logger.warning(f"Falha ao resolver entry target: {e}")
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_superuser)


class WorkspaceEntryView(View):
    """
    Ponto de entrada do usuário.

    Resolve qual workspace abrir e redireciona para /mesa/<public_id>/.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if _is_clivo_admin(request.user):
            return redirect('/console/')

        workspaces = WorkspaceService.list_for_user(request.user)
        if not workspaces:
            return redirect('/workspaces/novo/')

        workspace = WorkspaceQueries.get_last_accessed_for_user(request.user)
        if workspace is None:
            workspace = workspaces[0]

        WorkspaceMembershipService.touch_last_access(workspace, request.user)
        request.session['current_workspace_id'] = str(workspace.id)

        public_id = encode_workspace_id(workspace.id)
        return redirect(f'/mesa/{public_id}/')


class WorkspaceCreateView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if _is_clivo_admin(request.user):
            return redirect('/console/')

        if WorkspaceService.list_for_user(request.user):
            return redirect('/workspaces/entrar/')

        return render(request, 'workspace.html')


class InvitationEntryView(View):
    """Ponto de entrada do convite."""

    def get(self, request, token):
        invitation = WorkspaceInvitationService.get_by_token(token)

        if invitation is None:
            logger.warning(f"Convite não encontrado: token={token}")
            return render(request, 'convite_invalido.html', status=404)

        if request.user.is_authenticated:
            try:
                WorkspaceInvitationService.accept_all_for_email(request.user)
            except Exception as e:
                logger.exception(f"Falha ao aceitar convite: {e}")
            return redirect('/workspaces/entrar/')

        login_url = f"/login/?next=/convite/{token}/"
        return redirect(login_url)


class MesaView(View):
    """
    Renderiza a Mesa para um workspace específico.

    Recebe `<public_id>` no path, resolve para o UUID real, valida
    membership e grava na sessão. Se o token for inválido ou o usuário
    não for membro, redireciona para /workspaces/entrar/.
    """

    def get(self, request, public_id):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if _is_clivo_admin(request.user):
            return redirect('/console/')

        workspace_id = decode_workspace_id(public_id)
        if workspace_id is None:
            logger.warning(f"public_id inválido: {public_id}")
            return redirect('/workspaces/entrar/')

        # Resolução multi-tenant: (workspace_id, user)
        workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
        if workspace is None:
            logger.warning(
                f"Usuário {request.user.email} sem acesso ao workspace "
                f"{workspace_id} (via public_id={public_id})"
            )
            return redirect('/workspaces/entrar/')

        # Fixa o workspace como "atual"
        request.session['current_workspace_id'] = str(workspace.id)
        WorkspaceMembershipService.touch_last_access(workspace, request.user)

        return render(request, 'mesa.html')


class MesaRedirectView(View):
    """
    Atalho: /mesa/ sem public_id.
    Redireciona para o último workspace acessado.
    """

    def get(self, request):
        return redirect('/workspaces/entrar/')