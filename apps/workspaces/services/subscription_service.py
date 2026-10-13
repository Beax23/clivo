"""
WorkspaceSubscriptionService — consulta e alteração de plano.

V1:
    - A subscription é criada junto com o Workspace.
    - Troca de plano via `change_plan()` é o único ponto de mutação.
    - Sem billing.

REGRA ARQUITETURAL (após o Commit A):
    Um Workspace pode ter VÁRIAS `WorkspaceSubscription` ao longo
    do tempo (histórico de trocas de plano). Apenas UMA pode estar
    ativa, garantido pela constraint condicional
    `unique_active_subscription_per_workspace`.

    Portanto, qualquer método que busque "a assinatura do workspace"
    DEVE filtrar por `is_active=True`. Buscar sem filtro pode retornar
    uma assinatura histórica (inativa) ou levantar
    `MultipleObjectsReturned`.

REGRA DE TROCA DE PLANO (`change_plan`):
    - Encerra a assinatura ativa (is_active=False, ended_at=now).
    - Cria uma nova assinatura ativa para o plano destino.
    - Preenche `changed_from`, `changed_by` e `reason` para auditoria.
    - Bloqueia troca para o mesmo plano (H1).
    - Bloqueia troca para plano inativo (H2).
    - Se não houver assinatura ativa, cria nova sem encerrar nada (H3).

    Tudo dentro de `transaction.atomic` — a constraint
    `unique_active_subscription_per_workspace` garante que, se algo
    falhar, o banco não fica com duas ativas.
"""

from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.workspaces.models import (
    Workspace,
    WorkspaceSubscription,
)
from apps.workspaces.exceptions import (
    DefaultPlanNotFoundError,
    SubscriptionError,
)


# Motivos válidos para uma troca — espelham REASON_CHOICES do model.
VALID_REASONS = {
    'initial', 'upgrade', 'downgrade', 'manual', 'migration', 'other',
}


class WorkspaceSubscriptionService:

    # ==================================================================
    # CONSULTA
    # ==================================================================

    @staticmethod
    def get_subscription(workspace: Workspace) -> Optional[WorkspaceSubscription]:
        """
        Retorna a assinatura ATIVA do Workspace, ou None se não houver.

        NÃO retorna assinaturas históricas (inativas). Um Workspace
        pode ter N assinaturas inativas e 0 ou 1 ativa.
        """
        try:
            return (
                WorkspaceSubscription.objects
                .select_related('plan')
                .get(
                    workspace=workspace,
                    is_active=True,
                )
            )
        except WorkspaceSubscription.DoesNotExist:
            return None

    @staticmethod
    def get_active_plan(workspace: Workspace):
        """
        Retorna o Plan da assinatura ativa do Workspace, ou None.

        Conveniência sobre `get_subscription()` — evita o chamador
        ter que extrair o plano manualmente.
        """
        sub = WorkspaceSubscriptionService.get_subscription(workspace)
        if sub is None:
            return None
        return sub.plan

    # ==================================================================
    # TROCA DE PLANO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def change_plan(
        workspace: Workspace,
        new_plan,
        changed_by=None,
        reason: str = 'manual',
    ) -> WorkspaceSubscription:
        """
        Troca o plano do Workspace, preservando o histórico.

        Regras:
            H1 — Rejeita troca para o mesmo plano.
            H2 — Rejeita plano inativo.
            H3 — Se não houver assinatura ativa, cria uma nova.

        Args:
            workspace: o Workspace alvo.
            new_plan: instância de ConsolePlan (destino).
            changed_by: usuário que executou a troca (para auditoria).
            reason: motivo da troca — deve estar em VALID_REASONS.

        Returns:
            A nova `WorkspaceSubscription` ativa.

        Raises:
            SubscriptionError: para violações de H1, H2 ou reason inválido.
        """
        # Validação do motivo
        if reason not in VALID_REASONS:
            raise SubscriptionError(
                f'Motivo inválido: "{reason}". '
                f'Válidos: {", ".join(sorted(VALID_REASONS))}.'
            )

        # Validação do plano de destino
        if new_plan is None:
            raise SubscriptionError('O plano de destino é obrigatório.')

        if not new_plan.is_active:
            raise SubscriptionError(
                f'O plano "{new_plan.name}" está inativo e não pode ser '
                f'atribuído a um Workspace.'
            )

        # Assinatura ativa atual (se houver)
        current = WorkspaceSubscriptionService.get_subscription(workspace)

        # H1 — trocar para o mesmo plano não faz sentido
        if current is not None and current.plan_id == new_plan.id:
            raise SubscriptionError(
                f'O Workspace já está no plano "{new_plan.name}".'
            )

        now = timezone.now()

        # Encerra a assinatura ativa (se houver)
        if current is not None:
            current.is_active = False
            current.ended_at = now
            current.save(update_fields=['is_active', 'ended_at', 'updated_at'])

        # Cria a nova assinatura ativa
        new_sub = WorkspaceSubscription.objects.create(
            workspace=workspace,
            plan=new_plan,
            is_active=True,
            started_at=now,
            changed_by=changed_by if (changed_by and changed_by.is_authenticated) else None,
            changed_from=current,
            reason=reason,
        )

        return new_sub