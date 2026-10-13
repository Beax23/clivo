"""
WorkspaceStorageView — pill de armazenamento do header.

Calcula o uso total de imagens de referência do workspace.

NOTA: o "total" é um valor fixo do plano. No P0 assumimos 5 GB.
Quando o módulo de billing/planos existir, este valor vem de lá.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as http_status
from django.db.models import Sum

from apps.references.models import Reference
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership


# Limite fixo do workspace no P0 (5 GB).
# Quando o módulo de planos existir, este valor vem de lá.
DEFAULT_STORAGE_QUOTA_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB


class WorkspaceStorageView(APIView):
    """
    GET /api/workspace/storage/

    Retorna o uso de armazenamento do workspace ativo.

    Resposta:
        {
            "used": 1073741824,        # bytes usados
            "total": 5368709120,        # bytes totais (quota)
            "percent": 20,              # 0-100 (arredondado)
            "used_human": "1.0 GB",
            "total_human": "5.0 GB"
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace_id = request.session.get('current_workspace_id')
        if not workspace_id:
            return Response(
                {'error': 'Nenhum workspace ativo'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
        if workspace is None:
            return Response(
                {'error': 'Workspace não encontrado'},
                status=http_status.HTTP_404_NOT_FOUND,
            )

        # Verifica vínculo
        is_member = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user,
        ).exists()
        if not is_member:
            return Response(
                {'error': 'Você não é membro deste Workspace'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        used = self._compute_used_bytes(workspace)
        total = DEFAULT_STORAGE_QUOTA_BYTES
        percent = round((used / total) * 100) if total else 0
        percent = min(100, max(0, percent))

        return Response({
            'used': used,
            'total': total,
            'percent': percent,
            'used_human': self._humanize(used),
            'total_human': self._humanize(total),
        })

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_used_bytes(workspace) -> int:
        """
        Soma o tamanho das imagens das referências via `aggregate`.

        Não usa `iterator()` — isso evita o erro de cursor nomeado
        que acontece com PgBouncer / poolers de Postgres em modo
        transaction. É o mesmo padrão do `DocumentService.storage_usage`.
        """
        total = (
            Reference.objects
            .filter(workspace=workspace)
            .aggregate(total=Sum('size'))
            .get('total') or 0
        )
        return int(total)

    @staticmethod
    def _humanize(num_bytes: int) -> str:
        if not num_bytes:
            return '0 B'
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        size = float(num_bytes)
        i = 0
        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1
        return f'{size:.1f} {units[i]}'