"""
Views HTML do módulo briefings.

    /fluxo/                                         → painel do arquiteto (Mesa)
    /w/<public_id>/briefings/<briefing_id>/         → detalhe autenticado
    /portal/briefings/<briefing_id>/respostas/      → dados brutos (cliente)
    /w/<public_id>/briefings/<briefing_id>/resumo/  → dados brutos (arquiteto)

v22:
    - FluxoView passa `workspace_public_id` no contexto, para que o
      botão "Editar briefing" da Mesa consiga montar a URL correta.
"""

from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from apps.workspaces.helpers import resolve_workspace_or_redirect
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.queries import WorkspaceQueries
from apps.briefings.models import Briefing
from apps.briefings.api.serializers import PortalBriefingSerializer
from apps.briefings.queries import BriefingQueries


# =========================================================================
# HELPERS LOCAIS
# =========================================================================

def _resolve_current_workspace(request):
    """
    Retorna o Workspace ativo a partir de `request.session['current_workspace_id']`
    ou `None` se não houver sessão válida.

    Não redireciona. O chamador decide o que fazer.
    """
    workspace_id = request.session.get('current_workspace_id')
    if not workspace_id:
        return None
    return WorkspaceQueries.get_for_user(workspace_id, request.user)


def _workspace_public_id(workspace):
    """
    Resolve o identificador público do workspace usado nas URLs
    (`/w/<public_id>/...`).

    Tenta, nesta ordem:
        public_id → slug → id

    Isso permite funcionar mesmo se o modelo Workspace expuser o
    identificador sob outro nome.
    """
    if workspace is None:
        return ''
    return str(
        getattr(workspace, 'public_id', '')
        or getattr(workspace, 'slug', '')
        or workspace.id
    )


# =========================================================================
# MESA — PAINEL DO ARQUITETO
# =========================================================================

class FluxoView(View):
    """
    Renderiza a página da Mesa (painel principal do arquiteto).

    Contexto:
        workspace_public_id → identificador público do workspace ativo,
                              consumido por `mesa.js` para montar as URLs
                              de navegação ("Editar briefing" etc.).

    Se o usuário não estiver logado → redireciona para /login/.
    Se não houver workspace ativo na sessão → renderiza mesmo assim,
    com `workspace_public_id` vazio. O frontend exibe a lista vazia
    e evita ações que dependem do workspace.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace = _resolve_current_workspace(request)
        public_id = _workspace_public_id(workspace)

        return render(request, 'fluxo.html', {
            'workspace_public_id': public_id,
        })


# =========================================================================
# DETALHE AUTENTICADO DO BRIEFING (PÁGINA HTML)
# =========================================================================

class BriefingDetailView(View):
    """
    Página autenticada do briefing para o arquiteto.

    Resolve o workspace pelo `public_id` da URL e valida que o
    usuário é membro. Se o briefing não existir naquele workspace,
    volta para a Mesa.
    """

    def get(self, request, public_id, briefing_id):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace, error = resolve_workspace_or_redirect(request, public_id)
        if error is not None:
            return error

        is_member = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user,
        ).exists()
        if not is_member:
            return redirect('/workspaces/entrar/')

        briefing = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).first()
        if briefing is None:
            return redirect('/fluxo/')

        return render(request, 'briefing_detail.html', {
            'workspace': workspace,
            'briefing_id': str(briefing.id),
        })


# =========================================================================
# RESPOSTAS BRUTAS — VISÃO DO CLIENTE
# =========================================================================

class BriefingRawAnswersView(View):
    """
    Página HTML com as RESPOSTAS BRUTAS na visão do CLIENTE.

    - Perguntas + respostas do cliente
    - Imagens escolhidas / enviadas (moodboard pessoal)
    - Sem referências do arquiteto

    Depende do `ClientPortalMiddleware` para injetar
    `request.portal_client`. Sem sessão do portal → volta para /portal/.
    """

    def get(self, request, briefing_id=None):
        client = getattr(request, 'portal_client', None)
        if client is None:
            return redirect('/portal/')

        briefing = BriefingQueries.get_for_client(client, briefing_id)
        if briefing is None:
            raise Http404('Briefing não encontrado.')

        briefing.mark_expired_if_needed()

        payload = PortalBriefingSerializer(
            context={'request': request},
        ).to_representation(briefing)

        return render(
            request,
            'portal/briefing_raw_client.html',
            {'briefing': payload},
        )


# =========================================================================
# RESPOSTAS BRUTAS — VISÃO DO ARQUITETO
# =========================================================================

class BriefingArchitectRawView(View):
    """
    Página HTML com as RESPOSTAS BRUTAS na visão do ARQUITETO.

    - Perguntas + respostas (incluindo transcrições)
    - Referências do arquiteto
    - Imagens escolhidas / enviadas pelo cliente (moodboard)
    - Filtros por sessão e busca
    - Exportar PDF (mode='architect')
    """

    def get(self, request, public_id, briefing_id):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace, error = resolve_workspace_or_redirect(request, public_id)
        if error is not None:
            return error

        is_member = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user,
        ).exists()
        if not is_member:
            return redirect('/workspaces/entrar/')

        briefing = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).select_related('client', 'workspace', 'template').first()
        if briefing is None:
            return redirect('/fluxo/')

        payload = PortalBriefingSerializer(
            context={'request': request},
        ).to_representation(briefing)

        return render(
            request,
            'portal/briefing_raw_architect.html',
            {'briefing': payload},
        )