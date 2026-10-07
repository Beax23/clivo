"""
WorkspaceService — criação, gestão e exclusão de Workspace.

REGRA DE CRIAÇÃO (V1):
    O frontend NÃO escolhe:
        - governance_id
        - plan_id

    O backend determina:
        - Plan is_default=True (do Console)
        - Governance "proprietario" scope='workspace' (do Console)
        - Membership do criador como proprietário

    Tudo dentro de @transaction.atomic.
"""

import re
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceSubscription,
)
from apps.workspaces.exceptions import (
    WorkspaceNotFoundError,
    DefaultPlanNotFoundError,
    DefaultPlanAmbiguousError,
    ProprietarioGovernanceNotFoundError,
    WorkspaceUserNotActiveError,
    SlugGenerationError,
)


# Número máximo de tentativas de geração de slug antes de desistir.
# A constraint unique + tratamento de IntegrityError cuidam do caso
# real; este limite é só uma trava defensiva.
_MAX_SLUG_ATTEMPTS = 50


class WorkspaceService:

    # ==================================================================
    # CRIAÇÃO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def create_workspace(
        name: str,
        created_by,
        cnpj: str = '',
        city: str = '',
        state: str = '',
    ) -> Workspace:
        """
        Cria um Workspace completo.

        Passos:
            1. Valida usuário criador
            2. Gera slug único
            3. Resolve o Plan is_default=True (único) do Console
            4. Resolve a Governance 'proprietario' scope='workspace'
            5. Cria Workspace
            6. Cria WorkspaceSubscription
            7. Cria WorkspaceMembership do criador como proprietário

        Se qualquer passo falhar, nada é persistido.
        """
        from apps.console.models import Plan, ConsoleGovernance

        # 1. Validações básicas
        name = (name or '').strip()
        if not name:
            raise ValueError('O nome do Workspace é obrigatório')

        if not created_by or not created_by.is_active:
            raise WorkspaceUserNotActiveError(
                'O usuário criador do Workspace precisa estar ativo'
            )

        # 2. Slug
        slug = WorkspaceService._generate_unique_slug(name)

        # 3. Plan default — resolução estrita
        plan_qs = Plan.objects.filter(is_default=True, is_active=True)
        count = plan_qs.count()
        if count == 0:
            raise DefaultPlanNotFoundError(
                'Nenhum plano inicial (is_default=True) ativo encontrado. '
                'Defina um plano inicial no Console antes de criar Workspaces.'
            )
        if count > 1:
            raise DefaultPlanAmbiguousError(
                'Existe mais de um plano marcado como inicial. '
                'Isso é uma inconsistência de configuração do Console.'
            )
        default_plan = plan_qs.first()

        # 4. Governance proprietario
        try:
            proprietario_gov = ConsoleGovernance.objects.get(
                key='proprietario',
                scope='workspace',
            )
        except ConsoleGovernance.DoesNotExist:
            raise ProprietarioGovernanceNotFoundError(
                'A governança "proprietario" com scope="workspace" '
                'não foi encontrada. Rode `python manage.py seed_console`.'
            )

        # 5. Workspace
        workspace = Workspace.objects.create(
            name=name,
            slug=slug,
            cnpj=(cnpj or '').strip(),
            city=(city or '').strip(),
            state=(state or '').strip().upper(),
            is_active=True,
        )

        # 6. Subscription
        WorkspaceSubscription.objects.create(
            workspace=workspace,
            plan=default_plan,
            is_active=True,
            started_at=timezone.now(),
        )

        # 7. Membership do criador
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=created_by,
            governance=proprietario_gov,
        )

        return workspace

    # ==================================================================
    # EXCLUSÃO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def delete_workspace(workspace: Workspace) -> None:
        """
        Exclui o Workspace e todos os dados associados.

        V1: delete real. Sem soft delete.
        V2 (futuro): pode-se adicionar arquivamento quando outros
        domínios passarem a referenciar o Workspace.
        """
        workspace.delete()

    # ==================================================================
    # SLUG
    # ==================================================================

    @staticmethod
    def _generate_unique_slug(name: str) -> str:
        """
        Gera um slug único a partir do nome.

        Estratégia:
            1. Slugifica e limpa
            2. Tenta o slug base
            3. Se ocupado, tenta base-2, base-3, ...
            4. Se esgotar tentativas, levanta SlugGenerationError

        A constraint unique + IntegrityError no create() cobre
        race condition real. Este loop só evita a colisão óbvia.
        """
        base = slugify(name)
        base = re.sub(r'[^a-z0-9-]', '', base).strip('-') or 'workspace'

        # Tenta o slug base primeiro
        if not Workspace.objects.filter(slug=base).exists():
            return base

        # Tenta sufixos incrementais
        for counter in range(2, _MAX_SLUG_ATTEMPTS + 1):
            candidate = f"{base}-{counter}"
            if not Workspace.objects.filter(slug=candidate).exists():
                return candidate

        raise SlugGenerationError(
            f'Não foi possível gerar um slug único para "{name}" '
            f'após {_MAX_SLUG_ATTEMPTS} tentativas.'
        )

    # ==================================================================
    # CONSULTAS
    # ==================================================================

    @staticmethod
    def get_by_id(workspace_id) -> Optional[Workspace]:
        try:
            return Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return None

    @staticmethod
    def get_or_raise(workspace_id) -> Workspace:
        workspace = WorkspaceService.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(
                f'Workspace com id "{workspace_id}" não encontrado'
            )
        return workspace

    @staticmethod
    def list_for_user(user) -> list:
        """Lista Workspaces em que o usuário é membro."""
        return list(
            Workspace.objects.filter(
                memberships__user=user,
                is_active=True,
            ).distinct().order_by('name')
        )

    @staticmethod
    def user_has_access(user, workspace: Workspace) -> bool:
        """Verifica se o usuário é membro do Workspace."""
        return WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=user,
        ).exists()