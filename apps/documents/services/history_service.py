"""
DocumentHistoryService — porta única de escrita no histórico.

REGRA ARQUITETURAL
------------------
Nenhum ponto do código escreve em `DocumentHistory` diretamente.
Só este service escreve.

Isso garante:
    - formato consistente de `previous_value` / `new_value`
    - um único lugar para auditar "o que é registrado"
    - facilidade para adicionar novos eventos depois

DocumentHistory é APPEND-ONLY.
Este service NÃO expõe update nem delete.
"""

from typing import Optional, Any

from apps.documents.models import Document, DocumentHistory


class DocumentHistoryService:

    # ------------------------------------------------------------------
    # ESCRITA (única porta)
    # ------------------------------------------------------------------

    @staticmethod
    def log(
        *,
        document: Optional[Document],
        action: str,
        user=None,
        previous_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
    ) -> DocumentHistory:
        """
        Registra um evento no histórico.

        `document` é opcional apenas para o caso de `deleted` — quando
        o documento está prestes a ser (ou já foi) excluído, o service
        ainda passa a instância para preservar a FK no momento da
        criação. Depois, o próprio Django aplica SET_NULL quando o
        Document for apagado.

        Nunca chame este método fora dos services de documento.
        """
        return DocumentHistory.objects.create(
            document=document,
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            action=action,
            previous_value=previous_value,
            new_value=new_value,
        )

    # ------------------------------------------------------------------
    # CONSULTAS
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_document(document: Document):
        """
        Lista o histórico de um documento vivo, mais recente primeiro.

        Só funciona enquanto o documento existe. Depois da exclusão,
        o histórico permanece no banco (com `document = NULL`), mas
        não é acessível por este método.
        """
        return (
            DocumentHistory.objects
            .filter(document=document)
            .select_related('user')
            .order_by('-timestamp')
        )