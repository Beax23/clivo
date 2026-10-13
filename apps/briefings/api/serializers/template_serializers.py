"""
Serializers de BriefingTemplate, BriefingSection, BriefingQuestion
e BriefingTemplateEvent.

REGRA DE URL
-----------
Toda URL de mídia retornada por serializers passa por `_absolute_url`,
que:
    - Se já for absoluta (S3/B2 assinada), devolve como está.
    - Se for relativa (storage local), constrói absoluta com `request`.
"""

from rest_framework import serializers

from apps.briefings.models import (
    BriefingTemplate,
    BriefingSection,
    BriefingQuestion,
    BriefingTemplateEvent,
)


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
# QUESTION
# =========================================================================

class BriefingQuestionSerializer(serializers.ModelSerializer):
    reference_document_ids = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = BriefingQuestion
        fields = [
            'id',
            'text',
            'instructions',
            'question_type',
            'allowed_response_formats',
            'options',
            'position',
            'is_required',
            'reference_document_ids',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_reference_document_ids(self, obj):
        return [str(d.id) for d in obj.reference_documents.all()]

    def get_options(self, obj):
        """
        Expande `options` resolvendo cada `image_document_id` para
        uma URL absoluta e assinada do documento correspondente.

        Sem isso, o frontend recebe apenas o ID e não consegue exibir
        o preview da imagem da opção.
        """
        raw_options = obj.options or []
        if not raw_options:
            return []

        # Coleta os IDs de documentos referenciados
        doc_ids = [
            str(opt.get('image_document_id'))
            for opt in raw_options
            if opt.get('image_document_id')
        ]

        # Carrega os Documents em uma query só
        docs_by_id = {}
        if doc_ids:
            from apps.documents.models import Document
            docs = Document.objects.filter(id__in=doc_ids)
            docs_by_id = {str(d.id): d for d in docs}

        request = self.context.get('request')
        result = []
        for opt in raw_options:
            entry = {
                'text': opt.get('text', ''),
                'image_document_id': opt.get('image_document_id'),
                'image_url': None,
            }
            doc_id = opt.get('image_document_id')
            if doc_id:
                doc = docs_by_id.get(str(doc_id))
                if doc and doc.file:
                    try:
                        entry['image_url'] = _absolute_url(
                            request, doc.file.url,
                        )
                    except Exception:
                        entry['image_url'] = None
            result.append(entry)
        return result


class BriefingQuestionCreateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000, allow_blank=False)
    instructions = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )
    question_type = serializers.ChoiceField(
        choices=[c[0] for c in BriefingQuestion.QUESTION_TYPE_CHOICES],
        required=False,
        default=BriefingQuestion.QUESTION_TYPE_TEXT,
    )
    allowed_response_formats = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            BriefingQuestion.RESPONSE_FORMAT_TEXT,
            BriefingQuestion.RESPONSE_FORMAT_AUDIO,
            BriefingQuestion.RESPONSE_FORMAT_IMAGE,
        ]),
        required=False,
        allow_empty=False,
    )
    options = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )
    is_required = serializers.BooleanField(required=False, default=True)
    reference_document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        default=list,
    )

    def validate_text(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O enunciado é obrigatório.')
        return value

    def validate_options(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Deve ser uma lista.')
        cleaned = []
        for item in value:
            if not isinstance(item, dict):
                continue
            text = (item.get('text') or '').strip()
            if not text:
                continue
            image_id = item.get('image_document_id')
            # Normaliza None / '' para None
            if not image_id:
                image_id = None
            cleaned.append({
                'text': text,
                'image_document_id': image_id,
            })
        return cleaned


class BriefingQuestionUpdateSerializer(serializers.Serializer):
    text = serializers.CharField(
        required=False, allow_blank=False, max_length=2000,
    )
    instructions = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )
    question_type = serializers.ChoiceField(
        choices=[c[0] for c in BriefingQuestion.QUESTION_TYPE_CHOICES],
        required=False,
    )
    allowed_response_formats = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            BriefingQuestion.RESPONSE_FORMAT_TEXT,
            BriefingQuestion.RESPONSE_FORMAT_AUDIO,
            BriefingQuestion.RESPONSE_FORMAT_IMAGE,
        ]),
        required=False,
        allow_empty=False,
    )
    options = serializers.ListField(
        child=serializers.DictField(),
        required=False,
    )
    is_required = serializers.BooleanField(required=False)
    reference_document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )

    def validate_text(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O enunciado não pode ser vazio.')
        return value

    def validate_options(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Deve ser uma lista.')
        cleaned = []
        for item in value:
            if not isinstance(item, dict):
                continue
            text = (item.get('text') or '').strip()
            if not text:
                continue
            image_id = item.get('image_document_id')
            if not image_id:
                image_id = None
            cleaned.append({
                'text': text,
                'image_document_id': image_id,
            })
        return cleaned


# =========================================================================
# SECTION
# =========================================================================

class BriefingSectionSerializer(serializers.ModelSerializer):
    questions = BriefingQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = BriefingSection
        fields = [
            'id',
            'title',
            'description',
            'position',
            'questions',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class BriefingSectionCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, allow_blank=False)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )

    def validate_title(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O título é obrigatório.')
        return value


class BriefingSectionUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(
        required=False, allow_blank=False, max_length=200,
    )
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )

    def validate_title(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O título não pode ser vazio.')
        return value


# =========================================================================
# TEMPLATE EVENT
# =========================================================================

class BriefingTemplateEventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(
        source='get_kind_display', read_only=True,
    )
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = BriefingTemplateEvent
        fields = [
            'id',
            'template',
            'kind',
            'kind_display',
            'section_id',
            'question_id',
            'content',
            'user',
            'user_email',
            'created_at',
        ]
        read_only_fields = fields

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None


# =========================================================================
# TEMPLATE
# =========================================================================

class BriefingTemplateListSerializer(serializers.ModelSerializer):
    sections_count = serializers.IntegerField(read_only=True)
    questions_count = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    cover_url = serializers.SerializerMethodField()
    category_id = serializers.SerializerMethodField()

    class Meta:
        model = BriefingTemplate
        fields = [
            'id',
            'name',
            'description',
            'category',
            'category_id',
            'status',
            'status_display',
            'is_active',
            'position',
            'cover_url',
            'sections_count',
            'questions_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_cover_url(self, obj):
        if not obj.cover:
            return ''
        try:
            url = obj.cover.url
        except Exception:
            return ''
        request = self.context.get('request')
        return _absolute_url(request, url)

    def get_category_id(self, obj):
        if obj.category_fk_id:
            return str(obj.category_fk_id)
        return None


class BriefingTemplateDetailSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    sections_count = serializers.SerializerMethodField()
    questions_count = serializers.SerializerMethodField()
    is_editable = serializers.SerializerMethodField()
    can_start_execution = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    category_id = serializers.SerializerMethodField()

    class Meta:
        model = BriefingTemplate
        fields = [
            'id',
            'name',
            'description',
            'category',
            'category_id',
            'cover_url',
            'status',
            'status_display',
            'is_active',
            'position',
            'is_editable',
            'can_start_execution',
            'sections_count',
            'questions_count',
            'sections',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_sections(self, obj):
        qs = obj.sections.prefetch_related(
            'questions__reference_documents',
        ).order_by('position', 'created_at')
        # Passa contexto para os questions resolverem URLs de opções
        return BriefingSectionSerializer(
            qs, many=True, context=self.context,
        ).data

    def get_sections_count(self, obj):
        return obj.sections.count()

    def get_questions_count(self, obj):
        return BriefingQuestion.objects.filter(
            section__template=obj,
        ).count()

    def get_is_editable(self, obj):
        return obj.is_editable()

    def get_can_start_execution(self, obj):
        return obj.can_start_execution()

    def get_cover_url(self, obj):
        if not obj.cover:
            return ''
        try:
            url = obj.cover.url
        except Exception:
            return ''
        request = self.context.get('request')
        return _absolute_url(request, url)

    def get_category_id(self, obj):
        if obj.category_fk_id:
            return str(obj.category_fk_id)
        return None


class BriefingTemplateCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, allow_blank=False)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )
    category = serializers.CharField(
        required=False, allow_blank=True, max_length=50,
    )
    category_id = serializers.UUIDField(
        required=False, allow_null=True,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome é obrigatório.')
        return value


class BriefingTemplateUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=False, allow_blank=False, max_length=200,
    )
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )
    category = serializers.CharField(
        required=False, allow_blank=True, max_length=50,
    )
    category_id = serializers.UUIDField(
        required=False, allow_null=True,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class BriefingTemplateSetActiveSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=True)


# =========================================================================
# REORDER
# =========================================================================

class ReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
    )