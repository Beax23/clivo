"""
Modelo InsightItem — armazena os insights produzidos pela IA.

CONTRATO DE CONTAINERS
----------------------
Cada `kind` de `InsightItem` pertence a um ou mais containers fixos.
O mapeamento abaixo é a fonte de verdade da apresentação. Nenhuma
view ou serializer pode inventar um container novo.

    MESA (visão rápida do trabalho)
        01_desejos_prioridades     -> KIND_DESIRE
        02_pontos_atencao          -> KIND_ATTENTION
        03_mudancas                -> KIND_CHANGE
        04_novidades               -> KIND_NEWS
        05_resumo                  -> KIND_SUMMARY_BRIEFING

    CLIENTE (visão consolidada da pessoa)
        01_desejos_prioridades     -> KIND_DESIRE
        02_perfil_preferencias     -> KIND_PREFERENCE_PROFILE
        03_conhecimento_acumulado  -> KIND_KNOWLEDGE_ACCUMULATED
        04_como_conduzir_melhor    -> KIND_HOW_TO_CONDUCT
        05_perfil_cliente          -> KIND_CLIENT_PROFILE

    RELATORIO (visão completa das análises)
        01_sintese_executiva       -> KIND_EXECUTIVE_SUMMARY
        02_desejos_criterios       -> KIND_DESIRE, KIND_SUCCESS_CRITERIA
        03_leitura_referencias     -> KIND_REFERENCE_ANALYSIS
        04_restricoes_atencao      -> KIND_RESTRICTION, KIND_ATTENTION
        05_lacunas_inconsistencias -> KIND_GAP, KIND_INCONSISTENCY
        06_insights_cruzados       -> KIND_CROSS_INSIGHT
        07_perguntas_recomendadas  -> KIND_RECOMMENDED_QUESTION
        08_avaliacao_prontidao     -> KIND_READINESS_ASSESSMENT
        09_outras_analises         -> (kind futuro, declarado aqui)

PRESERVAÇÃO DO BRIEFING
-----------------------
`briefing` usa `on_delete=SET_NULL`. Se o briefing de origem for
excluído, o `InsightItem` sobrevive como conhecimento acumulado do
cliente. Nunca `CASCADE` aqui — destruiria o histórico.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class InsightItem(models.Model):

    # --- Containers: Mesa ---
    KIND_DESIRE = 'desire'
    KIND_ATTENTION = 'attention'
    KIND_CHANGE = 'change'
    KIND_NEWS = 'news'
    KIND_SUMMARY_BRIEFING = 'summary.briefing'

    # --- Containers: Cliente ---
    KIND_PREFERENCE_PROFILE = 'preference.profile'
    KIND_KNOWLEDGE_ACCUMULATED = 'knowledge.accumulated'
    KIND_HOW_TO_CONDUCT = 'how_to_conduct'
    KIND_CLIENT_PROFILE = 'client.profile'

    # --- Containers: Relatório ---
    KIND_EXECUTIVE_SUMMARY = 'executive.summary'
    KIND_SUCCESS_CRITERIA = 'success.criteria'
    KIND_REFERENCE_ANALYSIS = 'analysis.reference'
    KIND_RESTRICTION = 'restriction'
    KIND_GAP = 'gap'
    KIND_INCONSISTENCY = 'inconsistency'
    KIND_CROSS_INSIGHT = 'cross.insight'
    KIND_RECOMMENDED_QUESTION = 'recommended.question'
    KIND_READINESS_ASSESSMENT = 'assessment.readiness'

    # --- Tag (transversal) ---
    KIND_TAG = 'tag'

    KIND_CHOICES = [
        # Mesa
        (KIND_DESIRE, 'Desejo'),
        (KIND_ATTENTION, 'Ponto de Atenção'),
        (KIND_CHANGE, 'Mudança'),
        (KIND_NEWS, 'Novidade'),
        (KIND_SUMMARY_BRIEFING, 'Resumo do Briefing'),
        # Cliente
        (KIND_PREFERENCE_PROFILE, 'Perfil de Preferências'),
        (KIND_KNOWLEDGE_ACCUMULATED, 'Conhecimento Acumulado'),
        (KIND_HOW_TO_CONDUCT, 'Como Conduzir Melhor'),
        (KIND_CLIENT_PROFILE, 'Perfil do Cliente'),
        # Relatório
        (KIND_EXECUTIVE_SUMMARY, 'Síntese Executiva'),
        (KIND_SUCCESS_CRITERIA, 'Critério de Sucesso'),
        (KIND_REFERENCE_ANALYSIS, 'Leitura de Referência'),
        (KIND_RESTRICTION, 'Restrição'),
        (KIND_GAP, 'Lacuna'),
        (KIND_INCONSISTENCY, 'Inconsistência'),
        (KIND_CROSS_INSIGHT, 'Insight Cruzado'),
        (KIND_RECOMMENDED_QUESTION, 'Pergunta Recomendada'),
        (KIND_READINESS_ASSESSMENT, 'Avaliação de Prontidão'),
        # Transversal
        (KIND_TAG, 'Tag'),
    ]

    # Mapeamento container -> kinds. Fonte de verdade da apresentação.
    CONTAINER_MESA = 'mesa'
    CONTAINER_CLIENTE = 'cliente'
    CONTAINER_RELATORIO = 'relatorio'

    CONTAINER_KINDS = {
        CONTAINER_MESA: {
            '01_desejos_prioridades': [KIND_DESIRE],
            '02_pontos_atencao': [KIND_ATTENTION],
            '03_mudancas': [KIND_CHANGE],
            '04_novidades': [KIND_NEWS],
            '05_resumo': [KIND_SUMMARY_BRIEFING],
        },
        CONTAINER_CLIENTE: {
            '01_desejos_prioridades': [KIND_DESIRE],
            '02_perfil_preferencias': [KIND_PREFERENCE_PROFILE],
            '03_conhecimento_acumulado': [KIND_KNOWLEDGE_ACCUMULATED],
            '04_como_conduzir_melhor': [KIND_HOW_TO_CONDUCT],
            '05_perfil_cliente': [KIND_CLIENT_PROFILE],
        },
        CONTAINER_RELATORIO: {
            '01_sintese_executiva': [KIND_EXECUTIVE_SUMMARY],
            '02_desejos_criterios': [KIND_DESIRE, KIND_SUCCESS_CRITERIA],
            '03_leitura_referencias': [KIND_REFERENCE_ANALYSIS],
            '04_restricoes_atencao': [KIND_RESTRICTION, KIND_ATTENTION],
            '05_lacunas_inconsistencias': [KIND_GAP, KIND_INCONSISTENCY],
            '06_insights_cruzados': [KIND_CROSS_INSIGHT],
            '07_perguntas_recomendadas': [KIND_RECOMMENDED_QUESTION],
            '08_avaliacao_prontidao': [KIND_READINESS_ASSESSMENT],
            '09_outras_analises': [KIND_TAG],
        },
    }

    # --- Confiança ---
    CONFIDENCE_FACT = 'fact'
    CONFIDENCE_INTERPRETATION = 'interpretation'
    CONFIDENCE_GAP = 'gap'
    CONFIDENCE_CONTRADICTION = 'contradiction'

    CONFIDENCE_CHOICES = [
        (CONFIDENCE_FACT, 'Fato Explícito'),
        (CONFIDENCE_INTERPRETATION, 'Interpretação'),
        (CONFIDENCE_GAP, 'Informação Ausente'),
        (CONFIDENCE_CONTRADICTION, 'Contradição / Dúvida'),
    ]

    # --- Revisão ---
    REVIEW_STATE_NEW = 'new'
    REVIEW_STATE_CONFIRMED = 'confirmed'
    REVIEW_STATE_DISCARDED = 'discarded'

    REVIEW_STATE_CHOICES = [
        (REVIEW_STATE_NEW, 'Novo'),
        (REVIEW_STATE_CONFIRMED, 'Confirmado'),
        (REVIEW_STATE_DISCARDED, 'Descartado'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    run = models.ForeignKey(
        'intelligence.AnalysisRun',
        on_delete=models.CASCADE,
        related_name='insights',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='insight_items',
        db_index=True,
    )
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='insight_items',
    )
    briefing = models.ForeignKey(
        'briefings.Briefing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='insight_items',
    )

    kind = models.CharField(
        max_length=50, choices=KIND_CHOICES, db_index=True,
    )
    confidence = models.CharField(
        max_length=20, choices=CONFIDENCE_CHOICES,
        default=CONFIDENCE_INTERPRETATION, db_index=True,
    )
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    review_state = models.CharField(
        max_length=20, choices=REVIEW_STATE_CHOICES,
        default=REVIEW_STATE_NEW, db_index=True,
    )
    is_stale = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'intelligence_insight_item'
        verbose_name = _('Item de Insight')
        verbose_name_plural = _('Itens de Insight')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['workspace', 'kind']),
            models.Index(fields=['client', 'kind']),
            models.Index(fields=['briefing', 'kind']),
            models.Index(fields=['review_state', 'is_stale']),
        ]

    def __str__(self):
        return f"[{self.kind}] {self.content[:80]}..."

    # ------------------------------------------------------------------
    # HELPERS DE CONTAINER
    # ------------------------------------------------------------------

    @classmethod
    def kinds_for_container(cls, container: str) -> list:
        """
        Retorna todos os `kind` válidos para um container.
        Usado por serializers/views para filtrar sem duplicar a verdade.
        """
        mapping = cls.CONTAINER_KINDS.get(container)
        if mapping is None:
            raise ValueError(f'Container desconhecido: {container}')
        result = set()
        for kinds in mapping.values():
            result.update(kinds)
        return sorted(result)

    @classmethod
    def container_slots_for_kind(cls, kind: str) -> dict:
        """
        Retorna, para um `kind`, quais slots de container o exibem.

        Estrutura:
            {
                'mesa': ['01_desejos_prioridades'],
                'relatorio': ['02_desejos_criterios'],
                ...
            }

        Um `kind` pode aparecer em mais de um container (ex: KIND_DESIRE
        aparece na Mesa e no Relatório). Este método é o inverso do
        CONTAINER_KINDS e evita duplicação de lógica nas views.
        """
        result = {}
        for container, slots in cls.CONTAINER_KINDS.items():
            matching = [
                slot_name for slot_name, kinds in slots.items()
                if kind in kinds
            ]
            if matching:
                result[container] = matching
        return result

    # ------------------------------------------------------------------
    # HELPERS DE HISTÓRICO DE TAG
    # ------------------------------------------------------------------

    def has_tag_history(self) -> bool:
        """True se este item é uma tag com pelo menos uma transição."""
        if self.kind != self.KIND_TAG:
            return False
        return self.tag_history.exists()