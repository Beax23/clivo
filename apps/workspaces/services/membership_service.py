"""
WorkspaceMembershipService — gestão de membros do Workspace.

REGRA V1:
    - A Governance atribuída precisa ter scope='workspace'.
    - O último proprietário do Workspace não pode ser removido
      nem rebaixado.
    - Rastreabilidade de "quem adicionou quem" é responsabilidade
      de Audit/Event (futuro), não desta camada.
"""

from typing import Optional, List

from django.utils import timezone

from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
)
from apps.workspaces.exceptions import (
    DuplicateMembershipError,
    UserNotActiveError,
    GovernanceNotFoundError,
    GovernanceScopeError,
    LastOwnerError,
)


class WorkspaceMembershipService:

    # Governance key que define o proprietário — invariante estrutural
    # do tenant. Não é regra de autorização geral.
    PROPRIETARIO_KEY = 'proprietario'

    # ==================================================================
    # ADIÇÃO
    # ==================================================================

    @staticmethod
    def add_member(
        workspace: Workspace,
        user,
        governance_key: str,
    ) -> WorkspaceMembership:
        """
        Adiciona um usuário ao Workspace com a Governance informada.

        A Governance precisa:
            - existir no Console
            - ter scope='workspace'
        """
        from apps.console.models import ConsoleGovernance

        if not user.is_active:
            raise UserNotActiveError(
                'Usuário inativo não pode ser adicionado ao Workspace'
            )

        if WorkspaceMembership.objects.filter(
            workspace=workspace, user=user
        ).exists():
            raise DuplicateMembershipError(
                'Usuário já é membro deste Workspace'
            )

        # Resolve a Governance validando o escopo
        try:
            governance = ConsoleGovernance.objects.get(
                key=governance_key,
                scope='workspace',
            )
        except ConsoleGovernance.DoesNotExist:
            # Distinguir "não existe" de "existe fora do escopo"
            if ConsoleGovernance.objects.filter(key=governance_key).exists():
                raise GovernanceScopeError(
                    f'A governança "{governance_key}" existe, mas não é '
                    f'do escopo "workspace". Apenas governanças de Workspace '
                    f'podem ser atribuídas a membros.'
                )
            raise GovernanceNotFoundError(
                f'Governança "{governance_key}" não encontrada no Console'
            )

        membership = WorkspaceMembership.objects.create(
            workspace=workspace,
            user=user,
            governance=governance,
            joined_at=timezone.now(),
        )
        return membership

    # ==================================================================
    # REMOÇÃO
    # ==================================================================

    @staticmethod
    def remove_member(membership: WorkspaceMembership) -> None:
        """
        Remove um membro do Workspace.

        Bloqueia a remoção se for o último proprietário.
        """
        workspace = membership.workspace

        if membership.governance.key == WorkspaceMembershipService.PROPRIETARIO_KEY:
            owners_count = WorkspaceMembership.objects.filter(
                workspace=workspace,
                governance__key=WorkspaceMembershipService.PROPRIETARIO_KEY,
            ).count()

            if owners_count <= 1:
                raise LastOwnerError(
                    'Não é possível remover o último proprietário do Workspace. '
                    'Promova outro membro a proprietário primeiro.'
                )

        membership.delete()

    # ==================================================================
    # TROCA DE GOVERNANÇA
    # ==================================================================

    @staticmethod
    def change_governance(
        membership: WorkspaceMembership,
        governance_key: str,
    ) -> WorkspaceMembership:
        """
        Troca a governança de um membro.

        Impede rebaixar o último proprietário.
        """
        from apps.console.models import ConsoleGovernance

        try:
            new_gov = ConsoleGovernance.objects.get(
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

        # Se estava como proprietário e vai sair de proprietário,
        # garantir que outro proprietário existe
        if (
            membership.governance.key == WorkspaceMembershipService.PROPRIETARIO_KEY
            and new_gov.key != WorkspaceMembershipService.PROPRIETARIO_KEY
        ):
            owners_count = WorkspaceMembership.objects.filter(
                workspace=membership.workspace,
                governance__key=WorkspaceMembershipService.PROPRIETARIO_KEY,
            ).count()

            if owners_count <= 1:
                raise LastOwnerError(
                    'Não é possível rebaixar o último proprietário. '
                    'Promova outro membro primeiro.'
                )

        membership.governance = new_gov
        membership.save(update_fields=['governance', 'updated_at'])
        return membership

    # ==================================================================
    # CONSULTAS
    # ==================================================================

    @staticmethod
    def get_membership(workspace: Workspace, user) -> Optional[WorkspaceMembership]:
        try:
            return WorkspaceMembership.objects.get(
                workspace=workspace,
                user=user,
            )
        except WorkspaceMembership.DoesNotExist:
            return None

    @staticmethod
    def list_members(workspace: Workspace) -> List[WorkspaceMembership]:
        return list(
            WorkspaceMembership.objects
            .filter(workspace=workspace)
            .select_related('user', 'governance')
            .order_by('-joined_at')
        )

    @staticmethod
    def touch_last_access(workspace: Workspace, user) -> None:
        """
        Atualiza `last_access_at` da membership do usuário.

        Deve ser chamado sempre que a aplicação resolve o contexto
        do Workspace atual para o usuário — por exemplo, na entrada
        da Mesa, ou em um middleware leve de resolução de Workspace.
        """
        WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=user,
        ).update(last_access_at=timezone.now())