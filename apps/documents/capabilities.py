"""
Capabilities declaradas pelo módulo documents.

REGRA: capability nasce no app que executa a ação.
"""

CAPABILITIES = [
    # ==================================================================
    # DOCUMENT
    # ==================================================================
    {
        'code': 'documents.document.view',
        'name': 'Ver arquivos',
        'description': (
            'Permite listar e visualizar arquivos do workspace, '
            'incluindo seus metadados e o histórico de alterações.'
        ),
    },
    {
        'code': 'documents.document.upload',
        'name': 'Subir arquivo',
        'description': 'Permite enviar novos arquivos para o workspace.',
    },
    {
        'code': 'documents.document.rename',
        'name': 'Renomear arquivo',
        'description': 'Permite alterar o nome de um arquivo já existente.',
    },
    {
        'code': 'documents.document.replace',
        'name': 'Substituir arquivo',
        'description': (
            'Permite substituir o arquivo físico de um documento '
            'já existente, mantendo o mesmo registro e atualizando '
            'extensão, MIME type e tamanho.'
        ),
    },
    {
        'code': 'documents.document.move',
        'name': 'Mover arquivo',
        'description': (
            'Permite mover arquivos entre pastas ou deixá-los soltos '
            'na biblioteca.'
        ),
    },
    {
        'code': 'documents.document.associate_client',
        'name': 'Associar arquivo a cliente',
        'description': (
            'Permite vincular ou desvincular um arquivo a um cliente.'
        ),
    },
    {
        'code': 'documents.document.associate_project',
        'name': 'Associar arquivo a projeto',
        'description': (
            'Permite vincular ou desvincular um arquivo a um projeto.'
        ),
    },
    {
        'code': 'documents.document.download',
        'name': 'Baixar arquivo',
        'description': 'Permite baixar o arquivo original do Clivo.',
    },
    {
        'code': 'documents.document.toggle_visibility',
        'name': 'Alterar visibilidade do arquivo',
        'description': (
            'Permite decidir se um arquivo é visível apenas ao '
            'escritório ou também ao cliente.'
        ),
    },
    {
        'code': 'documents.document.delete',
        'name': 'Excluir arquivo',
        'description': (
            'Permite excluir arquivos do workspace. Ação irreversível. '
            'O arquivo físico é removido permanentemente.'
        ),
    },

    # ==================================================================
    # FOLDER
    # ==================================================================
    {
        'code': 'documents.folder.view',
        'name': 'Ver pastas',
        'description': 'Permite listar e visualizar pastas do workspace.',
    },
    {
        'code': 'documents.folder.create',
        'name': 'Criar pasta',
        'description': 'Permite criar novas pastas no workspace.',
    },
    {
        'code': 'documents.folder.rename',
        'name': 'Renomear pasta',
        'description': 'Permite alterar o nome de uma pasta existente.',
    },
    {
        'code': 'documents.folder.delete',
        'name': 'Excluir pasta',
        'description': (
            'Permite excluir pastas. Os documentos dentro da pasta NÃO '
            'são excluídos — voltam a ficar soltos na biblioteca.'
        ),
    },
]