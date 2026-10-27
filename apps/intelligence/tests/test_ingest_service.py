import pytest
from apps.intelligence.services import IngestService
from apps.intelligence.models import InsightEvent, AnalysisJob

pytestmark = pytest.mark.django_db


def test_ingest_creates_event_and_job(workspace, client):
    event, created = IngestService.ingest_change_event(
        workspace_id=workspace.id,
        client_id=client.id,
        source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
        occurrence_id='upd-1',
        data_version='v1',
    )
    assert created is True
    assert AnalysisJob.objects.count() == 1


def test_ingest_is_idempotent_for_same_occurrence(workspace, client):
    IngestService.ingest_change_event(
        workspace_id=workspace.id, client_id=client.id,
        source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
        occurrence_id='upd-1', data_version='v1',
    )
    _, created = IngestService.ingest_change_event(
        workspace_id=workspace.id, client_id=client.id,
        source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
        occurrence_id='upd-1', data_version='v1',
    )
    assert created is False
    assert InsightEvent.objects.count() == 1


def test_ingest_accepts_legit_new_occurrence(workspace, client):
    """
    Duas edições legítimas em momentos distintos produzem DOIS eventos.
    """
    IngestService.ingest_change_event(
        workspace_id=workspace.id, client_id=client.id,
        source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
        occurrence_id='upd-1', data_version='v1',
    )
    IngestService.ingest_change_event(
        workspace_id=workspace.id, client_id=client.id,
        source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
        occurrence_id='upd-2', data_version='v2',
    )
    assert InsightEvent.objects.count() == 2