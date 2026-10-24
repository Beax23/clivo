"""
Serializers de BriefingTemplateVersion.

REGRA:
- `BriefingTemplateVersionListSerializer` → metadados apenas (SEM `structure`).
  Usado por GET /api/briefing-templates/{id}/versions/.
- `BriefingTemplateVersionSerializer` → detalhe completo (COM `structure`).
  Usado por GET /api/briefing-templates/{id}/versions/{vid}/.

O cliente busca o detalhe sob demanda ao clicar em uma versão.

CACHE:
- O backend NÃO define `Cache-Control` aqui. A decisão de cachear é do
  cliente (browser/JS). Se futuramente forem adicionados cabeçalhos,
  ATENÇÃO: uma versão `published` é imutável, mas uma versão `draft`
  pode mudar. Não trate as duas igualmente.
"""

from rest_framework import serializers

from apps.briefings.models import BriefingTemplateVersion


# =========================================================================
# LIST — metadados apenas
# =========================================================================

class BriefingTemplateVersionListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    sections_count = serializers.SerializerMethodField()
    questions_count = serializers.SerializerMethodField()

    class Meta:
        model = BriefingTemplateVersion
        fields = [
            'id',
            'template',
            'version_number',
            'status',
            'status_display',
            'sections_count',
            'questions_count',
            'published_at',
            'created_at',
        ]
        read_only_fields = fields

    def get_sections_count(self, obj):
        s = (obj.structure or {}).get('sections') or []
        return len(s)

    def get_questions_count(self, obj):
        s = (obj.structure or {}).get('sections') or []
        total = 0
        for sec in s:
            total += len(sec.get('questions') or [])
        return total


# =========================================================================
# DETAIL — estrutura completa
# =========================================================================

class BriefingTemplateVersionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    is_editable = serializers.SerializerMethodField()
    sections_count = serializers.SerializerMethodField()
    questions_count = serializers.SerializerMethodField()

    class Meta:
        model = BriefingTemplateVersion
        fields = [
            'id',
            'template',
            'version_number',
            'status',
            'status_display',
            'is_editable',
            'structure',
            'sections_count',
            'questions_count',
            'published_at',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_is_editable(self, obj):
        return obj.is_editable()

    def get_sections_count(self, obj):
        s = (obj.structure or {}).get('sections') or []
        return len(s)

    def get_questions_count(self, obj):
        s = (obj.structure or {}).get('sections') or []
        total = 0
        for sec in s:
            total += len(sec.get('questions') or [])
        return total


# =========================================================================
# CREATE — body do POST /versions/
# =========================================================================

class BriefingTemplateVersionCreateSerializer(serializers.Serializer):
    """
    Body do POST /api/briefing-templates/<id>/versions/.

    Modos:
        'clone_current'          → clona a estrutura atual das tabelas (default)
        'blank'                  → cria rascunho vazio
        'restore_from_version'   → cria rascunho a partir de uma versão
                                   existente (usa `source_version_id`)
    """
    mode = serializers.ChoiceField(
        choices=['clone_current', 'blank', 'restore_from_version'],
        required=False,
        default='clone_current',
    )
    source_version_id = serializers.UUIDField(
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        mode = attrs.get('mode', 'clone_current')
        source_id = attrs.get('source_version_id')
        if mode == 'restore_from_version' and not source_id:
            raise serializers.ValidationError({
                'source_version_id': (
                    'Obrigatório quando mode="restore_from_version".'
                ),
            })
        return attrs