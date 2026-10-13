"""
Views HTML do módulo Workspace.

FLUXO DE URL:
    /w/<public_id>/mesa/
        │
        ├── decode public_id → UUID
        ├── valida membership do request.user nesse workspace
        ├── grava request.session['current_workspace_id']
        └── renderiza mesa.html

    /mesa/<public_id>/       (rota antiga, redireciona no Commit 5)
        └── comportamento atual preservado

    /mesa/
        └── redireciona para /workspaces/entrar/

    /configuracoes/
        │
        ├── resolve workspace atual da sessão (ou último acessado)
        ├── grava request.session['current_workspace_id']
        └── renderiza configuracoes.html
"""

from django.shortcuts import redirect, render
from django.views import View
import logging

from apps.workspaces.helpers import resolve_workspace_or_redirect
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
    Renderiza a Mesa.

    Aceita `public_id` opcional (rota nova `/w/<public_id>/mesa/`)
    ou nenhum `public_id` (rota antiga `/mesa/<public_id>/`, mantida
    durante a migração).

    Quando há `public_id`, resolve via helper `resolve_workspace_or_redirect`
    (URL vence a sessão). Quando não há, mantém o comportamento antigo
    (rota antiga com `<public_id>` no path ainda é registrada em
    `urls.py`, e a rota `/mesa/` sem public_id é redirecionada).
    """

    def get(self, request, public_id=None):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if _is_clivo_admin(request.user):
            return redirect('/console/')

        # -----------------------------------------------------------
        # Caminho 1: rota nova, com public_id na URL.
        # A URL vence. Sessão é sincronizada.
        # -----------------------------------------------------------
        if public_id is not None:
            workspace, error = resolve_workspace_or_redirect(request, public_id)
            if error is not None:
                return error
            return render(request, 'mesa.html')

        # -----------------------------------------------------------
        # Caminho 2: rota antiga `/mesa/<public_id>/`.
        # Chega aqui via `path('mesa/<str:public_id>/', ...)`, e o
        # Django entrega o public_id via kwargs, que NÃO é o `public_id`
        # desta assinatura — por isso o caminho antigo é tratado em
        # uma view separada (`LegacyMesaView`). Esta view só recebe
        # `public_id=None` quando a rota é literalmente `/mesa/`, sem
        # segmento extra.
        # -----------------------------------------------------------
        return redirect('/workspaces/entrar/')


class LegacyMesaView(View):
    """
    Rota antiga `/mesa/<public_id>/`.

    Durante a migração, aceita o formato antigo (public_id no path
    depois de `/mesa/`) e renderiza a Mesa normalmente. No Commit 5,
    passa a redirecionar para `/w/<public_id>/mesa/`.
    """

    def get(self, request, public_id):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if _is_clivo_admin(request.user):
            return redirect('/console/')

        workspace_id = decode_workspace_id(public_id)
        if workspace_id is None:
            logger.warning(f"public_id inválido (legacy): {public_id}")
            return redirect('/workspaces/entrar/')

        workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
        if workspace is None:
            logger.warning(
                f"Usuário {request.user.email} sem acesso ao workspace "
                f"{workspace_id} (via public_id={public_id})"
            )
            return redirect('/workspaces/entrar/')

        request.session['current_workspace_id'] = str(workspace.id)
        WorkspaceMembershipService.touch_last_access(workspace, request.user)

        return render(request, 'mesa.html')


class MesaRedirectView(View):
    """
    Atalho: /mesa/ sem public_id.
    Redireciona para /workspaces/entrar/.
    """

    def get(self, request):
        return redirect('/workspaces/entrar/')


class ConfiguracoesView(View):
    """
    Página de configurações do workspace atual.

    NÃO muda neste commit. Mantém o comportamento atual: resolve o
    workspace ativo via sessão (com fallback para o último acessado),
    grava na sessão e renderiza configuracoes.html.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if _is_clivo_admin(request.user):
            return redirect('/console/')

        workspace_id = request.session.get('current_workspace_id')
        workspace = None
        if workspace_id:
            workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)

        if workspace is None:
            workspace = WorkspaceQueries.get_last_accessed_for_user(request.user)

        if workspace is None:
            return redirect('/workspaces/entrar/')

        request.session['current_workspace_id'] = str(workspace.id)
        WorkspaceMembershipService.touch_last_access(workspace, request.user)

        return render(request, 'configuracoes.html')