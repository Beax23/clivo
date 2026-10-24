"""Serializers de BriefingQuestionInstance."""

from rest_framework import serializers

from apps.briefings.models import BriefingQuestionInstance


class BriefingQuestionInstanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BriefingQuestionInstance
        fields = [
            'id',
            'briefing',
            'section_ref',
            'text',
            'instructions',
            'question_type',
            'allowed_response_formats',
            'options',
            'position',
            'is_required',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


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
        cleaned.append({
            'text': text,
            'image_document_id': item.get('image_document_id') or None,
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
                clean_columns.append({'text': text, 'image_document_id': None})
        elif isinstance(col, dict):
            text = (col.get('text') or '').strip()
            if text:
                clean_columns.append({
                    'text': text,
                    'image_document_id': col.get('image_document_id') or None,
                })
    return {'rows': clean_rows, 'columns': clean_columns}


class BriefingQuestionInstanceCreateSerializer(serializers.Serializer):
    section_ref = serializers.CharField(max_length=36)
    text = serializers.CharField(max_length=2000, allow_blank=False)
    instructions = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )
    question_type = serializers.CharField(
        max_length=30, required=False, default='text',
    )
    allowed_response_formats = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        allow_empty=False,
    )
    options = serializers.JSONField(required=False, default=list)
    is_required = serializers.BooleanField(required=False, default=True)

    def validate_text(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O enunciado é obrigatório.')
        return value

    def validate(self, attrs):
        q_type = attrs.get('question_type') or 'text'
        options = attrs.get('options')
        if q_type in ('grid_single', 'grid_multiple') and options is not None:
            attrs['options'] = _validate_grid_options(options)
        elif options is not None:
            attrs['options'] = _validate_choice_options(options)
        return attrs


class BriefingQuestionInstanceUpdateSerializer(serializers.Serializer):
    text = serializers.CharField(
        required=False, allow_blank=False, max_length=2000,
    )
    instructions = serializers.CharField(
        required=False, allow_blank=True, max_length=2000,
    )
    question_type = serializers.CharField(
        max_length=30, required=False,
    )
    allowed_response_formats = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        allow_empty=False,
    )
    options = serializers.JSONField(required=False)
    is_required = serializers.BooleanField(required=False)

    def validate_text(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O enunciado não pode ser vazio.')
        return value

    def validate(self, attrs):
        q_type = attrs.get('question_type')
        options = attrs.get('options')
        if options is None:
            return attrs
        # Se o tipo não foi enviado, valida como lista (comportamento
        # antigo). Se foi enviado e é grid, valida como dict.
        if q_type in ('grid_single', 'grid_multiple'):
            attrs['options'] = _validate_grid_options(options)
        elif q_type is None:
            # Não sabemos o tipo. Aceita qualquer forma — a
            # validação acontecerá no model na hora de salvar.
            pass
        else:
            attrs['options'] = _validate_choice_options(options)
        return attrs