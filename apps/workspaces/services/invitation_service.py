"""
WorkspaceInvitationService — cria, reenvia, cancela e aceita convites.

REGRA:
    - Convite não cria membership. Fica `pending` até alguém se
      cadastrar com o email convidado.
    - Quando um usuário se cadastra com email que tem convite pendente,
      o signal `user_logged_in` chama `accept_all_for_email()`.
"""

from typing import Optional, List
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceInvitation,
)
from apps.workspaces.exceptions import (
    DuplicateMembershipError,
    GovernanceNotFoundError,
    GovernanceScopeError,
    WorkspaceInvitationError,
    InvitationResendLimitError,
)


class WorkspaceInvitationService:

    # ==================================================================
    # CRIAR
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def create_invitation(
        workspace: Workspace,
        email: str,
        governance_key: str,
        invited_by,
        send_email: bool = True,
    ) -> WorkspaceInvitation:
        from apps.console.models import ConsoleGovernance
        from django.contrib.auth import get_user_model

        User = get_user_model()
        email = User.normalize_email(email)

        if not email:
            raise WorkspaceInvitationError('Informe o email do convidado')

        # Já é membro?
        existing_member = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user__email__iexact=email,
        ).exists()
        if existing_member:
            raise DuplicateMembershipError(
                'Este email já é membro do workspace'
            )

        # Governance válida?
        try:
            governance = ConsoleGovernance.objects.get(
                key=governance_key,
                scope='workspace',
            )
        except ConsoleGovernance.DoesNotExist:
            if ConsoleGovernance.objects.filter(key=governance_key).exists():
                raise GovernanceScopeError(
                    f'A governança "{governance_key}" não é do escopo workspace'
                )
            raise GovernanceNotFoundError(
                f'Governança "{governance_key}" não encontrada'
            )

        # Convite pendente já existe?
        existing = WorkspaceInvitation.objects.filter(
            workspace=workspace,
            email__iexact=email,
            status=WorkspaceInvitation.STATUS_PENDING,
        ).first()

        if existing:
            if existing.governance_id != governance.id:
                existing.governance = governance
                existing.save(update_fields=['governance', 'updated_at'])
            if send_email:
                WorkspaceInvitationService._send(existing)
            return existing

        invitation = WorkspaceInvitation.objects.create(
            workspace=workspace,
            email=email,
            governance=governance,
            invited_by=invited_by,
            expires_at=timezone.now() + timedelta(
                days=WorkspaceInvitation.DEFAULT_TTL_DAYS
            ),
        )

        if send_email:
            WorkspaceInvitationService._send(invitation)

        return invitation

    # ==================================================================
    # REENVIAR
    # ==================================================================

    @staticmethod
    def resend_invitation(invitation: WorkspaceInvitation) -> WorkspaceInvitation:
        if invitation.status != WorkspaceInvitation.STATUS_PENDING:
            raise WorkspaceInvitationError(
                'Só é possível reenviar convites pendentes'
            )

        if not invitation.can_resend():
            raise InvitationResendLimitError(
                f'Limite de {WorkspaceInvitation.MAX_RESENDS} reenvios atingido. '
                f'Cancele o convite e crie um novo.'
            )

        invitation.expires_at = timezone.now() + timedelta(
            days=WorkspaceInvitation.DEFAULT_TTL_DAYS
        )
        invitation.save(update_fields=['expires_at', 'updated_at'])

        WorkspaceInvitationService._send(invitation)
        return invitation

    # ==================================================================
    # CANCELAR
    # ==================================================================

    @staticmethod
    def cancel_invitation(invitation: WorkspaceInvitation) -> None:
        if invitation.status != WorkspaceInvitation.STATUS_PENDING:
            raise WorkspaceInvitationError(
                'Só é possível cancelar convites pendentes'
            )
        invitation.status = WorkspaceInvitation.STATUS_CANCELLED
        invitation.save(update_fields=['status', 'updated_at'])

    # ==================================================================
    # ALTERAR GOVERNANÇA
    # ==================================================================

    @staticmethod
    def change_governance(
        invitation: WorkspaceInvitation,
        governance_key: str,
    ) -> WorkspaceInvitation:
        from apps.console.models import ConsoleGovernance

        if invitation.status != WorkspaceInvitation.STATUS_PENDING:
            raise WorkspaceInvitationError(
                'Só é possível alterar convites pendentes'
            )

        try:
            governance = ConsoleGovernance.objects.get(
                key=governance_key,
                scope='workspace',
            )
        except ConsoleGovernance.DoesNotExist:
            if ConsoleGovernance.objects.filter(key=governance_key).exists():
                raise GovernanceScopeError(
                    f'A governança "{governance_key}" não é do escopo workspace'
                )
            raise GovernanceNotFoundError(
                f'Governança "{governance_key}" não encontrada'
            )

        invitation.governance = governance
        invitation.save(update_fields=['governance', 'updated_at'])
        return invitation

    # ==================================================================
    # ACEITE AUTOMÁTICO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def accept_all_for_email(user) -> List[WorkspaceMembership]:
        email = user.email
        if not email:
            return []

        invitations = WorkspaceInvitation.objects.filter(
            email__iexact=email,
            status=WorkspaceInvitation.STATUS_PENDING,
        ).select_related('workspace', 'governance')

        created = []
        for inv in invitations:
            if inv.mark_expired_if_needed():
                continue

            if WorkspaceMembership.objects.filter(
                workspace=inv.workspace, user=user
            ).exists():
                inv.status = WorkspaceInvitation.STATUS_ACCEPTED
                inv.accepted_at = timezone.now()
                inv.save(update_fields=['status', 'accepted_at', 'updated_at'])
                continue

            membership = WorkspaceMembership.objects.create(
                workspace=inv.workspace,
                user=user,
                governance=inv.governance,
            )

            inv.status = WorkspaceInvitation.STATUS_ACCEPTED
            inv.accepted_at = timezone.now()
            inv.save(update_fields=['status', 'accepted_at', 'updated_at'])

            created.append(membership)

        return created

    # ==================================================================
    # CONSULTAS
    # ==================================================================

    @staticmethod
    def list_pending_for_workspace(workspace: Workspace) -> List[WorkspaceInvitation]:
        """
        Lista convites pendentes do workspace.

        Não marca expirados — apenas filtra por status='pending'.
        O serializer expõe `is_expired` para o frontend sinalizar.
        """
        return list(
            WorkspaceInvitation.objects
            .filter(
                workspace=workspace,
                status=WorkspaceInvitation.STATUS_PENDING,
            )
            .select_related('governance', 'invited_by')
            .order_by('-created_at')
        )

    @staticmethod
    def get_by_id(invitation_id) -> Optional[WorkspaceInvitation]:
        try:
            return WorkspaceInvitation.objects.select_related(
                'workspace', 'governance', 'invited_by'
            ).get(id=invitation_id)
        except (WorkspaceInvitation.DoesNotExist, ValueError):
            return None

    @staticmethod
    def get_by_token(token: str) -> Optional[WorkspaceInvitation]:
        try:
            return WorkspaceInvitation.objects.select_related(
                'workspace', 'governance'
            ).get(token=token)
        except WorkspaceInvitation.DoesNotExist:
            return None

    # ==================================================================
    # EMAIL
    # ==================================================================

    @staticmethod
    def _send(invitation: WorkspaceInvitation) -> None:
        from apps.accounts.services.email import EmailService
        from django.conf import settings

        base_url = settings.FRONTEND_URL.rstrip('/')
        invite_url = f"{base_url}/convite/{invitation.token}/"

        EmailService.send_workspace_invitation(
            invitation=invitation,
            invite_url=invite_url,
        )

        invitation.last_sent_at = timezone.now()
        invitation.send_count += 1
        invitation.save(update_fields=['last_sent_at', 'send_count', 'updated_at'])