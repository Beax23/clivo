"""
TranscriptionService — transcrição de áudio.

REGRA ARQUITETURAL
------------------
Transcrição é OPCIONAL. Se o provedor não estiver configurado, o
status fica `failed` com mensagem clara. NUNCA simulamos uma
transcrição.

A transcrição NÃO substitui o áudio original. O áudio permanece
acessível em `BriefingAnswer.latest_audio`.
"""

import logging

from django.conf import settings
from django.utils import timezone

from apps.briefings.models import BriefingAnswer, BriefingEvent
from apps.briefings.exceptions import TranscriptionError
from apps.briefings.services.event_service import BriefingEventService

logger = logging.getLogger('briefings')


class TranscriptionService:

    # ==================================================================
    # DISPONIBILIDADE
    # ==================================================================

    @staticmethod
    def is_available() -> bool:
        """Verifica se o provedor está configurado no ambiente."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        return bool(api_key)

    @staticmethod
    def is_required() -> bool:
        """Se `True`, a ausência do provedor é erro."""
        return bool(getattr(settings, 'BRIEFINGS_REQUIRE_AI', False))

    # ==================================================================
    # SINCRONO
    # ==================================================================

    @staticmethod
    def transcribe_answer(answer_id) -> None:
        """
        Transcreve o áudio vinculado a uma resposta.

        Idempotente: se já houver transcrição concluída, não faz nada.
        """
        try:
            answer = BriefingAnswer.objects.select_related(
                'latest_audio', 'briefing',
            ).get(id=answer_id)
        except BriefingAnswer.DoesNotExist:
            logger.warning('Answer %s não encontrado', answer_id)
            return

        if answer.latest_audio is None:
            answer.transcription_status = (
                BriefingAnswer.TRANSCRIPTION_NOT_APPLICABLE
            )
            answer.save(update_fields=['transcription_status', 'updated_at'])
            return

        if answer.transcription_status == BriefingAnswer.TRANSCRIPTION_COMPLETED:
            return

        if not TranscriptionService.is_available():
            answer.transcription_status = BriefingAnswer.TRANSCRIPTION_FAILED
            answer.latest_transcription = ''
            answer.save(update_fields=[
                'transcription_status', 'latest_transcription', 'updated_at',
            ])
            logger.warning(
                'Transcrição indisponível (answer=%s). '
                'Configure OPENAI_API_KEY para habilitar.', answer_id,
            )
            if TranscriptionService.is_required():
                raise TranscriptionError(
                    'Provedor de transcrição não configurado.'
                )
            return

        answer.transcription_status = BriefingAnswer.TRANSCRIPTION_PROCESSING
        answer.save(update_fields=['transcription_status', 'updated_at'])

        try:
            text = TranscriptionService._call_provider(answer.latest_audio)
        except Exception as exc:
            logger.exception('Falha na transcrição (answer=%s)', answer_id)
            answer.transcription_status = BriefingAnswer.TRANSCRIPTION_FAILED
            answer.latest_transcription = ''
            answer.save(update_fields=[
                'transcription_status', 'latest_transcription', 'updated_at',
            ])
            raise TranscriptionError(str(exc)) from exc

        answer.latest_transcription = text
        answer.transcription_status = BriefingAnswer.TRANSCRIPTION_COMPLETED
        answer.save(update_fields=[
            'latest_transcription', 'transcription_status', 'updated_at',
        ])

        BriefingEventService.log(
            briefing=answer.briefing,
            kind=BriefingEvent.KIND_TRANSCRIPTION_GENERATED,
            user=None,
            portal_session=None,
            question_id=answer.question_id,
            content={'status': 'completed'},
        )

    # ==================================================================
    # PROVIDER
    # ==================================================================

    @staticmethod
    def _call_provider(audio_document) -> str:
        """
        Chama o provedor real. Não simula.

        Usa a biblioteca `openai` (Whisper). Se a lib não estiver
        instalada, levanta TranscriptionError.
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise TranscriptionError(
                'Biblioteca openai não instalada.'
            ) from exc

        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        model = getattr(settings, 'AI_TRANSCRIPTION_MODEL', 'whisper-1')

        client = OpenAI(api_key=api_key)

        file_handle = audio_document.file.open('rb')
        try:
            result = client.audio.transcriptions.create(
                model=model,
                file=file_handle,
                response_format='text',
            )
        finally:
            try:
                file_handle.close()
            except Exception:
                pass

        if isinstance(result, str):
            return result.strip()
        text = getattr(result, 'text', None)
        return (text or '').strip()

    # ==================================================================
    # ASSÍNCRONO
    # ==================================================================

    @staticmethod
    def run_async(answer_id) -> None:
        """
        Publica a tarefa para execução assíncrona.

        Se Celery não estiver configurado, executa inline como
        fallback — não perde o evento.
        """
        try:
            from config.celery import app as celery_app  # noqa: F401
            from apps.briefings.tasks import transcribe_answer_task

            transcribe_answer_task.delay(str(answer_id))
            return
        except Exception:
            logger.info(
                'Celery indisponível. Executando transcrição inline '
                '(answer=%s).', answer_id,
            )

        try:
            TranscriptionService.transcribe_answer(answer_id)
        except Exception:
            logger.exception(
                'Falha na transcrição inline (answer=%s)', answer_id,
            )