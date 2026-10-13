"""
BriefingTemplateCategoryViewSet — CRUD de categorias de modelo.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.workspaces.queries import WorkspaceQueries
from apps.briefings.models.template_category import BriefingTemplateCategory


class BriefingTemplateCategoryViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def _current_workspace(self):
        ws_id = self.request.session.get('current_workspace_id')
        if not ws_id:
            return None
        return WorkspaceQueries.get_for_user(ws_id, self.request.user)

    def list(self, request):
        ws = self._current_workspace()
        if ws is None:
            return Response([], status=200)
        qs = ws.briefing_template_categories.all().order_by('position', 'name')
        data = [
            {'id': str(c.id), 'name': c.name, 'position': c.position}
            for c in qs
        ]
        return Response(data)

    def create(self, request):
        ws = self._current_workspace()
        if ws is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Nome obrigatório'}, status=400)

        if BriefingTemplateCategory.objects.filter(
            workspace=ws, name__iexact=name,
        ).exists():
            return Response(
                {'error': 'Já existe uma categoria com esse nome.'},
                status=400,
            )

        last = (
            BriefingTemplateCategory.objects
            .filter(workspace=ws)
            .order_by('-position')
            .first()
        )
        cat = BriefingTemplateCategory.objects.create(
            workspace=ws,
            name=name,
            position=(last.position + 1 if last else 1),
        )
        return Response(
            {'id': str(cat.id), 'name': cat.name, 'position': cat.position},
            status=201,
        )

    def partial_update(self, request, id=None):
        ws = self._current_workspace()
        if ws is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        cat = ws.briefing_template_categories.filter(id=id).first()
        if not cat:
            return Response({'error': 'Não encontrada'}, status=404)

        name = (request.data.get('name') or '').strip()
        if name:
            cat.name = name
            cat.save(update_fields=['name', 'updated_at'])

        return Response({
            'id': str(cat.id), 'name': cat.name, 'position': cat.position,
        })

    def destroy(self, request, id=None):
        ws = self._current_workspace()
        if ws is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        cat = ws.briefing_template_categories.filter(id=id).first()
        if not cat:
            return Response({'error': 'Não encontrada'}, status=404)

        cat.delete()
        return Response(status=204)

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        ws = self._current_workspace()
        if ws is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        ordered_ids = request.data.get('ordered_ids') or []
        if not isinstance(ordered_ids, list):
            return Response({'error': 'ordered_ids precisa ser lista'}, status=400)

        cats = {
            str(c.id): c
            for c in ws.briefing_template_categories.all()
        }

        for sid in ordered_ids:
            if str(sid) not in cats:
                return Response(
                    {'error': f'Categoria {sid} não pertence ao workspace.'},
                    status=400,
                )

        OFFSET = 100000
        for i, sid in enumerate(ordered_ids):
            c = cats[str(sid)]
            c.position = OFFSET + i
            c.save(update_fields=['position'])
        for i, sid in enumerate(ordered_ids):
            c = cats[str(sid)]
            c.position = i + 1
            c.save(update_fields=['position'])

        return Response({'ok': True})