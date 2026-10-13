"""
Serializers de Document.

REGRA DE URL
-----------
Toda URL de arquivo devolvida ao cliente passa por `_absolute_url`.
Isso garante:
    - Se o storage for S3/B2/R2 (URL assinada absoluta) → devolve como está.
    - Se o storage for local (`/media/...`) → constrói URL absoluta com
      `request`, para o frontend conseguir exibir de qualquer rota.
"""

from rest_framework import serializers

from apps.documents.models import Document


# =========================================================================
# HELPERS
# =========================================================================

def _absolute_url(request, url):
    """
    Retorna URL absoluta quando possível.

    B2/R2 com `AWS_QUERYSTRING_AUTH=True` já devolvem URLs assinadas
    absolutas. Local devolve `/media/...` — precisa do request para
    virar absoluta.
    """
    if not url:
        return ''
    if url.startswith(('http://', 'https://')):
        return url
    if request is not None:
        try:
            return request.build_absolute_uri(url)
        except Exception:
            return url
    return url


# =========================================================================
# LEITURA
# =========================================================================

class DocumentListSerializer(serializers.ModelSerializer):
    """
    Serializer leve para listagem.
    """

    full_name = serializers.CharField(read_only=True)
    size_display = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    source_display = serializers.CharField(
        source='get_source_display', read_only=True
    )

    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True
    )

    folder_name = serializers.CharField(
        source='folder.name', read_only=True, allow_null=True
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
            'preview_url',
            'extension',
            'mime_type',
            'size',
            'size_display',
            'client', 'client_name',
            'project_id',
            'folder', 'folder_name',
            'source', 'source_display',
            'source_url',
            'visible_to_client',
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
            url = obj.file.url
        except Exception:
            return ''
        request = self.context.get('request')
        return _absolute_url(request, url)

    def get_preview_url(self, obj):
        """
        No módulo documents, `preview_url` é a mesma URL do arquivo.

        Existe para padronizar com o módulo `briefings` (que usa
        o mesmo nome de campo em opções de pergunta). Se um dia
        houver thumbnail separada, ela vive aqui.
        """
        return self.get_file_url(obj)


class DocumentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer completo do documento.
    """

    full_name = serializers.CharField(read_only=True)
    size_display = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    workspace_id = serializers.UUIDField(source='workspace.id', read_only=True)

    source_display = serializers.CharField(
        source='get_source_display', read_only=True
    )

    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True
    )

    folder_name = serializers.CharField(
        source='folder.name', read_only=True, allow_null=True
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
            'preview_url',
            'extension',
            'mime_type',
            'size',
            'size_display',
            'client', 'client_name',
            'project_id',
            'folder', 'folder_name',
            'source', 'source_display',
            'source_url',
            'visible_to_client',
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
            'preview_url',
            'extension',
            'mime_type',
            'size',
            'size_display',
            'client',
            'project_id',
            'folder', 'folder_name',
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
            url = obj.file.url
        except Exception:
            return ''
        request = self.context.get('request')
        return _absolute_url(request, url)

    def get_preview_url(self, obj):
        return self.get_file_url(obj)


# =========================================================================
# ESCRITA
# =========================================================================

class DocumentUploadSerializer(serializers.Serializer):
    """
    Criação de Document via upload.
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
    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )
    source = serializers.ChoiceField(
        choices=[c[0] for c in Document.SOURCE_CHOICES],
        required=False,
        default=Document.SOURCE_UPLOAD,
    )
    source_url = serializers.URLField(
        required=False, allow_blank=True, max_length=1000,
    )
    visible_to_client = serializers.BooleanField(
        required=False, default=False,
    )
    # Aceita `kind` como no-op (compatibilidade com o fluxo de opções
    # de pergunta, que envia `kind=image`). Não é persistido.
    kind = serializers.CharField(
        required=False, allow_blank=True, max_length=32,
    )

    def validate_name(self, value):
        if value is None:
            return ''
        return value.strip()

    def validate_visible_to_client(self, value):
        return bool(value)


class DocumentUpdateSerializer(serializers.Serializer):
    """
    Atualização parcial do Document. No P0, só `name`.
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


class MoveDocumentSerializer(serializers.Serializer):
    """
    Body para mover um documento para uma pasta.
    """

    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )


class DocumentVisibilitySerializer(serializers.Serializer):
    """
    Body para alterar visibilidade do documento.
    """

    visible_to_client = serializers.BooleanField(required=True)


# =========================================================================
# GOOGLE DRIVE
# =========================================================================

class GDriveImportSerializer(serializers.Serializer):
    """
    Body para importar arquivos do Google Drive.
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
    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )