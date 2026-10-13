"""
Tasks Celery do módulo briefings.

Se Celery não estiver configurado, o fallback inline é usado em
TranscriptionService.run_async.
"""

import logging

logger = logging.getLogger('briefings')


try:
    from celery import shared_task
    _has_celery = True
except ImportError:
    _has_celery = False
    shared_task = None


if _has_celery:

    @shared_task(name='briefings.transcribe_answer', bind=True, max_retries=2)
    def transcribe_answer_task(self, answer_id: str):
        from apps.briefings.services.transcription_service import (
            TranscriptionService,
        )
        try:
            TranscriptionService.transcribe_answer(answer_id)
        except Exception as exc:
            logger.exception('Falha na task de transcrição')
            raise self.retry(exc=exc, countdown=60)

else:
    def transcribe_answer_task(*args, **kwargs):  # pragma: no cover
        raise RuntimeError('Celery não instalado.')