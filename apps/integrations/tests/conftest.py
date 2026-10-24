"""
Fixtures compartilhadas dos testes de integrations.

Concentra as fixtures usadas por mais de um arquivo. Fixtures
específicas de um arquivo moram no próprio arquivo.
"""

import pytest
from rest_framework.test import APIClient


# =========================================================================
# API CLIENT BASE
# =========================================================================

@pytest.fixture
def api_client():
    """
    Cliente DRF anônimo. Usado como base para outros clients.
    """
    return APIClient()


# =========================================================================
# PROVIDERS
# =========================================================================

@pytest.fixture
def integration_provider_google(db):
    """IntegrationProvider para Google."""
    from apps.integrations.models import IntegrationProvider
    return IntegrationProvider.objects.create(
        key='google',
        name='Google',
        category='productivity',
    )


# Alias para consistência com os testes que usam `provider_google`
@pytest.fixture
def provider_google(integration_provider_google):
    """
    Alias de `integration_provider_google`.

    Testes de view usam `provider_google`; testes de serviço usam
    `integration_provider_google`. Ambos apontam para a mesma
    fixture para evitar duplicação.
    """
    return integration_provider_google


# =========================================================================
# WORKSPACES
# =========================================================================

@pytest.fixture
def workspace_for_integrations(db):
    """Workspace simples para testes que não precisam de membership."""
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(
        name='WS Integrations',
        slug='ws-integrations',
    )