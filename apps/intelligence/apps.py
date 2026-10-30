"""
AppConfig do módulo intelligence.

INICIALIZAÇÃO AUTOMÁTICA DO WORKER
==================================
O worker de análise (`intelligence_worker`) precisa rodar continuamente
para processar os `AnalysisJob` pendentes. Este AppConfig inicia o
worker em uma thread daemon sempre que a aplicação Django sobe —
sem exigir terminal, sem exigir systemd, sem exigir NSSM.

Isso funciona em QUALQUER ambiente que execute Python:

    - DESENVOLVIMENTO (`python manage.py runserver`)
    - PRODUÇÃO LINUX (`gunicorn`, `uWSGI`)
    - PRODUÇÃO WINDOWS (`waitress`, `runserver` em prod)
    - PaaS (Render, Railway, Heroku, Fly.io)
    - Contêiner (Docker, se um dia você usar)

CONTROLE POR VARIÁVEIS DE AMBIENTE
==================================
O comportamento é controlado por 3 variáveis de ambiente. Nenhuma
delas é obrigatória — o default é "worker embutido ligado", que é o
que funciona em todos os ambientes sem configuração.

    INTELLIGENCE_WORKER_DISABLED
        "1"  → NÃO inicia o worker neste processo.
               Use quando o worker rodar em processo separado
               (systemd, NSSM, "Background Worker" de PaaS).
        ""   → inicia (default).

    INTELLIGENCE_WORKER_MODE
        "auto"     → default. Inicia o worker em TODOS os processos
                     que não forem comandos de management
                     (`migrate`, `shell`, `test`, etc.).
                     Em gunicorn com N workers, você terá N workers
                     embutidos. Seguro pela lógica de
                     `select_for_update(skip_locked=True)`, mas
                     consome CPU proporcional.
        "single"   → inicia o worker apenas em UM processo por
                     instância. Use a variável
                     INTELLIGENCE_WORKER_LEADER=1 para marcar QUAL
                     processo é o líder. Os demais não iniciam.
                     Ideal para gunicorn onde você quer 1 worker
                     embutido e não quer gerenciar processo separado.
        "off"      → equivalente a INTELLIGENCE_WORKER_DISABLED=1.

    INTELLIGENCE_WORKER_LEADER
        "1"  → este processo é o líder (só relevante em mode=single).
        ""   → não é líder.

SEGURANÇA
=========
    - A thread é `daemon=True`: morre junto com o processo principal.
    - Exceções dentro do worker são logadas, nunca propagadas.
    - `ready()` nunca bloqueia o startup do Django.
    - `_should_start_worker()` evita iniciar worker em comandos de
      management como `migrate`, `makemigrations`, `shell`, `test`,
      `collectstatic`, `createsuperuser`, `seed_*`, etc.

REAPROVEITAMENTO
================
O loop do worker é o `Command.handle()` do management command
`intelligence_worker`. Fonte única de verdade do processamento de
jobs. Não duplica lógica.
"""

import logging
import os
import sys
import threading
import time

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('intelligence')


# Intervalo entre polls do worker (segundos).
_WORKER_INTERVAL_SECONDS = 5

# Delay inicial antes do primeiro poll. Dá tempo para o Django
# terminar de montar o app registry, as conexões de banco e o
# middleware. Sem isso, a primeira query pode falhar.
_WORKER_STARTUP_DELAY_SECONDS = 2


# =========================================================================
# HELPERS DE AMBIENTE
# =========================================================================

def _env_flag(name: str) -> bool:
    """Lê uma env var booleana ('1'/'true'/'yes' = True)."""
    raw = os.environ.get(name, '').strip().lower()
    return raw in ('1', 'true', 'yes', 'on')


def _worker_disabled() -> bool:
    """
    Worker desativado explicitamente neste processo.

    Duas formas equivalentes:
        - INTELLIGENCE_WORKER_DISABLED=1
        - INTELLIGENCE_WORKER_MODE=off
    """
    if _env_flag('INTELLIGENCE_WORKER_DISABLED'):
        return True
    mode = os.environ.get(
        'INTELLIGENCE_WORKER_MODE', 'auto',
    ).strip().lower()
    if mode == 'off':
        return True
    return False


def _worker_mode() -> str:
    """
    Modo do worker: 'auto', 'single' ou 'off'.

    Default: 'auto'.
    """
    raw = os.environ.get(
        'INTELLIGENCE_WORKER_MODE', 'auto',
    ).strip().lower()
    if raw in ('auto', 'single', 'off'):
        return raw
    logger.warning(
        'INTELLIGENCE_WORKER_MODE inválido: %r. Usando "auto".',
        raw,
    )
    return 'auto'


def _is_leader_process() -> bool:
    """
    True apenas quando este processo é o líder (mode=single).

    Em mode=auto, é sempre True (todos iniciam).
    Em mode=single, é True só no processo com
    INTELLIGENCE_WORKER_LEADER=1.
    """
    mode = _worker_mode()
    if mode == 'auto':
        return True
    if mode == 'single':
        return _env_flag('INTELLIGENCE_WORKER_LEADER')
    return False


def _is_runserver_autoreload_child() -> bool:
    """
    Detecta o processo filho do autoreload do `runserver`.

    Em desenvolvimento, `runserver` inicia DOIS processos. O
    `ready()` roda em ambos. Sem essa checagem, o worker subiria
    duas vezes no dev.
    """
    if 'runserver' not in sys.argv:
        return False
    return os.environ.get('RUN_MAIN') != 'true'


def _is_management_command_that_should_not_run_worker() -> bool:
    """
    True quando o processo atual é um `manage.py <comando>` que NÃO
    é `runserver` e NÃO deve iniciar o worker.

    Exemplos: migrate, makemigrations, shell, test, collectstatic,
    createsuperuser, seed_*, sync_*, bootstrap_console, etc.

    Exceção: `runserver` — inicia worker.
    """
    argv = sys.argv or []
    if not any('manage.py' in arg for arg in argv):
        return False
    if 'runserver' in argv:
        return False
    return True


# =========================================================================
# APPCONFIG
# =========================================================================

class IntelligenceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.intelligence'
    verbose_name = _('Inteligência')

    def ready(self):
        """
        Inicializa o módulo intelligence.

        - Não registra signals (ingestão é explícita).
        - Inicia o worker embutido quando aplicável.
        """
        if _is_runserver_autoreload_child():
            return

        if _is_management_command_that_should_not_run_worker():
            return

        if _worker_disabled():
            logger.info(
                'Worker de Inteligência desativado neste processo '
                '(INTELLIGENCE_WORKER_DISABLED=1 ou '
                'INTELLIGENCE_WORKER_MODE=off).',
            )
            return

        if not _is_leader_process():
            logger.debug(
                'Worker de Inteligência não iniciado neste processo '
                '(mode=single e INTELLIGENCE_WORKER_LEADER!=1).',
            )
            return

        self._start_worker_thread()

    # ------------------------------------------------------------------
    # THREAD
    # ------------------------------------------------------------------

    @staticmethod
    def _start_worker_thread() -> None:
        """
        Inicia o worker em uma thread daemon.

        Idempotente por processo.
        """
        if getattr(
            IntelligenceConfig, '_worker_thread_started', False,
        ):
            return
        IntelligenceConfig._worker_thread_started = True

        thread = threading.Thread(
            target=IntelligenceConfig._run_worker_loop,
            name='intelligence-worker',
            daemon=True,
        )
        thread.start()

        logger.info(
            'Worker de Inteligência iniciado em thread daemon '
            '(mode=%s, interval=%ss, startup_delay=%ss).',
            _worker_mode(),
            _WORKER_INTERVAL_SECONDS,
            _WORKER_STARTUP_DELAY_SECONDS,
        )

    @staticmethod
    def _run_worker_loop() -> None:
        """
        Loop principal do worker.

        Reaproveita `Command.handle()` do management command.
        """
        time.sleep(_WORKER_STARTUP_DELAY_SECONDS)

        try:
            from apps.intelligence.management.commands.intelligence_worker import (
                Command as WorkerCommand,
            )
        except Exception:
            logger.exception(
                'Falha ao importar o management command do worker. '
                'O worker NÃO será iniciado.',
            )
            return

        while True:
            try:
                command = WorkerCommand()
                command.handle(
                    interval=_WORKER_INTERVAL_SECONDS,
                    run_once=False,
                )
                logger.warning(
                    'Worker retornou de handle() inesperadamente. '
                    'Encerrando thread.',
                )
                return
            except KeyboardInterrupt:
                logger.info('Worker interrompido por KeyboardInterrupt.')
                return
            except Exception:
                logger.exception(
                    'Exceção no loop do worker. Reiniciando em %ss.',
                    _WORKER_INTERVAL_SECONDS,
                )
                time.sleep(_WORKER_INTERVAL_SECONDS)