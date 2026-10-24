"""
BriefingTemplateVersionService — ciclo de vida das versões + diff + restauração.

REGRA ARQUITETURAL
------------------
- Uma versão publicada é imutável.
- Alterações estruturais só ocorrem em rascunhos.
- Um rascunho pode ser criado:
    a) vazio (nova versão em branco)
    b) clonando a estrutura atual das tabelas (clone_current)
    c) clonando a estrutura de um briefing já personalizado
    d) RESTAURANDO a estrutura de uma versão existente — que
       SUBSTITUI as tabelas atuais e cria uma nova versão draft
- Ao publicar, a estrutura é congelada em `structure` (JSONB).
- Ao publicar, a versão anterior do mesmo template é arquivada
  automaticamente.
- Excluir uma versão NÃO é permitido para a versão publicada
  atualmente ativa: use unpublish antes.

RESTAURAÇÃO (restore_into_template)
-----------------------------------
Substituição destrutiva da estrutura do modelo pelas seções/perguntas
de uma versão de origem.

REGRAS OBRIGATÓRIAS:
    1. A versão de origem precisa pertencer ao mesmo template.
    2. Se o template estiver `published`, é DESPUBLICADO
       automaticamente antes da substituição. O arquiteto confirma
       essa consequência no modal do frontend.
    3. TODA a validação da estrutura da versão acontece ANTES
       de qualquer exclusão. Se a estrutura for inválida, aborta
       sem tocar no modelo.
    4. Substitui todas as seções e perguntas atuais do template.
    5. Briefings já em execução NÃO são afetados — usam snapshot
       próprio, desacoplado das tabelas do template.
    6. Referências a Documents inexistentes ou de outro workspace
       não bloqueiam. Elas são ignoradas e contabilizadas para o
       relatório ao arquiteto.
    7. Toda a operação é atômica.
    8. Registra evento de auditoria com origem, contadores, refs
       ignoradas e flag `auto_unpublished`.

COMPARADOR (diff)
-----------------
Compara a estrutura "em edição" (o que está nas tabelas
BriefingSection / BriefingQuestion agora) com a última versão
publicada. Usa IDs estáveis (o UUID da seção / pergunta) para
identificar cada elemento.
"""

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.briefings.models import (
    BriefingTemplate,
    BriefingTemplateVersion,
    BriefingSection,
    BriefingQuestion,
    BriefingTemplateEvent,
)
from apps.briefings.exceptions import (
    BriefingError,
    BriefingTemplateNotFoundError,
)

logger = logging.getLogger('briefings')


class BriefingTemplateVersionService:

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_template(template: BriefingTemplate):
        return (
            BriefingTemplateVersion.objects
            .filter(template=template)
            .order_by('-version_number')
        )

    @staticmethod
    def get_or_raise(version_id, template: BriefingTemplate):
        try:
            version = BriefingTemplateVersion.objects.filter(
                id=version_id, template=template,
            ).first()
        except (ValueError, TypeError):
            version = None
        if version is None:
            raise BriefingError('Versão não encontrada.')
        return version

    @staticmethod
    def get_current_published(template: BriefingTemplate):
        return (
            BriefingTemplateVersion.objects
            .filter(
                template=template,
                status=BriefingTemplateVersion.STATUS_PUBLISHED,
            )
            .order_by('-version_number')
            .first()
        )

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_draft_from_template(
        *,
        template: BriefingTemplate,
        actor=None,
        blank: bool = False,
    ) -> BriefingTemplateVersion:
        """
        Cria uma nova versão em rascunho.

        Se `blank=True`, o rascunho nasce vazio.
        Se `blank=False` (padrão), clona a estrutura atual das
        tabelas `BriefingSection`/`BriefingQuestion` ligadas ao
        template lógico.
        """
        next_number = BriefingTemplateVersionService._next_version_number(
            template,
        )

        version = BriefingTemplateVersion.objects.create(
            template=template,
            version_number=next_number,
            status=BriefingTemplateVersion.STATUS_DRAFT,
            structure={},
            created_by=actor,
        )

        if blank:
            version.structure = {
                'snapshot_version': 1,
                'template_name': template.name,
                'sections': [],
            }
        else:
            sections_qs = (
                BriefingSection.objects
                .filter(template=template)
                .prefetch_related('questions__reference_documents')
                .order_by('position', 'created_at')
            )
            version.structure = (
                BriefingTemplateVersionService._build_structure_from_template(
                    template, sections_qs,
                )
            )

        version.save(update_fields=['structure'])
        return version

    @staticmethod
    @transaction.atomic
    def create_draft_from_version(
        *,
        template: BriefingTemplate,
        source_version: BriefingTemplateVersion,
        actor=None,
    ) -> BriefingTemplateVersion:
        """
        [DEPRECATED em favor de `restore_into_template`]

        Cria uma nova versão em rascunho clonando a `structure` de
        uma versão existente — SEM tocar nas tabelas do template.

        Mantida para retrocompatibilidade. A UI atual usa
        `restore_into_template`, que é destrutivo por design.
        """
        if source_version.template_id != template.id:
            raise BriefingError(
                'A versão de origem não pertence a este template.'
            )

        import copy
        next_number = BriefingTemplateVersionService._next_version_number(
            template,
        )

        version = BriefingTemplateVersion.objects.create(
            template=template,
            version_number=next_number,
            status=BriefingTemplateVersion.STATUS_DRAFT,
            structure=copy.deepcopy(source_version.structure or {}),
            created_by=actor,
        )
        return version

    @staticmethod
    @transaction.atomic
    def create_draft_from_briefing(
        *,
        briefing,
        actor=None,
        include_custom_questions: bool = True,
        template: BriefingTemplate = None,
    ) -> BriefingTemplateVersion:
        """
        Cria um rascunho de versão a partir da estrutura de um
        briefing existente. NÃO copia respostas, notas, eventos
        nem dados do cliente.
        """
        if template is None and briefing.template_id is not None:
            template = briefing.template

        next_number = 1
        if template is not None:
            next_number = (
                BriefingTemplateVersionService._next_version_number(template)
            )

        version = BriefingTemplateVersion.objects.create(
            template=template,
            version_number=next_number,
            status=BriefingTemplateVersion.STATUS_DRAFT,
            structure={},
            created_by=actor,
        )

        structure = (
            BriefingTemplateVersionService._build_structure_from_briefing(
                briefing,
                include_custom_questions=include_custom_questions,
            )
        )
        version.structure = structure
        version.save(update_fields=['structure'])
        return version

    # ------------------------------------------------------------------
    # RESTAURAÇÃO — substitui a estrutura do modelo
    # ------------------------------------------------------------------

    @staticmethod
    def restore_into_template(
        *,
        template: BriefingTemplate,
        source_version: BriefingTemplateVersion,
        actor=None,
    ) -> BriefingTemplateVersion:
        """
        Substitui a estrutura atual do modelo (tabelas
        BriefingSection / BriefingQuestion) pela estrutura da versão
        de origem.

        Retorna a NOVA versão em rascunho criada com a estrutura
        restaurada.

        Levanta BriefingError com mensagem clara em caso de:
            - versão de origem pertence a outro template
            - estrutura da versão é inválida

        Se o template estiver `published`, é despublicado
        automaticamente antes da substituição.
        """
        BriefingTemplateVersionService._assert_restore_preconditions(
            template, source_version,
        )
        plan = BriefingTemplateVersionService._build_restore_plan(
            template, source_version,
        )

        return BriefingTemplateVersionService._apply_restore_plan(
            template=template,
            source_version=source_version,
            plan=plan,
            actor=actor,
        )

    # ------------------------------------------------------------------
    # RESTORE — VALIDAÇÃO PRÉVIA (sem tocar no modelo)
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_restore_preconditions(
        template: BriefingTemplate,
        source_version: BriefingTemplateVersion,
    ) -> None:
        """
        Valida as condições para restaurar.

        Não exige `draft` — se o template estiver `published`, a
        restauração vai despublicá-lo automaticamente (a pedido do
        arquiteto, que confirma no modal). Só valida que a versão é
        do mesmo template e que a estrutura é minimamente coerente.
        """
        if source_version.template_id != template.id:
            raise BriefingError(
                'A versão de origem não pertence a este template.'
            )

        if not isinstance(source_version.structure, dict):
            raise BriefingError(
                'A versão de origem não tem estrutura válida.'
            )

        sections = source_version.structure.get('sections')
        if not isinstance(sections, list):
            raise BriefingError(
                'A estrutura da versão não contém uma lista de sessões.'
            )

    @staticmethod
    def _build_restore_plan(
        template: BriefingTemplate,
        source_version: BriefingTemplateVersion,
    ) -> dict:
        """
        Constrói o plano de restauração SEM aplicar nada.

        Valida cada seção/pergunta. Também resolve os
        `reference_document_ids` para uma lista de UUIDs VÁLIDOS
        no workspace atual.

        Retorna um dict:
            {
              'sections': [
                  {
                    'title': str,
                    'description': str,
                    'questions': [
                        {
                          'text': str,
                          'instructions': str,
                          'question_type': str,
                          'allowed_response_formats': [str, ...],
                          'options': [dict, ...],
                          'is_required': bool,
                          'reference_document_ids': [str, ...],
                          'reference_docs_missing': [str, ...],
                        },
                        ...
                    ],
                  },
                  ...
              ],
              'total_questions': int,
              'ignored_references_count': int,
              'ignored_references_by_question': [
                  {
                    'section_title': str,
                    'question_text_preview': str,
                    'missing_ids': [str, ...]
                  },
                  ...
              ],
            }
        """
        raw_sections = source_version.structure.get('sections') or []

        # 1) Coleta TODOS os reference_document_ids para validar de uma vez.
        all_ref_ids = set()
        for s in raw_sections:
            qs = (s or {}).get('questions') or []
            for q in qs:
                if not isinstance(q, dict):
                    continue
                for rid in (q.get('reference_document_ids') or []):
                    if rid:
                        all_ref_ids.add(str(rid))

        valid_doc_ids = set()
        if all_ref_ids:
            from apps.documents.models import Document
            valid_doc_ids = set(
                str(x) for x in Document.objects
                .filter(
                    id__in=list(all_ref_ids),
                    workspace=template.workspace,
                )
                .values_list('id', flat=True)
            )

        # 2) Valida a estrutura + resolve refs. Qualquer erro aqui
        #    levanta BriefingError ANTES de qualquer exclusão.
        plan_sections = []
        total_questions = 0
        ignored_refs_total = 0
        ignored_refs_by_question = []

        # Vocabulários aceitos — congelados aqui para não consultar o
        # model para cada item.
        valid_types = {c[0] for c in BriefingQuestion.QUESTION_TYPE_CHOICES}
        valid_formats = {
            BriefingQuestion.RESPONSE_FORMAT_TEXT,
            BriefingQuestion.RESPONSE_FORMAT_AUDIO,
            BriefingQuestion.RESPONSE_FORMAT_IMAGE,
        }
        default_formats = list(BriefingQuestion.DEFAULT_ALLOWED_FORMATS)

        for s_idx, section in enumerate(raw_sections):
            if not isinstance(section, dict):
                raise BriefingError(
                    f'Sessão #{s_idx + 1} da versão está em formato inválido.'
                )

            title = (
                (section.get('title') or '').strip()
                or f'Sessão {s_idx + 1}'
            )
            description = (section.get('description') or '').strip()

            questions_raw = section.get('questions') or []
            if not isinstance(questions_raw, list):
                raise BriefingError(
                    f'Sessão "{title}" tem "questions" em formato inválido.'
                )

            plan_questions = []
            for q_idx, q in enumerate(questions_raw):
                if not isinstance(q, dict):
                    raise BriefingError(
                        f'Pergunta #{q_idx + 1} da sessão "{title}" '
                        f'está em formato inválido.'
                    )

                text = (q.get('text') or '').strip()
                if not text:
                    raise BriefingError(
                        f'Pergunta #{q_idx + 1} da sessão "{title}" '
                        f'não tem enunciado.'
                    )

                instructions = (q.get('instructions') or '').strip()

                # Tipo: se não estiver no vocabulário atual, cai para 'text'.
                raw_type = (q.get('question_type') or '').strip() or 'text'
                question_type = raw_type if raw_type in valid_types else 'text'

                # Formatos: filtra os válidos; se sobrar vazio, usa default.
                raw_formats = q.get('allowed_response_formats') or []
                if not isinstance(raw_formats, list):
                    raw_formats = []
                formats = [
                    f for f in raw_formats
                    if isinstance(f, str) and f in valid_formats
                ]
                if not formats:
                    formats = list(default_formats)

                # Opções: normaliza.
                raw_options = q.get('options') or []
                if not isinstance(raw_options, list):
                    raw_options = []
                options = []
                for opt in raw_options:
                    if not isinstance(opt, dict):
                        continue
                    opt_text = (opt.get('text') or '').strip()
                    if not opt_text:
                        continue
                    options.append({
                        'text': opt_text,
                        'image_document_id': opt.get('image_document_id') or None,
                    })

                is_required = bool(q.get('is_required', True))

                # Referências: filtra para as válidas; registra as perdidas.
                raw_refs = q.get('reference_document_ids') or []
                if not isinstance(raw_refs, list):
                    raw_refs = []
                refs_valid = []
                refs_missing = []
                for rid in raw_refs:
                    if not rid:
                        continue
                    sid = str(rid)
                    if sid in valid_doc_ids:
                        refs_valid.append(sid)
                    else:
                        refs_missing.append(sid)

                if refs_missing:
                    ignored_refs_total += len(refs_missing)
                    ignored_refs_by_question.append({
                        'section_title': title,
                        'question_text_preview': text[:80],
                        'missing_ids': refs_missing,
                    })

                plan_questions.append({
                    'text': text,
                    'instructions': instructions,
                    'question_type': question_type,
                    'allowed_response_formats': formats,
                    'options': options,
                    'is_required': is_required,
                    'reference_document_ids': refs_valid,
                    'reference_docs_missing': refs_missing,
                })
                total_questions += 1

            plan_sections.append({
                'title': title,
                'description': description,
                'questions': plan_questions,
            })

        return {
            'sections': plan_sections,
            'total_questions': total_questions,
            'ignored_references_count': ignored_refs_total,
            'ignored_references_by_question': ignored_refs_by_question,
        }

    # ------------------------------------------------------------------
    # RESTORE — APLICAÇÃO (depois da validação)
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def _apply_restore_plan(
        *,
        template: BriefingTemplate,
        source_version: BriefingTemplateVersion,
        plan: dict,
        actor=None,
    ) -> BriefingTemplateVersion:
        """
        Executa a substituição. Só chega aqui se o plano é válido.

        Se o template estava `published`, ele é despublicado
        automaticamente ANTES de substituir a estrutura. Briefings
        em execução NÃO são afetados (usam snapshot próprio).
        """
        was_published = (
            template.status == BriefingTemplate.STATUS_PUBLISHED
        )

        # 1) Despublica se necessário (antes de mexer na estrutura).
        if was_published:
            template.status = BriefingTemplate.STATUS_DRAFT
            template.save(update_fields=['status', 'updated_at'])

        # 2) Apaga a estrutura atual.
        #    - BriefingSection cascateia para BriefingQuestion.
        #    - BriefingQuestion tem M2M para Document: apenas as linhas
        #      da tabela pivô são removidas; os Documents permanecem.
        #    - Nenhuma outra tabela referencia BriefingSection/Question
        #      diretamente (as execuções usam JSON snapshot).
        BriefingSection.objects.filter(template=template).delete()

        # 3) Recria a partir do plano validado.
        sections_created = 0
        questions_created = 0

        from apps.documents.models import Document

        for s_idx, sec in enumerate(plan['sections'], start=1):
            section = BriefingSection.objects.create(
                template=template,
                title=sec['title'],
                description=sec['description'],
                position=s_idx,
            )
            sections_created += 1

            for q_idx, q in enumerate(sec['questions'], start=1):
                question = BriefingQuestion.objects.create(
                    section=section,
                    text=q['text'],
                    instructions=q['instructions'],
                    question_type=q['question_type'],
                    allowed_response_formats=list(q['allowed_response_formats']),
                    options=list(q['options']),
                    position=q_idx,
                    is_required=q['is_required'],
                )
                questions_created += 1

                ref_ids = q['reference_document_ids']
                if ref_ids:
                    docs = list(
                        Document.objects.filter(
                            id__in=ref_ids,
                            workspace=template.workspace,
                        )
                    )
                    if docs:
                        question.reference_documents.set(docs)

        # 4) Cria uma nova versão em rascunho refletindo o estado restaurado.
        new_version = (
            BriefingTemplateVersionService.create_draft_from_template(
                template=template, actor=actor,
            )
        )

        # 5) Auditoria — nunca interrompe a operação se falhar.
        try:
            BriefingTemplateEvent.objects.create(
                template=template,
                kind=BriefingTemplateEvent.KIND_TEMPLATE_UPDATED,
                content={
                    'action': 'restore_from_version',
                    'source_version_id': str(source_version.id),
                    'source_version_number': source_version.version_number,
                    'new_version_id': str(new_version.id),
                    'sections_created': sections_created,
                    'questions_created': questions_created,
                    'ignored_references_count': (
                        plan['ignored_references_count']
                    ),
                    'ignored_references_by_question': (
                        plan['ignored_references_by_question']
                    ),
                    'auto_unpublished': was_published,
                },
                user=actor if (
                    actor and getattr(actor, 'is_authenticated', False)
                ) else None,
            )
        except Exception:
            logger.exception(
                'Falha ao gravar evento de auditoria de restauração'
            )

        return new_version

    # ------------------------------------------------------------------
    # PUBLICAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def publish(
        *,
        version: BriefingTemplateVersion,
        actor=None,
    ) -> BriefingTemplateVersion:
        """
        Publica a versão:
            1. Valida que está em rascunho.
            2. Congela a estrutura atual.
            3. Arquiva a versão publicada anterior.
            4. Marca a nova como publicada.
        """
        if version.status != BriefingTemplateVersion.STATUS_DRAFT:
            raise BriefingError(
                'Só versões em rascunho podem ser publicadas.'
            )

        if not version.structure or not version.structure.get('sections'):
            raise BriefingError(
                'A versão não tem estrutura para publicar.'
            )

        if version.template_id is not None:
            (
                BriefingTemplateVersion.objects
                .filter(
                    template=version.template,
                    status=BriefingTemplateVersion.STATUS_PUBLISHED,
                )
                .exclude(pk=version.pk)
                .update(
                    status=BriefingTemplateVersion.STATUS_ARCHIVED,
                    updated_at=timezone.now(),
                )
            )

        version.status = BriefingTemplateVersion.STATUS_PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=['status', 'published_at', 'updated_at'])
        return version

    # ------------------------------------------------------------------
    # EXCLUSÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def delete(
        *,
        version: BriefingTemplateVersion,
        actor=None,
    ) -> None:
        """
        Exclui uma versão.

        NÃO permite excluir a versão atualmente publicada. Para isso
        o usuário precisa despublicar o template antes.

        Rascunhos e versões arquivadas podem ser excluídos livremente.
        """
        if version.status == BriefingTemplateVersion.STATUS_PUBLISHED:
            raise BriefingError(
                'Não é possível excluir a versão publicada atualmente. '
                'Despublique o modelo antes.'
            )

        version.delete()

    # ------------------------------------------------------------------
    # DIFF — comparador
    # ------------------------------------------------------------------

    @staticmethod
    def diff_against_published(template: BriefingTemplate) -> dict:
        published = (
            BriefingTemplateVersionService.get_current_published(template)
        )

        current_structure = (
            BriefingTemplateVersionService
            ._build_structure_from_template(
                template,
                BriefingSection.objects
                    .filter(template=template)
                    .prefetch_related('questions__reference_documents')
                    .order_by('position', 'created_at'),
            )
        )

        baseline = (published.structure if published else {}) or {}

        return BriefingTemplateVersionService._diff_structures(
            baseline,
            current_structure,
            base_version_number=(
                published.version_number if published else None
            ),
        )

    @staticmethod
    def _diff_structures(
        base: dict, current: dict, *, base_version_number: Optional[int] = None,
    ) -> dict:
        base_sections = {
            str(s.get('id')): s for s in (base.get('sections') or [])
        }
        cur_sections = {
            str(s.get('id')): s for s in (current.get('sections') or [])
        }

        sec_added, sec_removed, sec_renamed = [], [], []
        for sid, s in cur_sections.items():
            if sid not in base_sections:
                sec_added.append({
                    'id': sid,
                    'title': s.get('title', ''),
                })

        for sid, s in base_sections.items():
            if sid not in cur_sections:
                sec_removed.append({
                    'id': sid,
                    'title': s.get('title', ''),
                })

        for sid, s in cur_sections.items():
            if sid in base_sections:
                old_title = base_sections[sid].get('title', '')
                new_title = s.get('title', '')
                if old_title != new_title:
                    sec_renamed.append({
                        'id': sid,
                        'from': old_title,
                        'to': new_title,
                    })

        cur_order = [
            str(s.get('id')) for s in (current.get('sections') or [])
            if str(s.get('id')) in base_sections
        ]
        base_order = [
            str(s.get('id')) for s in (base.get('sections') or [])
            if str(s.get('id')) in cur_sections
        ]
        sec_reordered = []
        for i, sid in enumerate(cur_order):
            if i < len(base_order) and base_order[i] != sid:
                sec_reordered.append({
                    'id': sid,
                    'from': base_order.index(sid) if sid in base_order else -1,
                    'to': i,
                })

        base_questions = BriefingTemplateVersionService._flatten_questions(
            base
        )
        cur_questions = BriefingTemplateVersionService._flatten_questions(
            current
        )

        q_added, q_removed, q_changed = [], [], []
        for qid, q in cur_questions.items():
            if qid not in base_questions:
                q_added.append({
                    'id': qid,
                    'text': q.get('text', ''),
                    'section_id': q.get('_section_id'),
                })

        for qid, q in base_questions.items():
            if qid not in cur_questions:
                q_removed.append({
                    'id': qid,
                    'text': q.get('text', ''),
                    'section_id': q.get('_section_id'),
                })

        WATCHED = (
            'text',
            'instructions',
            'question_type',
            'allowed_response_formats',
            'is_required',
            'options',
        )

        for qid, new_q in cur_questions.items():
            old_q = base_questions.get(qid)
            if not old_q:
                continue
            changes = {}
            for field in WATCHED:
                old_val = old_q.get(field)
                new_val = new_q.get(field)
                if old_val != new_val:
                    changes[field] = {'from': old_val, 'to': new_val}
            if changes:
                q_changed.append({
                    'id': qid,
                    'text': new_q.get('text', ''),
                    'section_id': new_q.get('_section_id'),
                    'changes': changes,
                })

        q_reordered = []
        cur_q_order = list(cur_questions.keys())
        base_q_order = list(base_questions.keys())
        for i, qid in enumerate(cur_q_order):
            if qid in base_questions:
                old_idx = base_q_order.index(qid)
                if old_idx != i:
                    q_reordered.append({
                        'id': qid,
                        'from': old_idx,
                        'to': i,
                    })

        summary = {
            'sections_added': len(sec_added),
            'sections_removed': len(sec_removed),
            'sections_renamed': len(sec_renamed),
            'sections_reordered': len(sec_reordered),
            'questions_added': len(q_added),
            'questions_removed': len(q_removed),
            'questions_changed': len(q_changed),
            'questions_reordered': len(q_reordered),
        }
        summary['total_changes'] = sum(summary.values())

        return {
            'base_version': base_version_number,
            'has_baseline': base_version_number is not None,
            'sections': {
                'added': sec_added,
                'removed': sec_removed,
                'renamed': sec_renamed,
                'reordered': sec_reordered,
            },
            'questions': {
                'added': q_added,
                'removed': q_removed,
                'changed': q_changed,
                'reordered': q_reordered,
            },
            'summary': summary,
        }

    @staticmethod
    def _flatten_questions(structure: dict) -> dict:
        result = {}
        sections = sorted(
            (structure.get('sections') or []),
            key=lambda s: s.get('position', 0),
        )
        for sec in sections:
            sid = str(sec.get('id'))
            questions = sorted(
                (sec.get('questions') or []),
                key=lambda q: q.get('position', 0),
            )
            for q in questions:
                qid = str(q.get('id'))
                result[qid] = {
                    **q,
                    '_section_id': sid,
                    '_section_title': sec.get('title', ''),
                }
        return result

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _next_version_number(template: BriefingTemplate) -> int:
        last = (
            BriefingTemplateVersion.objects
            .filter(template=template)
            .order_by('-version_number')
            .values_list('version_number', flat=True)
            .first()
        )
        return (last or 0) + 1

    @staticmethod
    def _build_structure_from_template(template, sections_qs) -> dict:
        sections = list(sections_qs)
        payload_sections = []
        for section in sections:
            payload_questions = []
            for q in section.questions.order_by('position', 'created_at'):
                payload_questions.append({
                    'id': str(q.id),
                    'text': q.text,
                    'instructions': q.instructions,
                    'question_type': q.question_type,
                    'allowed_response_formats': list(
                        q.allowed_response_formats or []
                    ),
                    'options': list(q.options or []),
                    'position': q.position,
                    'is_required': bool(q.is_required),
                    'reference_document_ids': [
                        str(d.id)
                        for d in q.reference_documents.all()
                    ],
                    'is_custom': False,
                })
            payload_sections.append({
                'id': str(section.id),
                'title': section.title,
                'description': section.description,
                'position': section.position,
                'questions': payload_questions,
            })
        return {
            'snapshot_version': 1,
            'template_name': template.name,
            'sections': payload_sections,
        }

    @staticmethod
    def _build_structure_from_briefing(
        briefing, *, include_custom_questions: bool = True,
    ) -> dict:
        snapshot = briefing.structure_snapshot or {}
        raw_sections = sorted(
            snapshot.get('sections', []),
            key=lambda s: s.get('position', 0),
        )

        new_sections = []
        for s in raw_sections:
            new_questions = []
            for q in sorted(
                s.get('questions', []),
                key=lambda x: x.get('position', 0),
            ):
                if q.get('is_custom') and not include_custom_questions:
                    continue
                new_q = {
                    'id': str(q.get('id')),
                    'text': q.get('text', ''),
                    'instructions': q.get('instructions', ''),
                    'question_type': q.get('question_type', 'text'),
                    'allowed_response_formats': list(
                        q.get('allowed_response_formats') or []
                    ),
                    'options': list(q.get('options') or []),
                    'position': len(new_questions) + 1,
                    'is_required': bool(q.get('is_required', True)),
                    'reference_document_ids': list(
                        q.get('reference_document_ids') or []
                    ),
                    'is_custom': False,
                }
                new_questions.append(new_q)

            new_sections.append({
                'id': str(s.get('id')),
                'title': s.get('title', ''),
                'description': s.get('description', ''),
                'position': len(new_sections) + 1,
                'questions': new_questions,
            })

        return {
            'snapshot_version': 1,
            'template_name': snapshot.get('template_name', briefing.title),
            'sections': new_sections,
        }