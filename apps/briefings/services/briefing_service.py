"""
BriefingService — ciclo de vida da execução.

REGRA ARQUITETURAL
------------------
Toda mutação passa por este service.

DOIS BLOCOS DE PERGUNTAS
------------------------
O briefing tem dois blocos independentes de perguntas:

    1. structure_snapshot      → bloco original, congelado no primeiro
                                 congelamento após primeira resposta.
    2. supplementary_snapshot  → bloco complementar, reconstruído a
                                 cada adição/remoção de
                                 BriefingQuestionInstance.

O `status` do Briefing refere-se ao BLOCO ORIGINAL. O estado do
bloco complementar é controlado por `supplementary_completed_at`.

INTRO
-----
`intro_message` é copiada do template na criação. O cliente pode
"consumir" a intro uma vez (via `mark_intro_seen`), e a partir daí
ela não aparece mais.
"""

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.briefings.models import (
    Briefing,
    BriefingAnswer,
    BriefingEvent,
    BriefingTemplate,
    BriefingTemplateVersion,
    BriefingQuestionInstance,
)
from apps.briefings.exceptions import (
    BriefingError,
    BriefingNotFoundError,
    BriefingClosedError,
    BriefingExpiredError,
    BriefingPausedError,
    InvalidQuestionSequenceError,
    InvalidResponseFormatError,
    BriefingReopenError,
)
from apps.briefings.services.event_service import BriefingEventService

logger = logging.getLogger('briefings')


class BriefingService:

    # ==================================================================
    # CRIAÇÃO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def create_briefing(
        *,
        template: BriefingTemplate,
        client,
        workspace,
        actor=None,
        expires_at=None,
        title: Optional[str] = None,
        intro_message: Optional[str] = None,
    ) -> Briefing:
        if template.workspace_id != workspace.id:
            raise BriefingError('Template não pertence a este workspace.')
        if client.workspace_id != workspace.id:
            raise BriefingError('Cliente não pertence a este workspace.')

        if template.status != BriefingTemplate.STATUS_PUBLISHED:
            raise BriefingError(
                'Só templates publicados podem originar execuções.'
            )

        if not template.sections.exists():
            raise BriefingError(
                'O template não possui sessões para executar.'
            )

        from apps.briefings.services.template_version_service import (
            BriefingTemplateVersionService,
        )
        current_version = (
            BriefingTemplateVersionService.get_current_published(template)
        )

        snapshot = BriefingService._build_structure_snapshot(
            template, version=current_version,
        )

        if intro_message is not None:
            resolved_intro = (intro_message or '').strip()
        else:
            resolved_intro = (template.intro_message or '').strip()

        briefing = Briefing.objects.create(
            workspace=workspace,
            client=client,
            template=template,
            template_version=current_version,
            title=(title or template.name).strip(),
            structure_snapshot=snapshot,
            supplementary_snapshot={},
            intro_message=resolved_intro,
            status=Briefing.STATUS_IN_PROGRESS,
            expires_at=expires_at,
            created_by=actor,
        )

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_REOPENED,
            user=actor,
            content={
                'action': 'created',
                'template_id': str(template.id),
                'template_version_id': (
                    str(current_version.id) if current_version else None
                ),
                'expires_at': (
                    expires_at.isoformat() if expires_at else None
                ),
            },
        )

        return briefing

    @staticmethod
    def _build_structure_snapshot(
        template: BriefingTemplate,
        version: Optional[BriefingTemplateVersion] = None,
    ) -> dict:
        if version and version.structure and version.structure.get('sections'):
            import copy
            data = copy.deepcopy(version.structure)
            for s in data.get('sections', []):
                for q in s.get('questions', []):
                    q['is_custom'] = False
            return data

        sections = list(
            template.sections
            .prefetch_related('questions__reference_documents')
            .order_by('position', 'created_at')
        )

        payload_sections = []
        for section in sections:
            payload_questions = []
            for question in section.questions.order_by(
                'position', 'created_at',
            ):
                payload_questions.append({
                    'id': str(question.id),
                    'text': question.text,
                    'instructions': question.instructions,
                    'question_type': question.question_type,
                    'allowed_response_formats': list(
                        question.allowed_response_formats or []
                    ),
                    'options': list(question.options or []),
                    'position': question.position,
                    'is_required': question.is_required,
                    'reference_document_ids': [
                        str(d.id)
                        for d in question.reference_documents.all()
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

    # ==================================================================
    # INTRO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def mark_intro_seen(briefing: Briefing) -> Briefing:
        if not briefing.has_intro():
            return briefing
        briefing.mark_intro_seen()
        return briefing

    @staticmethod
    @transaction.atomic
    def mark_viewed(briefing: Briefing) -> Briefing:
        briefing.mark_viewed()
        return briefing

    # ==================================================================
    # SNAPSHOTS — CUSTOM QUESTIONS
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def freeze_custom_questions_into_snapshot(briefing: Briefing) -> bool:
        """
        Congela custom questions no bloco ORIGINAL.

        Só roda enquanto o briefing não tem respostas. Depois disso,
        o bloco original está fechado e custom questions vão para o
        bloco complementar.
        """
        if briefing.answers.exists():
            return False

        custom_qs = list(
            BriefingQuestionInstance.objects
            .filter(briefing=briefing)
            .order_by('section_ref', 'position', 'created_at')
        )
        if not custom_qs:
            return False

        snapshot = dict(briefing.structure_snapshot or {})
        sections = list(snapshot.get('sections', []))
        sections_by_id = {str(s.get('id')): s for s in sections}

        for inst in custom_qs:
            section = sections_by_id.get(str(inst.section_ref))
            if section is None:
                continue
            questions = list(section.get('questions', []))
            already = any(
                str(q.get('id')) == str(inst.id) for q in questions
            )
            if already:
                continue
            questions.append(inst.to_snapshot_dict())
            section['questions'] = questions

        snapshot['sections'] = sections
        briefing.structure_snapshot = snapshot
        briefing.has_custom_questions = True
        briefing.save(update_fields=[
            'structure_snapshot', 'has_custom_questions', 'updated_at',
        ])
        return True

    @staticmethod
    @transaction.atomic
    def freeze_supplementary_questions_into_snapshot(briefing: Briefing) -> bool:
        """
        Reconstrói o bloco COMPLEMENTAR a partir das
        BriefingQuestionInstance.

        Roda em qualquer momento. NÃO toca em structure_snapshot.

        Marca `frozen_in_supplementary_snapshot_at` em cada instância
        que entrou no snapshot complementar.
        """
        custom_qs = list(
            BriefingQuestionInstance.objects
            .filter(briefing=briefing)
            .order_by('section_ref', 'position', 'created_at')
        )

        sections_by_ref = {}
        for inst in custom_qs:
            sections_by_ref.setdefault(str(inst.section_ref), []).append(inst)

        snapshot_sections = []
        for section_ref, instances in sections_by_ref.items():
            question_payloads = [inst.to_snapshot_dict() for inst in instances]
            snapshot_sections.append({
                'id': str(section_ref),
                'title': 'Perguntas complementares',
                'description': '',
                'position': 0,
                'questions': question_payloads,
            })

        new_snapshot = {
            'snapshot_version': 1,
            'sections': snapshot_sections,
        }

        changed = briefing.supplementary_snapshot != new_snapshot
        if changed:
            briefing.supplementary_snapshot = new_snapshot
            briefing.save(update_fields=[
                'supplementary_snapshot', 'updated_at',
            ])

        now = timezone.now()
        for inst in custom_qs:
            if inst.frozen_in_supplementary_snapshot_at is None:
                inst.frozen_in_supplementary_snapshot_at = now
                inst.save(update_fields=[
                    'frozen_in_supplementary_snapshot_at', 'updated_at',
                ])

        return changed

    @staticmethod
    @transaction.atomic
    def sync_snapshot_references(briefing: Briefing) -> bool:
        if briefing.answers.exists():
            return False

        if briefing.template_id is None:
            return False

        snapshot = dict(briefing.structure_snapshot or {})
        sections = list(snapshot.get('sections', []))
        if not sections:
            return False

        from apps.briefings.models import BriefingQuestion

        current_refs = {}
        for q in (
            BriefingQuestion.objects
            .filter(section__template_id=briefing.template_id)
            .prefetch_related('reference_documents')
        ):
            current_refs[str(q.id)] = [
                str(d.id) for d in q.reference_documents.all()
            ]

        changed = False
        for section in sections:
            for q in section.get('questions', []):
                qid = str(q.get('id'))
                if q.get('is_custom'):
                    continue
                new_ids = current_refs.get(qid)
                if new_ids is None:
                    continue
                old_ids = list(q.get('reference_document_ids') or [])
                if old_ids != new_ids:
                    q['reference_document_ids'] = new_ids
                    changed = True

        if changed:
            snapshot['sections'] = sections
            briefing.structure_snapshot = snapshot
            briefing.save(update_fields=[
                'structure_snapshot', 'updated_at',
            ])
            logger.info(
                'Snapshot references sincronizadas | briefing=%s',
                briefing.id,
            )

        return changed

    # ==================================================================
    # LEITURA / PROGRESSO
    # ==================================================================

    @staticmethod
    def get_or_raise(briefing_id, workspace) -> Briefing:
        try:
            briefing = (
                Briefing.objects
                .filter(id=briefing_id, workspace=workspace)
                .first()
            )
        except (ValueError, TypeError):
            briefing = None
        if briefing is None:
            raise BriefingNotFoundError('Briefing não encontrado.')
        return briefing

    @staticmethod
    def compute_progress(briefing: Briefing) -> dict:
        """
        Progresso em três blocos + campos planos por compatibilidade.

        Os campos planos no topo (`total_required`, `answered`, etc.)
        refletem o BLOCO ORIGINAL e são mantidos para não quebrar
        consumidores existentes (export_service, BriefingListSerializer,
        BriefingDetailSerializer, PortalBriefingSerializer).

        Os blocos `original`, `supplementary` e `overall` são novos e
        coexistem com os planos.
        """
        original = BriefingService._compute_progress_block(
            briefing=briefing,
            questions=briefing.snapshot_questions(),
        )
        supplementary = BriefingService._compute_progress_block(
            briefing=briefing,
            questions=briefing.supplementary_questions(),
        )

        overall_complete = (
            original['percent'] >= 100.0
            and supplementary.get('never_answered', 0) == 0
            and supplementary.get('pending_review', 0) == 0
        )

        return {
            'total_required': original['total_required'],
            'answered': original['answered'],
            'pending_review': original['pending_review'],
            'never_answered': original['never_answered'],
            'percent': original['percent'],
            'needs_attention': (
                original['needs_attention']
                or supplementary['needs_attention']
            ),
            'original': original,
            'supplementary': supplementary,
            'overall': {
                'is_fully_complete': overall_complete,
                'has_supplementary_pending': (
                    supplementary['never_answered'] > 0
                    or supplementary['pending_review'] > 0
                ),
            },
        }

    @staticmethod
    def _compute_progress_block(*, briefing, questions) -> dict:
        required_ids = [
            str(q['id']) for q in questions if q.get('is_required')
        ]
        total_required = len(required_ids)

        answers = {
            str(a.question_id): a
            for a in BriefingAnswer.objects.filter(briefing=briefing)
        }

        answered = 0
        pending_review = 0
        never_answered = 0

        for qid in required_ids:
            answer = answers.get(qid)
            if answer is None or answer.state == BriefingAnswer.STATE_PENDING:
                never_answered += 1
            elif answer.state == BriefingAnswer.STATE_ANSWERED:
                answered += 1
            elif answer.state in (
                BriefingAnswer.STATE_PENDING_CLARIFICATION,
                BriefingAnswer.STATE_REVIEW_REQUESTED,
            ):
                pending_review += 1

        percent = (
            round((answered / total_required) * 100, 2)
            if total_required > 0 else 0.0
        )

        return {
            'total_required': total_required,
            'answered': answered,
            'pending_review': pending_review,
            'never_answered': never_answered,
            'percent': percent,
            'needs_attention': pending_review > 0,
        }

    # ==================================================================
    # RESPOSTA
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def submit_answer(
        *,
        briefing_id,
        portal_session,
        question_id,
        content_text: str = '',
        audio_document=None,
        attachment_documents=None,
    ) -> BriefingAnswer:
        briefing = (
            Briefing.objects
            .select_for_update()
            .filter(id=briefing_id)
            .select_related('client', 'workspace')
            .first()
        )
        if briefing is None:
            raise BriefingNotFoundError('Briefing não encontrado.')

        if (
            portal_session is None
            or portal_session.client_id != briefing.client_id
        ):
            raise BriefingNotFoundError('Briefing não encontrado.')

        if briefing.status == Briefing.STATUS_PAUSED:
            raise BriefingPausedError('O briefing está pausado.')

        if briefing.has_expired():
            if briefing.status != Briefing.STATUS_CANCELLED:
                briefing.status = Briefing.STATUS_CANCELLED
                briefing.cancelled_at = timezone.now()
                briefing.save(update_fields=[
                    'status', 'cancelled_at', 'updated_at',
                ])
            raise BriefingExpiredError('O briefing expirou.')

        if briefing.status == Briefing.STATUS_CANCELLED:
            raise BriefingClosedError('O briefing foi cancelado.')

        # Se está `completed` no bloco original, só aceita resposta
        # se a pergunta alvo estiver no bloco COMPLEMENTAR.
        target_in_supplementary = briefing.supplementary_question_by_id(
            question_id,
        ) is not None

        if briefing.status == Briefing.STATUS_COMPLETED and not target_in_supplementary:
            raise BriefingError('O briefing já foi concluído.')

        BriefingService.freeze_custom_questions_into_snapshot(briefing)
        BriefingService.freeze_supplementary_questions_into_snapshot(briefing)
        BriefingService.sync_snapshot_references(briefing)
        briefing.refresh_from_db(
            fields=[
                'structure_snapshot',
                'supplementary_snapshot',
                'has_custom_questions',
            ],
        )

        next_question = BriefingService.get_next_eligible_question(briefing)
        if next_question is None:
            raise BriefingError('Não há perguntas pendentes.')
        if str(next_question['id']) != str(question_id):
            raise InvalidQuestionSequenceError(
                'Você só pode responder à próxima pergunta da sequência.'
            )

        allowed = set(next_question.get('allowed_response_formats') or [])
        content_text_clean = (content_text or '').strip()
        has_text = bool(content_text_clean)
        has_audio = audio_document is not None
        has_attachments = bool(attachment_documents)

        logger.debug(
            'submit_answer validation | q=%s | allowed=%s | '
            'has_text=%s | has_audio=%s | has_attachments=%s',
            next_question['id'], sorted(allowed),
            has_text, has_audio, has_attachments,
        )

        if has_text and 'text' not in allowed:
            raise InvalidResponseFormatError(
                'Esta pergunta não aceita resposta por texto.'
            )
        if has_audio and 'audio' not in allowed:
            raise InvalidResponseFormatError(
                'Esta pergunta não aceita resposta por áudio.'
            )
        if has_attachments and 'image' not in allowed:
            raise InvalidResponseFormatError(
                'Esta pergunta não aceita anexos de imagem.'
            )
        if not (has_text or has_audio or has_attachments):
            raise InvalidResponseFormatError(
                'Envie um texto, um áudio ou uma imagem.'
            )

        content_payload = {
            'text': content_text_clean or None,
            'audio_document_id': (
                str(audio_document.id) if audio_document else None
            ),
            'attachment_document_ids': [
                str(d.id) for d in (attachment_documents or [])
            ],
            'is_custom': bool(next_question.get('is_custom')),
            'is_supplementary': bool(target_in_supplementary),
        }

        event = BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_ANSWERED,
            portal_session=portal_session,
            question_id=next_question['id'],
            content=content_payload,
        )

        answer, _ = BriefingAnswer.objects.select_for_update().get_or_create(
            briefing=briefing,
            question_id=next_question['id'],
            defaults={'state': BriefingAnswer.STATE_ANSWERED},
        )
        answer.state = BriefingAnswer.STATE_ANSWERED
        answer.latest_content = content_text_clean
        answer.latest_event = event

        if audio_document is not None:
            answer.latest_audio = audio_document
            answer.transcription_status = BriefingAnswer.TRANSCRIPTION_PENDING
            answer.latest_transcription = ''
        else:
            answer.latest_audio = None
            answer.transcription_status = (
                BriefingAnswer.TRANSCRIPTION_NOT_APPLICABLE
            )
            answer.latest_transcription = ''

        answer.save()

        logger.info(
            'Answer saved | briefing=%s | q=%s | state=%s | '
            'has_text=%s | has_audio=%s | attachments=%d | supplementary=%s',
            briefing.id, next_question['id'], answer.state,
            bool(content_text_clean), bool(audio_document),
            len(attachment_documents or []),
            target_in_supplementary,
        )

        if attachment_documents:
            answer.attachments.set(attachment_documents)

        if target_in_supplementary:
            if BriefingService._all_supplementary_required_answered(briefing):
                briefing.mark_supplementary_completed()
                BriefingEventService.log(
                    briefing=briefing,
                    kind=BriefingEvent.KIND_SUPPLEMENTARY_COMPLETED,
                    portal_session=portal_session,
                    content={'auto': True},
                )
        else:
            if BriefingService._all_required_answered(briefing):
                briefing.status = Briefing.STATUS_COMPLETED
                briefing.completed_at = timezone.now()
                briefing.save(update_fields=[
                    'status', 'completed_at', 'updated_at',
                ])
                BriefingEventService.log(
                    briefing=briefing,
                    kind=BriefingEvent.KIND_COMPLETED,
                    portal_session=portal_session,
                    content={'auto': True},
                )

                from django.db import transaction as _tx
                _briefing_id = briefing.id
                _tx.on_commit(
                    lambda: BriefingService._schedule_completion_notification(
                        _briefing_id,
                    )
                )

        if audio_document is not None:
            try:
                from django.db import transaction as _tx
                _tx.on_commit(
                    lambda: BriefingService._schedule_transcription(
                        answer.id,
                    )
                )
            except Exception:
                logger.exception('Falha ao agendar transcrição')

        return answer

    # ==================================================================
    # FLUXO
    # ==================================================================

    @staticmethod
    def get_next_eligible_question(briefing: Briefing) -> Optional[dict]:
        answers = {
            str(a.question_id): a
            for a in BriefingAnswer.objects.filter(briefing=briefing)
        }

        # 1. Bloco original
        for q in briefing.snapshot_questions():
            if not q.get('is_required'):
                continue
            answer = answers.get(str(q['id']))
            if answer is None:
                return q
            if answer.state in (
                BriefingAnswer.STATE_PENDING,
                BriefingAnswer.STATE_REVIEW_REQUESTED,
                BriefingAnswer.STATE_PENDING_CLARIFICATION,
            ):
                return q

        # 2. Bloco complementar
        for q in briefing.supplementary_questions():
            if not q.get('is_required'):
                continue
            answer = answers.get(str(q['id']))
            if answer is None:
                return q
            if answer.state in (
                BriefingAnswer.STATE_PENDING,
                BriefingAnswer.STATE_REVIEW_REQUESTED,
                BriefingAnswer.STATE_PENDING_CLARIFICATION,
            ):
                return q

        return None

    @staticmethod
    def _all_required_answered(briefing: Briefing) -> bool:
        questions = briefing.snapshot_questions()
        required_ids = {
            str(q['id']) for q in questions if q.get('is_required')
        }
        if not required_ids:
            return True
        answered_ids = set(
            str(a.question_id)
            for a in BriefingAnswer.objects.filter(
                briefing=briefing,
                state=BriefingAnswer.STATE_ANSWERED,
            )
        )
        return required_ids.issubset(answered_ids)

    @staticmethod
    def _all_supplementary_required_answered(briefing: Briefing) -> bool:
        questions = briefing.supplementary_questions()
        required_ids = {
            str(q['id']) for q in questions if q.get('is_required')
        }
        if not required_ids:
            return True
        answered_ids = set(
            str(a.question_id)
            for a in BriefingAnswer.objects.filter(
                briefing=briefing,
                state=BriefingAnswer.STATE_ANSWERED,
            )
        )
        return required_ids.issubset(answered_ids)

    # ==================================================================
    # AÇÕES DO ARQUITETO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def pause(*, briefing: Briefing, actor) -> Briefing:
        if briefing.status != Briefing.STATUS_IN_PROGRESS:
            raise BriefingError(
                'Só é possível pausar briefings em andamento.'
            )
        briefing.status = Briefing.STATUS_PAUSED
        briefing.save(update_fields=['status', 'updated_at'])
        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_PAUSED,
            user=actor,
        )
        return briefing

    @staticmethod
    @transaction.atomic
    def resume(*, briefing: Briefing, actor) -> Briefing:
        if briefing.status != Briefing.STATUS_PAUSED:
            raise BriefingError(
                'Só é possível retomar briefings pausados.'
            )
        if briefing.has_expired():
            raise BriefingExpiredError(
                'O briefing expirou. Reabra com um novo prazo.'
            )
        briefing.status = Briefing.STATUS_IN_PROGRESS
        briefing.save(update_fields=['status', 'updated_at'])
        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_RESUMED,
            user=actor,
        )
        return briefing

    @staticmethod
    @transaction.atomic
    def cancel(*, briefing: Briefing, actor) -> Briefing:
        if briefing.status == Briefing.STATUS_CANCELLED:
            return briefing
        briefing.status = Briefing.STATUS_CANCELLED
        briefing.cancelled_at = timezone.now()
        briefing.save(update_fields=[
            'status', 'cancelled_at', 'updated_at',
        ])
        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_CLOSED,
            user=actor,
            content={'reason': 'architect_cancelled'},
        )
        return briefing

    @staticmethod
    @transaction.atomic
    def close(*, briefing: Briefing, actor) -> Briefing:
        return BriefingService.cancel(briefing=briefing, actor=actor)

    @staticmethod
    @transaction.atomic
    def reopen(
        *,
        briefing: Briefing,
        actor,
        new_expires_at=None,
        reason: str = '',
    ) -> Briefing:
        allowed_states = {
            Briefing.STATUS_PAUSED,
            Briefing.STATUS_CANCELLED,
            Briefing.STATUS_COMPLETED,
        }
        if briefing.status not in allowed_states:
            raise BriefingReopenError(
                f'Não é possível reabrir um briefing no estado '
                f'"{briefing.status}".'
            )

        needs_new_deadline = (
            briefing.status == Briefing.STATUS_CANCELLED
            and briefing.has_expired()
        )
        if needs_new_deadline and new_expires_at is None:
            raise BriefingReopenError(
                'O briefing expirou. Informe um novo prazo para reabri-lo.'
            )

        if new_expires_at is not None:
            if new_expires_at <= timezone.now():
                raise BriefingReopenError(
                    'O novo prazo precisa ser no futuro.'
                )
            briefing.expires_at = new_expires_at

        briefing.status = Briefing.STATUS_IN_PROGRESS
        briefing.cancelled_at = None
        briefing.completed_at = None
        briefing.save(update_fields=[
            'status', 'cancelled_at', 'completed_at',
            'expires_at', 'updated_at',
        ])

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_REOPENED,
            user=actor,
            content={
                'reason': reason or '',
                'new_expires_at': (
                    new_expires_at.isoformat() if new_expires_at else None
                ),
            },
        )
        return briefing

    # ==================================================================
    # DÚVIDA / REVISÃO (portal)
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def request_clarification(
        *,
        briefing: Briefing,
        portal_session,
        question_id,
        message: str,
    ) -> BriefingAnswer:
        message = (message or '').strip()
        if not message:
            raise BriefingError('Escreva sua dúvida.')

        answer = BriefingAnswer.objects.select_for_update().filter(
            briefing=briefing, question_id=question_id,
        ).first()
        if answer is None:
            raise BriefingError(
                'Só é possível tirar dúvida sobre perguntas já respondidas.'
            )

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_CLARIFICATION_REQUESTED,
            portal_session=portal_session,
            question_id=question_id,
            content={'message': message},
        )
        answer.state = BriefingAnswer.STATE_PENDING_CLARIFICATION
        answer.save(update_fields=['state', 'updated_at'])
        return answer

    @staticmethod
    @transaction.atomic
    def request_review(
        *,
        briefing: Briefing,
        portal_session,
        question_id,
        message: str = '',
    ) -> BriefingAnswer:
        answer = BriefingAnswer.objects.select_for_update().filter(
            briefing=briefing, question_id=question_id,
        ).first()
        if answer is None:
            raise BriefingError(
                'Só é possível solicitar revisão de perguntas respondidas.'
            )

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_REVIEW_REQUESTED,
            portal_session=portal_session,
            question_id=question_id,
            content={'message': (message or '').strip()},
        )
        answer.state = BriefingAnswer.STATE_REVIEW_REQUESTED
        answer.save(update_fields=['state', 'updated_at'])
        return answer

    # ==================================================================
    # TRANSCRIÇÃO / NOTIFICAÇÃO — agendamento
    # ==================================================================

    @staticmethod
    def _schedule_transcription(answer_id) -> None:
        try:
            from apps.briefings.services.transcription_service import (
                TranscriptionService,
            )
            TranscriptionService.run_async(answer_id)
        except Exception:
            logger.exception(
                'Não foi possível agendar transcrição (answer=%s).',
                answer_id,
            )

    @staticmethod
    def _schedule_completion_notification(briefing_id) -> None:
        try:
            from apps.briefings.services.notification_service import (
                NotificationService,
            )
            NotificationService.on_briefing_completed(briefing_id)
        except Exception:
            logger.exception(
                'Falha ao agendar notificação de conclusão '
                '(briefing=%s)', briefing_id,
            )