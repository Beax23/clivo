"""
Teste de fronteira arquitetural.

Verifica via AST (não grep textual) que:
    - integrations NÃO importa apps.console
    - core NÃO importa apps.*
    - integrations NÃO usa import dinâmico sem whitelist
    - console NÃO importa integrations
"""

import ast
from pathlib import Path

import pytest


# =========================================================================
# HELPERS
# =========================================================================

def _walk_python_files(root: Path):
    """Devolve todos os .py sob `root`, exceto testes e migrations."""
    for path in root.rglob('*.py'):
        rel = path.relative_to(root)
        parts = rel.parts
        if 'migrations' in parts:
            continue
        if 'tests' in parts:
            continue
        yield path


def _iter_imports(tree: ast.AST):
    """
    Devolve tuplas (module_name, is_from) para cada import no AST.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield (alias.name, False)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield (node.module, True)


def _has_dynamic_import(tree: ast.AST):
    """
    Detecta __import__() e importlib.import_module().
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == '__import__':
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == 'import_module':
                return True
    return False


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture(scope='module')
def repo_root():
    """
    Raiz do repositório. Ajuste se necessário.
    Assume que este arquivo está em apps/integrations/tests/.
    """
    return Path(__file__).resolve().parents[3]


# =========================================================================
# TESTES
# =========================================================================

def test_integrations_does_not_import_console(repo_root):
    root = repo_root / 'apps' / 'integrations'
    offenders = []
    for path in _walk_python_files(root):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for module, _is_from in _iter_imports(tree):
            if module == 'apps.console' or module.startswith('apps.console.'):
                offenders.append((path, module))
    assert not offenders, (
        f'Integrations importa apps.console (proibido): {offenders}'
    )


def test_core_does_not_import_apps(repo_root):
    root = repo_root / 'core'
    if not root.exists():
        pytest.skip('core/ ausente')
    offenders = []
    for path in _walk_python_files(root):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for module, _is_from in _iter_imports(tree):
            if module == 'apps' or module.startswith('apps.'):
                offenders.append((path, module))
    assert not offenders, (
        f'core importa apps (proibido): {offenders}'
    )


def test_console_does_not_import_integrations(repo_root):
    root = repo_root / 'apps' / 'console'
    offenders = []
    for path in _walk_python_files(root):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for module, _is_from in _iter_imports(tree):
            if module == 'apps.integrations' or module.startswith('apps.integrations.'):
                offenders.append((path, module))
    assert not offenders, (
        f'Console importa integrations (proibido): {offenders}'
    )


def test_integrations_does_not_use_dynamic_imports(repo_root):
    root = repo_root / 'apps' / 'integrations'
    offenders = []
    for path in _walk_python_files(root):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        if _has_dynamic_import(tree):
            offenders.append(path)
    assert not offenders, (
        f'Integrations usa import dinâmico (proibido): {offenders}'
    )


def test_walker_finds_files(repo_root):
    """Garante que o walker não está passando por vazio."""
    root = repo_root / 'apps' / 'integrations'
    files = list(_walk_python_files(root))
    assert len(files) >= 5, (
        f'Walker encontrou apenas {len(files)} arquivos. '
        'Verifique o path ou a estrutura.'
    )