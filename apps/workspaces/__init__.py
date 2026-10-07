"""
Workspaces — tenant boundary da Clivo.

============================================================================
REGRA ARQUITETURAL
============================================================================

    Console administra a plataforma.
    Workspace executa o trabalho do escritório.

O app `workspaces` é DELIBERADAMENTE pequeno. Ele não replica a
complexidade administrativa do Console.

============================================================================
O QUE O WORKSPACE POSSUI (V1)
============================================================================

    Workspace
        └── identidade do escritório (nome, slug, CNPJ, cidade/UF)

    WorkspaceMembership
        ├── user
        └── governance → ConsoleGovernance

    WorkspaceSubscription
        └── plan → ConsolePlan

============================================================================
O QUE O WORKSPACE NÃO POSSUI
============================================================================

    Governance própria          → pertence ao Console
    Capability própria          → pertence ao Console
    Plan próprio                → pertence ao Console
    Feature própria             → pertence ao Console
    Branding / logo / settings  → deferred
    Client / Project / Briefing → outros domínios (futuro)
    Document / Intelligence     → outros domínios (futuro)
    Billing / Invoice           → deferred

============================================================================
FRONTEIRA CONGELADA (V1)
============================================================================

    Console administra Governance, Capability, Plan, Feature.
    Workspace consome via referência (FK).

    WorkspaceMembership.governance  → ConsoleGovernance
    WorkspaceSubscription.plan      → ConsolePlan

    O Workspace NÃO duplica nem redefine nenhum desses conceitos.
"""

default_app_config = 'apps.workspaces.apps.WorkspacesConfig'