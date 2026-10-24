"""
Tipos de suporte aos connectors.

Estes tipos são INTERNOS ao módulo integrations. Não vazam para
consumidores. Os consumidores recebem ExternalFile/ExternalForm
da camada de normalização.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class OAuthResult:
    """
    Resultado de uma troca de código ou refresh.

    Representa fielmente a resposta do provider. Se o provider não
    devolve refresh_token, refresh_token=None — o connector não inventa.
    """
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    granted_scopes: list[str]
    external_account_id: str
    external_account_email: str
    external_account_display_name: str
    external_account_avatar_url: str | None
    provider_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PaginatedResult:
    """
    Envelope de paginação bruto (baixo nível).

    O consumidor normalmente usa o iterador de alto nível
    (ex: list_files_all), que encapsula a paginação.
    """
    items: list
    next_cursor: str | None
    has_more: bool
    provider_metadata: dict = field(default_factory=dict)