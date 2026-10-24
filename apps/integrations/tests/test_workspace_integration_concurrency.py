"""
Testes de concorrência real do WorkspaceIntegrationService.

Só rodam em PostgreSQL, porque SQLite em memória não compartilha o
banco entre threads — o que tornaria o teste inútil (falso positivo).

Este teste cobre o Risco 2 identificado na Etapa 01: o
`select_for_update()` só tem efeito real em Postgres, e precisa ser
verificado antes de congelar a versão 1.
"""

import threading

import pytest
from django.db import connection
from django.test import TransactionTestCase

from apps.integrations.models import (
    IntegrationProvider,
    WorkspaceIntegration,
)
from apps.integrations.services.access import WorkspaceIntegrationService


def _running_on_postgres() -> bool:
    try:
        return connection.vendor == 'postgresql'
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _running_on_postgres(),
    reason=(
        'Concorrência real requer Postgres. SQLite em memória não '
        'compartilha o banco entre threads. Rode no CI com Postgres '
        'habilitado.'
    ),
)


class TestWorkspaceIntegrationConcurrency(TransactionTestCase):
    """
    Verifica que duas chamadas concorrentes a `get_for_workspace`,
    com apenas uma conta ativa, marcam essa conta como preferida
    APENAS UMA VEZ e retornam a mesma integração.
    """

    reset_sequences = False

    def setUp(self):
        from apps.workspaces.models import Workspace

        self.provider = IntegrationProvider.objects.create(
            key='google',
            name='Google',
            category='productivity',
        )
        self.workspace = Workspace.objects.create(
            name='WS Conc',
            slug='ws-conc-int',
        )
        self.integration = WorkspaceIntegration.objects.create(
            workspace=self.workspace,
            provider=self.provider,
            external_account_id='ext-1',
            external_account_email='a@b.com',
            encrypted_payload=b'x',
            granted_scopes=[],
            is_preferred=False,
            status=WorkspaceIntegration.STATUS_ACTIVE,
        )

    def tearDown(self):
        connection.close()

    def test_concurrent_get_marks_only_one_preferred(self):
        errors = []
        results = []
        lock = threading.Lock()

        def worker():
            try:
                integration = (
                    WorkspaceIntegrationService.get_for_workspace(
                        workspace=self.workspace,
                        provider_key='google',
                    )
                )
                with lock:
                    results.append(integration.id)
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

        # Nenhum erro esperado
        assert not errors, f'Erros durante concorrência: {errors}'

        # Ambas devem retornar a mesma integração
        assert len(results) == 2
        assert results[0] == results[1]
        assert results[0] == self.integration.id

        # E apenas uma preferida no banco
        preferred_count = WorkspaceIntegration.objects.filter(
            workspace=self.workspace,
            is_preferred=True,
            status=WorkspaceIntegration.STATUS_ACTIVE,
        ).count()
        assert preferred_count == 1

    def test_concurrent_ambiguity_is_consistent(self):
        """
        Duas contas ativas, nenhuma preferida. Duas chamadas
        concorrentes devem ambas levantar AmbiguousConnectionError.
        """
        from apps.integrations.exceptions import AmbiguousConnectionError

        WorkspaceIntegration.objects.create(
            workspace=self.workspace,
            provider=self.provider,
            external_account_id='ext-2',
            external_account_email='b@b.com',
            encrypted_payload=b'x',
            granted_scopes=[],
            is_preferred=False,
            status=WorkspaceIntegration.STATUS_ACTIVE,
        )

        errors = []
        results = []
        lock = threading.Lock()

        def worker():
            try:
                integration = (
                    WorkspaceIntegrationService.get_for_workspace(
                        workspace=self.workspace,
                        provider_key='google',
                    )
                )
                with lock:
                    results.append(integration.id)
            except AmbiguousConnectionError as exc:
                with lock:
                    errors.append(exc)
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

        assert not results, (
            f'Nenhuma chamada deveria ter sucesso, mas retornou: {results}'
        )
        assert len(errors) == 2
        assert all(
            isinstance(e, AmbiguousConnectionError) for e in errors
        )