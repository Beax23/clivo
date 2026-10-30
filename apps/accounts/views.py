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
    Raiz do site (https://clivoos.com/).

    Comportamento por estado do usuário:

        Anônimo      → renderiza a landing pública.
        Autenticado  → resolve o destino via resolve_entry_target()
                       (/console/ ou /workspaces/entrar/).

    A landing pública existe para atender ao Google OAuth
    Verification: a home precisa explicar a finalidade do app e
    por que ele pede acesso ao Drive/Forms.

    NUNCA redireciona para "/" — evita loop.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return render(request, 'landing.html')

        request.session.pop('_clivo_session_type', None)

        target = resolve_entry_target(request.user)

        if target == 'console':
            logger.debug(
                f"Pós-login (raiz): {request.user.email} → /console/"
            )
            return redirect('/console/')

        logger.debug(
            f"Pós-login (raiz): {request.user.email} → /workspaces/entrar/"
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


# =========================================================================
# PÁGINAS LEGAIS (exigidas pelo Google OAuth Verification)
# =========================================================================
#
# O Google exige que o app tenha URLs públicas com:
#   - Política de Privacidade (obrigatório)
#   - Termos de Uso (não obrigatório para OAuth, mas exigido pelo
#     próprio Clivo como contrato de uso do serviço)
#
# Ambas devem:
#   - retornar 200 sem exigir login;
#   - estar linkadas na home pública do site (a landing em /);
#   - não ter PDF — precisam ser páginas HTML acessíveis.
#
# Não há autenticação. Não há dados dinâmicos. Não há dependência
# de tenant. São páginas institucionais.


class PrivacyPolicyView(View):
    """
    Página pública de Política de Privacidade.

    Exigida pelo Google OAuth Verification quando o app usa
    escopos sensíveis (Drive, Forms). Precisa ser acessível sem
    login, retornar 200 e ter o link presente na home do site.

    Conteúdo cobre:
        - Quais dados do Google o Clivo acessa (Drive/Forms).
        - Como os dados são usados.
        - Como são armazenados e protegidos.
        - Como o usuário revoga o acesso.
    """

    def get(self, request):
        return render(request, 'legal/privacidade.html')


class TermsOfUseView(View):
    """
    Página pública de Termos de Uso.

    Não é exigida pelo Google, mas é o contrato de uso do Clivo.
    Está linkada na home pública (landing e login). Não exige
    autenticação.
    """

    def get(self, request):
        return render(request, 'legal/termos.html')