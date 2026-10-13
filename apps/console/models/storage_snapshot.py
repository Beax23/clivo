"""
Modelo StorageProviderSnapshot.

Persiste uma leitura pontual da API do provider de armazenamento ativo
(atualmente Backblaze B2; historicamente Cloudinary).

REGRA ARQUITETURAL
------------------
Este modelo é histórico, não estado atual. Cada execução da sincronização
grava UMA linha. Não há upsert, não há "singleton".

O "snapshot atual" é o snapshot com status='ok' mais recente. Se a última
execução falhou, o Console deve exibir o último 'ok' com um aviso de
desatualização — nunca sobrescrever dados válidos com zeros.

SOBRE CAMPOS NULLABLE
---------------------
Todos os campos extraídos do payload são nullable. Regra:
    - Se a API devolveu, o campo tem valor.
    - Se a API não devolveu (provider diferente, mudança de contrato,
      campo opcional), o campo é NULL.
    - NUNCA inventar número. NUNCA derivar `storage_limit_bytes` a
      partir de `credits_limit`.

SOBRE `raw_payload`
-------------------
Payload bruto completo, para auditoria e para permitir reinterpretação
retroativa caso o extrator evolua. Não contém credenciais — a API de
uso do provider de armazenamento só devolve métricas e limites.

SOBRE `status`
--------------
    ok          → payload recebido, extração bem-sucedida
    error       → tentativa falhou (rede, HTTP, credenciais)
    unavailable → credentials ausentes ou provider desconfigurado
                  (não houve tentativa)

O status `stale` foi removido do desenho inicial — a desatualização é
derivada no momento da leitura (comparando timestamps), não persistida.

SOBRE CAMPOS ESPECÍFICOS DE CLOUDINARY
--------------------------------------
Os campos `credits_*`, `transformations_*`, `bandwidth_*`, `plan_name`,
`media_limits`, `rate_limit_*`, `objects_count`, `resources_count` e
`derived_resources_count` foram desenhados para o formato de payload do
Cloudinary. Permanecem no modelo por compatibilidade histórica. Para o
B2, ficam NULL — o B2 não tem equivalentes.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class StorageProviderSnapshot(models.Model):

    STATUS_OK = 'ok'
    STATUS_ERROR = 'error'
    STATUS_UNAVAILABLE = 'unavailable'

    STATUS_CHOICES = [
        (STATUS_OK, 'OK'),
        (STATUS_ERROR, 'Erro'),
        (STATUS_UNAVAILABLE, 'Indisponível'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    provider_key = models.SlugField(
        max_length=50,
        db_index=True,
        help_text=_(
            'Chave do provider (ex: "backblaze_b2", "cloudinary"). '
            'Não é FK — o snapshot sobrevive se o Provider for removido.'
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ERROR,
        db_index=True,
        help_text=_('Resultado da tentativa de sincronização'),
    )

    plan_name = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text=_(
            'Nome do plano reportado pela API (específico do Cloudinary).'
        ),
    )

    # ------------------------------------------------------------------
    # Payload bruto (auditoria)
    # ------------------------------------------------------------------

    raw_payload = models.JSONField(
        null=True,
        blank=True,
        help_text=_(
            'Payload bruto devolvido pela API. Nunca contém credenciais. '
            'Permite reinterpretação retroativa se o extrator evoluir.'
        ),
    )

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    storage_usage_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_(
            'storage.usage em bytes (nulo se ausente). '
            'Para o B2, representa o tamanho físico do bucket informado '
            'pela API do provider — NÃO é a soma lógica dos arquivos '
            'contabilizados por workspace.'
        ),
    )

    storage_credits_usage = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_('storage.credits_usage (específico do Cloudinary)'),
    )

    # ------------------------------------------------------------------
    # Bandwidth (específico do Cloudinary)
    # ------------------------------------------------------------------

    bandwidth_usage_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('bandwidth.usage em bytes (específico do Cloudinary)'),
    )

    bandwidth_credits_usage = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_('bandwidth.credits_usage (específico do Cloudinary)'),
    )

    # ------------------------------------------------------------------
    # Transformations (específico do Cloudinary)
    # ------------------------------------------------------------------

    transformations_usage = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('transformations.usage (específico do Cloudinary)'),
    )

    transformations_credits_usage = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_('transformations.credits_usage (específico do Cloudinary)'),
    )

    # ------------------------------------------------------------------
    # Credits (específico do Cloudinary)
    # ------------------------------------------------------------------

    credits_usage = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_('credits.usage — total consumido no ciclo (Cloudinary)'),
    )

    credits_limit = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_(
            'credits.limit — teto do plano (Cloudinary). '
            'NÃO é limite de armazenamento; créditos são compartilhados '
            'entre storage, bandwidth e transformações.'
        ),
    )

    credits_used_percent = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_('credits.used_percent (específico do Cloudinary)'),
    )

    # ------------------------------------------------------------------
    # Objetos (específico do Cloudinary)
    # ------------------------------------------------------------------

    objects_count = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Total de assets (específico do Cloudinary)'),
    )

    resources_count = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Recursos originais (específico do Cloudinary)'),
    )

    derived_resources_count = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Recursos derivados (específico do Cloudinary)'),
    )

    # ------------------------------------------------------------------
    # Limites por tipo de mídia (específico do Cloudinary)
    # ------------------------------------------------------------------

    media_limits = models.JSONField(
        null=True,
        blank=True,
        help_text=_(
            'media_limits — limites por tipo de mídia (específico do '
            'Cloudinary). Estrutura depende do plano.'
        ),
    )

    # ------------------------------------------------------------------
    # Rate limit (específico do Cloudinary)
    # ------------------------------------------------------------------

    rate_limit_remaining = models.IntegerField(
        null=True,
        blank=True,
        help_text=_('rate_limit_remaining (específico do Cloudinary)'),
    )

    rate_limit_reset_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('rate_limit_reset_at (específico do Cloudinary)'),
    )

    # ------------------------------------------------------------------
    # Erro
    # ------------------------------------------------------------------

    error_message = models.TextField(
        blank=True,
        default='',
        help_text=_('Descrição do erro quando status != ok'),
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------

    fetched_at = models.DateTimeField(
        db_index=True,
        help_text=_('Momento em que a API respondeu (ou tentou responder)'),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'console_storage_provider_snapshot'
        verbose_name = _('Snapshot de Provider de Armazenamento')
        verbose_name_plural = _('Snapshots de Provider de Armazenamento')
        ordering = ['-fetched_at']
        indexes = [
            models.Index(fields=['provider_key', '-fetched_at']),
            models.Index(fields=['provider_key', 'status', '-fetched_at']),
        ]

    def __str__(self):
        return f"{self.provider_key} · {self.status} · {self.fetched_at:%Y-%m-%d %H:%M}"