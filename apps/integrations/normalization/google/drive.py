"""
GoogleDriveNormalizer — converte payloads do Google Drive em
ExternalFile.

Puro: sem I/O. Testável sem mock de rede.
"""

from datetime import datetime

from apps.integrations.normalization.contracts import ExternalFile


class GoogleDriveNormalizer:

    @staticmethod
    def to_external_file(raw: dict) -> ExternalFile:
        """
        Converte um dict de arquivo do Google Drive em ExternalFile.
        """
        return ExternalFile(
            external_id=str(raw.get('id', '')),
            name=raw.get('name', ''),
            mime_type=raw.get('mimeType'),
            size_bytes=_parse_int(raw.get('size')),
            parent_ids=tuple(raw.get('parents') or ()),
            path=None,  # Drive não expõe path direto.
            url=raw.get('webViewLink'),
            created_at=_parse_datetime(raw.get('createdTime')),
            modified_at=_parse_datetime(raw.get('modifiedTime')),
            provider_metadata={
                'owners': raw.get('owners', []),
                'shared': raw.get('shared', False),
                'trashed': raw.get('trashed', False),
            },
        )


def _parse_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None