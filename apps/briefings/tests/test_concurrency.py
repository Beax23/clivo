"""
Testes de concorrência no submit_answer.

Estratégia em duas camadas:

1. Teste de CONTRATO (`test_submit_answer_uses_select_for_update`)
   Verifica que o serviço usa `select_for_update` no Briefing,
   garantindo que o lock existe. Roda em qualquer banco — inclusive
   SQLite.

2. Teste REAL de concorrência (`test_simultaneous_answers_create_single_event`)
   Duas threads chamam `submit_answer` ao mesmo tempo. Só roda em
   PostgreSQL (SQLite em memória não compartilha o banco entre
   conexões de threads). Em CI com Postgres, roda. Localmente em
   SQLite, é pulado.
"""

import threading

import pytest
from django.db import connection
from django.test import TransactionTestCase

from apps.briefings.models import BriefingEvent
from apps.briefings.services import BriefingService


# =========================================================================
# 1. TESTE DE CONTRATO — roda sempre
# =========================================================================

@pytest.mark.django_db
def test_submit_answer_uses_select_for_update(
    briefing_a, portal_session_a,
):
    """
    Verifica que `submit_answer` usa `select_for_update` no Briefing.

    Não substitui um teste real de concorrência, mas documenta o
    contrato: o lock existe e é chamado no caminho crítico. Se
    alguém remover o `select_for_update` no futuro, este teste
    quebra e a intenção fica registrada.
    """
    from unittest.mock import patch
    from django.db.models import QuerySet

    real_select = QuerySet.select_for_update
    called = {'count': 0}

    def spy_select_for_update(self_qs, *args, **kwargs):
        called['count'] += 1
        return real_select(self_qs, *args, **kwargs)

    questions = briefing_a.snapshot_questions()
    first = questions[0]

    with patch.object(
        QuerySet, 'select_for_update', spy_select_for_update,
    ):
        BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=first['id'],
            content_text='Resposta.',
        )

    # Pelo menos uma chamada — a do Briefing.
    assert called['count'] >= 1, (
        'submit_answer não chamou select_for_update. '
        'O lock de concorrência pode ter sido removido.'
    )


# =========================================================================
# 2. TESTE REAL — só roda em Postgres
# =========================================================================

def _running_on_postgres() -> bool:
    """Detecta se o banco atual é Postgres."""
    try:
        return connection.vendor == 'postgresql'
    except Exception:
        return False


@pytest.mark.skipif(
    not _running_on_postgres(),
    reason=(
        'Teste real de concorrência requer Postgres. '
        'SQLite em memória não compartilha o banco entre threads. '
        'Rode no CI com Postgres habilitado.'
    ),
)
class TestConcurrencyReal(TransactionTestCase):
    """
    Duas threads chamam `submit_answer` na mesma pergunta.

    Com `select_for_update` correto, uma vence, a outra recebe
    erro de sequência. Apenas UM `BriefingEvent` do tipo `answered`
    é persistido.
    """

    reset_sequences = False

    def setUp(self):
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from apps.console.models import (
            ConsoleGovernance, Plan,
        )
        from apps.workspaces.models import (
            Workspace, WorkspaceMembership, WorkspaceSubscription,
        )
        from apps.clients.models import Client, ClientPortalSession
        from apps.briefings.models import (
            BriefingTemplate, BriefingSection, BriefingQuestion,
        )
        from apps.briefings.services import BriefingService

        User = get_user_model()

        self.user = User.objects.create_user(
            email='conc@briefings.test', password='x',
        )
        self.gov = ConsoleGovernance.objects.create(
            key='proprietario', name='Proprietário', description='',
            scope='workspace', is_system=True, is_protected=True,
        )
        self.plan = Plan.objects.create(
            key='basic', name='Basic', price=Decimal('0'),
            is_active=True, is_default=True,
        )
        self.ws = Workspace.objects.create(name='Conc', slug='conc')
        WorkspaceSubscription.objects.create(
            workspace=self.ws, plan=self.plan, is_active=True,
            started_at=timezone.now(),
        )
        WorkspaceMembership.objects.create(
            workspace=self.ws, user=self.user, governance=self.gov,
        )
        self.client = Client.objects.create(
            workspace=self.ws, name='Cliente Conc',
            email='cli@conc.test', public_code='CLI-CONC01',
        )
        self.portal_session, _ = ClientPortalSession.issue(
            client=self.client,
        )

        tpl = BriefingTemplate.objects.create(
            workspace=self.ws, name='T', status='published',
            is_active=True, created_by=self.user,
        )
        s = BriefingSection.objects.create(
            template=tpl, title='S', position=1,
        )
        BriefingQuestion.objects.create(
            section=s, text='Q1', position=1, is_required=True,
            allowed_response_formats=['text'],
        )
        self.briefing = BriefingService.create_briefing(
            template=tpl, client=self.client,
            workspace=self.ws, actor=self.user,
        )
        self.question_id = self.briefing.snapshot_questions()[0]['id']

    def tearDown(self):
        connection.close()

    def test_simultaneous_answers_create_single_event(self):
        errors = []
        successes = []
        lock = threading.Lock()

        def worker():
            try:
                BriefingService.submit_answer(
                    briefing_id=self.briefing.id,
                    portal_session=self.portal_session,
                    question_id=self.question_id,
                    content_text='Resposta concorrente.',
                )
                with lock:
                    successes.append(True)
            except Exception as exc:
                with lock:
                    errors.append(exc)
            finally:
                connection.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        count = BriefingEvent.objects.filter(
            briefing=self.briefing,
            kind=BriefingEvent.KIND_ANSWERED,
            question_id=self.question_id,
        ).count()
        assert count == 1, (
            f'Esperado 1 evento answered, obtido {count}. '
            f'Sucessos={len(successes)} erros={len(errors)}.'
        )

        assert len(successes) >= 1, (
            'Nenhuma das duas requisições foi bem-sucedida.'
        )