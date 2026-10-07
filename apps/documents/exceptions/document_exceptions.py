"""
Exceções do módulo documents.

Padrão:

    DocumentError (base)
        ├── DocumentNotFoundError
        ├── DocumentFileMissingError
        ├── DocumentInvalidUploadError
        ├── DocumentClientNotFoundError
        ├── DocumentProjectNotFoundError
        └── DocumentStorageError
"""


class DocumentError(Exception):
    """Exceção base do módulo documents."""
    pass


# =====================================================================
# DOCUMENT
# =====================================================================

class DocumentNotFoundError(DocumentError):
    """Documento não encontrado no workspace."""
    pass


class DocumentFileMissingError(DocumentError):
    """
    O registro Document existe, mas o arquivo físico está ausente
    no storage (órfão de storage).
    """
    pass


class DocumentInvalidUploadError(DocumentError):
    """
    O upload não possui arquivo, ou o arquivo é inválido
    (sem nome, sem tamanho, ou sem conteúdo legível).
    """
    pass


# =====================================================================
# CONTEXTO
# =====================================================================

class DocumentClientNotFoundError(DocumentError):
    """Cliente referenciado não existe no workspace do documento."""
    pass


class DocumentProjectNotFoundError(DocumentError):
    """
    Projeto referenciado não existe.

    Como `projects` ainda não existe no P0, esta exceção é reservada
    para quando o app `projects` nascer e o UUID passado não corresponder
    a nenhum projeto.
    """
    pass


# =====================================================================
# STORAGE
# =====================================================================

class DocumentStorageError(DocumentError):
    """
    Falha ao interagir com o storage (gravar, remover ou recuperar
    o arquivo físico).
    """
    pass