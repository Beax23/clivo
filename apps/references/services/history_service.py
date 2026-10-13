"""
ReferenceHistoryService — porta única de escrita no histórico.

REGRA ARQUITETURAL
------------------
Nenhum ponto do código escreve em `ReferenceHistory` diretamente.
Só este service escreve.

Isso garante:
    - formato consistente de `previous_value` / `new_value`
    - um único lugar para auditar "o que é registrado"
    - facilidade para adicionar novos eventos depois

ReferenceHistory é APPEND-ONLY.
Este service NÃO expõe update nem delete.
"""

from typing import Optional, Any

from apps.references.models import Reference, ReferenceHistory


class ReferenceHistoryService:

    # ------------------------------------------------------------------
    # ESCRITA (única porta)
    # ------------------------------------------------------------------

    @staticmethod
    def log(
        *,
        reference: Optional[Reference],
        action: str,
        user=None,
        previous_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
    ) -> ReferenceHistory:
        """
        Registra um evento no histórico.

        `reference` é opcional apenas para o caso de `deleted` — quando
        a referência está prestes a ser (ou já foi) excluída, o service
        ainda passa a instância para preservar a FK no momento da
        criação. Depois, o próprio Django aplica SET_NULL quando a
        Reference for apagada.

        Nunca chame este método fora dos services de referência.
        """
        return ReferenceHistory.objects.create(
            reference=reference,
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            action=action,
            previous_value=previous_value,
            new_value=new_value,
        )

    # ------------------------------------------------------------------
    # CONSULTAS
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_reference(reference: Reference):
        """
        Lista o histórico de uma referência viva, mais recente primeiro.

        Só funciona enquanto a referência existe. Depois da exclusão,
        o histórico permanece no banco (com `reference = NULL`), mas
        não é acessível por este método.
        """
        return (
            ReferenceHistory.objects
            .filter(reference=reference)
            .select_related('user')
            .order_by('-timestamp')
        )