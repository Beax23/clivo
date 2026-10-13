"""
Capabilities declaradas pelo módulo references.
"""

CAPABILITIES = [
    # ==================================================================
    # REFERENCE
    # ==================================================================
    {
        'code': 'references.reference.view',
        'name': 'Ver referências',
        'description': (
            'Permite listar e visualizar referências do workspace, '
            'incluindo seus metadados e o histórico de alterações.'
        ),
    },
    {
        'code': 'references.reference.upload',
        'name': 'Subir referência',
        'description': (
            'Permite enviar novas imagens de referência para o workspace.'
        ),
    },
    {
        'code': 'references.reference.edit',
        'name': 'Editar referência',
        'description': (
            'Permite alterar título, descrição e categorias de uma '
            'referência já existente.'
        ),
    },
    {
        'code': 'references.reference.replace_image',
        'name': 'Substituir imagem',
        'description': (
            'Permite substituir a imagem física de uma referência '
            'já existente, mantendo o mesmo registro.'
        ),
    },
    {
        'code': 'references.reference.move',
        'name': 'Mover referência',
        'description': (
            'Permite mover referências entre pastas ou deixá-las '
            'soltas na biblioteca.'
        ),
    },
    {
        'code': 'references.reference.associate_client',
        'name': 'Associar referência a cliente',
        'description': (
            'Permite vincular ou desvincular uma referência a um cliente.'
        ),
    },
    {
        'code': 'references.reference.associate_project',
        'name': 'Associar referência a projeto',
        'description': (
            'Permite vincular ou desvincular uma referência a um projeto.'
        ),
    },
    {
        'code': 'references.reference.download',
        'name': 'Baixar imagem da referência',
        'description': (
            'Permite baixar a imagem original de uma referência do Clivo.'
        ),
    },
    {
        'code': 'references.reference.toggle_visibility',
        'name': 'Alterar visibilidade da referência',
        'description': (
            'Permite decidir se uma referência é visível apenas ao '
            'escritório ou também ao cliente.'
        ),
    },
    {
        'code': 'references.reference.delete',
        'name': 'Excluir referência',
        'description': (
            'Permite excluir referências do workspace. Ação irreversível. '
            'A imagem física é removida permanentemente. O histórico '
            'é preservado com a referência marcada como excluída.'
        ),
    },

    # ==================================================================
    # FOLDER
    # ==================================================================
    {
        'code': 'references.folder.view',
        'name': 'Ver pastas de referências',
        'description': 'Permite listar e visualizar pastas do workspace.',
    },
    {
        'code': 'references.folder.create',
        'name': 'Criar pasta de referências',
        'description': 'Permite criar novas pastas de referências no workspace.',
    },
    {
        'code': 'references.folder.rename',
        'name': 'Renomear pasta de referências',
        'description': 'Permite alterar o nome de uma pasta existente.',
    },
    {
        'code': 'references.folder.delete',
        'name': 'Excluir pasta de referências',
        'description': (
            'Permite excluir pastas. As referências dentro da pasta NÃO '
            'são excluídas — voltam a ficar soltas na biblioteca.'
        ),
    },

    # ==================================================================
    # CATEGORY
    # ==================================================================
    {
        'code': 'references.category.view',
        'name': 'Ver categorias',
        'description': (
            'Permite listar e visualizar categorias de referências.'
        ),
    },
    {
        'code': 'references.category.create',
        'name': 'Criar categoria',
        'description': (
            'Permite criar novas categorias de referências no workspace.'
        ),
    },
    {
        'code': 'references.category.rename',
        'name': 'Renomear categoria',
        'description': (
            'Permite alterar o nome de uma categoria existente.'
        ),
    },
    {
        'code': 'references.category.delete',
        'name': 'Excluir categoria',
        'description': (
            'Permite excluir categorias. As referências dentro da categoria '
            'NÃO são excluídas — ficam sem categoria até o usuário reatribuir.'
        ),
    },
]