"""
BriefingTemplateService — ciclo de vida do template reutilizável.

Emite `BriefingTemplateEvent` para toda alteração estrutural.

REGRA P0:
    - `delete_template` NÃO apaga execuções em cascata.
    - Versões (`BriefingTemplateVersion`) sobrevivem com
      `template=NULL` quando o modelo lógico é excluído.
    - O snapshot do briefing já contém tudo que precisa para
      continuar funcionando.

PUBLICAÇÃO / DESPUBLICAÇÃO:
    - `publish_template` valida que existem sessões, cria uma nova
      `BriefingTemplateVersion` (rascunho), popula `structure` a partir
      das tabelas atuais, e publica essa versão.
    - `unpublish_template` volta o status do template para `draft`
      SEM tocar em versões publicadas.
    - `archive_template` move o template para `archived`.

Briefings em execução NUNCA são afetados por essas transições —
usam `structure_snapshot` imutável.
"""

import logging

from django.db import transaction

from apps.briefings.models import (
    BriefingTemplate,
    BriefingSection,
    BriefingQuestion,
    BriefingTemplateEvent,
    BriefingTemplateVersion,
)
from apps.briefings.exceptions import (
    BriefingTemplateNotFoundError,
    BriefingTemplateNotDraftError,
    BriefingSectionNotFoundError,
    BriefingQuestionNotFoundError,
    BriefingError,
)

logger = logging.getLogger('briefings')


_REORDER_OFFSET = 100000


class BriefingTemplateService:

    # ==================================================================
    # EVENTOS
    # ==================================================================

    @staticmethod
    def _log_event(
        *, template, kind, user=None,
        section_id=None, question_id=None, content=None,
    ):
        BriefingTemplateEvent.objects.create(
            template=template,
            kind=kind,
            section_id=section_id,
            question_id=question_id,
            content=content or {},
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
        )

    # ==================================================================
    # TEMPLATE
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def create_template(
        *, workspace, name: str, description: str = '',
        category: str = '', intro_message: str = '', actor=None,
    ) -> BriefingTemplate:
        name = (name or '').strip()
        if not name:
            raise BriefingError('O nome do template é obrigatório.')

        last = (
            BriefingTemplate.objects
            .filter(workspace=workspace)
            .order_by('-position')
            .first()
        )

        template = BriefingTemplate.objects.create(
            workspace=workspace,
            name=name,
            description=(description or '').strip(),
            category=(category or '').strip(),
            intro_message=(intro_message or '').strip(),
            status=BriefingTemplate.STATUS_DRAFT,
            position=(last.position + 1 if last else 1),
            created_by=actor,
        )

        BriefingTemplateVersion.objects.create(
            template=template,
            version_number=1,
            status=BriefingTemplateVersion.STATUS_DRAFT,
            structure={},
            created_by=actor,
        )

        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_TEMPLATE_CREATED,
            user=actor,
            content={'name': template.name},
        )
        return template

    @staticmethod
    @transaction.atomic
    def update_template(
        *, template: BriefingTemplate,
        name: str = None, description: str = None, category: str = None,
        intro_message: str = None, actor=None,
    ) -> BriefingTemplate:
        fields = []
        changes = {}

        if name is not None:
            name = name.strip()
            if not name:
                raise BriefingError('O nome do template não pode ser vazio.')
            if template.name != name:
                changes['name'] = {'old': template.name, 'new': name}
                template.name = name
                fields.append('name')

        if description is not None:
            new_desc = description.strip()
            if template.description != new_desc:
                changes['description'] = True
                template.description = new_desc
                fields.append('description')

        if category is not None:
            new_cat = category.strip()
            if template.category != new_cat:
                changes['category'] = {
                    'old': template.category, 'new': new_cat,
                }
                template.category = new_cat
                fields.append('category')

        if intro_message is not None:
            new_intro = (intro_message or '').strip()
            if template.intro_message != new_intro:
                changes['intro_message'] = True
                template.intro_message = new_intro
                fields.append('intro_message')

        if fields:
            template.save(update_fields=fields + ['updated_at'])
            BriefingTemplateService._log_event(
                template=template,
                kind=BriefingTemplateEvent.KIND_TEMPLATE_UPDATED,
                user=actor,
                content={'changes': changes},
            )
        return template

    @staticmethod
    @transaction.atomic
    def set_cover(*, template: BriefingTemplate, uploaded_file, actor=None):
        if uploaded_file is None:
            raise BriefingError('Nenhuma imagem enviada.')

        name = getattr(uploaded_file, 'name', '') or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext not in {'jpg', 'jpeg', 'jfif', 'png', 'webp', 'gif'}:
            raise BriefingError(
                'Formato inválido. Envie JPG, PNG, WEBP ou GIF.'
            )

        old_name = None
        old_storage = None
        if template.cover:
            try:
                old_name = template.cover.name
                old_storage = template.cover.storage
            except Exception:
                pass

        try:
            template.cover.save(name, uploaded_file, save=False)
        except Exception as exc:
            logger.exception('Falha ao salvar capa do template')
            raise BriefingError('Falha ao salvar a capa no storage.') from exc

        template.save(update_fields=['cover', 'updated_at'])

        if old_name and old_storage:
            try:
                old_storage.delete(old_name)
            except Exception:
                logger.warning(
                    'Não foi possível remover a capa antiga: %s', old_name,
                )

        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_TEMPLATE_UPDATED,
            user=actor,
            content={'action': 'cover_changed'},
        )
        return template

    @staticmethod
    @transaction.atomic
    def clear_cover(*, template: BriefingTemplate, actor=None):
        if not template.cover:
            return template
        old_name = template.cover.name
        old_storage = template.cover.storage
        template.cover = None
        template.save(update_fields=['cover', 'updated_at'])
        try:
            old_storage.delete(old_name)
        except Exception:
            logger.warning('Não foi possível remover a capa: %s', old_name)
        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_TEMPLATE_UPDATED,
            user=actor,
            content={'action': 'cover_removed'},
        )
        return template

    @staticmethod
    @transaction.atomic
    def delete_template(*, template: BriefingTemplate, actor=None) -> None:
        BriefingTemplateVersion.objects.filter(template=template).update(
            template=None,
        )

        if template.cover:
            try:
                template.cover.delete(save=False)
            except Exception:
                logger.warning('Falha ao remover capa ao excluir template')

        template.delete()

    @staticmethod
    @transaction.atomic
    def publish_template(
        *, template: BriefingTemplate, actor=None,
    ) -> BriefingTemplate:
        if template.status != BriefingTemplate.STATUS_DRAFT:
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser publicados.'
            )
        if not template.sections.exists():
            raise BriefingError('Não é possível publicar sem sessões.')

        from apps.briefings.services.template_version_service import (
            BriefingTemplateVersionService,
        )

        version = BriefingTemplateVersionService.create_draft_from_template(
            template=template, actor=actor,
        )
        BriefingTemplateVersionService.publish(
            version=version, actor=actor,
        )

        template.status = BriefingTemplate.STATUS_PUBLISHED
        template.save(update_fields=['status', 'updated_at'])

        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_TEMPLATE_PUBLISHED,
            user=actor,
            content={
                'version_id': str(version.id),
                'version_number': version.version_number,
            },
        )
        return template

    @staticmethod
    @transaction.atomic
    def unpublish_template(
        *, template: BriefingTemplate, actor=None,
    ) -> BriefingTemplate:
        if template.status != BriefingTemplate.STATUS_PUBLISHED:
            raise BriefingError(
                'Só templates publicados podem voltar para rascunho.'
            )

        template.status = BriefingTemplate.STATUS_DRAFT
        template.save(update_fields=['status', 'updated_at'])

        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_TEMPLATE_UNPUBLISHED,
            user=actor,
        )
        return template

    @staticmethod
    @transaction.atomic
    def archive_template(
        *, template: BriefingTemplate, actor=None,
    ) -> BriefingTemplate:
        if template.status == BriefingTemplate.STATUS_ARCHIVED:
            return template

        template.status = BriefingTemplate.STATUS_ARCHIVED
        template.save(update_fields=['status', 'updated_at'])

        BriefingTemplateVersion.objects.filter(
            template=template,
            status=BriefingTemplateVersion.STATUS_PUBLISHED,
        ).update(
            status=BriefingTemplateVersion.STATUS_ARCHIVED,
        )

        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_TEMPLATE_ARCHIVED,
            user=actor,
        )
        return template

    @staticmethod
    def get_or_raise(template_id, workspace) -> BriefingTemplate:
        try:
            template = (
                BriefingTemplate.objects
                .filter(id=template_id, workspace=workspace)
                .first()
            )
        except (ValueError, TypeError):
            template = None
        if template is None:
            raise BriefingTemplateNotFoundError('Template não encontrado.')
        return template

    # ==================================================================
    # REORDER — TEMPLATES
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def reorder_templates(
        *, workspace, ordered_ids: list, actor=None,
    ) -> None:
        templates = {
            str(t.id): t
            for t in BriefingTemplate.objects.filter(workspace=workspace)
        }

        for tid in ordered_ids:
            if str(tid) not in templates:
                raise BriefingTemplateNotFoundError(
                    f'Modelo {tid} não pertence ao workspace.'
                )

        for i, tid in enumerate(ordered_ids):
            t = templates[str(tid)]
            t.position = _REORDER_OFFSET + i
            t.save(update_fields=['position'])

        for i, tid in enumerate(ordered_ids):
            t = templates[str(tid)]
            t.position = i + 1
            t.save(update_fields=['position'])

    # ==================================================================
    # SECTION
    # ==================================================================

    @staticmethod
    def _next_section_position(template: BriefingTemplate) -> int:
        last = (
            BriefingSection.objects
            .filter(template=template)
            .order_by('-position')
            .values_list('position', flat=True)
            .first()
        )
        return (last or 0) + 1

    @staticmethod
    @transaction.atomic
    def add_section(
        *, template: BriefingTemplate, title: str,
        description: str = '', actor=None,
    ) -> BriefingSection:
        if not template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )
        title = (title or '').strip()
        if not title:
            raise BriefingError('O título da sessão é obrigatório.')

        section = BriefingSection.objects.create(
            template=template,
            title=title,
            description=(description or '').strip(),
            position=BriefingTemplateService._next_section_position(template),
        )
        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_SECTION_CREATED,
            user=actor,
            section_id=section.id,
            content={'title': section.title, 'position': section.position},
        )
        return section

    @staticmethod
    @transaction.atomic
    def update_section(
        *, section: BriefingSection,
        title: str = None, description: str = None, actor=None,
    ) -> BriefingSection:
        if not section.template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )
        fields = []
        changes = {}
        if title is not None:
            title = title.strip()
            if not title:
                raise BriefingError('O título não pode ser vazio.')
            if section.title != title:
                changes['title'] = {'old': section.title, 'new': title}
                section.title = title
                fields.append('title')
        if description is not None:
            new_desc = description.strip()
            if section.description != new_desc:
                changes['description'] = True
                section.description = new_desc
                fields.append('description')
        if fields:
            section.save(update_fields=fields + ['updated_at'])
            BriefingTemplateService._log_event(
                template=section.template,
                kind=BriefingTemplateEvent.KIND_SECTION_UPDATED,
                user=actor,
                section_id=section.id,
                content={'changes': changes},
            )
        return section

    @staticmethod
    @transaction.atomic
    def delete_section(*, section: BriefingSection, actor=None) -> None:
        if not section.template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )
        template = section.template
        section_id = section.id
        title = section.title
        section.delete()
        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_SECTION_DELETED,
            user=actor,
            section_id=section_id,
            content={'title': title},
        )

    @staticmethod
    @transaction.atomic
    def reorder_sections(
        *, template: BriefingTemplate, ordered_ids: list, actor=None,
    ) -> None:
        if not template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )

        sections = {
            str(s.id): s
            for s in BriefingSection.objects.filter(template=template)
        }
        for sid in ordered_ids:
            if str(sid) not in sections:
                raise BriefingSectionNotFoundError(
                    f'Sessão {sid} não pertence ao template.'
                )

        for i, sid in enumerate(ordered_ids):
            s = sections[str(sid)]
            s.position = _REORDER_OFFSET + i
            s.save(update_fields=['position'])

        for i, sid in enumerate(ordered_ids):
            s = sections[str(sid)]
            s.position = i + 1
            s.save(update_fields=['position'])

        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_SECTION_REORDERED,
            user=actor,
            content={'ordered_ids': [str(x) for x in ordered_ids]},
        )

    # ==================================================================
    # QUESTION
    # ==================================================================

    @staticmethod
    def _next_question_position(section: BriefingSection) -> int:
        last = (
            BriefingQuestion.objects
            .filter(section=section)
            .order_by('-position')
            .values_list('position', flat=True)
            .first()
        )
        return (last or 0) + 1

    @staticmethod
    @transaction.atomic
    def add_question(
        *, section: BriefingSection,
        text: str, instructions: str = '',
        question_type: str = BriefingQuestion.QUESTION_TYPE_TEXT,
        allowed_response_formats=None,
        options=None,
        is_required: bool = True,
        reference_document_ids=None, actor=None,
    ) -> BriefingQuestion:
        if not section.template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )
        text = (text or '').strip()
        if not text:
            raise BriefingError('O enunciado da pergunta é obrigatório.')

        question = BriefingQuestion.objects.create(
            section=section,
            text=text,
            instructions=(instructions or '').strip(),
            question_type=question_type,
            allowed_response_formats=(
                list(allowed_response_formats)
                if allowed_response_formats is not None
                else list(BriefingQuestion.DEFAULT_ALLOWED_FORMATS)
            ),
            options=list(options) if options else [],
            position=BriefingTemplateService._next_question_position(section),
            is_required=bool(is_required),
        )

        if reference_document_ids:
            BriefingTemplateService._attach_reference_documents(
                question=question,
                document_ids=reference_document_ids,
                workspace=section.template.workspace,
            )

        BriefingTemplateService._log_event(
            template=section.template,
            kind=BriefingTemplateEvent.KIND_QUESTION_CREATED,
            user=actor,
            section_id=section.id,
            question_id=question.id,
            content={'text': question.text},
        )
        return question

    @staticmethod
    @transaction.atomic
    def update_question(
        *, question: BriefingQuestion,
        text: str = None, instructions: str = None,
        question_type: str = None,
        allowed_response_formats=None,
        options=None,
        is_required: bool = None,
        reference_document_ids=None, actor=None,
    ) -> BriefingQuestion:
        if not question.section.template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )

        fields = []
        if text is not None:
            text = text.strip()
            if not text:
                raise BriefingError('O enunciado não pode ser vazio.')
            question.text = text
            fields.append('text')
        if instructions is not None:
            question.instructions = instructions.strip()
            fields.append('instructions')
        if question_type is not None:
            question.question_type = question_type
            fields.append('question_type')
        if allowed_response_formats is not None:
            question.allowed_response_formats = list(allowed_response_formats)
            fields.append('allowed_response_formats')
        if options is not None:
            question.options = list(options)
            fields.append('options')
        if is_required is not None:
            question.is_required = bool(is_required)
            fields.append('is_required')

        if fields:
            question.save(update_fields=fields + ['updated_at'])

        if reference_document_ids is not None:
            question.reference_documents.clear()
            BriefingTemplateService._attach_reference_documents(
                question=question,
                document_ids=reference_document_ids,
                workspace=question.section.template.workspace,
            )

        BriefingTemplateService._log_event(
            template=question.section.template,
            kind=BriefingTemplateEvent.KIND_QUESTION_UPDATED,
            user=actor,
            section_id=question.section_id,
            question_id=question.id,
            content={'fields': fields or ['references']},
        )
        return question

    @staticmethod
    @transaction.atomic
    def delete_question(
        *, question: BriefingQuestion, actor=None,
    ) -> None:
        if not question.section.template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )
        template = question.section.template
        section_id = question.section_id
        question_id = question.id
        question.delete()
        BriefingTemplateService._log_event(
            template=template,
            kind=BriefingTemplateEvent.KIND_QUESTION_DELETED,
            user=actor,
            section_id=section_id,
            question_id=question_id,
        )

    @staticmethod
    @transaction.atomic
    def reorder_questions(
        *, section: BriefingSection, ordered_ids: list, actor=None,
    ) -> None:
        if not section.template.is_editable():
            raise BriefingTemplateNotDraftError(
                'Só templates em rascunho podem ser editados.'
            )
        questions = {
            str(q.id): q
            for q in BriefingQuestion.objects.filter(section=section)
        }
        for qid in ordered_ids:
            if str(qid) not in questions:
                raise BriefingQuestionNotFoundError(
                    f'Pergunta {qid} não pertence à sessão.'
                )

        for i, qid in enumerate(ordered_ids):
            q = questions[str(qid)]
            q.position = _REORDER_OFFSET + i
            q.save(update_fields=['position'])

        for i, qid in enumerate(ordered_ids):
            q = questions[str(qid)]
            q.position = i + 1
            q.save(update_fields=['position'])

        BriefingTemplateService._log_event(
            template=section.template,
            kind=BriefingTemplateEvent.KIND_QUESTION_REORDERED,
            user=actor,
            section_id=section.id,
            content={'ordered_ids': [str(x) for x in ordered_ids]},
        )

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _attach_reference_documents(
        *, question: BriefingQuestion, document_ids, workspace,
    ) -> None:
        from apps.documents.models import Document
        ids = [str(d) for d in document_ids if d]
        if not ids:
            return
        docs = list(
            Document.objects.filter(id__in=ids, workspace=workspace)
        )
        if docs:
            question.reference_documents.set(docs)