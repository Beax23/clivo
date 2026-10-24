"""
Testes da validação de redirects internos.
"""

import pytest

from apps.integrations.services.redirects import (
    DEFAULT_FALLBACK,
    is_safe_redirect,
    safe_redirect_or_fallback,
)


class TestIsSafeRedirect:

    @pytest.mark.parametrize('target', [
        '/w/abc123/integracoes/',
        '/w/abc123/integracoes',
        '/w/abc123/configuracoes/',
        '/w/abc123/configuracoes',
        '/w/abc123/mesa/',
        '/w/abc123/qualquer/coisa/',
        '/workspaces/entrar/',
        '/workspaces/entrar',
        '/w/A-b_c-d/integracoes/',
        '/fluxo/',
        '/clientes/',
        '/configuracoes/',
        '/mesa/',
    ])
    def test_allowed(self, target):
        assert is_safe_redirect(target) is True

    @pytest.mark.parametrize('target', [
        '',
        None,
        'https://evil.com',
        'http://evil.com',
        '//evil.com',
        '/\\evil.com',
        '/admin/',
        'javascript:alert(1)',
    ])
    def test_blocked(self, target):
        assert is_safe_redirect(target) is False

    @pytest.mark.parametrize('target', [
        '/w/abc/../../../admin',
        '/w/abc/..',
        '/w/abc/../outro',
        '/fluxo/../../../etc/passwd',
        '/fluxo/%2e%2e/%2e%2e/admin',
        '/fluxo/%252e%252e/admin',
        '/w/abc/integracoes\\..\\..\\admin',
    ])
    def test_path_traversal_blocked(self, target):
        assert is_safe_redirect(target) is False


class TestSafeRedirectOrFallback:

    def test_returns_target_if_safe(self):
        target = '/w/abc/integracoes/'
        assert safe_redirect_or_fallback(target) == target

    def test_returns_target_for_fluxo(self):
        target = '/fluxo/'
        assert safe_redirect_or_fallback(target) == target

    def test_returns_fallback_if_unsafe(self):
        assert safe_redirect_or_fallback('https://evil.com') == DEFAULT_FALLBACK
        assert safe_redirect_or_fallback('//evil.com') == DEFAULT_FALLBACK
        assert safe_redirect_or_fallback('') == DEFAULT_FALLBACK
        assert safe_redirect_or_fallback(None) == DEFAULT_FALLBACK

    def test_returns_fallback_for_path_traversal(self):
        assert safe_redirect_or_fallback('/w/abc/../../../admin') == DEFAULT_FALLBACK