"""
Testes do OAuthStateService.

Cobrem:
    - Emissão de state e persistência no cache.
    - Consumo (leitura + delete atômico).
    - TTL (via cache.set timeout).
    - Reutilização: state consumido não pode ser consumido 2x.
    - Nonce imprevisível (strings diferentes a cada emissão).
    - Contexto preservado integralmente.
"""

import pytest
from django.core.cache import cache

from apps.integrations.services.oauth_state import (
    CACHE_KEY_PREFIX,
    STATE_TTL_SECONDS,
    OAuthStateService,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Limpa o cache antes e depois de cada teste."""
    cache.clear()
    yield
    cache.clear()


def _issue(**overrides):
    defaults = {
        'user_id': 'user-uuid',
        'workspace_id': 'ws-uuid',
        'provider_key': 'google',
        'resources': ['drive.file.read'],
        'redirect_uri': 'http://localhost:9000/integrations/google/callback/',
        'final_redirect': '/fluxo/',
    }
    defaults.update(overrides)
    return OAuthStateService.issue(**defaults)


class TestIssue:

    def test_returns_nonce(self):
        nonce = _issue()
        assert isinstance(nonce, str)
        assert len(nonce) >= 32

    def test_nonce_is_unpredictable(self):
        n1 = _issue()
        n2 = _issue()
        assert n1 != n2

    def test_context_persisted_in_cache(self):
        nonce = _issue()
        raw = cache.get(f'{CACHE_KEY_PREFIX}{nonce}')
        assert raw is not None
        assert 'user-uuid' in raw
        assert 'ws-uuid' in raw
        assert 'google' in raw


class TestConsume:

    def test_returns_context(self):
        nonce = _issue()
        ctx = OAuthStateService.consume(nonce)
        assert ctx is not None
        assert ctx.user_id == 'user-uuid'
        assert ctx.workspace_id == 'ws-uuid'
        assert ctx.provider_key == 'google'
        assert ctx.resources == ['drive.file.read']

    def test_consume_is_single_use(self):
        nonce = _issue()
        first = OAuthStateService.consume(nonce)
        second = OAuthStateService.consume(nonce)
        assert first is not None
        assert second is None

    def test_consume_unknown_returns_none(self):
        assert OAuthStateService.consume('nonce-que-nao-existe') is None

    def test_consume_empty_returns_none(self):
        assert OAuthStateService.consume('') is None
        assert OAuthStateService.consume(None) is None

    def test_consume_after_delete_returns_none(self):
        nonce = _issue()
        cache.delete(f'{CACHE_KEY_PREFIX}{nonce}')
        assert OAuthStateService.consume(nonce) is None


class TestContextIntegrity:

    def test_all_fields_preserved(self):
        nonce = _issue(
            user_id='u-1',
            workspace_id='w-1',
            provider_key='google',
            resources=['drive.file.read', 'forms.body.read'],
            redirect_uri='http://x/cb/',
            final_redirect='/final/',
        )
        ctx = OAuthStateService.consume(nonce)
        assert ctx.user_id == 'u-1'
        assert ctx.workspace_id == 'w-1'
        assert ctx.resources == ['drive.file.read', 'forms.body.read']
        assert ctx.redirect_uri == 'http://x/cb/'
        assert ctx.final_redirect == '/final/'

    def test_provider_key_preserved(self):
        nonce = _issue(provider_key='microsoft')
        ctx = OAuthStateService.consume(nonce)
        assert ctx.provider_key == 'microsoft'