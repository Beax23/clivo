"""
ProviderConnector — contrato que todo connector de provider cumpre.

O connector encapsula OAuth, tradução recurso→escopo, chamadas HTTP,
paginação, rate limit e erros específicos do provider.

O connector NÃO faz:
    - autorização de usuário
    - isolamento de workspace
    - decisão de qual conta usar

NOTA DE NOMENCLATURA:
    NÃO confundir com `CustomSocialAccountAdapter` de `apps.accounts`,
    que é adapter do django-allauth para login de usuário via Google.
    São coisas diferentes:
        - allauth Adapter → identidade de usuário (login)
        - ProviderConnector → operações com API externa (Drive, Forms)
"""

from abc import ABC, abstractmethod

from apps.integrations.providers.types import OAuthResult


class ProviderConnector(ABC):

    # Identificador canônico do provider. Corresponde a
    # IntegrationProvider.key.
    key: str = ''

    # =====================================================================
    # OAUTH
    # =====================================================================

    @abstractmethod
    def build_auth_url(
        self,
        *,
        redirect_uri: str,
        resources: list,
        state: str,
    ) -> str:
        """
        Gera a URL de autorização do provider.

        `resources` é uma lista de slugs de IntegrationResource.
        O connector traduz cada slug para o escopo OAuth correspondente.

        Levanta UnsupportedResourceError se algum recurso não é
        suportado pelo connector.
        """

    @abstractmethod
    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OAuthResult:
        """
        Troca code por tokens.

        Levanta:
            - OAuthExchangeError se o provider recusa o code.
            - InsufficientScopesError se faltar recurso obrigatório.
        """

    @abstractmethod
    def refresh(
        self,
        *,
        refresh_token: str,
    ) -> OAuthResult:
        """
        Renova o access_token.

        Levanta:
            - RefreshTokenInvalidError se o refresh_token é inválido.
            - RefreshTransientError se foi erro transitório.
        """

    @abstractmethod
    def revoke(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        """
        Revoga tokens no provider.

        Best-effort: se o provider não responder, o connector registra
        o erro mas não levanta (a revogação local já foi feita).
        """

    # =====================================================================
    # HELPERS DE MAPEAMENTO
    # =====================================================================

    @abstractmethod
    def resource_to_scope(self, resource_slug: str) -> str:
        """
        Traduz um slug de recurso para o escopo OAuth correspondente.

        Levanta UnsupportedResourceError se o slug não existe.
        """

    def required_resources_for_operation(self, operation: str) -> list:
        """
        Retorna os recursos obrigatórios para uma operação.

        Subclasses sobrescrevem. Default: lista vazia.
        """
        return []

    def optional_resources_for_operation(self, operation: str) -> list:
        """
        Retorna os recursos opcionais para uma operação.

        Subclasses sobrescrevem. Default: lista vazia.
        """
        return []