"""
BriefingQuestionInstanceService — CRUD de perguntas complementares.

REGRA ARQUITETURAL
------------------
Perguntas complementares vão SEMPRE para o `supplementary_snapshot`,
nunca reescrevem o `structure_snapshot` original.

Podem ser adicionadas em qualquer momento — inclusive quando o
briefing já tem respostas ou está `completed`. NÃO são bloqueadas
por `is_snapshot_locked()`.

Exceção: briefings `cancelled` NÃO aceitam perguntas complementares.

REMOÇÃO
-------
Remoção é DELETE real. Sem soft delete.

Perguntas JÁ RESPONDIDAS não podem ser removidas. Regra de negócio:
o arquiteto deve adicionar uma nova pergunta complementar para
corrigir, e a resposta antiga permanece no histórico.

Perguntas NÃO respondidas podem ser removidas. O evento
`custom_question_removed` guarda o snapshot completo da pergunta
removida no `content`, preservando o histórico.
"""

import logging

from django.db import transaction

from apps.briefings.models import (
    Briefing,
    BriefingAnswer,
    BriefingEvent,
    BriefingQuestionInstance,
)
from apps.briefings.exceptions import BriefingError
from apps.briefings.services.event_service import BriefingEventService

logger = logging.getLogger('briefings')


class BriefingQuestionInstanceService:

    @staticmethod
    def _assert_briefing_accepts_supplementary(briefing: Briefing) -> None:
        """
        Levanta BriefingError se o briefing não aceita perguntas
        complementares no estado atual.

        Permitido em: in_progress, paused, completed.
        Bloqueado em: cancelled.
        """
        if briefing.status == Briefing.STATUS_CANCELLED:
            raise BriefingError(
                'Este briefing foi cancelado. Não é possível adicionar '
                'ou remover perguntas complementares.'
            )

    @staticmethod
    def _assert_instance_not_answered(
        briefing: Briefing,
        instance_id,
    ) -> None:
        """
        Levanta BriefingError se a pergunta já foi respondida.
        Perguntas respondidas não podem ser editadas nem removidas.
        """
        exists = BriefingAnswer.objects.filter(
            briefing=briefing,
            question_id=instance_id,
        ).exists()
        if exists:
            raise BriefingError(
                'Esta pergunta já foi respondida e não pode ser '
                'alterada. Para corrigir, adicione uma nova pergunta '
                'complementar.'
            )

    # ------------------------------------------------------------------
    # LISTAGEM
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_briefing(briefing: Briefing):
        return (
            BriefingQuestionInstance.objects
            .filter(briefing=briefing)
            .order_by('section_ref', 'position', 'created_at')
        )

    @staticmethod
    def list_for_section(briefing: Briefing, section_ref: str):
        return (
            BriefingQuestionInstance.objects
            .filter(briefing=briefing, section_ref=str(section_ref))
            .order_by('position', 'created_at')
        )

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def add_custom_question(
        *,
        briefing: Briefing,
        section_ref: str,
        text: str,
        instructions: str = '',
        question_type: str = 'text',
        allowed_response_formats=None,
        options=None,
        is_required: bool = True,
        actor=None,
    ) -> BriefingQuestionInstance:
        BriefingQuestionInstanceService._assert_briefing_accepts_supplementary(
            briefing,
        )

        text = (text or '').strip()
        if not text:
            raise BriefingError('O enunciado é obrigatório.')

        section_ref = str(section_ref or '').strip()
        if not section_ref:
            raise BriefingError('A seção é obrigatória.')

        section_exists = False
        for s in (briefing.structure_snapshot or {}).get('sections', []):
            if str(s.get('id')) == section_ref:
                section_exists = True
                break
        if not section_exists:
            for s in (briefing.supplementary_snapshot or {}).get('sections', []):
                if str(s.get('id')) == section_ref:
                    section_exists = True
                    break
        if not section_exists:
            raise BriefingError(
                'A seção informada não pertence a este briefing.'
            )

        last_position = BriefingQuestionInstanceService._next_position(
            briefing=briefing,
            section_ref=section_ref,
        )

        instance = BriefingQuestionInstance.objects.create(
            briefing=briefing,
            section_ref=section_ref,
            text=text,
            instructions=(instructions or '').strip(),
            question_type=question_type or 'text',
            allowed_response_formats=(
                list(allowed_response_formats)
                if allowed_response_formats is not None
                else ['text', 'audio', 'image']
            ),
            options=list(options) if options else [],
            position=last_position,
            is_required=bool(is_required),
            created_by=actor,
        )

        from apps.briefings.services.briefing_service import BriefingService
        BriefingService.freeze_supplementary_questions_into_snapshot(briefing)

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_CUSTOM_QUESTION_ADDED,
            user=actor,
            question_id=instance.id,
            content={
                'instance_id': str(instance.id),
                'section_ref': section_ref,
                'text': text,
                'is_required': bool(is_required),
                'question_type': instance.question_type,
            },
        )

        if not briefing.has_custom_questions:
            briefing.has_custom_questions = True
            briefing.save(update_fields=[
                'has_custom_questions', 'updated_at',
            ])

        logger.info(
            'Pergunta complementar adicionada | briefing=%s | instance=%s',
            briefing.id, instance.id,
        )

        return instance

    @staticmethod
    def _next_position(*, briefing: Briefing, section_ref: str) -> int:
        snapshot_positions = []
        for s in (briefing.structure_snapshot or {}).get('sections', []):
            if str(s.get('id')) != section_ref:
                continue
            for q in s.get('questions', []):
                snapshot_positions.append(int(q.get('position') or 0))

        custom_positions = list(
            BriefingQuestionInstance.objects
            .filter(briefing=briefing, section_ref=section_ref)
            .values_list('position', flat=True)
        )

        all_positions = snapshot_positions + custom_positions
        return (max(all_positions) if all_positions else 0) + 1

    # ------------------------------------------------------------------
    # ATUALIZAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def update_custom_question(
        *,
        instance: BriefingQuestionInstance,
        text: str = None,
        instructions: str = None,
        question_type: str = None,
        allowed_response_formats=None,
        options=None,
        is_required: bool = None,
        actor=None,
    ) -> BriefingQuestionInstance:
        BriefingQuestionInstanceService._assert_briefing_accepts_supplementary(
            instance.briefing,
        )
        BriefingQuestionInstanceService._assert_instance_not_answered(
            instance.briefing, instance.id,
        )

        fields = []

        if text is not None:
            text = text.strip()
            if not text:
                raise BriefingError('O enunciado não pode ser vazio.')
            instance.text = text
            fields.append('text')

        if instructions is not None:
            instance.instructions = instructions.strip()
            fields.append('instructions')

        if question_type is not None:
            instance.question_type = question_type
            fields.append('question_type')

        if allowed_response_formats is not None:
            instance.allowed_response_formats = list(allowed_response_formats)
            fields.append('allowed_response_formats')

        if options is not None:
            instance.options = list(options)
            fields.append('options')

        if is_required is not None:
            instance.is_required = bool(is_required)
            fields.append('is_required')

        if fields:
            instance.save(update_fields=fields + ['updated_at'])

            from apps.briefings.services.briefing_service import BriefingService
            BriefingService.freeze_supplementary_questions_into_snapshot(
                instance.briefing,
            )

        return instance

    # ------------------------------------------------------------------
    # EXCLUSÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def remove_custom_question(
        *,
        instance: BriefingQuestionInstance,
        actor=None,
    ) -> None:
        BriefingQuestionInstanceService._assert_briefing_accepts_supplementary(
            instance.briefing,
        )
        BriefingQuestionInstanceService._assert_instance_not_answered(
            instance.briefing, instance.id,
        )

        briefing = instance.briefing
        instance_id = instance.id
        payload = instance.to_removal_event_payload()

        instance.delete()

        from apps.briefings.services.briefing_service import BriefingService
        BriefingService.freeze_supplementary_questions_into_snapshot(briefing)

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_CUSTOM_QUESTION_REMOVED,
            user=actor,
            question_id=instance_id,
            content=payload,
        )

        remaining = BriefingQuestionInstance.objects.filter(
            briefing=briefing,
        ).exists()
        if not remaining:
            briefing.has_custom_questions = False
            briefing.save(update_fields=[
                'has_custom_questions', 'updated_at',
            ])

        logger.info(
            'Pergunta complementar removida | briefing=%s | instance=%s',
            briefing.id, instance_id,
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_raise(instance_id, briefing: Briefing):
        try:
            instance = BriefingQuestionInstance.objects.filter(
                id=instance_id, briefing=briefing,
            ).first()
        except (ValueError, TypeError):
            instance = None
        if instance is None:
            raise BriefingError('Pergunta complementar não encontrada.')
        return instance