"""
Capabilities declaradas pelo módulo briefings.
"""

CAPABILITIES = [
    # ==================================================================
    # TEMPLATE
    # ==================================================================
    {
        'code': 'briefings.template.view',
        'name': 'Ver modelos de briefing',
        'description': 'Permite visualizar modelos de briefing do workspace.',
    },
    {
        'code': 'briefings.template.manage',
        'name': 'Gerenciar modelos de briefing',
        'description': (
            'Permite criar, editar, publicar e arquivar modelos de '
            'briefing, incluindo suas sessões, perguntas, ordem, '
            'formatos de resposta permitidos, categoria, capa e '
            'estado ativo/inativo.'
        ),
    },

    # ==================================================================
    # BRIEFING (execução)
    # ==================================================================
    {
        'code': 'briefings.briefing.view',
        'name': 'Ver briefings',
        'description': (
            'Permite visualizar briefings em execução e concluídos, '
            'incluindo respostas e histórico.'
        ),
    },
    {
        'code': 'briefings.briefing.start',
        'name': 'Iniciar briefing',
        'description': (
            'Permite iniciar a execução de um briefing para um cliente.'
        ),
    },
    {
        'code': 'briefings.briefing.review',
        'name': 'Revisar briefings',
        'description': (
            'Permite pausar, retomar, encerrar e reabrir briefings.'
        ),
    },
    {
        'code': 'briefings.briefing.delete',
        'name': 'Excluir briefing',
        'description': 'Permite excluir briefings. Ação irreversível.',
    },
    {
        'code': 'briefings.briefing.export',
        'name': 'Exportar briefing',
        'description': (
            'Permite gerar PDF do briefing e abrir a versão autenticada '
            'no navegador.'
        ),
    },
    {
        'code': 'briefings.briefing.send_to_client',
        'name': 'Enviar briefing para o cliente',
        'description': (
            'Permite enviar ou reenviar o briefing para o cliente '
            'por e-mail, a qualquer momento.'
        ),
    },

    # ==================================================================
    # NOTES (Journal privado)
    # ==================================================================
    {
        'code': 'briefings.note.view',
        'name': 'Ver anotações',
        'description': (
            'Permite visualizar as anotações privadas do escritório '
            'sobre um briefing.'
        ),
    },
    {
        'code': 'briefings.note.manage',
        'name': 'Gerenciar anotações',
        'description': (
            'Permite criar, editar e excluir anotações privadas do '
            'escritório sobre um briefing.'
        ),
    },
]