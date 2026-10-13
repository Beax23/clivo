"""
Validação real de imagem para o módulo references.

Diferente da validação superficial (extensão + tamanho > 0), aqui
inspecionamos o CONTEÚDO do arquivo:

    - magic bytes (assinatura binária) para confirmar que é imagem
    - Pillow para confirmar que abre, é válida e tem dimensões
    - limite de tamanho configurável
    - limite de pixels (largura x altura) configurável

SOBRE PILLOW
------------
Pillow é OBRIGATÓRIO em produção. Sem Pillow, a validação cai para
apenas magic bytes — o que bloqueia arquivos maliciosos com extensão
falsa, mas NÃO valida dimensões nem detecta imagens corrompidas com
cabeçalho válido.

Para forçar a obrigatoriedade, defina em settings:

    REFERENCES_REQUIRE_PILLOW = True   # padrão em produção

Se `REFERENCES_REQUIRE_PILLOW` for True e Pillow não estiver
instalado, `validate_image_content` levanta erro claro. Isso evita
subir um deploy onde a validação é silenciosamente mais fraca.

Em testes/CI, você pode deixar `REFERENCES_REQUIRE_PILLOW = False`
para não exigir a lib. Em produção, sempre True.

Este módulo é importado tanto pelo ReferenceService.upload quanto
pelo replace_image, garantindo a mesma régua em todos os caminhos
de entrada.
"""

import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger('references')


# =========================================================================
# LIMITES (configuráveis via settings)
# =========================================================================

# Tamanho máximo por imagem. Default: 25 MB.
DEFAULT_MAX_IMAGE_SIZE_BYTES = 25 * 1024 * 1024

# Dimensão máxima em pixels (largura * altura). Default: 100 MP.
# Serve para evitar bombas de descompressão (imagem pequena no disco
# que explode em memória ao abrir).
DEFAULT_MAX_IMAGE_PIXELS = 100_000_000

# Pillow obrigatório? Default True — o comportamento seguro.
# Em CI sem Pillow, defina settings.REFERENCES_REQUIRE_PILLOW = False.
DEFAULT_REQUIRE_PILLOW = True


# =========================================================================
# MAGIC BYTES
# =========================================================================
# Assinaturas binárias mínimas. Não substituem Pillow — apenas garantem
# que o arquivo COMEÇA como uma imagem.
#
# Fonte: file signature table (Gary Kessler) — subconjunto relevante.

MAGIC_SIGNATURES = [
    (b'\xff\xd8\xff', 'jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'png'),
    (b'GIF87a', 'gif'),
    (b'GIF89a', 'gif'),
    (b'RIFF', 'webp_maybe'),
    (b'BM', 'bmp'),
    (b'II*\x00', 'tiff'),
    (b'MM\x00*', 'tiff'),
]


class ImageValidationError(Exception):
    """Levantada quando a imagem não passa na validação."""
    pass


# =========================================================================
# API PÚBLICA
# =========================================================================

def validate_image_content(uploaded_file) -> str:
    """
    Valida o conteúdo de uma imagem enviada.

    Retorna o "kind" detectado (ex: "jpeg", "png", "gif", "webp").
    Levanta ImageValidationError se o arquivo não for uma imagem válida.

    Não altera o ponteiro de leitura do arquivo no final — garante
    que ele fica no início para o storage conseguir salvar.
    """
    if uploaded_file is None:
        raise ImageValidationError('Nenhuma imagem foi enviada.')

    name = getattr(uploaded_file, 'name', None)
    if not name:
        raise ImageValidationError('A imagem enviada não possui nome.')

    size = getattr(uploaded_file, 'size', None)
    if size is None or size <= 0:
        raise ImageValidationError('A imagem enviada está vazia.')

    max_size = int(
        getattr(settings, 'REFERENCES_MAX_IMAGE_SIZE_BYTES',
                DEFAULT_MAX_IMAGE_SIZE_BYTES)
    )
    if max_size > 0 and size > max_size:
        raise ImageValidationError(
            f'A imagem excede o tamanho máximo permitido '
            f'({_humanize(max_size)}).'
        )

    # Lê os primeiros bytes para checar a assinatura
    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(32)
    except Exception as exc:
        raise ImageValidationError(
            'Não foi possível ler o conteúdo da imagem.'
        ) from exc
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    if not header or len(header) < 4:
        raise ImageValidationError('Arquivo muito pequeno para ser imagem.')

    kind = _detect_magic(header)
    if kind is None:
        raise ImageValidationError(
            'O arquivo enviado não é uma imagem válida.'
        )

    if kind == 'webp_maybe':
        if len(header) >= 12 and header[8:12] == b'WEBP':
            kind = 'webp'
        else:
            raise ImageValidationError(
                'O arquivo enviado não é uma imagem válida.'
            )

    declared_ext = _extension_of(name)
    if declared_ext and not _extension_matches(declared_ext, kind):
        logger.info(
            'Extensão declarada "%s" não bate com tipo detectado "%s" '
            'para arquivo "%s". Aceitando mesmo assim.',
            declared_ext, kind, name,
        )

    # -------------------------------------------------------------------
    # Validação profunda com Pillow.
    #
    # Se REQUIRE_PILLOW for True e a lib não estiver instalada, FALHA
    # com mensagem clara. Isso evita produção com validação degradada.
    # -------------------------------------------------------------------
    require_pillow = bool(
        getattr(settings, 'REFERENCES_REQUIRE_PILLOW',
                DEFAULT_REQUIRE_PILLOW)
    )
    pillow_available = _pillow_available()

    if require_pillow and not pillow_available:
        logger.error(
            'REFERENCES_REQUIRE_PILLOW=True mas Pillow não está '
            'instalado. A validação profunda de imagens está '
            'desabilitada. Instale Pillow: pip install Pillow'
        )
        raise ImageValidationError(
            'Validação de imagem indisponível no servidor. '
            'Contate o suporte.'
        )

    if pillow_available:
        pillow_error = _validate_with_pillow(uploaded_file)
        if pillow_error is not None:
            raise ImageValidationError(pillow_error)

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    return kind


def pillow_is_available() -> bool:
    """Diagnóstico público — útil para health checks."""
    return _pillow_available()


# =========================================================================
# HELPERS INTERNOS
# =========================================================================

def _pillow_available() -> bool:
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_magic(header: bytes) -> Optional[str]:
    for sig, kind in MAGIC_SIGNATURES:
        if header.startswith(sig):
            return kind
    return None


def _extension_of(filename: str) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


def _extension_matches(ext: str, kind: str) -> bool:
    if ext in ('jpg', 'jpeg', 'jfif') and kind == 'jpeg':
        return True
    if ext == 'png' and kind == 'png':
        return True
    if ext == 'gif' and kind == 'gif':
        return True
    if ext == 'webp' and kind == 'webp':
        return True
    if ext == 'bmp' and kind == 'bmp':
        return True
    if ext in ('tif', 'tiff') and kind == 'tiff':
        return True
    return False


def _validate_with_pillow(uploaded_file) -> Optional[str]:
    """
    Tenta abrir com Pillow. Retorna mensagem de erro (str) ou None.
    Pressupõe que Pillow está instalado (chamador verifica antes).
    """
    from PIL import Image

    max_pixels = int(
        getattr(settings, 'REFERENCES_MAX_IMAGE_PIXELS',
                DEFAULT_MAX_IMAGE_PIXELS)
    )

    try:
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        img.verify()
    except Exception as exc:
        logger.warning('Pillow recusou a imagem: %s', exc)
        return 'A imagem enviada parece estar corrompida ou inválida.'

    try:
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        width, height = img.size
        if width <= 0 or height <= 0:
            return 'A imagem tem dimensões inválidas.'
        if max_pixels > 0 and (width * height) > max_pixels:
            return (
                f'A imagem tem dimensões muito grandes '
                f'({width}x{height}). O limite é '
                f'{_humanize_int(max_pixels)} pixels totais.'
            )
    except Exception as exc:
        logger.warning('Pillow falhou ao checar dimensões: %s', exc)
        return 'Não foi possível ler as dimensões da imagem.'
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    return None


def _humanize(num_bytes: int) -> str:
    if not num_bytes:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB']
    size = float(num_bytes)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f'{size:.1f} {units[i]}'


def _humanize_int(n: int) -> str:
    """Formata inteiro com separador de milhar em pt-BR (ponto)."""
    return f'{n:,}'.replace(',', '.')