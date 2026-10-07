"""
Serializers de Document.

SEPARAÇÃO DE RESPONSABILIDADES
------------------------------
    DocumentListSerializer           → listagem leve
    DocumentDetailSerializer         → detalhe completo
    DocumentUploadSerializer         → criação (multipart)
    DocumentUpdateSerializer         → renomear (PATCH simples)
    DocumentReplaceSerializer        → substituir arquivo físico
    DocumentAssociateClientSerializer  → associar/desassociar cliente
    DocumentAssociateProjectSerializer → associar/desassociar projeto

REGRA DE SEGURANÇA
------------------
`workspace`, `created_by`, `updated_by`, `created_at`, `updated_at`,
`extension`, `mime_type` e `size` são sempre read-only.

Nunca vêm do body. São extraídos do upload pelo service.
"""

from rest_framework import serializers

from apps.documents.models import Document


# =========================================================================
# LEITURA
# =========================================================================

class DocumentListSerializer(serializers.ModelSerializer):
    """
    Serializer leve para listagem.

    Expõe apenas o necessário para a lista de arquivos:
    nome, extensão, tamanho, contexto, origem e rastreabilidade.
    """

    full_name = serializers.CharField(read_only=True)
    size_display = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()

    source_display = serializers.CharField(
        source='get_source_display', read_only=True
    )

    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True
    )

    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, allow_null=True
    )
    updated_by_name = serializers.CharField(
        source='updated_by.full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = Document
        fields = [
            'id',
            'name',
            'full_name',
            'file_url',
            'extension',
            'mime_type',
            'size',
            'size_display',
            'client', 'client_name',
            'project_id',
            'source', 'source_display',
            'source_url',
            'created_by', 'created_by_name',
            'updated_by', 'updated_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file:
            return ''
        try:
            return obj.file.url
        except Exception:
            return ''


class DocumentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer completo do documento.
    """

    full_name = serializers.CharField(read_only=True)
    size_display = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()

    workspace_id = serializers.UUIDField(source='workspace.id', read_only=True)

    source_display = serializers.CharField(
        source='get_source_display', read_only=True
    )

    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True
    )

    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, allow_null=True
    )
    created_by_email = serializers.EmailField(
        source='created_by.email', read_only=True, allow_null=True
    )
    updated_by_name = serializers.CharField(
        source='updated_by.full_name', read_only=True, allow_null=True
    )
    updated_by_email = serializers.EmailField(
        source='updated_by.email', read_only=True, allow_null=True
    )

    class Meta:
        model = Document
        fields = [
            'id',
            'workspace_id',
            'name',
            'full_name',
            'file_url',
            'extension',
            'mime_type',
            'size',
            'size_display',
            'client', 'client_name',
            'project_id',
            'source', 'source_display',
            'source_url',
            'created_by', 'created_by_name', 'created_by_email',
            'updated_by', 'updated_by_name', 'updated_by_email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'workspace_id',
            'name',
            'full_name',
            'file_url',
            'extension',
            'mime_type',
            'size',
            'size_display',
            'client',
            'project_id',
            'source', 'source_display',
            'source_url',
            'created_by', 'created_by_name', 'created_by_email',
            'updated_by', 'updated_by_name', 'updated_by_email',
            'created_at',
            'updated_at',
        ]

    def get_file_url(self, obj):
        if not obj.file:
            return ''
        try:
            return obj.file.url
        except Exception:
            return ''


# =========================================================================
# ESCRITA
# =========================================================================

class DocumentUploadSerializer(serializers.Serializer):
    """
    Criação de Document via upload.

    Multipart form-data:
        file        → arquivo (obrigatório)
        name        → opcional (se vazio, extraído do filename)
        client_id   → opcional
        project_id  → opcional
        source      → opcional (padrão 'upload')

    `workspace` e `created_by` vêm do contexto autenticado.
    """

    file = serializers.FileField(required=True)
    name = serializers.CharField(
        required=False, allow_blank=True, max_length=255,
    )
    client_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )
    project_id = serializers.UUIDField(
        required=False, allow_null=True,
    )
    source = serializers.ChoiceField(
        choices=[c[0] for c in Document.SOURCE_CHOICES],
        required=False,
        default=Document.SOURCE_UPLOAD,
    )
    source_url = serializers.URLField(
        required=False, allow_blank=True, max_length=1000,
    )

    def validate_name(self, value):
        if value is None:
            return ''
        return value.strip()


class DocumentUpdateSerializer(serializers.Serializer):
    """
    Atualização parcial do Document.

    No P0, o único campo editável via PATCH é `name`.
    """

    name = serializers.CharField(
        required=False, max_length=255,
    )

    def validate_name(self, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class DocumentReplaceSerializer(serializers.Serializer):
    """
    Substituição do arquivo físico.
    """

    file = serializers.FileField(required=True)


class DocumentAssociateClientSerializer(serializers.Serializer):
    """
    Body para associar ou desassociar cliente.
    """

    client_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )


class DocumentAssociateProjectSerializer(serializers.Serializer):
    """
    Body para associar ou desassociar projeto.
    """

    project_id = serializers.UUIDField(
        required=False, allow_null=True,
    )


# =========================================================================
# GOOGLE DRIVE
# =========================================================================

class GDriveImportSerializer(serializers.Serializer):
    """
    Body para importar arquivos do Google Drive.

    Recebe uma lista de arquivos com id + metadados básicos.
    O backend baixa cada um e cria um Document.
    """

    files = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )

    client_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )
    project_id = serializers.UUIDField(
        required=False, allow_null=True,
    )