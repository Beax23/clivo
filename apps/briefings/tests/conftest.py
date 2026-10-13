"""
Fixtures compartilhadas dos testes de `briefings`.

Estrutura mínima para exercitar o domínio sem depender de
frontend, Portal real, storage remoto ou Celery.
"""

import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.console.models import (
    ConsoleGovernance,
    ConsoleMembership,
    Feature,
    Plan,
    PlanFeature,
    PlanFeatureLimit,
    UsageMetric,
)
from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceSubscription,
)
from apps.clients.models import Client, ClientPortalSession
from apps.briefings.models import (
    BriefingTemplate,
    BriefingSection,
    BriefingQuestion,
    Briefing,
)


User = get_user_model()


# =========================================================================
# GOVERNANÇA / CONSOLE
# =========================================================================

@pytest.fixture
def governance_proprietario(db):
    return ConsoleGovernance.objects.create(
        key='proprietario',
        name='Proprietário',
        description='',
        scope='workspace',
        is_system=True,
        is_protected=True,
    )


@pytest.fixture
def default_plan(db):
    return Plan.objects.create(
        key='basic',
        name='Basic',
        price=Decimal('49.00'),
        is_active=True,
        is_default=True,
    )


@pytest.fixture
def storage_metric(db):
    return UsageMetric.objects.create(
        key='storage.bytes',
        name='Armazenamento',
        unit='byte',
        kind='gauge',
        origin='derived',
        is_active=True,
    )


@pytest.fixture
def storage_feature(db):
    return Feature.objects.create(
        key='armazenamento',
        name='Armazenamento',
        is_active=True,
    )


# =========================================================================
# USUÁRIOS
# =========================================================================

@pytest.fixture
def user_owner(db):
    return User.objects.create_user(
        email='owner@briefings.test',
        password='senha-fraca-123',
    )


@pytest.fixture
def user_other(db):
    return User.objects.create_user(
        email='other@briefings.test',
        password='senha-fraca-123',
    )


@pytest.fixture
def user_outsider(db):
    """Usuário ativo, sem membership em nenhum workspace."""
    return User.objects.create_user(
        email='outsider@briefings.test',
        password='senha-fraca-123',
    )


# =========================================================================
# WORKSPACES
# =========================================================================

def _make_workspace(slug, name):
    return Workspace.objects.create(name=name, slug=slug)


def _make_membership(workspace, user, governance):
    return WorkspaceMembership.objects.create(
        workspace=workspace, user=user, governance=governance,
    )


@pytest.fixture
def workspace_a(db, user_owner, governance_proprietario, default_plan):
    ws = _make_workspace('ws-a', 'Workspace A')
    WorkspaceSubscription.objects.create(
        workspace=ws, plan=default_plan, is_active=True,
        started_at=timezone.now(),
    )
    _make_membership(ws, user_owner, governance_proprietario)
    return ws


@pytest.fixture
def workspace_b(
    db, user_other, governance_proprietario, default_plan,
):
    ws = _make_workspace('ws-b', 'Workspace B')
    WorkspaceSubscription.objects.create(
        workspace=ws, plan=default_plan, is_active=True,
        started_at=timezone.now(),
    )
    _make_membership(ws, user_other, governance_proprietario)
    return ws


# =========================================================================
# CLIENTES
# =========================================================================

@pytest.fixture
def client_a(db, workspace_a):
    return Client.objects.create(
        workspace=workspace_a,
        name='Cliente A',
        email='cliente-a@briefings.test',
        public_code='CLI-AAAAAA',
    )


@pytest.fixture
def client_b(db, workspace_b):
    return Client.objects.create(
        workspace=workspace_b,
        name='Cliente B',
        email='cliente-b@briefings.test',
        public_code='CLI-BBBBBB',
    )


@pytest.fixture
def portal_session_a(db, client_a):
    session, _raw = ClientPortalSession.issue(client=client_a)
    return session


@pytest.fixture
def portal_session_b(db, client_b):
    session, _raw = ClientPortalSession.issue(client=client_b)
    return session


# =========================================================================
# TEMPLATE
# =========================================================================

@pytest.fixture
def published_template(db, workspace_a, user_owner):
    """
    Template publicado com 2 sessões e 3 perguntas (todas obrigatórias).
    """
    template = BriefingTemplate.objects.create(
        workspace=workspace_a,
        name='Briefing Residencial',
        description='Briefing para projetos residenciais',
        category='residencial',
        status=BriefingTemplate.STATUS_PUBLISHED,
        is_active=True,
        created_by=user_owner,
    )
    s1 = BriefingSection.objects.create(
        template=template, title='Sobre você', position=1,
    )
    s2 = BriefingSection.objects.create(
        template=template, title='Sobre a casa', position=2,
    )
    BriefingQuestion.objects.create(
        section=s1,
        text='Como você descreveria sua rotina?',
        position=1,
        is_required=True,
        allowed_response_formats=['text', 'audio'],
    )
    BriefingQuestion.objects.create(
        section=s1,
        text='O que não pode faltar?',
        position=2,
        is_required=True,
        allowed_response_formats=['text', 'audio', 'image'],
    )
    BriefingQuestion.objects.create(
        section=s2,
        text='Quantos ambientes você imagina?',
        position=1,
        is_required=True,
        allowed_response_formats=['text'],
    )
    return template


@pytest.fixture
def draft_template(db, workspace_a, user_owner):
    return BriefingTemplate.objects.create(
        workspace=workspace_a,
        name='Briefing em Rascunho',
        status=BriefingTemplate.STATUS_DRAFT,
        is_active=True,
        created_by=user_owner,
    )


# =========================================================================
# BRIEFING
# =========================================================================

@pytest.fixture
def briefing_a(db, published_template, client_a, workspace_a, user_owner):
    from apps.briefings.services import BriefingService
    return BriefingService.create_briefing(
        template=published_template,
        client=client_a,
        workspace=workspace_a,
        actor=user_owner,
    )


# =========================================================================
# API CLIENTS
# =========================================================================

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner_client(api_client, user_owner, workspace_a):
    api_client.force_authenticate(user=user_owner)
    session = api_client.session
    session['current_workspace_id'] = str(workspace_a.id)
    session.save()
    return api_client


@pytest.fixture
def other_client(api_client, user_other, workspace_b):
    api_client.force_authenticate(user=user_other)
    session = api_client.session
    session['current_workspace_id'] = str(workspace_b.id)
    session.save()
    return api_client


@pytest.fixture
def outsider_client(api_client, user_outsider):
    api_client.force_authenticate(user=user_outsider)
    return api_client