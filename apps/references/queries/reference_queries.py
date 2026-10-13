"""
Queries otimizadas para Reference.

REGRA MULTI-TENANT:
    Toda consulta nasce SEMPRE da combinação (workspace, ...).
    Nunca de "reference depois checar workspace".
"""

from apps.references.models import Reference


class ReferenceQueries:

    # ------------------------------------------------------------------
    # LISTAGEM
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_workspace(workspace):
        """
        Lista TODAS as referências do workspace, sem filtro.

        Ordenação: mais recentes primeiro.
        """
        return (
            Reference.objects
            .filter(workspace=workspace)
            .select_related('client', 'folder', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    @staticmethod
    def list_for_client(workspace, client):
        """
        Lista referências associadas a um cliente específico
        dentro de um workspace.
        """
        return (
            Reference.objects
            .filter(workspace=workspace, client=client)
            .select_related('client', 'folder', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    @staticmethod
    def list_for_project(workspace, project_id):
        """
        Lista referências associadas a um projeto específico
        dentro de um workspace.

        `project_id` é o UUID solto (até `projects` existir).
        """
        return (
            Reference.objects
            .filter(workspace=workspace, project_id=project_id)
            .select_related('client', 'folder', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    @staticmethod
    def list_for_folder(workspace, folder):
        """
        Lista referências associadas a uma pasta específica
        dentro de um workspace.
        """
        return (
            Reference.objects
            .filter(workspace=workspace, folder=folder)
            .select_related('client', 'folder', 'created_by', 'updated_by')
            .order_by('-created_at')
        )

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_id_in_workspace(reference_id, workspace):
        """
        Resolve uma Reference por id DENTRO de um workspace.

        Retorna a Reference ou None.
        """
        try:
            return (
                Reference.objects
                .select_related('client', 'folder', 'created_by', 'updated_by', 'workspace')
                .filter(id=reference_id, workspace=workspace)
                .first()
            )
        except (ValueError, TypeError):
            return None