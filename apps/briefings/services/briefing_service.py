"""
BriefingService — ciclo de vida da execução.

REGRA ARQUITETURAL
------------------
Toda mutação passa por este service. Nenhuma view escreve
diretamente em `Briefing`, `BriefingAnswer` ou `BriefingEvent`.

Concorrência:
    `submit_answer` roda dentro de `transaction.atomic` e usa
    `select_for_update` no Briefing para serializar envios
    concorrentes do mesmo cliente.

Sequência:
    O cliente só pode responder a próxima pergunta elegível.
    Validação é feita aqui, com base no snapshot.

ANÁLISE
-------
Este service NÃO gera análise. Análise pertence ao app `intelligence`.

NOTIFICAÇÃO
-----------
Ao concluir, agenda (via `on_commit`) o envio de e-mail através
do `NotificationService`.
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
    ) -> Briefing:
        """
        Cria uma execução a partir de um template publicado.

        Copia a estrutura do template para `structure_snapshot`.
        """
        if template.workspace_id != workspace.id:
            raise BriefingError('Template não pertence a este workspace.')

        if client.workspace_id != workspace.id:
            raise BriefingError('Cliente não pertence a este workspace.')

        if template.status != BriefingTemplate.STATUS_PUBLISHED:
            raise BriefingError(
                'Só templates publicados podem originar execuções.'
            )

        if not template.is_active:
            raise BriefingError(
                'O template está inativo e não pode originar novas '
                'execuções.'
            )

        if not template.sections.exists():
            raise BriefingError(
                'O template não possui sessões para executar.'
            )

        snapshot = BriefingService._build_structure_snapshot(template)

        briefing = Briefing.objects.create(
            workspace=workspace,
            client=client,
            template=template,
            title=(title or template.name).strip(),
            structure_snapshot=snapshot,
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
                'expires_at': (
                    expires_at.isoformat() if expires_at else None
                ),
            },
        )

        return briefing

    @staticmethod
    def _build_structure_snapshot(template: BriefingTemplate) -> dict:
        """
        Serializa a estrutura do template num dict imutável.
        """
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
                    'position': question.position,
                    'is_required': question.is_required,
                    'reference_document_ids': [
                        str(d.id)
                        for d in question.reference_documents.all()
                    ],
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
        Cálculo canônico de progresso.
        """
        questions = briefing.snapshot_questions()
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
    # RESPOSTA (fluxo do portal)
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
        """
        Registra uma resposta do cliente.
        """
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
        if briefing.status == Briefing.STATUS_CLOSED:
            raise BriefingClosedError('O briefing foi encerrado.')
        if briefing.status == Briefing.STATUS_EXPIRED:
            raise BriefingExpiredError('O briefing expirou.')
        if briefing.has_expired():
            briefing.status = Briefing.STATUS_EXPIRED
            briefing.save(update_fields=['status', 'updated_at'])
            raise BriefingExpiredError('O briefing expirou.')
        if briefing.status == Briefing.STATUS_COMPLETED:
            raise BriefingError('O briefing já foi concluído.')

        next_question = BriefingService.get_next_eligible_question(briefing)
        if next_question is None:
            raise BriefingError('Não há perguntas pendentes.')
        if str(next_question['id']) != str(question_id):
            raise InvalidQuestionSequenceError(
                'Você só pode responder à próxima pergunta da sequência.'
            )

        allowed = set(next_question.get('allowed_response_formats') or [])
        has_text = bool((content_text or '').strip())
        has_audio = audio_document is not None
        has_attachments = bool(attachment_documents)

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
        if not (has_text or has_audio):
            raise InvalidResponseFormatError(
                'Envie um texto ou um áudio.'
            )

        content_payload = {
            'text': (content_text or '').strip() or None,
            'audio_document_id': (
                str(audio_document.id) if audio_document else None
            ),
            'attachment_document_ids': [
                str(d.id) for d in (attachment_documents or [])
            ],
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
        answer.latest_content = (content_text or '').strip()
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

        if attachment_documents:
            answer.attachments.set(attachment_documents)

        # 8. Conclusão automática?
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

            # Notificação por e-mail — FORA da transação
            from django.db import transaction as _tx
            _briefing_id = briefing.id
            _tx.on_commit(
                lambda: BriefingService._schedule_completion_notification(
                    _briefing_id,
                )
            )

        # 9. Agenda transcrição (best-effort)
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
    # FLUXO / SEQUÊNCIA
    # ==================================================================

    @staticmethod
    def get_next_eligible_question(briefing: Briefing) -> Optional[dict]:
        questions = briefing.snapshot_questions()
        answers = {
            str(a.question_id): a
            for a in BriefingAnswer.objects.filter(briefing=briefing)
        }

        for q in questions:
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
    def close(*, briefing: Briefing, actor) -> Briefing:
        if briefing.status == Briefing.STATUS_CLOSED:
            return briefing
        briefing.status = Briefing.STATUS_CLOSED
        briefing.closed_at = timezone.now()
        briefing.save(update_fields=[
            'status', 'closed_at', 'updated_at',
        ])
        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_CLOSED,
            user=actor,
        )
        return briefing

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
            Briefing.STATUS_CLOSED,
            Briefing.STATUS_EXPIRED,
            Briefing.STATUS_COMPLETED,
        }
        if briefing.status not in allowed_states:
            raise BriefingReopenError(
                f'Não é possível reabrir um briefing no estado '
                f'"{briefing.status}".'
            )

        needs_new_deadline = (
            briefing.status == Briefing.STATUS_EXPIRED
            or briefing.has_expired()
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
        briefing.closed_at = None
        briefing.completed_at = None
        briefing.save(update_fields=[
            'status', 'closed_at', 'completed_at',
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
    # TRANSCRIÇÃO — agenda
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
                'Não foi possível agendar transcrição (answer=%s). '
                'Verifique se Celery está configurado.', answer_id,
            )

    # ==================================================================
    # NOTIFICAÇÃO DE CONCLUSÃO — agenda
    # ==================================================================

    @staticmethod
    def _schedule_completion_notification(briefing_id) -> None:
        """
        Dispara a notificação de conclusão após o commit.

        Nunca levanta: falha de e-mail não pode derrubar a conclusão
        do briefing.
        """
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