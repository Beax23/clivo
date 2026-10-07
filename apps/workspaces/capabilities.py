"""
Capabilities declaradas pelo módulo workspaces.

REGRA ARQUITETURAL:
    Capability nasce no app que executa a ação.
    O Console descobre, cataloga e permite que Governanças selecionem.

FORMATO:
    code        → "<app>.<resource>.<action>"
                  (o primeiro segmento DEVE ser o label do AppConfig: 'workspaces')
    name        → nome exibido no Console
    description → descrição do que a capability permite
"""

CAPABILITIES = [
    # ==================================================================
    # WORKSPACE
    # ==================================================================

    {
        'code': 'workspaces.workspace.view',
        'name': 'Ver Workspace',
        'description': (
            'Permite visualizar os dados do Workspace '
            '(nome, CNPJ, cidade, estado, plano ativo).'
        ),
    },
    {
        'code': 'workspaces.workspace.update',
        'name': 'Editar Workspace',
        'description': (
            'Permite alterar nome, CNPJ, cidade e estado do Workspace.'
        ),
    },
    {
        'code': 'workspaces.workspace.delete',
        'name': 'Excluir Workspace',
        'description': (
            'Permite excluir o Workspace e todos os dados associados. '
            'Ação irreversível.'
        ),
    },

    # ==================================================================
    # MEMBERS
    # ==================================================================

    {
        'code': 'workspaces.member.view',
        'name': 'Ver membros',
        'description': (
            'Permite listar os membros do Workspace e suas governanças.'
        ),
    },
    {
        'code': 'workspaces.member.invite',
        'name': 'Convidar membro',
        'description': (
            'Permite convidar um novo membro por email, '
            'atribuindo-lhe uma governança do escopo workspace.'
        ),
    },
    {
        'code': 'workspaces.member.remove',
        'name': 'Remover membro',
        'description': (
            'Permite remover um membro do Workspace ou cancelar um convite. '
            'O último proprietário não pode ser removido.'
        ),
    },
    {
        'code': 'workspaces.member.change_governance',
        'name': 'Alterar governança de membro',
        'description': (
            'Permite trocar a governança atribuída a um membro ou convite. '
            'O último proprietário não pode ser rebaixado.'
        ),
    },

    # ==================================================================
    # SUBSCRIPTION
    # ==================================================================

    {
        'code': 'workspaces.subscription.view',
        'name': 'Ver assinatura',
        'description': (
            'Permite visualizar o plano ativo do Workspace.'
        ),
    },
]