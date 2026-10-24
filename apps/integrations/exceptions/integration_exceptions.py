"""
Hierarquia de exceções do módulo integrations.

    IntegrationError (base)
    ├── IntegrationConfigurationError
    ├── ConnectorNotFoundError
    ├── ConnectionNotFoundError
    ├── ConnectionNotEstablishedError
    ├── AmbiguousConnectionError
    ├── ConnectionExpiredError
    ├── ConnectionRevokedError
    ├── EncryptionError
    │   ├── EncryptionDecryptError
    │   └── EncryptionKeyMissingError
    ├── ProviderError
    │   ├── UnsupportedResourceError
    │   ├── OAuthExchangeError
    │   ├── InsufficientScopesError
    │   ├── RefreshTokenInvalidError
    │   ├── RefreshTransientError
    │   ├── RateLimitError
    │   ├── ProviderTimeoutError
    │   ├── ProviderServerError
    │   └── ProviderClientError
    ├── NormalizationError
    │   └── UnexpectedProviderPayloadError
    └── WorkspaceIntegrationError
        ├── IntegrationInactiveError
        ├── IntegrationAlreadyExistsError
        └── CannotRevokePreferredError

REGRA DE SEGURANÇA:
    `message` e `context` NUNCA contêm tokens, refresh_tokens,
    authorization codes ou client_secrets. Se um contexto precisar
    de tais dados, eles são hash/mascarados ANTES de serem anexados.

    A regra é verificada por testes de regressão em
    apps/integrations/tests/test_exception_sanitization.py.

NOMENCLATURA:
    "Connector" (não "Adapter") é o nome do componente que encapsula
    a comunicação com um provider externo. Isso evita colisão visual
    com `CustomSocialAccountAdapter` de apps/accounts/ (adapter do
    django-allauth para login de usuário via Google).
"""


class IntegrationError(Exception):
    """
    Base de todas as exceções de integrations.

    Não deve ser levantada diretamente. Use uma subclasse.

    `context` é um dict com dados diagnósticos seguros. Nunca deve
    conter tokens, refresh_tokens, authorization codes ou secrets.
    """

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message)
        self.context = context or {}


# =========================================================================
# CONFIGURAÇÃO DO APP / RESOLUÇÃO DE CONEXÃO
# =========================================================================

class IntegrationConfigurationError(IntegrationError):
    """
    Configuração obrigatória do módulo integrations está ausente
    ou inválida.

    Causa: variável de ambiente faltando, Client OAuth não configurado,
    settings incompletos.

    Diferente de UnsupportedResourceError (que é sobre um recurso
    pedido pelo chamador), esta é sobre o estado do próprio módulo.

    Contexto esperado:
        {"provider_key": str | None, "missing": str}
    """


class ConnectorNotFoundError(IntegrationError):
    """
    Provider sem connector registrado.

    Causa: bug de configuração (provider no catálogo sem connector
    correspondente registrado no ProviderRegistry).

    Contexto esperado: {"provider_key": str}
    """


class ConnectionNotFoundError(IntegrationError):
    """
    Integração referenciada não existe no workspace.

    Causa: chamador passou `integration_id` de outro workspace,
    ou um id que não existe.

    Contexto esperado: {"workspace_id": str, "integration_id": str}
    """


class ConnectionNotEstablishedError(IntegrationError):
    """
    Nenhuma integração ativa do provider no workspace.

    Causa: usuário ainda não conectou nenhuma conta, ou todas foram
    revogadas/expiradas.

    Contexto esperado: {"workspace_id": str, "provider_key": str}
    """


class AmbiguousConnectionError(IntegrationError):
    """
    Múltiplas contas ativas sem preferida. Exige escolha explícita.

    Causa: usuário conectou mais de uma conta do mesmo provider, e
    nenhuma foi marcada como preferida. O sistema NÃO escolhe por
    conta própria — o chamador deve passar `integration_id`.

    Contexto esperado:
        {"workspace_id": str, "provider_key": str, "count": int}
    """


class ConnectionExpiredError(IntegrationError):
    """
    Conexão expirada. Precisa reconectar.

    Causa: refresh_token inválido, ou revogação remota detectada.
    O estado persiste como 'expired' até o usuário reconectar.

    Contexto esperado: {"integration_id": str}
    """


class ConnectionRevokedError(IntegrationError):
    """
    Conexão revogada (local ou remotamente).

    Causa: revogação explícita pelo usuário ou pela Clivo, ou
    detecção de revogação remota no provider.

    Contexto esperado: {"integration_id": str, "revoked_remotely": bool}
    """


# =========================================================================
# CRIPTOGRAFIA
# =========================================================================

class EncryptionError(IntegrationError):
    """
    Base para erros de cifra/decifra.

    Não deve ser levantada diretamente. Use uma subclasse.
    """


class EncryptionDecryptError(EncryptionError):
    """
    Falha ao decifrar payload.

    Causa: chave errada, payload corrompido, ou versão de chave
    não reconhecida.

    A mensagem NUNCA inclui o plaintext nem fragmentos do ciphertext.
    """


class EncryptionKeyMissingError(EncryptionError):
    """
    Chave de criptografia ausente nas settings.

    Causa: INTEGRATIONS_ENCRYPTION_KEY não foi definida no ambiente.

    A mensagem NUNCA inclui o valor da chave.
    """


# =========================================================================
# PROVIDER
# =========================================================================

class ProviderError(IntegrationError):
    """
    Erro originado na comunicação com um provider externo.

    Base para todas as exceções que representam algo deu errado
    do lado do provider (rede, HTTP, autenticação remota).
    """


class UnsupportedResourceError(ProviderError):
    """
    Recurso pedido não é suportado pelo connector.

    Causa: chamador passou um slug de recurso que o connector
    não sabe traduzir para escopo OAuth.

    Contexto esperado:
        {"provider_key": str, "resource_slug": str}
    """


class OAuthExchangeError(ProviderError):
    """
    Troca de code por tokens falhou.

    Causa: code inválido, expirado, ou redirect_uri incompatível.
    A mensagem NUNCA inclui o code nem os tokens.

    Contexto esperado: {"provider_key": str}
    """


class InsufficientScopesError(ProviderError):
    """
    Faltam recursos obrigatórios para a operação.

    Causa: o usuário concedeu menos recursos do que a operação
    exige. Verificado contra os recursos obrigatórios, não contra
    todos os solicitados.

    Contexto esperado:
        {"operation": str, "missing_resources": list[str]}
    """


class RefreshTokenInvalidError(ProviderError):
    """
    Refresh token inválido ou revogado remotamente.

    Causa: usuário revogou acesso no provider, ou o refresh_token
    expirou por política do provider.

    Contexto esperado: {"provider_key": str}
    """


class RefreshTransientError(ProviderError):
    """
    Falha transitória no refresh (rede/5xx).

    Causa: erro de rede, timeout, ou resposta 5xx durante o refresh.

    Contexto esperado:
        {"provider_key": str, "retry_after_s": int | None}
    """


class RateLimitError(ProviderError):
    """
    Provider sinalizou rate limit (HTTP 429).

    Causa: muitas chamadas em curto intervalo.

    Contexto esperado: {"retry_after_s": int | None}
    """


class ProviderTimeoutError(ProviderError):
    """
    Timeout na comunicação com o provider.

    Causa: operação excedeu o timeout configurado.

    Contexto esperado: {"timeout_s": int}
    """


class ProviderServerError(ProviderError):
    """
    Erro 5xx do provider.

    Causa: falha no lado do provider.

    Contexto esperado: {"status_code": int}
    """


class ProviderClientError(ProviderError):
    """
    Erro 4xx genérico do provider.

    Causa: 4xx que não se encaixa em causas específicas.
    Preferir exceções específicas (NotFound, Forbidden, etc.) quando
    possível. Esta é a "fallback" para casos não mapeados.

    Contexto esperado: {"status_code": int}
    """


# =========================================================================
# NORMALIZAÇÃO
# =========================================================================

class NormalizationError(IntegrationError):
    """
    Falha ao converter payload do provider para contrato interno.

    Base para erros de normalização.
    """


class UnexpectedProviderPayloadError(NormalizationError):
    """
    Payload do provider não corresponde ao formato esperado.

    Causa: mudança no provider OU bug no normalizador. Indica
    divergência entre o que o código espera e o que veio.

    Contexto esperado: {"provider_key": str, "field": str}
    """


# =========================================================================
# ERROS DE NEGÓCIO
# =========================================================================

class WorkspaceIntegrationError(IntegrationError):
    """
    Base para erros de negócio no gerenciamento de integrações.

    Diferente de ProviderError (que é técnico), esta hierarquia
    representa violações de regras de negócio do workspace.
    """


class IntegrationInactiveError(WorkspaceIntegrationError):
    """
    Operação requer integração ativa, mas ela está inativa/revogada.

    Causa: chamador referenciou integração com `status != active`.

    Contexto esperado: {"integration_id": str, "status": str}
    """


class IntegrationAlreadyExistsError(WorkspaceIntegrationError):
    """
    Conta externa já conectada ao workspace com este provider.

    Causa: tentativa de conectar novamente a mesma conta.

    Contexto esperado:
        {"workspace_id": str, "provider_key": str, "external_account_id": str}
    """


class CannotRevokePreferredError(WorkspaceIntegrationError):
    """
    Não é possível revogar a conta preferida sem antes promover outra.

    Causa: chamador pediu revogação da conta marcada como preferida
    enquanto há outras contas ativas do mesmo provider. Evita
    deixar o workspace sem conta preferida por ação destrutiva.

    Contexto esperado: {"integration_id": str}
    """