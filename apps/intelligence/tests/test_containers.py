"""
Testes dos containers fixos (Mesa, Cliente, Relatório).

Verificam que:
    - Nenhum container aceita kinds fora do contrato.
    - O ContainerService monta os 5/5/8 slots corretos.
    - Insights stale são filtrados por padrão.
    - `container_slots_for_kind` (inverso do CONTAINER_KINDS) é coerente.
"""

import pytest

from apps.intelligence.models import InsightItem
from apps.intelligence.services import ContainerService


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-int-test')


@pytest.fixture
def client(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace, name='Cli', email='cli@x.com',
        public_code='CLI-INT001',
    )


@pytest.fixture
def briefing(db, workspace, client):
    from apps.briefings.models import Briefing
    return Briefing.objects.create(
        workspace=workspace, client=client,
        title='B', structure_snapshot={'sections': []},
    )


def _make_insight(workspace, client, briefing, kind, content='x', stale=False):
    from apps.intelligence.models import AnalysisJob, AnalysisRun
    from django.utils import timezone
    job = AnalysisJob.objects.create(
        workspace=workspace, client=client, briefing=briefing,
        target_kinds=[kind], data_version='v1', job_key=f'j-{kind}-{content}',
    )
    run = AnalysisRun.objects.create(
        job=job, workspace=workspace, client=client, briefing=briefing,
        input_hash=f'h-{kind}-{content}', data_version='v1',
        provider='openai', model='m', prompt_version='v1',
        status='completed', started_at=timezone.now(),
    )
    return InsightItem.objects.create(
        run=run, workspace=workspace, client=client, briefing=briefing,
        kind=kind, content=content, is_stale=stale,
    )


@pytest.mark.django_db
class TestContainerMapping:

    def test_mesa_has_exactly_five_slots(self):
        assert len(InsightItem.CONTAINER_KINDS[
            InsightItem.CONTAINER_MESA
        ]) == 5

    def test_cliente_has_exactly_five_slots(self):
        assert len(InsightItem.CONTAINER_KINDS[
            InsightItem.CONTAINER_CLIENTE
        ]) == 5

    def test_relatorio_has_eight_slots(self):
        # A diretriz pede 8 containers de relatório + 09_outras_analises.
        slots = InsightItem.CONTAINER_KINDS[InsightItem.CONTAINER_RELATORIO]
        # 01..08 são os obrigatórios; 09_outras_analises é adicional.
        mandatory = [s for s in slots if s.startswith(
            ('01_', '02_', '03_', '04_', '05_', '06_', '07_', '08_')
        )]
        assert len(mandatory) == 8

    def test_unknown_container_raises(self):
        with pytest.raises(ValueError):
            InsightItem.kinds_for_container('nao_existe')

    def test_container_slots_for_kind_is_inverse(self):
        slots = InsightItem.container_slots_for_kind(
            InsightItem.KIND_DESIRE,
        )
        assert 'mesa' in slots
        assert 'relatorio' in slots
        assert '01_desejos_prioridades' in slots['mesa']
        assert '02_desejos_criterios' in slots['relatorio']


@pytest.mark.django_db
class TestBuildMesa:

    def test_mesa_slots_populated(self, workspace, client, briefing):
        _make_insight(workspace, client, briefing, InsightItem.KIND_DESIRE, 'd')
        _make_insight(workspace, client, briefing, InsightItem.KIND_ATTENTION, 'a')

        payload = ContainerService.build_mesa(
            workspace=workspace, client=client,
        )
        assert payload['counts']['01_desejos_prioridades'] == 1
        assert payload['counts']['02_pontos_atencao'] == 1
        assert payload['counts']['03_mudancas'] == 0

    def test_stale_filtered_by_default(self, workspace, client, briefing):
        _make_insight(
            workspace, client, briefing,
            InsightItem.KIND_DESIRE, 'old', stale=True,
        )
        payload = ContainerService.build_mesa(
            workspace=workspace, client=client,
        )
        assert payload['counts']['01_desejos_prioridades'] == 0

    def test_include_stale_flag(self, workspace, client, briefing):
        _make_insight(
            workspace, client, briefing,
            InsightItem.KIND_DESIRE, 'old', stale=True,
        )
        payload = ContainerService.build_mesa(
            workspace=workspace, client=client, include_stale=True,
        )
        assert payload['counts']['01_desejos_prioridades'] == 1


@pytest.mark.django_db
class TestBuildRelatorio:

    def test_relatorio_isolated_by_briefing(
        self, workspace, client, briefing,
    ):
        from apps.briefings.models import Briefing
        other = Briefing.objects.create(
            workspace=workspace, client=client,
            title='Other', structure_snapshot={'sections': []},
        )
        _make_insight(
            workspace, client, briefing,
            InsightItem.KIND_EXECUTIVE_SUMMARY, 'main',
        )
        _make_insight(
            workspace, client, other,
            InsightItem.KIND_EXECUTIVE_SUMMARY, 'other',
        )

        payload = ContainerService.build_relatorio(
            workspace=workspace, briefing=briefing,
        )
        contents = [
            i.content
            for i in payload['containers']['01_sintese_executiva']
        ]
        assert contents == ['main']