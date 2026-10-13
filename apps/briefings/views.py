"""
Views HTML do módulo briefings.

    /fluxo/                                       → painel do arquiteto
    /w/<public_id>/briefings/<briefing_id>/       → detalhe autenticado

Ambas as páginas consomem a API do próprio módulo. O shell
(sidebar.html) resolve o resto no client-side.
"""

from django.shortcuts import redirect, render
from django.views import View

from apps.workspaces.helpers import resolve_workspace_or_redirect
from apps.workspaces.models import WorkspaceMembership
from apps.briefings.models import Briefing


class FluxoView(View):
    """Página de Fluxo (Briefings) — painel do arquiteto."""

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')
        return render(request, 'fluxo.html')


class BriefingDetailView(View):
    """
    Detalhe HTML autenticado de um briefing.

    Rota: /w/<public_id>/briefings/<briefing_id>/

    Resolve o workspace a partir do public_id + user. Depois
    valida que o briefing pertence a esse workspace. Só então
    renderiza.
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