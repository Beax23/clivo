"""
Serializers da API de Google Forms.

Grupos:

    ENTRADA (busca):
        FormsSearchQuerySerializer  — query params de /search/

    ENTRADA (preview):
        FormPreviewSerializer       — body de /preview/

    ENTRADA (import):
        FormImportSerializer        — body de /import/
                                       (aceita template_name opcional)

    SAÍDA (busca):
        FormSummarySerializer       — item de lista em /search/

    SAÍDA (preview):
        FormPreviewResultSerializer — retorno de /preview/

    SAÍDA (import):
        FormImportResultSerializer  — retorno de /import/
"""

from rest_framework import serializers


# =========================================================================
# ENTRADA
# =========================================================================

class FormsSearchQuerySerializer(serializers.Serializer):
    """
    Query params de GET /api/integrations/google/forms/search/
    """
    q = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
        default='',
    )


class FormPreviewSerializer(serializers.Serializer):
    """
    Body de POST /api/integrations/google/forms/preview/

    Aceita URL completa ou ID cru. A validação fina é feita pelo
    service — aqui garantimos que é uma string não vazia.
    """
    form = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=2000,
        help_text=(
            'URL do Google Forms ou o ID do formulário.'
        ),
    )


class FormImportSerializer(serializers.Serializer):
    """
    Body de POST /api/integrations/google/forms/import/

    `template_name` é OPCIONAL. Se ausente, o backend usa o nome
    do formulário do Google como nome do template criado.
    """
    form = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=2000,
        help_text=(
            'URL do Google Forms ou o ID do formulário.'
        ),
    )
    template_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
        default='',
        help_text=(
            'Nome do novo modelo. Se vazio, usa o nome do formulário '
            'do Google.'
        ),
    )

    def validate_template_name(self, value):
        if value is None:
            return ''
        return value.strip()


# =========================================================================
# SAÍDA
# =========================================================================

class FormSummarySerializer(serializers.Serializer):
    """
    Item da lista de formulários retornado por /search/.
    """
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    url = serializers.URLField(read_only=True, allow_blank=True)


class FormPreviewResultSerializer(serializers.Serializer):
    """
    Resultado de /preview/.

    Envelope do resumo do formulário ANTES da criação do template.
    Usado pelo frontend para montar a tela de confirmação.
    """
    form_id = serializers.CharField(read_only=True)
    form_name = serializers.CharField(read_only=True)
    form_description = serializers.CharField(
        read_only=True, allow_blank=True,
    )
    sections_count = serializers.IntegerField(read_only=True)
    questions_count = serializers.IntegerField(read_only=True)


class FormImportResultSerializer(serializers.Serializer):
    """
    Resultado de /import/.

    Devolve o `template_id` do NOVO modelo criado — o frontend
    usa isso para navegar até ele.
    """
    imported = serializers.BooleanField(read_only=True)
    form_id = serializers.CharField(read_only=True)
    template_id = serializers.UUIDField(read_only=True)
    template_name = serializers.CharField(read_only=True)
    sections_created = serializers.IntegerField(read_only=True)
    questions_created = serializers.IntegerField(read_only=True)