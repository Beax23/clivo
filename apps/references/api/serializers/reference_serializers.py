"""
Serializers de Reference.
"""

from rest_framework import serializers

from apps.references.models import Reference, ReferenceCategory


# =========================================================================
# LEITURA
# =========================================================================

class _CategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferenceCategory
        fields = ['id', 'name', 'slug', 'color']
        read_only_fields = fields


class ReferenceListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    categories = _CategoryMiniSerializer(many=True, read_only=True)

    file_type_display = serializers.CharField(read_only=True)
    image_size_display = serializers.CharField(read_only=True)

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

    class Meta:
        model = Reference
        fields = [
            'id',
            'title',
            'image_url',
            'thumbnail_url',
            'file_url',
            'description',
            'categories',
            'client', 'client_name',
            'project_id',
            'folder', 'folder_name',
            'source', 'source_display',
            'source_url',
            'visible_to_client',
            'extension', 'file_type_display',
            'size', 'image_size_display',
            'created_by', 'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_image_url(self, obj):
        if not obj.image:
            return ''
        try:
            return obj.image.url
        except Exception:
            return ''

    def get_thumbnail_url(self, obj):
        return self.get_image_url(obj)

    def get_file_url(self, obj):
        return self.get_image_url(obj)


class ReferenceDetailSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    categories = _CategoryMiniSerializer(many=True, read_only=True)

    file_type_display = serializers.CharField(read_only=True)
    image_size_display = serializers.CharField(read_only=True)

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
        model = Reference
        fields = [
            'id',
            'workspace_id',
            'title',
            'image_url',
            'thumbnail_url',
            'file_url',
            'images',
            'description',
            'categories',
            'client', 'client_name',
            'project_id',
            'folder', 'folder_name',
            'source', 'source_display',
            'source_url',
            'visible_to_client',
            'metadata',
            'extension', 'file_type_display',
            'size', 'image_size_display',
            'created_by', 'created_by_name', 'created_by_email',
            'updated_by', 'updated_by_name', 'updated_by_email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'workspace_id',
            'image_url', 'thumbnail_url', 'file_url', 'images',
            'categories',
            'client_name', 'folder_name', 'source_display',
            'metadata', 'extension', 'file_type_display',
            'size', 'image_size_display',
            'created_by', 'created_by_name', 'created_by_email',
            'updated_by', 'updated_by_name', 'updated_by_email',
            'created_at', 'updated_at',
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return ''
        try:
            return obj.image.url
        except Exception:
            return ''

    def get_thumbnail_url(self, obj):
        return self.get_image_url(obj)

    def get_file_url(self, obj):
        return self.get_image_url(obj)

    def get_images(self, obj):
        url = self.get_image_url(obj)
        if not url:
            return []
        return [{'url': url, 'name': obj.title or ''}]


# =========================================================================
# ESCRITA
# =========================================================================

class ReferenceUploadSerializer(serializers.Serializer):
    image = serializers.FileField(required=True)
    title = serializers.CharField(
        required=True, allow_blank=False, max_length=255,
    )
    description = serializers.CharField(required=False, allow_blank=True)
    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False, allow_empty=True, default=list,
    )
    client_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )
    project_id = serializers.UUIDField(required=False, allow_null=True)
    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )
    source = serializers.ChoiceField(
        choices=[c[0] for c in Reference.SOURCE_CHOICES],
        required=False,
        default=Reference.SOURCE_UPLOAD,
    )
    source_url = serializers.URLField(
        required=False, allow_blank=True, max_length=1000,
    )
    visible_to_client = serializers.BooleanField(required=False, default=False)

    def validate_title(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O título é obrigatório.')
        return value

    def validate_description(self, value):
        if value is None:
            return ''
        return value.strip()

    def validate_visible_to_client(self, value):
        return bool(value)


class ReferenceUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(
        required=False, allow_blank=False, max_length=255,
    )
    description = serializers.CharField(required=False, allow_blank=True)
    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False, allow_empty=True,
    )

    def validate_title(self, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise serializers.ValidationError('O título não pode ser vazio.')
        return value

    def validate_description(self, value):
        if value is None:
            return value
        return value.strip()


class ReferenceSetCategoriesSerializer(serializers.Serializer):
    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True, allow_empty=True,
    )


class ReferenceAssociateClientSerializer(serializers.Serializer):
    client_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )


class ReferenceAssociateProjectSerializer(serializers.Serializer):
    project_id = serializers.UUIDField(required=False, allow_null=True)


class MoveReferenceSerializer(serializers.Serializer):
    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )


class ReferenceVisibilitySerializer(serializers.Serializer):
    visible_to_client = serializers.BooleanField(required=True)


class GDriveImportSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )


class PinterestImportSerializer(serializers.Serializer):
    pins = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True,
    )