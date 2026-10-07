"""
Console — Control Plane administrativo da Clivo.

============================================================================
REGRA ARQUITETURAL
============================================================================

    Console administra a plataforma.
    Os domínios executam suas próprias regras de negócio.

============================================================================
AUTORIZAÇÃO NO V1
============================================================================

    ConsoleMembership
         ↓
    acesso administrativo integral ao Console

Todo usuário com ConsoleMembership é administrador do Console.
Não há níveis de administrador no Console.
A Governance NÃO controla o acesso ao Console.

============================================================================
GOVERNANCE — QUEM CRIA E QUEM CONSOME
============================================================================

Governance é criada e administrada pelo Console.

    Console
        │
        │  cria / edita / exclui
        ▼
    ConsoleGovernance
        │
        │  associa capabilities
        ▼
    ConsoleGovernanceCapability
        │
        ▼
    ConsoleCapability

Quando `workspaces` existir, ele irá:

    - referenciar uma Governance existente
    - atribuir essa Governance aos seus membros
    - executar autorização baseada nessa Governance

O Workspace NÃO cria nem administra Governance.
O Workspace NÃO possui um segundo modelo de Governance.

Referência futura:

    WorkspaceMembership
        └── governance → ConsoleGovernance

============================================================================
CAPABILITY — QUEM DECLARA E QUEM CATALOGA
============================================================================

Capability nasce no app que executa a ação.

    apps/<app>/capabilities.py
        │
        │  declara
        ▼
    CAPABILITIES = [...]

O Console descobre e cataloga.

    ConsoleCapabilityService.discover_capabilities()
        │
        ▼
    ConsoleCapability
        │
        ▼
    ConsoleGovernanceCapability
        │
        ▼
    ConsoleGovernance

Regra:
    - App declara.
    - Console cataloga.
    - Governance seleciona.
    - Workspace (futuro) consome via Authorization.

============================================================================
CAMADAS DO CONSOLE V1
============================================================================

ConsoleMembership
    Quem administra a plataforma.

ConsoleGovernance / ConsoleGovernanceCapability / ConsoleCapability
    Governanças e capabilities administradas pelo Console.

Provider / ProviderConnection / ProviderContract
    Identidade, conexões e contratos dos fornecedores externos.

ProviderPricing
    Quanto custa cada unidade de consumo (economia interna da Clivo).

UsageMetric
    Catálogo de métricas de uso (tokens, bytes, emails, etc).

UsageRecord
    Telemetria econômica: consumo real, agregado por provider,
    metric e (opcionalmente) workspace.

ProviderLog
    Observabilidade operacional: cada chamada a um provider,
    com latência, status, modelo e correlação.

============================================================================
COMERCIAL — PLANOS, FEATURES E LIMITES
============================================================================

Plan
    Pacote comercial vendido pela Clivo (Starter, Pro, Enterprise).

Feature
    Catálogo comercial de itens que um plano pode oferecer.
    Feature NÃO é permissão. Feature NÃO agrupa capabilities.
    Feature é apenas um item comercial.

PlanFeature
    Associação entre Plan e Feature.
    Um plano oferece várias features; uma feature pode
    pertencer a vários planos.

PlanFeatureLimit
    Quanto de uma métrica uma Feature permite dentro de um Plan.
    Um limite é sempre contra uma UsageMetric do catálogo.
    O limite vive aqui, NÃO na Feature.

    Diagrama:

        Plan
            └── PlanFeature
                    └── PlanFeatureLimit
                            └── UsageMetric

============================================================================
SERVIÇOS ECONÔMICOS
============================================================================

CostService
    Cálculo determinístico: UsageRecord × ProviderPricing → custo.

MarginService
    Estimativa de margem por plano
    (preço de tabela - custo estimado).

============================================================================
O QUE O CONSOLE NÃO POSSUI
============================================================================

O Console NÃO contém modelos ou regras de negócio de outros domínios:

    Workspace / WorkspaceMembership   → pertence a `workspaces` (futuro)
    Client                            → pertence a `clients` (futuro)
    Briefing                          → pertence a `briefings` (futuro)
    Document                          → pertence a `documents` (futuro)
    Intelligence                      → pertence a `intelligence` (futuro)
    Subscription / Billing            → deferred
    Invoice                           → deferred
    CostEngine                        → responsabilidade do CostService

============================================================================
RELAÇÃO ENTRE APPS
============================================================================

    accounts          (identidade)
         ↑
    console           (governa)
         │
         ├── administra Governance
         ├── cataloga Capabilities
         ├── administra providers / pricing / plans / features
         ├── registra uso e observabilidade
         └── calcula custo e margem
                ↑
    workspaces        (executa — futuro)
         │
         ├── Workspace
         ├── WorkspaceMembership
         ├── referencia Governance do Console
         └── Authorization
                ↑
    clients / briefings / documents / intelligence / integrations
         └── executam seus próprios domínios
         └── reportam uso via UsageRecordService / ProviderLogService

============================================================================
FRONTEIRA CONGELADA (V1)
============================================================================

    CONSOLE administra.
    WORKSPACE consome.

    Governance: Console cria, Workspace referencia.
    Capability: App declara, Console cataloga, Workspace autoriza.
    Usage:      Domínio reporta, Console cataloga.
    Custo:      Console calcula.
    Billing:    Não existe na V1.
"""

default_app_config = 'apps.console.apps.ConsoleConfig'