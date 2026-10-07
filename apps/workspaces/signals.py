"""
Signals do módulo workspaces.

REGRA:
    Quando um usuário faz login (ou se cadastra), aceita automaticamente
    todos os convites pendentes para o email dele.
"""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
import logging

from apps.workspaces.services.invitation_service import WorkspaceInvitationService

logger = logging.getLogger('workspaces')


@receiver(user_logged_in)
def accept_pending_invitations(sender, request, user, **kwargs):
    """
    Após um login bem-sucedido, verifica se existem convites pendentes
    para o email do usuário e cria as memberships correspondentes.
    """
    try:
        memberships = WorkspaceInvitationService.accept_all_for_email(user)
        if memberships:
            logger.info(
                f"Convites aceitos para {user.email}: "
                f"{', '.join(m.workspace.name for m in memberships)}"
            )
            # Guarda na sessão o último workspace criado, para redirecionar
            if request is not None:
                request.session['current_workspace_id'] = str(memberships[-1].workspace_id)
    except Exception as e:
        # Nunca quebra o login por causa disso
        logger.exception(f"Falha ao aceitar convites para {user.email}: {e}")