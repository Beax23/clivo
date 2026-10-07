"""
Endpoint de resolução de entrada pós-login.

Responde uma única pergunta:
    "Para onde este usuário autenticado deve ir agora?"

Regras (V1):
    ConsoleMembershipService.has_access(user)  → console
    user.is_superuser                          → console  (bootstrap)
    senão                                      → workspace

Este endpoint é a FONTE DE VERDADE da decisão.
O login.js chama este endpoint após autenticar.
O PostLoginRedirectView (allauth/Google) usa o mesmo serviço.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
import logging

from apps.console.services.membership_service import ConsoleMembershipService

logger = logging.getLogger('accounts')


class EntryTargetView(APIView):
    """
    Informa para onde o usuário autenticado deve ser redirecionado.

    GET /api/auth/entry/

    Resposta:
        {"target": "console"}    → /console/
        {"target": "workspace"}  → /workspaces/entrar/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        target = resolve_entry_target(request.user)
        logger.debug(f"entry target para {request.user.email}: {target}")
        return Response({'target': target}, status=status.HTTP_200_OK)


# =============================================================================
# HELPER COMPARTILHADO
# =============================================================================

def resolve_entry_target(user) -> str:
    """
    Decide o destino de entrada do usuário.

    Retorna:
        "console"    → usuário é da Clivo (admin do Console)
        "workspace"  → usuário comum (fluxo de Workspace)
    """
    if not user or not user.is_authenticated:
        return 'workspace'

    # Fonte primária: ConsoleMembership
    try:
        if ConsoleMembershipService.has_access(user):
            return 'console'
    except Exception as e:
        logger.warning(f"Falha ao checar ConsoleMembership: {e}")

    # Fallback de bootstrap enquanto ConsoleMembership não cobre todos
    if user.is_superuser:
        return 'console'

    return 'workspace'