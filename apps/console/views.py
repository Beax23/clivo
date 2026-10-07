"""
View do Console.

Autorização:
    ConsoleMembership concede acesso administrativo integral.
    Não usar is_superuser como regra de negócio.
"""

from django.shortcuts import render, redirect
from django.views import View
import logging

from apps.console.services.membership_service import ConsoleMembershipService

logger = logging.getLogger('console')


class ConsoleView(View):
    """View para a página do Console."""

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        service = ConsoleMembershipService()
        if not service.has_access(request.user):
            logger.debug(
                f"⛔ Usuário {request.user.email} sem ConsoleMembership "
                f"tentou acessar /console/ — redirecionando para /mesa/"
            )
            return redirect('/mesa/')

        return render(request, 'console.html')