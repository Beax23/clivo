"""
BackblazeB2UsageService — snapshot físico do bucket no B2.

REGRA ARQUITETURAL
------------------
Este serviço faz UMA coisa: consultar a API do B2 e persistir um
StorageProviderSnapshot com o total físico de bytes do bucket.

Ele NÃO calcula cota por workspace.
Ele NÃO autoriza upload.
Ele NÃO soma `size` de `documents.Document` nem `references.Reference`.
Ele NÃO interfere no caminho crítico do usuário.

A cota por workspace vem de outra fonte (`PlanFeatureLimit`) e o uso
por workspace vem do `Sum('size')` local nos módulos. Isso é decisão
consolidada: o snapshot do B2 é auditoria e reconciliação — nunca a
fonte de verdade da cota.

SOBRE A API DO B2 E O VERSIONAMENTO
-----------------------------------
O B2 é S3-compatible. Consultamos via `boto3.client('s3')`.

IMPORTANTE:
    O Backblaze B2 COBRA por TODAS as versões de cada arquivo, não
    só a versão ativa. Um arquivo de 1 GB sobrescrito 3 vezes ocupa
    4 GB na cobrança (1 ativa + 3 versões antigas).

    Por isso NÃO usamos `list_objects_v2` (que só devolve a versão
    ativa de cada objeto). Usamos `list_object_versions`, que devolve
    TODAS as versões. A soma dos `Size` de todas as versões é o
    "uso físico real" que o painel do B2 mostra.

    Se o bucket NÃO tem versionamento ativo, `list_object_versions`
    devolve os mesmos objetos de `list_objects_v2` — sem diferença.

    `DeleteMarkers` são retornados em `list_object_versions` mas NÃO
    têm `Size` — a B2 os cobra como metadata mínima (desprezível na
    prática). Contamos a quantidade para auditoria mas não somamos
    bytes deles.

SOBRE FALHAS
------------
- Erro de rede, credenciais, bucket inexistente, etc → grava snapshot
  `status='error'` com a mensagem.
- Credenciais ausentes → grava snapshot `status='unavailable'`.
- Sucesso → grava snapshot `status='ok'`.

O serviço NUNCA levanta exceção para o chamador. O management command
precisa terminar com código 0 mesmo em falha, para não poluir logs de
cron com falsos alertas. O erro fica registrado no snapshot e no logger.

SOBRE A SEMÂNTICA DE `storage_usage_bytes`
------------------------------------------
Neste serviço, `storage_usage_bytes` é o tamanho FÍSICO COBRADO do
bucket: soma dos `Size` de TODAS as versões de TODOS os objetos.

NÃO é a soma lógica de `Document.size` + `Reference.size`. As duas
grandezas podem divergir (versões antigas, arquivos órfãos no bucket,
registros sem `size` preenchido, duplicatas fora do Clivo). Essa
diferença é o ponto de auditoria — não um erro.

SOBRE `raw_payload`
-------------------
Persistido versionado. Chave `payload_version` = 2 identifica este
formato (v1 era `list_objects_v2`). Contém bucket name, contagem de
versões ativas e de versões totais, e um flag `truncated` que sinaliza
se a paginação foi interrompida antes do fim. Nunca contém credenciais.
"""

import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone

from apps.console.models import StorageProviderSnapshot

logger = logging.getLogger('console')


PROVIDER_KEY_B2 = 'backblaze_b2'
PAYLOAD_VERSION = 2


class BackblazeB2UsageService:

    # ==================================================================
    # DISPONIBILIDADE
    # ==================================================================

    @staticmethod
    def is_available() -> bool:
        """
        Verifica se há credenciais B2 configuradas no ambiente.

        A flag `B2_CONFIGURED` é definida em settings.py quando as
        variáveis necessárias existem. Se a flag não existir (settings
        de versão antiga), fazemos fallback checando as envs.

        NÃO chama a API. Só verifica configuração.
        """
        if hasattr(settings, 'B2_CONFIGURED'):
            return bool(settings.B2_CONFIGURED)

        import os
        return all([
            os.getenv('B2_KEY_ID'),
            os.getenv('B2_APPLICATION_KEY'),
            os.getenv('B2_BUCKET_NAME'),
            os.getenv('B2_ENDPOINT'),
            os.getenv('B2_REGION'),
        ])

    # ==================================================================
    # FETCH
    # ==================================================================

    @staticmethod
    def fetch() -> dict:
        """
        Consulta a API do B2 e devolve o resumo físico do bucket.

        Usa `list_object_versions` para contabilizar TODAS as versões
        de cada objeto — é o que a B2 efetivamente cobra.

        Retorna:
            {
                'ok': bool,
                'payload': dict | None,
                'error': str | None,
            }

        NÃO persiste nada. NÃO levanta exceção.
        """
        if not BackblazeB2UsageService.is_available():
            return {
                'ok': False,
                'payload': None,
                'error': 'Credenciais B2 ausentes no ambiente.',
            }

        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import (
                BotoCoreError,
                ClientError,
                EndpointConnectionError,
            )
        except ImportError as exc:
            return {
                'ok': False,
                'payload': None,
                'error': f'boto3/botocore não disponível: {exc}',
            }

        bucket = settings.B2_BUCKET_NAME
        endpoint = settings.B2_ENDPOINT
        region = settings.B2_REGION

        try:
            client = boto3.client(
                's3',
                endpoint_url=endpoint,
                region_name=region,
                aws_access_key_id=settings.B2_KEY_ID,
                aws_secret_access_key=settings.B2_APPLICATION_KEY,
                config=Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'virtual'},
                    connect_timeout=10,
                    read_timeout=60,
                    retries={'max_attempts': 3, 'mode': 'standard'},
                ),
            )
        except Exception as exc:
            logger.exception('Falha ao criar cliente B2')
            return {
                'ok': False,
                'payload': None,
                'error': f'Falha ao criar cliente B2: {exc}',
            }

        total_bytes = 0
        active_versions_count = 0   # versões ativas (IsLatest=True)
        total_versions_count = 0    # todas as versões (ativas + antigas)
        delete_markers_count = 0    # hides (contados para auditoria)
        paginator_truncated = False

        try:
            paginator = client.get_paginator('list_object_versions')
            pages = paginator.paginate(Bucket=bucket)

            for page in pages:
                versions = page.get('Versions') or []
                delete_markers = page.get('DeleteMarkers') or []

                for v in versions:
                    size = v.get('Size')
                    if isinstance(size, int):
                        total_bytes += size
                        total_versions_count += 1
                        if v.get('IsLatest'):
                            active_versions_count += 1

                delete_markers_count += len(delete_markers)

        except ClientError as exc:
            err = exc.response.get('Error', {})
            code = err.get('Code', 'Unknown')
            msg = err.get('Message', str(exc))
            logger.warning(
                'B2 ClientError: %s — %s', code, msg,
            )
            return {
                'ok': False,
                'payload': None,
                'error': f'B2 ClientError {code}: {msg}',
            }
        except EndpointConnectionError as exc:
            logger.warning('B2 endpoint inacessível: %s', exc)
            return {
                'ok': False,
                'payload': None,
                'error': f'Endpoint B2 inacessível: {exc}',
            }
        except BotoCoreError as exc:
            logger.warning('B2 BotoCoreError: %s', exc)
            return {
                'ok': False,
                'payload': None,
                'error': f'Erro do SDK B2: {exc}',
            }
        except Exception as exc:
            logger.exception('Falha inesperada ao consultar B2')
            return {
                'ok': False,
                'payload': None,
                'error': f'{type(exc).__name__}: {exc}',
            }

        payload = {
            'payload_version': PAYLOAD_VERSION,
            'bucket_name': bucket,
            'endpoint': endpoint,
            'region': region,
            'total_bytes': total_bytes,
            'file_count': active_versions_count,
            'active_versions_count': active_versions_count,
            'total_versions_count': total_versions_count,
            'delete_markers_count': delete_markers_count,
            'truncated': paginator_truncated,
        }
        return {'ok': True, 'payload': payload, 'error': None}

    # ==================================================================
    # SYNC
    # ==================================================================

    @staticmethod
    def sync() -> StorageProviderSnapshot:
        """
        Consulta a API e persiste um novo snapshot.

        Sempre persiste — sucesso, erro ou indisponibilidade. Nunca
        levanta exceção.
        """
        now = timezone.now()

        if not BackblazeB2UsageService.is_available():
            return BackblazeB2UsageService._persist(
                status=StorageProviderSnapshot.STATUS_UNAVAILABLE,
                fetched_at=now,
                error_message=(
                    'B2 não configurado — variáveis de ambiente '
                    'B2_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET_NAME / '
                    'B2_ENDPOINT / B2_REGION ausentes.'
                ),
            )

        result = BackblazeB2UsageService.fetch()

        if not result['ok']:
            logger.warning(
                'Sincronização B2 falhou: %s', result['error'],
            )
            return BackblazeB2UsageService._persist(
                status=StorageProviderSnapshot.STATUS_ERROR,
                fetched_at=now,
                error_message=result['error'] or 'Erro desconhecido',
            )

        payload = result['payload']
        snapshot = BackblazeB2UsageService._persist(
            status=StorageProviderSnapshot.STATUS_OK,
            fetched_at=now,
            raw_payload=payload,
            storage_usage_bytes=payload.get('total_bytes'),
        )

        logger.info(
            'B2 snapshot persistido: bucket=%s total_bytes=%s '
            'active_versions=%s total_versions=%s delete_markers=%s',
            payload.get('bucket_name'),
            payload.get('total_bytes'),
            payload.get('active_versions_count'),
            payload.get('total_versions_count'),
            payload.get('delete_markers_count'),
        )
        return snapshot

    # ==================================================================
    # PERSISTÊNCIA
    # ==================================================================

    @staticmethod
    def _persist(
        status: str,
        fetched_at,
        raw_payload: Optional[dict] = None,
        error_message: str = '',
        storage_usage_bytes: Optional[int] = None,
    ) -> StorageProviderSnapshot:
        """
        Grava um snapshot do B2.

        Só preenche campos que o B2 tem equivalente. Os campos
        específicos de Cloudinary (credits_*, bandwidth_*,
        transformations_*, plan_name, media_limits, rate_limit_*,
        objects_count, resources_count, derived_resources_count)
        ficam NULL.
        """
        return StorageProviderSnapshot.objects.create(
            provider_key=PROVIDER_KEY_B2,
            status=status,
            plan_name='',
            raw_payload=raw_payload,
            storage_usage_bytes=storage_usage_bytes,
            storage_credits_usage=None,
            bandwidth_usage_bytes=None,
            bandwidth_credits_usage=None,
            transformations_usage=None,
            transformations_credits_usage=None,
            credits_usage=None,
            credits_limit=None,
            credits_used_percent=None,
            objects_count=None,
            resources_count=None,
            derived_resources_count=None,
            media_limits=None,
            rate_limit_remaining=None,
            rate_limit_reset_at=None,
            error_message=error_message,
            fetched_at=fetched_at,
        )