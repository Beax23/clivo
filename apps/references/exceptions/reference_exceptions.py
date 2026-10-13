"""
Exceções do módulo references.

Padrão:

    ReferenceError (base)
        ├── ReferenceNotFoundError
        ├── ReferenceInvalidImageError
        ├── ReferenceClientNotFoundError
        ├── ReferenceProjectNotFoundError
        ├── ReferenceFolderError
        │     ├── ReferenceFolderNotFoundError
        │     └── ReferenceFolderNameConflictError
        ├── ReferenceCategoryError
        │     ├── ReferenceCategoryNotFoundError
        │     └── ReferenceCategoryNameConflictError
        └── ReferenceStorageError
"""


class ReferenceError(Exception):
    """Exceção base do módulo references."""
    pass


# =====================================================================
# REFERENCE
# =====================================================================

class ReferenceNotFoundError(ReferenceError):
    """Referência não encontrada no workspace."""
    pass


class ReferenceInvalidImageError(ReferenceError):
    """
    A imagem enviada é inválida.

    Isso cobre:
        - arquivo ausente
        - nome ausente
        - arquivo vazio
        - extensão fora da lista permitida
        - conteúdo que não é imagem (magic bytes)
        - imagem corrompida (Pillow)
        - imagem acima do limite de tamanho
        - imagem acima do limite de pixels
    """
    pass


# =====================================================================
# CONTEXTO
# =====================================================================

class ReferenceClientNotFoundError(ReferenceError):
    """Cliente referenciado não existe no workspace da referência."""
    pass


class ReferenceProjectNotFoundError(ReferenceError):
    """
    Projeto referenciado não existe.

    Como `projects` ainda não existe no P0, esta exceção é reservada
    para quando o app `projects` nascer e o UUID passado não corresponder
    a nenhum projeto.
    """
    pass


# =====================================================================
# PASTA
# =====================================================================

class ReferenceFolderError(ReferenceError):
    """Erro genérico de pasta."""
    pass


class ReferenceFolderNotFoundError(ReferenceFolderError):
    """Pasta não encontrada no workspace."""
    pass


class ReferenceFolderNameConflictError(ReferenceFolderError):
    """Já existe uma pasta com este nome no workspace."""
    pass


# =====================================================================
# CATEGORIA
# =====================================================================

class ReferenceCategoryError(ReferenceError):
    """Erro genérico de categoria."""
    pass


class ReferenceCategoryNotFoundError(ReferenceCategoryError):
    """Categoria não encontrada no workspace."""
    pass


class ReferenceCategoryNameConflictError(ReferenceCategoryError):
    """Já existe uma categoria com este nome no workspace."""
    pass


# =====================================================================
# STORAGE
# =====================================================================

class ReferenceStorageError(ReferenceError):
    """
    Falha ao interagir com o storage (gravar, remover ou recuperar
    a imagem física).
    """
    pass