"""
Modelos do template reutilizável de briefing.

Hierarquia:

    BriefingTemplate
        └── BriefingSection
                └── BriefingQuestion

REGRA ARQUITETURAL
------------------
Template é ESTRUTURA. Não é execução.

Estados:
    `status`: draft / published / archived
    `is_active`: eixo independente. Um template ativo pode estar
                 em rascunho; um template publicado pode estar
                 inativo. `is_active=False` bloqueia NOVAS execuções,
                 mas preserva as execuções existentes.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingTemplate(models.Model):

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Rascunho'),
        (STATUS_PUBLISHED, 'Publicado'),
        (STATUS_ARCHIVED, 'Arquivado'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='briefing_templates',
        help_text=_('Workspace ao qual o template pertence'),
    )

    name = models.CharField(
        max_length=200,
        help_text=_('Nome do template (ex: "Briefing Residencial")'),
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição do objetivo do template'),
    )

    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text=_(
            'Categoria livre do operador (ex: "residencial", '
            '"comercial"). Sem FK no MVP.'
        ),
    )

    # FK opcional para a categoria estruturada
    category_fk = models.ForeignKey(
        'briefings.BriefingTemplateCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates',
        db_index=True,
    )

    # Sem `storage=` explícito — usa o default storage
    # (B2/R2/local conforme settings.STORAGES).
    cover = models.FileField(
        upload_to='briefing-templates/covers/',
        max_length=500,
        blank=True,
        null=True,
        help_text=_('Imagem de capa opcional do template.'),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        help_text=_('Estado editorial do template'),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_(
            'Eixo independente do status. Se False, bloqueia NOVAS '
            'execuções, mas preserva as execuções existentes.'
        ),
    )

    position = models.IntegerField(
        default=0,
        db_index=True,
        help_text=_('Ordem explícita do modelo dentro do workspace'),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_briefing_templates',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_template'
        verbose_name = _('Modelo de Briefing')
        verbose_name_plural = _('Modelos de Briefing')
        ordering = ['position', '-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['workspace', 'is_active']),
            models.Index(fields=['workspace', 'category']),
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['workspace', 'position']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def sections_count(self) -> int:
        return self.sections.count()

    @property
    def questions_count(self) -> int:
        return BriefingQuestion.objects.filter(section__template=self).count()

    def is_editable(self) -> bool:
        return self.status == self.STATUS_DRAFT

    def can_start_execution(self) -> bool:
        return (
            self.status == self.STATUS_PUBLISHED
            and self.is_active
        )


class BriefingSection(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    template = models.ForeignKey(
        BriefingTemplate,
        on_delete=models.CASCADE,
        related_name='sections',
    )

    title = models.CharField(
        max_length=200,
        help_text=_('Título da sessão (ex: "Sobre você")'),
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição opcional da sessão'),
    )

    position = models.IntegerField(
        default=0,
        help_text=_('Ordem explícita da sessão dentro do template'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_section'
        verbose_name = _('Sessão de Briefing')
        verbose_name_plural = _('Sessões de Briefing')
        ordering = ['position', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'position'],
                name='briefing_section_unique_position_per_template',
            ),
        ]
        indexes = [
            models.Index(fields=['template', 'position']),
        ]

    def __str__(self):
        return f"{self.template.name} → {self.title}"


class BriefingQuestion(models.Model):

    QUESTION_TYPE_TEXT = 'text'
    QUESTION_TYPE_SHORT_TEXT = 'short_text'
    QUESTION_TYPE_LONG_TEXT = 'long_text'
    QUESTION_TYPE_SINGLE_CHOICE = 'single_choice'
    QUESTION_TYPE_MULTIPLE_CHOICE = 'multiple_choice'
    QUESTION_TYPE_SCALE = 'scale'
    QUESTION_TYPE_RATING = 'rating'
    QUESTION_TYPE_YES_NO = 'yes_no'
    QUESTION_TYPE_DATE = 'date'
    QUESTION_TYPE_NUMBER = 'number'
    QUESTION_TYPE_URL = 'url'
    QUESTION_TYPE_CHOICE = 'choice'  # legado

    QUESTION_TYPE_CHOICES = [
        (QUESTION_TYPE_TEXT, 'Texto livre'),
        (QUESTION_TYPE_SHORT_TEXT, 'Texto curto'),
        (QUESTION_TYPE_LONG_TEXT, 'Texto longo'),
        (QUESTION_TYPE_SINGLE_CHOICE, 'Escolha única'),
        (QUESTION_TYPE_MULTIPLE_CHOICE, 'Múltipla escolha'),
        (QUESTION_TYPE_SCALE, 'Escala (1–10)'),
        (QUESTION_TYPE_RATING, 'Avaliação (estrelas)'),
        (QUESTION_TYPE_YES_NO, 'Sim / Não'),
        (QUESTION_TYPE_DATE, 'Data'),
        (QUESTION_TYPE_NUMBER, 'Número'),
        (QUESTION_TYPE_URL, 'Link'),
        (QUESTION_TYPE_CHOICE, 'Escolha (legado)'),
    ]

    RESPONSE_FORMAT_TEXT = 'text'
    RESPONSE_FORMAT_AUDIO = 'audio'
    RESPONSE_FORMAT_IMAGE = 'image'

    DEFAULT_ALLOWED_FORMATS = ['text', 'audio', 'image']

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    section = models.ForeignKey(
        BriefingSection,
        on_delete=models.CASCADE,
        related_name='questions',
    )

    text = models.TextField(
        help_text=_('Enunciado da pergunta'),
    )

    instructions = models.TextField(
        blank=True,
        help_text=_('Instruções adicionais para o cliente'),
    )

    question_type = models.CharField(
        max_length=30,
        choices=QUESTION_TYPE_CHOICES,
        default=QUESTION_TYPE_TEXT,
        help_text=_('Tipo da pergunta (intenção do arquiteto)'),
    )

    allowed_response_formats = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            'Lista de formatos de resposta permitidos ao cliente. '
            'Ex: ["text", "audio", "image"].'
        ),
    )

    options = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            'Para perguntas de escolha única/múltipla: lista de '
            'opções. Cada item é um dict '
            '{"text": str, "image_document_id": uuid|null}.'
        ),
    )

    position = models.IntegerField(
        default=0,
        help_text=_('Ordem explícita da pergunta dentro da sessão'),
    )

    is_required = models.BooleanField(
        default=True,
        help_text=_('Se a pergunta é obrigatória'),
    )

    reference_documents = models.ManyToManyField(
        'documents.Document',
        blank=True,
        related_name='briefing_question_references',
        help_text=_('Imagens de referência disponibilizadas pelo arquiteto'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_question'
        verbose_name = _('Pergunta de Briefing')
        verbose_name_plural = _('Perguntas de Briefing')
        ordering = ['position', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['section', 'position'],
                name='briefing_question_unique_position_per_section',
            ),
        ]
        indexes = [
            models.Index(fields=['section', 'position']),
        ]

    def __str__(self):
        return f"{self.section.title} → {self.text[:50]}"

    def clean(self):
        from django.core.exceptions import ValidationError

        formats = self.allowed_response_formats or []
        if not isinstance(formats, list):
            raise ValidationError({
                'allowed_response_formats': _(
                    'Deve ser uma lista de strings.'
                )
            })

        valid = {
            self.RESPONSE_FORMAT_TEXT,
            self.RESPONSE_FORMAT_AUDIO,
            self.RESPONSE_FORMAT_IMAGE,
        }
        invalid = [f for f in formats if f not in valid]
        if invalid:
            raise ValidationError({
                'allowed_response_formats': _(
                    f'Formatos inválidos: {invalid}. '
                    f'Válidos: {sorted(valid)}.'
                )
            })

        choice_types = {
            self.QUESTION_TYPE_SINGLE_CHOICE,
            self.QUESTION_TYPE_MULTIPLE_CHOICE,
            self.QUESTION_TYPE_CHOICE,
        }
        if self.question_type in choice_types:
            if not isinstance(self.options, list):
                raise ValidationError({
                    'options': 'Deve ser uma lista.'
                })

    def save(self, *args, **kwargs):
        if not self.allowed_response_formats:
            self.allowed_response_formats = list(self.DEFAULT_ALLOWED_FORMATS)
        self.full_clean()
        super().save(*args, **kwargs)