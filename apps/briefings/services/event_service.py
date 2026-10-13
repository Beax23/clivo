"""
BriefingEventService — porta única de escrita no histórico.

REGRA ARQUITETURAL
------------------
Nenhum ponto do código escreve em `BriefingEvent` diretamente.
Só este service escreve.

Isso garante:
    - consistência do campo `content`
    - autoria explícita (user XOR portal_session)
    - eventos de sistema (user=None, portal_session=None) permitidos
      para ações internas (envio de e-mail, notificações), mas
      marcados como tal
"""

from typing import Optional

from apps.briefings.models import Briefing, BriefingEvent
from apps.briefings.exceptions import BriefingError


class BriefingEventService:

    @staticmethod
    def log(
        *,
        briefing: Briefing,
        kind: str,
        user=None,
        portal_session=None,
        question_id=None,
        content: Optional[dict] = None,
    ) -> BriefingEvent:
        """
        Registra um evento no histórico.

        Autoridade:
            - Se `user` preenchido → autor é o usuário do escritório.
            - Se `portal_session` preenchido → autor é o cliente.
            - Se ambos vazios → evento de sistema (ex.: envio
              automático de e-mail pelo NotificationService).
            - Se ambos preenchidos → erro (autor ambíguo).

        Validação:
            - kind precisa estar em KIND_CHOICES
            - user, se passado, precisa estar autenticado
            - portal_session, se passada, precisa estar válida
        """
        if user is not None and portal_session is not None:
            raise BriefingError(
                'Evento não pode ter dois autores '
                '(user e portal_session).'
            )

        valid_kinds = {c[0] for c in BriefingEvent.KIND_CHOICES}
        if kind not in valid_kinds:
            raise BriefingError(f'kind inválido: {kind}')

        if user is not None and not getattr(user, 'is_authenticated', False):
            user = None

        if portal_session is not None and not getattr(
            portal_session, 'is_valid', lambda: True
        )():
            raise BriefingError('Sessão do portal inválida')

        return BriefingEvent.objects.create(
            briefing=briefing,
            kind=kind,
            question_id=question_id,
            content=content or {},
            user=user,
            portal_session=portal_session,
        )

    # ------------------------------------------------------------------
    # CONSULTAS
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_briefing(briefing: Briefing):
        return (
            BriefingEvent.objects
            .filter(briefing=briefing)
            .select_related('user', 'portal_session')
            .order_by('-created_at')
        )

    @staticmethod
    def latest_answer_event(briefing: Briefing, question_id):
        return (
            BriefingEvent.objects
            .filter(
                briefing=briefing,
                question_id=question_id,
                kind=BriefingEvent.KIND_ANSWERED,
            )
            .order_by('-created_at')
            .first()
        )