"""
BriefingQuestionInstanceService — CRUD de perguntas exclusivas.

REGRA ARQUITETURAL
------------------
Perguntas exclusivas só podem ser adicionadas/removidas enquanto o
briefing NÃO tem nenhuma resposta (`is_snapshot_locked()` retorna
False).

Quando a primeira resposta chega, o snapshot do briefing já
incorporou as custom questions — e a partir daí qualquer alteração
invalidaria a estrutura que o cliente está vendo.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.briefings.models import (
    Briefing,
    BriefingQuestionInstance,
)
from apps.briefings.exceptions import (
    BriefingError,
    BriefingNotFoundError,
)

logger = logging.getLogger('briefings')


class BriefingQuestionInstanceService:

    @staticmethod
    def _assert_briefing_editable(briefing: Briefing) -> None:
        """
        Levanta BriefingError se o briefing não aceita mais edições
        estruturais.
        """
        if briefing.status == Briefing.STATUS_COMPLETED:
            raise BriefingError(
                'Este briefing já foi concluído. Não é possível '
                'adicionar ou remover perguntas.'
            )
        if briefing.status == Briefing.STATUS_CLOSED:
            raise BriefingError(
                'Este briefing foi encerrado. Não é possível '
                'adicionar ou remover perguntas.'
            )
        if briefing.status == Briefing.STATUS_EXPIRED:
            raise BriefingError(
                'Este briefing expirou. Não é possível '
                'adicionar ou remover perguntas.'
            )
        if briefing.is_snapshot_locked():
            raise BriefingError(
                'O cliente já começou a responder. Não é possível '
                'alterar a estrutura agora.'
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
        BriefingQuestionInstanceService._assert_briefing_editable(briefing)

        text = (text or '').strip()
        if not text:
            raise BriefingError('O enunciado é obrigatório.')

        section_ref = str(section_ref or '').strip()
        if not section_ref:
            raise BriefingError('A seção é obrigatória.')

        # Confirma que a seção existe no snapshot do briefing
        snapshot = briefing.structure_snapshot or {}
        section_ids = {
            str(s.get('id')) for s in snapshot.get('sections', [])
        }
        if section_ref not in section_ids:
            raise BriefingError(
                'A seção informada não pertence a este briefing.'
            )

        # Próxima posição (respeitando o que já existe no snapshot
        # daquela seção E as custom questions já adicionadas)
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

        # Marca o briefing como personalizado
        if not briefing.has_custom_questions:
            briefing.has_custom_questions = True
            briefing.save(update_fields=['has_custom_questions', 'updated_at'])

        return instance

    @staticmethod
    def _next_position(*, briefing: Briefing, section_ref: str) -> int:
        """
        Retorna a próxima posição livre na seção, considerando tanto
        as perguntas do snapshot quanto as custom questions já criadas.
        """
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
        BriefingQuestionInstanceService._assert_briefing_editable(
            instance.briefing,
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
        BriefingQuestionInstanceService._assert_briefing_editable(
            instance.briefing,
        )
        instance.delete()

        # Se não sobrou nenhuma, limpa a flag
        remaining = BriefingQuestionInstance.objects.filter(
            briefing=instance.briefing,
        ).exists()
        if not remaining:
            b = instance.briefing
            b.has_custom_questions = False
            b.save(update_fields=['has_custom_questions', 'updated_at'])

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
            raise BriefingError('Pergunta exclusiva não encontrada.')
        return instance