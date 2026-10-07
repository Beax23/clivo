"""
Service de ConsoleMembership.

V1: ConsoleMembership concede acesso administrativo integral.
Não há níveis de administrador no Console.
"""

from typing import Optional, List

from apps.console.models import ConsoleMembership
from apps.console.exceptions.console_exceptions import (
    DuplicateMembershipError,
    UserNotActiveError,
)


class ConsoleMembershipService:
    """
    Serviço para gerenciamento de membros do Console.

    REGRA V1:
        Todo membro do Console é administrador integral.
    """

    @staticmethod
    def add_member(user, created_by) -> ConsoleMembership:
        """Adiciona um usuário ao Console."""
        if not user.is_active:
            raise UserNotActiveError(
                'Usuário inativo não pode ser adicionado ao Console'
            )

        if ConsoleMembership.objects.filter(user=user).exists():
            raise DuplicateMembershipError('Usuário já é membro do Console')

        membership = ConsoleMembership.objects.create(
            user=user,
            created_by=created_by,
        )
        return membership

    @staticmethod
    def remove_member(membership: ConsoleMembership) -> None:
        """Remove um membro do Console (DELETE real)."""
        membership.delete()

    @staticmethod
    def remove_member_by_user(user) -> bool:
        """Remove a membership de um usuário, se existir."""
        deleted, _ = ConsoleMembership.objects.filter(user=user).delete()
        return deleted > 0

    @staticmethod
    def get_membership(user) -> Optional[ConsoleMembership]:
        try:
            return ConsoleMembership.objects.get(user=user)
        except ConsoleMembership.DoesNotExist:
            return None

    @staticmethod
    def get_members() -> List[ConsoleMembership]:
        return list(
            ConsoleMembership.objects.select_related(
                'user', 'created_by'
            ).order_by('-created_at')
        )

    @staticmethod
    def has_access(user) -> bool:
        """Verifica se o usuário tem acesso ao Console."""
        if not user or not user.is_authenticated:
            return False
        return ConsoleMembership.objects.filter(user=user).exists()