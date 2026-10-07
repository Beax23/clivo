"""
Capabilities declaradas pelo módulo documents.

REGRA: capability nasce no app que executa a ação.
O Console descobre, cataloga e permite que Governanças selecionem.

Formato: <app>.<resource>.<action> — o primeiro segmento DEVE ser
o label do AppConfig ('documents').

NOTA SOBRE GRANULARIDADE
------------------------
As capabilities refletem operações reais e distinguíveis.

O que É permissão:

    "pode ver arquivos do workspace"
    "pode subir arquivo"
    "pode renomear arquivo"
    "pode substituir o arquivo físico"
    "pode associar arquivo a um cliente"
    "pode associar arquivo a um projeto"
    "pode baixar arquivo"
    "pode excluir arquivo"

O que NÃO é permissão:

    - "pode ver histórico" → visualizar histórico é parte da
      visualização do documento (documents.document.view), não
      uma operação independente
    - "pode editar metadados" → renomear cobre o caso de P0
    - "pode gerenciar tags" → tags não existem no P0
    - "pode aprovar" → aprovação não existe no P0

Não existe `documents.document.manage`.
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
        'description': (
            'Permite enviar novos arquivos para o workspace.'
        ),
    },
    {
        'code': 'documents.document.rename',
        'name': 'Renomear arquivo',
        'description': (
            'Permite alterar o nome de um arquivo já existente.'
        ),
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
        'description': (
            'Permite baixar o arquivo original do Clivo.'
        ),
    },
    {
        'code': 'documents.document.delete',
        'name': 'Excluir arquivo',
        'description': (
            'Permite excluir arquivos do workspace. Ação irreversível. '
            'O arquivo físico é removido permanentemente. O histórico '
            'é preservado com o documento marcado como excluído.'
        ),
    },
]