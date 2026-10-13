"""
Rotina de detecção e limpeza de imagens órfãs no storage.

============================================================================
CONTEXTO
============================================================================

`replace_image` e `delete` são "best-effort" em relação ao storage:

    - Se a remoção da imagem antiga falha, sobra arquivo órfão.
    - Se a atualização do banco falha após salvar no storage, sobra
      arquivo órfão.
    - Se o processo morre entre as duas etapas, sobra arquivo órfão.

Este módulo fornece duas operações:

    find_orphan_images(workspace=None) → list[str] (nomes no storage)
    delete_orphan_images(names)        → dict (relatório)

IMPORTANTE
----------
- `find_orphan_images` NÃO apaga nada. Só compara o storage com o
  banco. Rode em um management command (cron / manual).
- `delete_orphan_images` apaga os nomes passados. Chamado por quem
  já decidiu que aquilo é lixo.
- A varredura do storage é feita sob o prefixo `references/`. Por
  padrão, TODOS os workspaces compartilham esse prefixo — então a
  checagem de "vivo" é feita contra **todos** os workspaces, não
  só o passado como filtro. O parâmetro `workspace` restringe
  apenas o relatório, não a fonte de verdade.

  Ou seja: a limpeza de A NUNCA apaga arquivo referenciado por B.

- Não mexe em arquivos de outros módulos (documents, etc.).
"""

import logging
from typing import Iterable, List

from apps.references.models import Reference

logger = logging.getLogger('references')


# =========================================================================
# DETECÇÃO
# =========================================================================

def find_orphan_images(workspace=None) -> List[str]:
    """
    Retorna a lista de nomes de arquivo que existem no storage sob
    `references/` mas NÃO estão referenciados por NENHUMA
    `Reference.image` de NENHUM workspace.

    O parâmetro `workspace`, quando passado, filtra **apenas o
    retorno do log** — a checagem de "vivo" é sempre feita contra
    todos os workspaces, para garantir que nenhum arquivo válido de
    outro workspace seja apagado.

    ATENÇÃO: é operação O(n) no storage. Rode com moderação.
    """
    from django.core.files.storage import default_storage

    # Nomes vivos: TODOS os workspaces, sempre. Sem filtro.
    # Se filtrássemos por workspace, apagaríamos arquivos legítimos
    # de outros workspaces que compartilham o prefixo `references/`.
    live = set(
        Reference.objects
        .exclude(image='')
        .values_list('image', flat=True)
    )

    # Lista arquivos do storage sob "references/"
    try:
        _dirs, files = default_storage.listdir('references/')
    except FileNotFoundError:
        # Pasta ainda não existe — nada a varrer.
        return []

    orphans: List[str] = []
    for fname in files:
        full_name = f'references/{fname}'
        if full_name not in live:
            orphans.append(full_name)

    return orphans


# =========================================================================
# LIMPEZA
# =========================================================================

def delete_orphan_images(names: Iterable[str]) -> dict:
    """
    Apaga uma lista de nomes do storage. Best-effort por item.

    Retorna:

        {
            'requested': 12,
            'deleted': 10,
            'failed': 2,
            'errors': [{'name': '...', 'error': '...'}, ...],
        }
    """
    from django.core.files.storage import default_storage

    names = list(names or [])
    deleted = 0
    failed = 0
    errors = []

    for name in names:
        try:
            default_storage.delete(name)
            deleted += 1
        except Exception as exc:
            failed += 1
            errors.append({'name': name, 'error': str(exc)})
            logger.exception(
                'Falha ao remover órfão: name=%s', name,
            )

    logger.info(
        'Limpeza de órfãos: requested=%d deleted=%d failed=%d',
        len(names), deleted, failed,
    )

    return {
        'requested': len(names),
        'deleted': deleted,
        'failed': failed,
        'errors': errors,
    }


# =========================================================================
# MANAGEMENT COMMAND HELPER
# =========================================================================

def cleanup_workspace(workspace, dry_run: bool = True) -> dict:
    """
    Combina detecção + limpeza.

    Se `dry_run=True` (padrão), só reporta os órfãos, sem apagar.

    O parâmetro `workspace` hoje é apenas informativo (aparece no
    log). A detecção é global porque a checagem de vivos também é.
    """
    orphans = find_orphan_images(workspace=workspace)

    if dry_run or not orphans:
        return {
            'dry_run': True,
            'orphans_found': len(orphans),
            'orphans': orphans,
            'deleted': 0,
            'failed': 0,
        }

    report = delete_orphan_images(orphans)
    report['dry_run'] = False
    report['orphans_found'] = len(orphans)
    return report