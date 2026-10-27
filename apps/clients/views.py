from django.shortcuts import render, redirect
from django.views import View
from apps.workspaces.queries import WorkspaceQueries

class ClientesView(View):
    """Página HTML de clientes do arquiteto."""

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        # Resgata o workspace ativo da sessão
        workspace_id = request.session.get('current_workspace_id')
        workspace = WorkspaceQueries.get_for_user(workspace_id, request.user) if workspace_id else None
        
        # Descobre o ID público (mesma lógica usada em briefings/views.py)
        public_id = ''
        if workspace:
            public_id = str(
                getattr(workspace, 'public_id', '') 
                or getattr(workspace, 'slug', '') 
                or workspace.id
            )

        return render(request, 'cliente.html', {
            'workspace_public_id': public_id
        })


class PortalLoginView(View):
    """Tela de login do cliente."""
    def get(self, request):
        session = getattr(request, 'portal_session', None)
        if session and session.is_valid():
            return redirect('/portal/home/')
        return render(request, 'portal/login.html')


class PortalHomeView(View):
    """Lista os briefings do cliente."""
    def get(self, request):
        session = getattr(request, 'portal_session', None)
        if not session or not session.is_valid():
            return redirect('/portal/')
        return render(request, 'portal/home.html')


class PortalChatView(View):
    """Chat de perguntas de um briefing."""
    def get(self, request, briefing_id):
        session = getattr(request, 'portal_session', None)
        if not session or not session.is_valid():
            return redirect('/portal/')
        return render(request, 'portal/chat.html', {
            'briefing_id': str(briefing_id),
        })