"""
Queries otimizadas para os modelos de briefing.

REGRA MULTI-TENANT:
    Toda consulta nasce SEMPRE da combinação (workspace, ...).
    Nunca de "briefing depois checar workspace".
"""

from apps.briefings.models import (
    Briefing,
    BriefingTemplate,
    BriefingAnswer,
)


class BriefingQueries:

    # ------------------------------------------------------------------
    # TEMPLATES
    # ------------------------------------------------------------------

    @staticmethod
    def list_templates_for_workspace(workspace):
        return (
            BriefingTemplate.objects
            .filter(workspace=workspace)
            .order_by('-created_at')
        )

    @staticmethod
    def get_template_in_workspace(template_id, workspace):
        try:
            return (
                BriefingTemplate.objects
                .filter(id=template_id, workspace=workspace)
                .first()
            )
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # BRIEFINGS
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_workspace(workspace, status=None):
        qs = (
            Briefing.objects
            .filter(workspace=workspace)
            .select_related('client', 'template')
            .order_by('-created_at')
        )
        if status:
            qs = qs.filter(status=status)
        return qs

    @staticmethod
    def get_in_workspace(briefing_id, workspace):
        try:
            return (
                Briefing.objects
                .filter(id=briefing_id, workspace=workspace)
                .select_related('client', 'template', 'workspace')
                .first()
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    def get_for_client(client, briefing_id):
        """
        Resolve um briefing no contexto do portal do cliente.

        NÃO confiar em UUIDs enviados pelo navegador. A checagem é
        sempre (client, id).
        """
        try:
            return (
                Briefing.objects
                .filter(id=briefing_id, client=client)
                .select_related('workspace', 'template', 'client')
                .first()
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    def list_for_client(client):
        return (
            Briefing.objects
            .filter(client=client)
            .select_related('template')
            .order_by('-created_at')
        )

    # ------------------------------------------------------------------
    # ANSWERS
    # ------------------------------------------------------------------

    @staticmethod
    def list_answers_for_briefing(briefing):
        return (
            BriefingAnswer.objects
            .filter(briefing=briefing)
            .select_related('latest_event', 'latest_audio')
            .prefetch_related('attachments')
            .order_by('created_at')
        )

    @staticmethod
    def get_answer(briefing, question_id):
        try:
            return (
                BriefingAnswer.objects
                .filter(briefing=briefing, question_id=question_id)
                .select_related('latest_event', 'latest_audio')
                .prefetch_related('attachments')
                .first()
            )
        except (ValueError, TypeError):
            return None