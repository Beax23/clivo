from django.shortcuts import render, redirect
from django.views import View
import logging

from apps.accounts.api.entry import resolve_entry_target

logger = logging.getLogger('accounts')


class LoginView(View):
    """View para a página de login."""

    def get(self, request):
        return render(request, 'login.html')


class GoogleOAuthEntryView(View):
    """
    Ponto de entrada para autenticação com Google.

    Redireciona para o fluxo oficial do allauth.
    Esta view NÃO implementa OAuth manualmente.

    Query params:
        ?surface=app     → sessão do tipo App (Mesa)
        ?surface=console → sessão do tipo Console
    """

    def get(self, request):
        surface = request.GET.get('surface', 'app')

        if surface not in {'app', 'console'}:
            surface = 'app'

        request.session['_clivo_session_type'] = surface

        logger.debug(f"Iniciando OAuth Google com surface={surface}")

        return redirect('/accounts/google/login/')


class PostLoginRedirectView(View):
    """
    Roteador de pós-login.

    Usado pelo allauth (Google) após autenticação bem-sucedida.
    A decisão é a mesma do endpoint /api/auth/entry/ — ambos
    delegam para resolve_entry_target().

    Regra:
        ConsoleMember / superuser  → /console/
        Qualquer outro autenticado → /workspaces/entrar/
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        request.session.pop('_clivo_session_type', None)

        target = resolve_entry_target(request.user)

        if target == 'console':
            logger.debug(
                f"Pós-login (allauth): {request.user.email} → /console/"
            )
            return redirect('/console/')

        logger.debug(
            f"Pós-login (allauth): {request.user.email} → /workspaces/entrar/"
        )
        return redirect('/workspaces/entrar/')


class MesaView(View):
    """
    View para a página da Mesa (arquiteto).

    A Mesa em si ainda é um stub. Ela só exige autenticação.
    A resolução de Workspace ocorre em /workspaces/entrar/.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        return render(request, 'mesa.html')


class ConsoleView(View):
    """
    View para a página do Console (Admin da Clivo).

    V1: superuser OU ConsoleMembership.
    V2: migrar 100% para ConsoleMembership via IsConsoleAdmin.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        if resolve_entry_target(request.user) != 'console':
            logger.debug(
                f"Usuário {request.user.email} sem acesso ao Console — "
                f"redirecionando para /workspaces/entrar/"
            )
            return redirect('/workspaces/entrar/')

        return render(request, 'console.html')