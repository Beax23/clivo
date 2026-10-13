"""
Testes do AdminWorkspaceViewSet.

Cobrem:
    - Autenticação e autorização (IsAuthenticated + IsConsoleAdmin).
    - Listagem com filtros (q, is_active, city).
    - Contagem de queries constante — sem N+1 por assinatura.

O endpoint é paginado pelo DRF (DEFAULT_PAGINATION_CLASS global).
Por isso `response.data` é o envelope `{'count', 'next', 'previous',
'results'}`, não a lista direta. Os testes usam `_results(response)`
para extrair a lista.

O teste de query-count mede o comportamento real do serializer. Ele
flagra N+1 — inclusive os que NÃO são de assinatura (members_count,
governance_keys). O limiar de `assertNumQueries` foi escolhido para
acomodar os N+1 pré-existentes do serializer, mas garantir que o
N+1 de assinatura NÃO cresça com o número de workspaces.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.console.models import ConsoleMembership, Plan
from apps.workspaces.models import Workspace, WorkspaceSubscription


User = get_user_model()

LIST_URL = '/api/console/workspaces/'


# =========================================================================
# HELPERS
# =========================================================================

def _results(response):
    """
    Extrai a lista de resultados do envelope paginado do DRF.

    O `AdminWorkspaceViewSet` é paginado (DEFAULT_PAGINATION_CLASS
    global). `response.data` é o dicionário
    `{'count', 'next', 'previous', 'results'}`, não a lista.
    """
    return response.data['results']


def _make_workspace(slug: str, name: str = None, city: str = '') -> Workspace:
    return Workspace.objects.create(
        name=name or f'WS {slug}',
        slug=slug,
        city=city,
    )


def _subscribe(workspace, plan, is_active=True):
    return WorkspaceSubscription.objects.create(
        workspace=workspace,
        plan=plan,
        is_active=is_active,
        started_at=workspace.created_at,
    )


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def plain_user_admin(db):
    """Usuário ativo, SEM ConsoleMembership."""
    return User.objects.create_user(
        email='plain-admin-ws@example.com',
        password='senha-fraca-123',
    )


@pytest.fixture
def console_admin_user(db):
    """Usuário ativo COM ConsoleMembership."""
    user = User.objects.create_user(
        email='admin-ws@example.com',
        password='senha-fraca-123',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    return user


@pytest.fixture
def admin_client(api_client, console_admin_user):
    api_client.force_authenticate(user=console_admin_user)
    return api_client


@pytest.fixture
def plain_client(api_client, plain_user_admin):
    api_client.force_authenticate(user=plain_user_admin)
    return api_client


@pytest.fixture
def plan_pro(db):
    return Plan.objects.create(
        key='pro',
        name='Pro',
        price=Decimal('99.00'),
        is_active=True,
    )


@pytest.fixture
def plan_basic(db):
    return Plan.objects.create(
        key='basic',
        name='Basic',
        price=Decimal('49.00'),
        is_active=True,
    )


# =========================================================================
# AUTENTICAÇÃO / AUTORIZAÇÃO
# =========================================================================

@pytest.mark.django_db
class TestAdminWorkspaceViewAuth:

    def test_anonymous_gets_401_or_403(self, api_client):
        response = api_client.get(LIST_URL)
        assert response.status_code in (401, 403)

    def test_authenticated_without_console_membership_gets_403(
        self, plain_client,
    ):
        response = plain_client.get(LIST_URL)
        assert response.status_code == 403

    def test_admin_gets_200(self, admin_client):
        response = admin_client.get(LIST_URL)
        assert response.status_code == 200


# =========================================================================
# LISTAGEM BÁSICA
# =========================================================================

@pytest.mark.django_db
class TestAdminWorkspaceViewListing:

    def test_empty_list(self, admin_client):
        response = admin_client.get(LIST_URL)
        assert response.status_code == 200
        assert response.data['count'] == 0
        assert _results(response) == []

    def test_lists_all_workspaces(self, admin_client, plan_pro):
        ws1 = _make_workspace('ws-1')
        ws2 = _make_workspace('ws-2')
        _subscribe(ws1, plan_pro, is_active=True)
        # ws2 sem assinatura

        response = admin_client.get(LIST_URL)
        assert response.status_code == 200
        assert response.data['count'] == 2
        assert len(_results(response)) == 2

    def test_serializer_exposes_plan_of_active_subscription(
        self, admin_client, plan_pro,
    ):
        ws = _make_workspace('ws-plan')
        _subscribe(ws, plan_pro, is_active=True)

        response = admin_client.get(LIST_URL)
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['plan_key'] == 'pro'
        assert results[0]['plan_name'] == 'Pro'

    def test_workspace_without_active_subscription_has_null_plan(
        self, admin_client, plan_pro,
    ):
        ws = _make_workspace('ws-no-plan')
        # Apenas assinatura inativa — não conta como plano ativo.
        _subscribe(ws, plan_pro, is_active=False)

        response = admin_client.get(LIST_URL)
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['plan_key'] is None
        assert results[0]['plan_name'] is None

    def test_plan_ignores_historical_inactive_subscriptions(
        self, admin_client, plan_pro, plan_basic,
    ):
        """
        Workspace com histórico de dois planos: só a ativa aparece.
        """
        ws = _make_workspace('ws-history')
        _subscribe(ws, plan_basic, is_active=False)
        _subscribe(ws, plan_pro, is_active=True)

        response = admin_client.get(LIST_URL)
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['plan_key'] == 'pro'


# =========================================================================
# FILTROS
# =========================================================================

@pytest.mark.django_db
class TestAdminWorkspaceViewFilters:

    def test_filter_by_q_matches_name(self, admin_client):
        _make_workspace('ws-alpha', name='Alpha Studio')
        _make_workspace('ws-beta', name='Beta Studio')

        response = admin_client.get(LIST_URL + '?q=alpha')
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['name'] == 'Alpha Studio'

    def test_filter_by_q_matches_slug(self, admin_client):
        _make_workspace('ws-gamma', name='Outro Nome')
        _make_workspace('ws-other', name='Nome Diferente')

        response = admin_client.get(LIST_URL + '?q=gamma')
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['slug'] == 'ws-gamma'

    def test_filter_by_is_active(self, admin_client):
        active_ws = _make_workspace('ws-active')
        inactive_ws = _make_workspace('ws-inactive')
        inactive_ws.is_active = False
        inactive_ws.save(update_fields=['is_active'])

        response = admin_client.get(LIST_URL + '?is_active=1')
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['slug'] == 'ws-active'

        response = admin_client.get(LIST_URL + '?is_active=0')
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['slug'] == 'ws-inactive'

    def test_filter_by_city(self, admin_client):
        _make_workspace('ws-salvador', city='Salvador')
        _make_workspace('ws-saopaulo', city='São Paulo')

        response = admin_client.get(LIST_URL + '?city=salvador')
        assert response.status_code == 200
        results = _results(response)
        assert len(results) == 1
        assert results[0]['city'] == 'Salvador'


# =========================================================================
# QUERY COUNT — SEM N+1 DE ASSINATURA
# =========================================================================

@pytest.mark.django_db
class TestAdminWorkspaceViewQueryCount:
    """
    O que este teste mede:

        O N+1 de ASSINATURA não existe. O `Prefetch` filtrado popula
        `_active_subscriptions`, e a property `Workspace.active_subscription`
        consome esse cache.

    O que este teste NÃO mede (ainda existem, fora do escopo do B2):

        O serializer `AdminWorkspaceSerializer` tem outros dois N+1:
            - `get_members_count`: 1 query por workspace
            - `get_governance_keys`: 1 query por workspace

        Esses N+1 pré-existentes fazem o número total de queries
        crescer linearmente com o número de workspaces — mas por
        razões que NÃO são assinatura.

    Por isso a asserção usa `assertNumQueries(..., exact=False)`:
    mede um TETO. O importante é que o teto seja o mesmo para 5 e
    para 10 workspaces — se o N+1 de assinatura voltasse, esse teto
    seria estourado.
    """

    def test_listing_with_many_workspaces_is_bounded(
        self, admin_client, plan_pro, django_assert_num_queries,
    ):
        """
        Cria 10 Workspaces, todos com assinatura ativa.

        Conta esperada:
            - 1 auth (ConsoleMembership)
            - 1 COUNT (paginação)
            - 1 SELECT workspace
            - 1 Prefetch de assinaturas ativas
            - 20 queries do serializer (2 por workspace: members + governance)
            - ~algumas queries de sessão/middleware
        """
        for i in range(10):
            ws = _make_workspace(f'ws-many-{i}')
            _subscribe(ws, plan_pro, is_active=True)

        # Teto: o N+1 de assinatura NÃO conta. Se contasse, seria
        # 10 queries a mais (uma por workspace). O teto reflete apenas
        # os N+1 pré-existentes do serializer.
        with django_assert_num_queries(30, exact=False):
            response = admin_client.get(LIST_URL)

        assert response.status_code == 200
        assert response.data['count'] == 10
        assert len(_results(response)) == 10

    def test_listing_with_mixed_workspaces_is_bounded(
        self, admin_client, plan_pro, django_assert_num_queries,
    ):
        """
        Mistura: Workspaces com assinatura ativa, com apenas histórico,
        e sem nenhuma assinatura. O número de queries deve permanecer
        dentro do mesmo teto — o Prefetch de assinatura não depende
        da presença delas.
        """
        for i in range(5):
            ws = _make_workspace(f'ws-active-{i}')
            _subscribe(ws, plan_pro, is_active=True)

        for i in range(3):
            ws = _make_workspace(f'ws-hist-{i}')
            _subscribe(ws, plan_pro, is_active=False)

        for i in range(2):
            _make_workspace(f'ws-empty-{i}')

        with django_assert_num_queries(30, exact=False):
            response = admin_client.get(LIST_URL)

        assert response.status_code == 200
        assert response.data['count'] == 10
        assert len(_results(response)) == 10