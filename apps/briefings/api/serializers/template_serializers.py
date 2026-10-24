"""
Serializers de BriefingTemplate, BriefingSection, BriefingQuestion
e BriefingTemplateEvent.

REGRA DE URL
-----------
Toda URL de mídia retornada por serializers passa por `_absolute_url`.
"""

from rest_framework import serializers

from apps.briefings.models import (
    BriefingTemplate,
    BriefingSection,
    BriefingQuestion,
    BriefingTemplateEvent,
)


def _absolute_url(request, url):
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


def _validate_choice_options(value):
    if not isinstance(value, list):
        raise serializers.ValidationError('Deve ser uma lista.')

    cleaned = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = (item.get('text') or '').strip()
        if not text:
            continue
        image_id = item.get('image_document_id') or None
        cleaned.append({
            'text': text,
            'image_document_id': image_id,
        })
    return cleaned


def _validate_grid_options(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError(
            'Para grades, deve ser um dict com "rows" e "columns".'
        )

    rows = value.get('rows') or []
    columns = value.get('columns') or []

    if not isinstance(rows, list) or not isinstance(columns, list):
        raise serializers.ValidationError(
            'Grid precisa de "rows" (list) e "columns" (list).'
        )

    clean_rows = [str(r).strip() for r in rows if str(r).strip()]

    clean_columns = []
    for col in columns:
        if isinstance(col, str):
            text = col.strip()
            if text:
                clean_columns.append({
                    'text': text,
                    'image_document_id': None,
                })
        elif isinstance(col, dict):
            text = (col.get('text') or '').strip()
            if text:
                clean_columns.append({
                    'text': text,
                    'image_document_id': col.get('image_document_id') or None,
                })

    return {
        'rows': clean_rows,
        'columns': clean_columns,
    }


class BriefingQuestionSerializer(serializers.ModelSerializer):
    reference_document_ids = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()

    class Meta:
        model = BriefingQuestion
        fields = [
            'id', 'text', 'instructions', 'question_type',
            'allowed_response_formats', 'options', 'position',
            'is_required', 'reference_document_ids',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_reference_document_ids(self, obj):
        return [str(d.id) for d in obj.reference_documents.all()]

    def get_options(self, obj):
        raw_options = obj.options or []

        if isinstance(raw_options, dict):
            raw_columns = raw_options.get('columns') or []
            doc_ids = [
                str(col.get('image_document_id'))
                for col in raw_columns
                if isinstance(col, dict) and col.get('image_document_id')
            ]
            docs_by_id = self._load_documents_map(doc_ids)
            request = self.context.get('request')

            clean_columns = []
            for col in raw_columns:
                if not isinstance(col, dict):
                    continue
                entry = {
                    'text': col.get('text', ''),
                    'image_document_id': col.get('image_document_id'),
                    'image_url': None,
                }
                doc_id = col.get('image_document_id')
                if doc_id:
                    doc = docs_by_id.get(str(doc_id))
                    if doc and doc.file:
                        try:
                            entry['image_url'] = _absolute_url(
                                request, doc.file.url,
                            )
                        except Exception:
                            entry['image_url'] = None
                clean_columns.append(entry)

            return {
                'rows': list(raw_options.get('rows') or []),
                'columns': clean_columns,
            }

        if not isinstance(raw_options, list) or not raw_options:
            return []

        doc_ids = [
            str(opt.get('image_document_id'))
            for opt in raw_options
            if isinstance(opt, dict) and opt.get('image_document_id')
        ]
        docs_by_id = self._load_documents_map(doc_ids)
        request = self.context.get('request')

        result = []
        for opt in raw_options:
            if not isinstance(opt, dict):
                continue
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

    @staticmethod
    def _load_documents_map(doc_ids):
        if not doc_ids:
            return {}
        from apps.documents.models import Document
        docs = Document.objects.filter(id__in=doc_ids)
        return {str(d.id): d for d in docs}


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
    options = serializers.JSONField(required=False)
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

    def validate(self, attrs):
        q_type = attrs.get('question_type') or BriefingQuestion.QUESTION_TYPE_TEXT
        raw_options = attrs.get('options')

        if raw_options is None:
            attrs['options'] = []
            return attrs

        if q_type in BriefingQuestion.GRID_TYPES:
            attrs['options'] = _validate_grid_options(raw_options)
        elif q_type in BriefingQuestion.CHOICE_TYPES:
            attrs['options'] = _validate_choice_options(raw_options)
        else:
            attrs['options'] = []

        return attrs


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
    options = serializers.JSONField(required=False)
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

    def validate(self, attrs):
        q_type = attrs.get('question_type')
        raw_options = attrs.get('options')

        if raw_options is None:
            return attrs

        if q_type in BriefingQuestion.GRID_TYPES:
            attrs['options'] = _validate_grid_options(raw_options)
        elif q_type in BriefingQuestion.CHOICE_TYPES:
            attrs['options'] = _validate_choice_options(raw_options)
        elif q_type is None:
            if isinstance(raw_options, dict):
                attrs['options'] = _validate_grid_options(raw_options)
            else:
                attrs['options'] = _validate_choice_options(raw_options)
        else:
            attrs['options'] = []

        return attrs


class BriefingSectionSerializer(serializers.ModelSerializer):
    questions = BriefingQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = BriefingSection
        fields = [
            'id', 'title', 'description', 'position', 'questions',
            'created_at', 'updated_at',
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


class BriefingTemplateEventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(
        source='get_kind_display', read_only=True,
    )
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = BriefingTemplateEvent
        fields = [
            'id', 'template', 'kind', 'kind_display',
            'section_id', 'question_id', 'content',
            'user', 'user_email', 'created_at',
        ]
        read_only_fields = fields

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None


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
            'id', 'name', 'description', 'category', 'category_id',
            'status', 'status_display', 'position', 'cover_url',
            'intro_message', 'sections_count', 'questions_count',
            'created_at', 'updated_at',
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
            'id', 'name', 'description', 'category', 'category_id',
            'cover_url', 'intro_message',
            'status', 'status_display', 'position',
            'is_editable', 'can_start_execution',
            'sections_count', 'questions_count', 'sections',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_sections(self, obj):
        qs = obj.sections.prefetch_related(
            'questions__reference_documents',
        ).order_by('position', 'created_at')
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
    intro_message = serializers.CharField(
        required=False, allow_blank=True,
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
    intro_message = serializers.CharField(
        required=False, allow_blank=True,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class ReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
    )