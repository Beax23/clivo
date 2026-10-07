"""
Capabilities declaradas pelo módulo clients.

REGRA: capability nasce no app que executa a ação.
O Console descobre, cataloga e permite que Governanças selecionem.

Formato: <app>.<resource>.<action> — o primeiro segmento DEVE ser
o label do AppConfig ('clients').
"""

CAPABILITIES = [
    # ==================================================================
    # CLIENT
    # ==================================================================
    {
        'code': 'clients.client.view',
        'name': 'Ver clientes',
        'description': (
            'Permite listar e visualizar clientes do workspace, '
            'incluindo seu contexto consolidado.'
        ),
    },
    {
        'code': 'clients.client.create',
        'name': 'Criar cliente',
        'description': 'Permite cadastrar novos clientes no workspace.',
    },
    {
        'code': 'clients.client.update',
        'name': 'Editar cliente',
        'description': (
            'Permite alterar dados cadastrais, status e contexto do cliente.'
        ),
    },
    {
        'code': 'clients.client.delete',
        'name': 'Excluir cliente',
        'description': (
            'Permite excluir clientes do workspace. Ação irreversível.'
        ),
    },

    # ==================================================================
    # CONTACTS
    # ==================================================================
    {
        'code': 'clients.contact.manage',
        'name': 'Gerenciar contatos',
        'description': (
            'Permite criar, editar e remover contatos de um cliente.'
        ),
    },

    # ==================================================================
    # NOTES
    # ==================================================================
    {
        'code': 'clients.note.create',
        'name': 'Adicionar nota',
        'description': 'Permite adicionar anotações a um cliente.',
    },
    {
        'code': 'clients.note.update',
        'name': 'Editar nota',
        'description': 'Permite editar anotações de um cliente.',
    },
    {
        'code': 'clients.note.delete',
        'name': 'Excluir nota',
        'description': 'Permite excluir anotações de um cliente.',
    },

    # ==================================================================
    # PORTAL
    # ==================================================================
    {
        'code': 'clients.portal.view',
        'name': 'Ver Portal do cliente',
        'description': (
            'Permite visualizar o estado do Portal do cliente, '
            'incluindo sessões e histórico de acesso.'
        ),
    },
    {
        'code': 'clients.portal.share',
        'name': 'Compartilhar acesso via Portal',
        'description': (
            'Permite enviar/reenviar o acesso do cliente ao Portal.'
        ),
    },
]