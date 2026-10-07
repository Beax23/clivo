"""
Queries otimizadas para Document.

REGRA MULTI-TENANT:
    Toda consulta nasce SEMPRE da combinação (workspace, ...).
    Nunca de "document depois checar workspace".
"""

from apps.documents.models import Document


class DocumentQueries:

    # ------------------------------------------------------------------
    # LISTAGEM
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_workspace(workspace):
        """
        Lista TODOS os documentos do workspace, sem filtro.

        Ordenação: mais recentes primeiro.
        """
        return (
            Document.objects
            .filter(workspace=workspace)
            .select_related('client', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    @staticmethod
    def list_for_client(workspace, client):
        """
        Lista documentos associados a um cliente específico
        dentro de um workspace.
        """
        return (
            Document.objects
            .filter(workspace=workspace, client=client)
            .select_related('client', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    @staticmethod
    def list_for_project(workspace, project_id):
        """
        Lista documentos associados a um projeto específico
        dentro de um workspace.

        `project_id` é o UUID solto (até `projects` existir).
        """
        return (
            Document.objects
            .filter(workspace=workspace, project_id=project_id)
            .select_related('client', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_id_in_workspace(document_id, workspace):
        """
        Resolve um Document por id DENTRO de um workspace.

        Retorna o Document ou None.
        """
        try:
            return (
                Document.objects
                .select_related('client', 'created_by', 'updated_by', 'workspace')
                .filter(id=document_id, workspace=workspace)
                .first()
            )
        except (ValueError, TypeError):
            return None