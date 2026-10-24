"""
Integrations — ferramentas externas conectadas pelo escritório.

============================================================================
FRONTEIRA ARQUITETURAL — console × integrations
============================================================================

    console      → fornecedores de infraestrutura da Clivo.
                   Quanto a Clivo gasta, com quem, em quê.
                   Dono de: Provider, ProviderConnection,
                            ProviderContract, ProviderPricing,
                            UsageRecord, ProviderLog.

    integrations → ferramentas externas que o escritório conecta
                   para operar.
                   Dono de: IntegrationProvider, IntegrationResource,
                            WorkspaceIntegration, ProviderConnector,
                            ExternalFile, ExternalForm.

============================================================================
REGRAS DE FRONTEIRA (CONGELADAS)
============================================================================

    1. console NUNCA importa integrations.
    2. integrations NUNCA importa console.models.Provider
       (nem qualquer outro model de fornecedor do console).
    3. Utilitários técnicos genéricos (cifra, logging, correlation,
       envelope de erro) podem viver em core/ e ser consumidos por
       ambos, sem criar dependência entre os domínios.
    4. Modelos e regras de negócio NUNCA são compartilhados entre os
       dois eixos.

    Protegido por teste automatizado em
    apps/integrations/tests/test_architectural_boundaries.py.

============================================================================
O QUE O APP POSSUI
============================================================================

    IntegrationProvider     → catálogo de serviços externos
    IntegrationResource     → recursos que um provider oferece
    WorkspaceIntegration    → conta externa autorizada por um workspace

    WorkspaceIntegrationService
                            → API interna para apps consumidores

    ProviderConnector       → contrato para comunicação com APIs externas
    ProviderRegistry        → registro em memória dos connectors

    EncryptionService       → cifra de credenciais em repouso

============================================================================
NOTA DE NOMENCLATURA — ProviderConnector × SocialAccountAdapter
============================================================================

    O termo "connector" foi escolhido para evitar colisão conceitual
    com `CustomSocialAccountAdapter` de `apps/accounts/`, que é um
    adapter do django-allauth para login de usuário via Google.

    São coisas distintas:

        - allauth Adapter     → identidade de usuário (login)
        - ProviderConnector   → operações com API externa (Drive, Forms)

    Os dois convivem sem competir. O primeiro gerencia QUEM o usuário é.
    O segundo gerencia COMO o workspace acessa serviços externos.

============================================================================
O QUE O APP NÃO POSSUI
============================================================================

    - Credenciais de infraestrutura da Clivo  → console
    - Identidade do usuário                   → accounts
    - Tenant owner                            → workspaces
    - Regras de negócio de consumidores       → briefings, intelligence, ...
    - Grants por consumer_app                 → fora do V1 (decisão congelada)

============================================================================
V1 — ESCOPO
============================================================================

    - Reconexão completa (sem consentimento incremental).
    - Somente leitura (sem upload/escrita).
    - Um provider: Google (Drive, Forms).
    - Sem grants por app consumidor.
    - Sem auditoria por consumer_app.
"""

default_app_config = 'apps.integrations.apps.IntegrationsConfig'