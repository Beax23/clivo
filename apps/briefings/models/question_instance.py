"""
Modelo BriefingQuestionInstance — pergunta exclusiva de uma execução.

REGRA ARQUITETURAL
------------------
`BriefingQuestionInstance` representa uma pergunta que o arquiteto
adicionou APENAS para um briefing específico, sem alterar o modelo
reutilizável.

Ela NÃO substitui `BriefingQuestion` (que é do template). Ela é um
complemento local — vive dentro da execução.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingQuestionInstance(models.Model):

    # Mesmos tipos do BriefingQuestion (template). Mantido em
    # sincronia manual porque o Django não permite herança de
    # choices entre classes sem um módulo comum. Se um tipo for
    # adicionado aqui, precisa ser adicionado em template.py também.
    QUESTION_TYPE_TEXT = 'text'
    QUESTION_TYPE_SHORT_TEXT = 'short_text'
    QUESTION_TYPE_LONG_TEXT = 'long_text'

    QUESTION_TYPE_SINGLE_CHOICE = 'single_choice'
    QUESTION_TYPE_MULTIPLE_CHOICE = 'multiple_choice'
    QUESTION_TYPE_DROPDOWN = 'dropdown'

    QUESTION_TYPE_SCALE = 'scale'
    QUESTION_TYPE_RATING = 'rating'
    QUESTION_TYPE_NUMBER = 'number'

    QUESTION_TYPE_GRID_SINGLE = 'grid_single'
    QUESTION_TYPE_GRID_MULTIPLE = 'grid_multiple'

    QUESTION_TYPE_DATE = 'date'
    QUESTION_TYPE_TIME = 'time'
    QUESTION_TYPE_URL = 'url'

    QUESTION_TYPE_YES_NO = 'yes_no'
    QUESTION_TYPE_FILE_UPLOAD = 'file_upload'

    RESPONSE_FORMAT_TEXT = 'text'
    RESPONSE_FORMAT_AUDIO = 'audio'
    RESPONSE_FORMAT_IMAGE = 'image'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.CASCADE,
        related_name='custom_questions',
    )

    section_ref = models.CharField(
        max_length=36,
        db_index=True,
        help_text=_(
            'ID da seção no snapshot ao qual esta pergunta pertence.'
        ),
    )

    text = models.TextField(
        help_text=_('Enunciado da pergunta exclusiva'),
    )

    instructions = models.TextField(
        blank=True,
        help_text=_('Instruções adicionais para o cliente'),
    )

    question_type = models.CharField(
        max_length=30,
        default=QUESTION_TYPE_TEXT,
        help_text=_('Tipo da pergunta'),
    )

    allowed_response_formats = models.JSONField(
        default=list,
        blank=True,
        help_text=_('Formatos de resposta permitidos'),
    )

    options = models.JSONField(
        default=list,
        blank=True,
        help_text=_('Opções (para perguntas de escolha ou grid)'),
    )

    position = models.IntegerField(
        default=0,
        help_text=_('Ordem dentro da seção'),
    )

    is_required = models.BooleanField(
        default=True,
        help_text=_('Se a pergunta é obrigatória'),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_briefing_question_instances',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_question_instance'
        verbose_name = _('Pergunta exclusiva de execução')
        verbose_name_plural = _('Perguntas exclusivas de execução')
        ordering = ['briefing', 'section_ref', 'position', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['briefing', 'section_ref', 'position'],
                name='briefing_question_instance_unique_position',
            ),
        ]
        indexes = [
            models.Index(fields=['briefing', 'section_ref']),
        ]

    def __str__(self):
        return f"{self.briefing_id} · Q:{str(self.id)[:8]} · {self.text[:40]}"

    def to_snapshot_dict(self) -> dict:
        """
        Serializa esta instância no formato usado dentro do
        `structure_snapshot` do Briefing.
        """
        return {
            'id': str(self.id),
            'text': self.text,
            'instructions': self.instructions,
            'question_type': self.question_type,
            'allowed_response_formats': list(
                self.allowed_response_formats or []
            ),
            'options': self.options if self.options else [],
            'position': self.position,
            'is_required': bool(self.is_required),
            'reference_document_ids': [],
            'is_custom': True,
        }