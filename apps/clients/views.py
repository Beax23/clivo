"""
Views HTML do módulo clients.

Painel do arquiteto:
    /clientes/                          → ClientesView

Portal do cliente:
    /portal/                            → PortalLoginView
    /portal/home/                       → PortalHomeView (lista briefings)
    /portal/briefings/<uuid>/           → PortalChatView (chat de perguntas)

O portal do cliente NÃO usa login de Workspace. Ele autentica via
código público (`public_code`) do cliente.
"""

from django.shortcuts import render, redirect
from django.views import View


class ClientesView(View):
    """Página HTML de clientes do arquiteto."""

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')
        return render(request, 'cliente.html')


# =========================================================================
# PORTAL DO CLIENTE
# =========================================================================

class PortalLoginView(View):
    """
    Tela de login do cliente.

    O cliente digita o código (public_code, ex: CLI-X7K92P).
    O JS envia para POST /api/portal/login/ que valida e seta o cookie.
    """

    def get(self, request):
        session = getattr(request, 'portal_session', None)
        if session and session.is_valid():
            return redirect('/portal/home/')
        return render(request, 'portal/login.html')


class PortalHomeView(View):
    """
    Lista os briefings do cliente.

    A view só renderiza o HTML. O JS carrega via
    GET /api/portal/briefings/.
    """

    def get(self, request):
        session = getattr(request, 'portal_session', None)
        if not session or not session.is_valid():
            return redirect('/portal/')
        return render(request, 'portal/home.html')


class PortalChatView(View):
    """
    Chat de perguntas de um briefing.

    Renderiza o HTML. O JS carrega o briefing via
    GET /api/portal/briefings/<id>/ e envia respostas via
    POST /api/portal/briefings/<id>/questions/<qid>/answer/.
    """

    def get(self, request, briefing_id):
        session = getattr(request, 'portal_session', None)
        if not session or not session.is_valid():
            return redirect('/portal/')
        return render(request, 'portal/chat.html', {
            'briefing_id': str(briefing_id),
        })