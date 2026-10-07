from apps.documents.api.serializers.document_serializers import (
    DocumentListSerializer,
    DocumentDetailSerializer,
    DocumentUploadSerializer,
    DocumentUpdateSerializer,
    DocumentReplaceSerializer,
    DocumentAssociateClientSerializer,
    DocumentAssociateProjectSerializer,
    GDriveImportSerializer,
)

from apps.documents.api.serializers.history_serializers import (
    DocumentHistorySerializer,
)

__all__ = [
    'DocumentListSerializer',
    'DocumentDetailSerializer',
    'DocumentUploadSerializer',
    'DocumentUpdateSerializer',
    'DocumentReplaceSerializer',
    'DocumentAssociateClientSerializer',
    'DocumentAssociateProjectSerializer',
    'GDriveImportSerializer',
    'DocumentHistorySerializer',
]