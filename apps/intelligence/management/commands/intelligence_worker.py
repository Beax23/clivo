"""
Comando de gerenciamento para processar jobs de inteligência.

CONCORRÊNCIA
------------
Cada job é reivindicado via `JobService.claim_next_job()`, que usa
`select_for_update(skip_locked=True)` E marca o job como `processing`
dentro da mesma transação. Dois workers concorrentes nunca processam
o mesmo job.
"""

import logging
import time

from django.core.management.base import BaseCommand

from apps.intelligence.services import JobService, AnalysisService
from apps.intelligence.models import AnalysisJob, AnalysisRun
from apps.intelligence.exceptions import BudgetExceededError, StaleAnalysisError

logger = logging.getLogger('intelligence')


class Command(BaseCommand):
    help = 'Processa os jobs de análise de inteligência pendentes.'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=5)
        parser.add_argument('--run-once', action='store_true')

    def handle(self, *args, **options):
        run_once = options['run_once']
        interval = options['interval']

        self.stdout.write(self.style.SUCCESS('Worker de Inteligência iniciado.'))

        while True:
            try:
                job = JobService.claim_next_job()

                if job is None:
                    if run_once:
                        break
                    time.sleep(interval)
                    continue

                self.process_job(job)

            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nWorker interrompido.'))
                break
            except Exception:
                logger.exception('Erro no loop principal do worker.')
                if run_once:
                    raise
                time.sleep(interval)

        self.stdout.write(self.style.SUCCESS('Worker finalizado.'))

    def process_job(self, job: AnalysisJob):
        job_id_str = str(job.id)
        self.stdout.write(f'Processando job {job_id_str}...')

        try:
            run = AnalysisService.execute(job)

            if run is None:
                self.stdout.write(self.style.WARNING(
                    f'Job {job_id_str} ignorado (duplicado).'
                ))
                JobService.mark_as_completed(job)
                return

            if run.status == AnalysisRun.STATUS_COMPLETED:
                self.stdout.write(self.style.SUCCESS(
                    f'Job {job_id_str} concluído (Run {run.id}).'
                ))
                JobService.mark_as_completed(job)
            else:
                JobService.mark_as_failed(job, f'Estado inesperado: {run.status}')

        except StaleAnalysisError as exc:
            self.stdout.write(self.style.WARNING(
                f'Job {job_id_str} ignorado (stale): {exc}'
            ))
            JobService.mark_as_completed(job)

        except BudgetExceededError as exc:
            self.stdout.write(self.style.ERROR(
                f'Job {job_id_str} falhou (orçamento): {exc}'
            ))
            JobService.mark_as_failed(job, f'BudgetExceeded: {exc}')

        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                f'Job {job_id_str} falhou: {exc}'
            ))
            logger.exception('Falha ao processar job %s', job_id_str)
            JobService.mark_as_failed(job, str(exc))