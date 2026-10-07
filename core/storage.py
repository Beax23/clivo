"""
Storage do Cloudinary com suporte a arquivos binários (raw).

============================================================================
PROBLEMA
============================================================================

Por padrão, `MediaCloudinaryStorage` envia TUDO como `resource_type='image'`.
O Cloudinary aceita o upload, mas não guarda o binário original:
transforma em imagem derivada (JPEG) e descarta o conteúdo real.

Resultado:

    - .docx é salvo como .jpg (assinatura ff d8 ff ...)
    - .xlsx, .pptx, .zip idem
    - download devolve imagem corrompida
    - preview nunca renderiza

============================================================================
SOLUÇÃO
============================================================================

Esta subclasse decide o `resource_type` pela extensão do arquivo:

    - Documentos (.docx, .xlsx, .pptx, .odt, .ods, .odp)
    - Compactados (.zip, .rar, .7z, .tar, .gz)
    - Texto (.txt, .md, .csv, .rtf)
    - CAD (.dwg, .dxf, .skp)
        → resource_type='raw'  (binário preservado)

    - Imagens (.jpg, .png, .gif, .webp, .svg, .bmp, .tiff, .ico)
    - PDFs
        → resource_type='image'  (Cloudinary otimiza)

O Cloudinary armazena `raw` sem transformar o conteúdo. O arquivo
é servido exatamente como foi enviado.

============================================================================
NOTA SOBRE O `cloudinary_storage`
============================================================================

A lib `cloudinary_storage` lê `self.RESOURCE_TYPE` no momento do upload.
Sobrescrevemos temporariamente essa propriedade antes de chamar `_save`.

Se a versão instalada ignorar isso, há um fallback que chama
`cloudinary.uploader.upload()` diretamente. Veja `_save_direct`.
"""

import logging

from cloudinary_storage.storage import MediaCloudinaryStorage

logger = logging.getLogger('documents')


# Extensões que precisam ir como `raw` no Cloudinary.
RAW_EXTENSIONS = {
    # Documentos
    'doc', 'docx', 'odt', 'rtf', 'txt', 'md',
    # Planilhas
    'xls', 'xlsx', 'ods', 'csv',
    # Apresentações
    'ppt', 'pptx', 'odp',
    # Compactados
    'zip', 'rar', '7z', 'tar', 'gz',
    # CAD
    'dwg', 'dxf', 'skp',
}


def _ext_of(name: str) -> str:
    if not name or '.' not in name:
        return ''
    return name.rsplit('.', 1)[-1].lower()


class SmartMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Storage que decide `resource_type` pela extensão do arquivo.
    """

    def _resolve_resource_type(self, name: str) -> str:
        ext = _ext_of(name)
        if ext in RAW_EXTENSIONS:
            return 'raw'
        return 'image'

    def _save(self, name, content):
        """
        Intercepta o `_save` do Cloudinary para trocar `resource_type`
        quando a extensão exigir `raw`.

        Funciona sobrescrevendo temporariamente `self.RESOURCE_TYPE`
        (o atributo que a lib `cloudinary_storage` lê).
        """
        resource_type = self._resolve_resource_type(name)

        logger.info(
            'Cloudinary upload: name=%s resource_type=%s',
            name, resource_type,
        )

        # Guarda o valor original para restaurar após o save.
        original = getattr(self, 'RESOURCE_TYPE', 'image')

        try:
            self.RESOURCE_TYPE = resource_type
            return super()._save(name, content)
        finally:
            self.RESOURCE_TYPE = original