"""
Fixtures compartilhadas do app `console`.

Contém apenas fixtures que são usadas por mais de um arquivo de teste
OU que encapsulam setup não-trivial (ex: criação de usuário autenticado
com ConsoleMembership).

Fixtures específicas de um único arquivo de teste devem morar no
próprio arquivo — não aqui.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.console.models import ConsoleMembership

User = get_user_model()


# =========================================================================
# USUÁRIOS
# =========================================================================

@pytest.fixture
def plain_user(db):
    """
    Usuário comum, ativo, SEM ConsoleMembership.

    Serve para testar rejeição em endpoints do Console.
    """
    return User.objects.create_user(
        email='plain@example.com',
        password='senha-fraca-123',
    )


@pytest.fixture
def console_admin(db):
    """
    Usuário ativo COM ConsoleMembership.

    V1: ConsoleMembership concede acesso administrativo integral.
    Não há níveis — todo membro é admin.
    """
    user = User.objects.create_user(
        email='admin@example.com',
        password='senha-fraca-123',
    )
    ConsoleMembership.objects.create(user=user, created_by=user)
    return user


# =========================================================================
# API CLIENTS
# =========================================================================

@pytest.fixture
def api_client():
    """
    APIClient anônimo. Não autenticado.

    Usa SessionAuthentication por padrão — o mesmo que o projeto.
    """
    return APIClient()


@pytest.fixture
def plain_client(api_client, plain_user):
    """
    APIClient autenticado como usuário comum (sem ConsoleMembership).
    """
    api_client.force_authenticate(user=plain_user)
    return api_client


@pytest.fixture
def admin_client(api_client, console_admin):
    """
    APIClient autenticado como admin do Console.
    """
    api_client.force_authenticate(user=console_admin)
    return api_client