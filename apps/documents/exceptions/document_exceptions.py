"""
Exceções do módulo documents.

Padrão:

    DocumentError (base)
        ├── DocumentNotFoundError
        ├── DocumentFileMissingError
        ├── DocumentInvalidUploadError
        ├── DocumentClientNotFoundError
        ├── DocumentProjectNotFoundError
        ├── DocumentFolderError
        │     ├── DocumentFolderNotFoundError
        │     └── DocumentFolderNameConflictError
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
    """Projeto referenciado não existe."""
    pass


# =====================================================================
# PASTA
# =====================================================================

class DocumentFolderError(DocumentError):
    """Erro genérico de pasta."""
    pass


class DocumentFolderNotFoundError(DocumentFolderError):
    """Pasta não encontrada no workspace."""
    pass


class DocumentFolderNameConflictError(DocumentFolderError):
    """Já existe uma pasta com este nome no workspace."""
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