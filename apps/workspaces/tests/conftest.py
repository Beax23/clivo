"""
Fixtures compartilhadas do app workspaces.

Contém apenas fixtures usadas por mais de um arquivo de teste.
Fixtures específicas de um arquivo devem morar nele.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# =========================================================================
# USUÁRIOS
# =========================================================================

@pytest.fixture
def user_member(db):
    """Usuário comum que será membro do workspace."""
    return User.objects.create_user(
        email='member@example.com',
        password='senha-fraca-123',
    )


@pytest.fixture
def user_outsider(db):
    """Usuário ativo, sem membership em nenhum workspace."""
    return User.objects.create_user(
        email='outsider@example.com',
        password='senha-fraca-123',
    )


# =========================================================================
# API CLIENTS
# =========================================================================

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def member_client(api_client, user_member):
    api_client.force_authenticate(user=user_member)
    return api_client


@pytest.fixture
def outsider_client(api_client, user_outsider):
    api_client.force_authenticate(user=user_outsider)
    return api_client