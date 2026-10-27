"""
Testes do histórico de tags.

Cobrem:
    - Transições válidas gravam histórico.
    - Transições inválidas são rejeitadas.
    - No-op é rejeitado.
    - kind != 'tag' é rejeitado.
    - Histórico preserva quem/quando/estado anterior.
"""

import pytest

from apps.intelligence.models import InsightItem, InsightTagHistory
from apps.intelligence.services import TagService, InvalidTagTransitionError


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-tag-test')


@pytest.fixture
def client(db, workspace):
    from apps.clients.models import Client
    return Client.objects.create(
        workspace=workspace, name='Cli', email='c@x.com',
        public_code='CLI-TAG001',
    )


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(email='u@x.com', password='x')


@pytest.fixture
def tag(db, workspace, client):
    from apps.intelligence.models import AnalysisJob, AnalysisRun
    from django.utils import timezone
    job = AnalysisJob.objects.create(
        workspace=workspace, client=client, briefing=None,
        target_kinds=[InsightItem.KIND_TAG],
        data_version='v1', job_key='j-tag',
    )
    run = AnalysisRun.objects.create(
        job=job, workspace=workspace, client=client, briefing=None,
        input_hash='h-tag', data_version='v1',
        provider='openai', model='m', prompt_version='v1',
        status='completed', started_at=timezone.now(),
    )
    return InsightItem.objects.create(
        run=run, workspace=workspace, client=client,
        kind=InsightItem.KIND_TAG, content='tag-x',
    )


@pytest.mark.django_db
class TestTagTransition:

    def test_confirm_creates_history(self, tag, user):
        TagService.transition(
            insight=tag, new_state='confirmed',
            changed_by=user, reason='ok',
        )
        tag.refresh_from_db()
        assert tag.review_state == 'confirmed'
        h = InsightTagHistory.objects.filter(insight=tag).first()
        assert h.previous_state == 'new'
        assert h.new_state == 'confirmed'
        assert h.changed_by_id == user.id
        assert h.reason == 'ok'

    def test_discard_creates_history(self, tag):
        TagService.transition(
            insight=tag, new_state='discarded',
        )
        tag.refresh_from_db()
        assert tag.review_state == 'discarded'
        h = InsightTagHistory.objects.filter(insight=tag).first()
        assert h.previous_state == 'new'
        assert h.new_state == 'discarded'
        assert h.changed_by_id is None  # sistema

    def test_no_op_rejected(self, tag):
        TagService.transition(insight=tag, new_state='confirmed')
        with pytest.raises(InvalidTagTransitionError):
            TagService.transition(insight=tag, new_state='confirmed')

    def test_invalid_state_rejected(self, tag):
        with pytest.raises(InvalidTagTransitionError):
            TagService.transition(insight=tag, new_state='foo')

    def test_non_tag_rejected(self, db, workspace, client):
        from apps.intelligence.models import AnalysisJob, AnalysisRun
        from django.utils import timezone
        job = AnalysisJob.objects.create(
            workspace=workspace, client=client, briefing=None,
            target_kinds=[InsightItem.KIND_DESIRE],
            data_version='v1', job_key='j-desire',
        )
        run = AnalysisRun.objects.create(
            job=job, workspace=workspace, client=client, briefing=None,
            input_hash='h-desire', data_version='v1',
            provider='openai', model='m', prompt_version='v1',
            status='completed', started_at=timezone.now(),
        )
        insight = InsightItem.objects.create(
            run=run, workspace=workspace, client=client,
            kind=InsightItem.KIND_DESIRE, content='d',
        )
        with pytest.raises(InvalidTagTransitionError):
            TagService.transition(insight=insight, new_state='confirmed')

    def test_history_is_append_only(self, tag, user):
        TagService.transition(
            insight=tag, new_state='confirmed', changed_by=user,
        )
        TagService.transition(
            insight=tag, new_state='discarded', changed_by=user,
        )
        history = list(
            InsightTagHistory.objects.filter(insight=tag).order_by('created_at')
        )
        assert len(history) == 2
        assert history[0].new_state == 'confirmed'
        assert history[1].previous_state == 'confirmed'
        assert history[1].new_state == 'discarded'