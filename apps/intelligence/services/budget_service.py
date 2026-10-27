"""
BudgetService — delega a verificação de orçamento ao Console via
contrato público. Não importa `QuotaService` diretamente.
"""

import logging
from apps.intelligence.exceptions import BudgetExceededError

logger = logging.getLogger('intelligence')


class BudgetService:

    @staticmethod
    def check_if_execution_is_allowed(workspace) -> bool:
        from apps.console import public as console_public
        allowed, reason = console_public.is_ai_execution_allowed(workspace)
        if not allowed:
            logger.warning(
                'Execução bloqueada para workspace=%s (motivo=%s)',
                workspace.id, reason,
            )
            raise BudgetExceededError(
                f'Limite de uso de IA excedido (motivo: {reason}).'
            )
        return True