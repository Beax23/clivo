"""
AnalysisService — orquestra a análise de IA.

REGRA ARQUITETURAL
------------------
`intelligence` NÃO chama OpenAI diretamente. Chama a ponte
`console.public.call_ai(...)`, que:
    - verifica quota,
    - seleciona provider/modelo,
    - executa a chamada real,
    - registra ProviderLog e UsageRecord,
    - devolve um payload normalizado.

RESOLUÇÃO DE PROVIDER/MODELO
----------------------------
Quando `INTELLIGENCE_PROVIDER` / `INTELLIGENCE_MODEL` estão definidos
em settings, eles vencem. Quando NÃO estão definidos, o serviço lê
`AIConfigService.get_or_create_default()` — a config ativa do Console.

O provider/modelo escolhidos são PERSISTIDOS no `AnalysisRun` como
snapshot histórico.

ESCOPO DOS KINDS
----------------
A `user_message` lista EXPLICITAMENTE os `target_kinds` da execução.

IDEMPOTÊNCIA POR TENTATIVA
--------------------------
O `input_hash` inclui `job.attempt_count`. Cada tentativa do worker
cria um `AnalysisRun` NOVO. Isso é essencial porque:

    - o `created_at` do run é atualizado a cada tentativa (é
      `auto_now_add=True`, não dá para alterar via `save()`);
    - o `StalenessService` compara `latest_event.created_at` com
      `run.created_at` — se o run for reaproveitado, o
      `created_at` continua sendo o original (velho), e o run
      é sempre considerado stale;
    - com um run novo por tentativa, o `created_at` é sempre
      posterior ao evento `manual.reanalyze` que disparou o job;
    - o `request_id` (=run.id) também muda, o que força o
      `AICallService` a fazer uma chamada real ao provider em vez
      de retornar `raw_content=""` do `UsageRecord` antigo.

Ao criar um run novo, também DELETAMOS os `UsageRecord` e
`ProviderLog` de runs anteriores do MESMO job — evita lixo no
banco e garante que nenhum artefato antigo interfira na nova
tentativa.
"""

import hashlib
import json
import logging
import time
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.intelligence.models import (
    AnalysisJob, AnalysisRun, InsightItem, InsightEvidence, InsightEvent,
)
from apps.intelligence.services.prompt_loader import get_prompt
from apps.intelligence.exceptions import (
    AnalysisInputError,
    AIProviderError,
    AIResponseError,
    StaleAnalysisError,
    BudgetExceededError,
)

logger = logging.getLogger('intelligence')


KINDS_REQUIRING_EVIDENCE = frozenset({
    InsightItem.KIND_DESIRE,
    InsightItem.KIND_ATTENTION,
    InsightItem.KIND_RESTRICTION,
    InsightItem.KIND_PREFERENCE_PROFILE,
    InsightItem.KIND_CLIENT_PROFILE,
    InsightItem.KIND_HOW_TO_CONDUCT,
    InsightItem.KIND_KNOWLEDGE_ACCUMULATED,
    InsightItem.KIND_SUCCESS_CRITERIA,
    InsightItem.KIND_REFERENCE_ANALYSIS,
    InsightItem.KIND_EXECUTIVE_SUMMARY,
    InsightItem.KIND_SUMMARY_BRIEFING,
})


DEFAULT_KINDS_WITH_BRIEFING = [
    InsightItem.KIND_SUMMARY_BRIEFING,
    InsightItem.KIND_DESIRE,
    InsightItem.KIND_ATTENTION,
    InsightItem.KIND_CHANGE,
    InsightItem.KIND_NEWS,
    InsightItem.KIND_RECOMMENDED_QUESTION,
    InsightItem.KIND_GAP,
    InsightItem.KIND_INCONSISTENCY,
    InsightItem.KIND_CROSS_INSIGHT,
    InsightItem.KIND_SUCCESS_CRITERIA,
    InsightItem.KIND_REFERENCE_ANALYSIS,
    InsightItem.KIND_RESTRICTION,
    InsightItem.KIND_READINESS_ASSESSMENT,
    InsightItem.KIND_EXECUTIVE_SUMMARY,
    InsightItem.KIND_TAG,
    InsightItem.KIND_PREFERENCE_PROFILE,
    InsightItem.KIND_KNOWLEDGE_ACCUMULATED,
    InsightItem.KIND_HOW_TO_CONDUCT,
    InsightItem.KIND_CLIENT_PROFILE,
]

DEFAULT_KINDS_WITHOUT_BRIEFING = [
    InsightItem.KIND_KNOWLEDGE_ACCUMULATED,
    InsightItem.KIND_PREFERENCE_PROFILE,
    InsightItem.KIND_HOW_TO_CONDUCT,
    InsightItem.KIND_CLIENT_PROFILE,
    InsightItem.KIND_DESIRE,
    InsightItem.KIND_TAG,
]


class AnalysisService:

    @staticmethod
    def execute(job: AnalysisJob) -> Optional[AnalysisRun]:
        run = None
        try:
            with transaction.atomic():
                run = AnalysisService._create_analysis_run(job)
                if run is None:
                    return None

            from apps.console import public as console_public
            allowed, reason = console_public.is_ai_execution_allowed(job.workspace)
            if not allowed:
                raise BudgetExceededError(
                    f'Execução bloqueada pela política de quota: {reason}'
                )

            input_data = AnalysisService._prepare_input(run)
            if not input_data:
                raise AnalysisInputError('Falha ao preparar os dados de entrada.')

            ai_response = AnalysisService._call_ai_via_console(run, input_data)

            insights_data = AnalysisService._parse_and_validate_ai_response(
                ai_response,
                target_kinds=AnalysisService._resolve_target_kinds(run),
            )

            with transaction.atomic():
                AnalysisService._apply_ai_results(
                    run=run,
                    ai_response=ai_response,
                    insights_data=insights_data,
                    duration_ms=ai_response.get('duration_ms'),
                )

            try:
                from apps.intelligence.services.cost_allocation_service import (
                    CostAllocationService,
                )
                CostAllocationService.allocate_for_run(run, ai_response)
            except Exception:
                logger.exception(
                    'Falha ao alocar custo (run=%s). Insights persistidos.',
                    run.id,
                )

            try:
                from apps.intelligence.services.staleness_service import (
                    StalenessService,
                )
                StalenessService.mark_previous_runs_stale(run)
            except Exception:
                logger.exception(
                    'Falha ao marcar runs anteriores como stale (run=%s).',
                    run.id,
                )

            return run

        except StaleAnalysisError:
            if run is not None:
                with transaction.atomic():
                    run.status = AnalysisRun.STATUS_SKIPPED_STALE
                    run.is_stale = True
                    run.completed_at = timezone.now()
                    run.save(update_fields=[
                        'status', 'is_stale', 'completed_at', 'updated_at',
                    ])
            raise

        except Exception as exc:
            logger.exception(
                'Falha na execução da análise (Run=%s)',
                run.id if run else '<none>',
            )
            if run is not None:
                with transaction.atomic():
                    run.status = AnalysisRun.STATUS_FAILED
                    run.error_message = str(exc)
                    run.completed_at = timezone.now()
                    run.save(update_fields=[
                        'status', 'error_message', 'completed_at', 'updated_at',
                    ])
            raise

    # ------------------------------------------------------------------
    # TARGET KINDS
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_target_kinds(run: AnalysisRun) -> List[str]:
        job = run.job
        requested = job.target_kinds or []
        valid = {c[0] for c in InsightItem.KIND_CHOICES}
        filtered = [k for k in requested if k in valid]
        if filtered:
            return filtered

        if run.briefing_id:
            return list(DEFAULT_KINDS_WITH_BRIEFING)
        return list(DEFAULT_KINDS_WITHOUT_BRIEFING)

    # ------------------------------------------------------------------
    # RESOLUÇÃO DE PROVIDER/MODELO
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_provider_and_model() -> tuple:
        prompt_version = getattr(settings, 'INTELLIGENCE_PROMPT_VERSION', 'v1')

        explicit_provider = getattr(settings, 'INTELLIGENCE_PROVIDER', None)
        explicit_model = getattr(settings, 'INTELLIGENCE_MODEL', None)

        if explicit_provider and explicit_model:
            return (explicit_provider, explicit_model, prompt_version)

        try:
            from apps.console.services.ai_config_service import AIConfigService
            config = AIConfigService.get_or_create_default()
        except Exception:
            logger.warning(
                'AIProviderConfig indisponível. Usando fallback de settings.',
            )
            config = None

        if config is not None and config.is_active:
            return (
                explicit_provider or config.provider.key,
                explicit_model or config.model,
                prompt_version,
            )

        return (
            explicit_provider or 'openai',
            explicit_model or 'gpt-4o-mini',
            prompt_version,
        )

    # ------------------------------------------------------------------
    # CRIAÇÃO DO RUN
    # ------------------------------------------------------------------

    @staticmethod
    def _create_analysis_run(job: AnalysisJob) -> Optional[AnalysisRun]:
        """
        Cria um `AnalysisRun` NOVO para esta tentativa do job.

        O `input_hash` inclui `job.attempt_count` (incrementado pelo
        `JobService.claim_next_job` antes de chamar `execute`). Isso
        garante que cada tentativa cria um run distinto:

            - Tentativa 1: hash A → run 1
            - Tentativa 2: hash B → run 2
            - Tentativa 3: hash C → run 3

        Motivos:
            - O `created_at` do run é `auto_now_add=True`. Reaproveitar
              o run mantém o `created_at` ORIGINAL, o que faz o
              `StalenessService` sempre rejeitar como stale quando o
              evento `manual.reanalyze` é posterior ao run original.
            - O `request_id` (=run.id) muda a cada tentativa, então
              o `AICallService` faz uma chamada real ao provider em
              vez de devolver `raw_content=""` do `UsageRecord`
              antigo.

        Se já existe um run `COMPLETED` para ESTA tentativa (mesmo
        attempt_count), retorna `None` — idempotência real (o worker
        reivindicou o mesmo job duas vezes sem incrementar o
        attempt_count não deveria acontecer, mas é defesa em
        profundidade).

        Antes de criar o run novo, DELETA os `UsageRecord` e
        `ProviderLog` de runs anteriores do MESMO job — evita lixo no
        banco e garante que nenhum artefato antigo interfira na nova
        tentativa.
        """
        input_payload = AnalysisService._prepare_input(job)
        if not input_payload:
            raise AnalysisInputError('Falha ao preparar input para hashing.')

        provider, model, prompt_version = (
            AnalysisService._resolve_provider_and_model()
        )

        target_kinds = AnalysisService._resolve_target_kinds_from_job(job)
        payload_hash = hashlib.sha256(
            json.dumps(
                {'input': input_payload, 'kinds': sorted(target_kinds)},
                sort_keys=True, default=str,
            ).encode('utf-8')
        ).hexdigest()

        # `job.id` distingue jobs diferentes com o mesmo input.
        # `job.attempt_count` distingue tentativas do MESMO job.
        # Juntos, garantem hash único por tentativa — e, por
        # consequência, `created_at` sempre atual no run.
        composite = '|'.join([
            str(job.id),
            str(job.attempt_count),
            str(job.workspace_id),
            prompt_version,
            provider,
            model,
            payload_hash,
        ])
        input_hash = hashlib.sha256(composite.encode('utf-8')).hexdigest()

        # ------------------------------------------------------------------
        # 1. Se já existe run COMPLETED para este attempt_count → idempotente
        #
        #    Defesa em profundidade: `claim_next_job` incrementa
        #    `attempt_count` antes de chamar `execute`, então este
        #    cenário não deveria ocorrer. Mas se ocorrer, o run está
        #    completo e a IA já produziu os insights. Não roda de novo.
        # ------------------------------------------------------------------
        completed = AnalysisRun.objects.filter(
            input_hash=input_hash,
            status=AnalysisRun.STATUS_COMPLETED,
        ).first()
        if completed is not None:
            logger.info(
                'Run idêntico já concluído para este attempt (hash=%s). '
                'Ignorando.', input_hash,
            )
            return None

        # ------------------------------------------------------------------
        # 2. Limpa artefatos de runs anteriores do MESMO job.
        #
        #    Como cada tentativa cria um run novo, os `UsageRecord` e
        #    `ProviderLog` das tentativas anteriores ficam órfãos
        #    (apontando para `request_id` de runs antigos). Deletamos
        #    para manter o banco limpo e evitar que o `StalenessService`
        #    ou o `CostAllocationService` tropecem neles.
        # ------------------------------------------------------------------
        previous_runs = AnalysisRun.objects.filter(job=job)
        for prev_run in previous_runs:
            AnalysisService._cleanup_run_artifacts(prev_run)

        # ------------------------------------------------------------------
        # 3. Cria run novo
        # ------------------------------------------------------------------
        return AnalysisRun.objects.create(
            job=job,
            workspace=job.workspace,
            client=job.client,
            briefing=job.briefing,
            input_hash=input_hash,
            data_version=job.data_version,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            status=AnalysisRun.STATUS_RUNNING,
            started_at=timezone.now(),
        )

    @staticmethod
    def _cleanup_run_artifacts(run: AnalysisRun) -> None:
        """
        Remove `UsageRecord` e `ProviderLog` de um run anterior.

        Chamado antes de criar um run novo para a mesma tentativa
        de job. Não levanta — falhas de limpeza não impedem a nova
        tentativa.

        Não mexe em `InsightItem` — esses são artefatos do run
        anterior, mas o `StalenessService` marca como stale
        apropriadamente quando o run novo conclui. Deletá-los
        aqui quebraria a auditoria histórica.
        """
        try:
            from apps.console.models import UsageRecord, ProviderLog

            deleted_usage, _ = UsageRecord.objects.filter(
                provider__key=run.provider,
                request_id=str(run.id),
            ).delete()
            if deleted_usage:
                logger.info(
                    'UsageRecord antigo do run=%s deletado '
                    '(forçar chamada real).', run.id,
                )

            deleted_log, _ = ProviderLog.objects.filter(
                provider__key=run.provider,
                request_id=str(run.id),
            ).delete()
            if deleted_log:
                logger.info(
                    'ProviderLog antigo do run=%s deletado.', run.id,
                )
        except Exception:
            logger.exception(
                'Falha ao limpar artefatos do run=%s. Prosseguindo.',
                run.id,
            )

    @staticmethod
    def _resolve_target_kinds_from_job(job: AnalysisJob) -> List[str]:
        requested = job.target_kinds or []
        valid = {c[0] for c in InsightItem.KIND_CHOICES}
        filtered = [k for k in requested if k in valid]
        if filtered:
            return filtered
        if job.briefing_id:
            return list(DEFAULT_KINDS_WITH_BRIEFING)
        return list(DEFAULT_KINDS_WITHOUT_BRIEFING)

    # ------------------------------------------------------------------
    # INPUT
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_input(job_or_run) -> Optional[Dict[str, Any]]:
        from apps.briefings import public as briefings_public
        from apps.clients import public as clients_public

        client_snap = clients_public.get_client_snapshot(job_or_run.client_id)
        if not client_snap:
            raise AnalysisInputError('Cliente não encontrado.')

        payload = {'client': client_snap}

        if job_or_run.briefing_id:
            briefing_snap = briefings_public.get_briefing_snapshot(
                job_or_run.briefing_id
            )
            if not briefing_snap:
                raise AnalysisInputError('Briefing não encontrado.')
            payload['briefing'] = briefing_snap

            images = AnalysisService._collect_images(
                briefings_public, briefing_snap,
            )
            if images:
                payload['images'] = images

        return payload

    @staticmethod
    def _collect_images(briefings_public, briefing_snap: dict) -> List[Dict]:
        getter = getattr(
            briefings_public, 'get_reference_document_payloads', None,
        )
        if getter is None:
            logger.info(
                'briefings.public.get_reference_document_payloads '
                'indisponível. Análise será apenas textual.'
            )
            return []

        doc_ids = set()
        for answer in briefing_snap.get('answers', []):
            doc_ids.update(answer.get('attachments') or [])
            if answer.get('audio_document_id'):
                doc_ids.add(answer['audio_document_id'])

        for section in (briefing_snap.get('structure_snapshot') or {}).get(
            'sections', []
        ):
            for q in section.get('questions', []):
                for rid in q.get('reference_document_ids') or []:
                    doc_ids.add(rid)

        if not doc_ids:
            return []

        try:
            payloads = getter(list(doc_ids)) or []
        except Exception:
            logger.exception(
                'Falha ao obter payloads de documentos. '
                'Análise será apenas textual.'
            )
            return []

        result = []
        for p in payloads:
            if not isinstance(p, dict):
                continue
            url = p.get('url')
            mime = p.get('mime_type') or ''
            if not url or not mime.startswith('image/'):
                continue
            result.append({
                'document_id': str(p.get('id') or ''),
                'url': url,
                'mime_type': mime,
                'source': p.get('source') or 'briefing',
            })
        return result

    # ------------------------------------------------------------------
    # IA
    # ------------------------------------------------------------------

    @staticmethod
    def _call_ai_via_console(run: AnalysisRun, input_data: dict) -> dict:
        from apps.console import public as console_public

        call_ai = getattr(console_public, 'call_ai', None)
        if call_ai is None:
            raise AIProviderError(
                'A ponte console.public.call_ai não está disponível. '
                'A inteligência não pode executar IA sem passar pelo '
                'Console (governança + custo).'
            )

        system_prompt = get_prompt()

        target_kinds = AnalysisService._resolve_target_kinds(run)
        kinds_list = '\n'.join(f'  - "{k}"' for k in target_kinds)

        user_message = (
            "Analise os dados abaixo e produza insights no formato JSON.\n\n"
            "============================================================================\n"
            "KINDS A PRODUZIR NESTA EXECUÇÃO (use SOMENTE estes):\n"
            "============================================================================\n"
            f"{kinds_list}\n\n"
            "Se a análise não tiver evidência suficiente para um kind\n"
            "que exige evidência, NÃO invente — produza apenas os kinds\n"
            "que conseguir sustentar.\n\n"
            "============================================================================\n"
            "DADOS:\n"
            "============================================================================\n"
            f"{json.dumps(input_data, ensure_ascii=False, indent=2, default=str)}"
        )

        started = time.time()
        try:
            response = call_ai(
                workspace=run.workspace,
                operation='intelligence.analysis',
                provider_key=run.provider,
                model=run.model,
                prompt_version=run.prompt_version,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ],
                images=input_data.get('images') or [],
                response_format='json_object',
                request_id=str(run.id),
            )
        except Exception as exc:
            duration_ms = int((time.time() - started) * 1000)
            logger.exception(
                'Falha na ponte call_ai (run=%s, duration=%sms)',
                run.id, duration_ms,
            )
            raise AIProviderError(f'Falha na chamada da IA: {exc}') from exc

        duration_ms = int((time.time() - started) * 1000)

        return {
            'raw_content': response.get('raw_content', ''),
            'input_tokens': int(response.get('input_tokens') or 0),
            'output_tokens': int(response.get('output_tokens') or 0),
            'duration_ms': response.get('duration_ms', duration_ms),
            'usage_record_id': response.get('usage_record_id'),
            'provider_request_id': response.get('provider_request_id') or '',
        }

    # ------------------------------------------------------------------
    # VALIDAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_and_validate_ai_response(
        ai_response: dict,
        target_kinds: Optional[List[str]] = None,
    ) -> List[Dict]:
        raw = ai_response.get('raw_content') or ''

        if not raw.strip():
            logger.error(
                'Resposta da IA veio VAZIA. Isso geralmente significa '
                'que o `AICallService` devolveu `raw_content=""` '
                'porque o `UsageRecord` já existia (idempotência) e '
                'o `metadata["raw_content"]` não foi persistido. '
                'Solução: deletar o UsageRecord antigo com '
                '`request_id=<run.id>` e tentar de novo.'
            )
            raise AIResponseError(
                'Resposta da IA veio vazia. O `UsageRecord` antigo '
                'pode ter sido reaproveitado sem `raw_content`. '
                'Delete o `UsageRecord` do run e tente novamente.'
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(
                'Resposta da IA não é JSON. raw_content=%r '
                '(primeiros 500 chars)',
                raw[:500],
            )
            raise AIResponseError(f'Resposta da IA não é JSON válido: {exc}')

        if not isinstance(data, dict) or 'insights' not in data:
            logger.error(
                'Resposta da IA não tem chave "insights". '
                'chaves=%r, raw=%r',
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                raw[:500],
            )
            raise AIResponseError("Resposta da IA não contém a chave 'insights'.")

        insights = data['insights']
        if not isinstance(insights, list):
            raise AIResponseError("'insights' deve ser uma lista.")

        valid_kinds = {c[0] for c in InsightItem.KIND_CHOICES}
        valid_confidences = {c[0] for c in InsightItem.CONFIDENCE_CHOICES}
        allowed = set(target_kinds) if target_kinds else valid_kinds

        validated = []
        for i, item in enumerate(insights):
            if not isinstance(item, dict):
                logger.error(
                    'Insight #%d não é dict. Recebido: %r', i, item,
                )
                raise AIResponseError(f'Insight #{i} não é um objeto.')

            kind = item.get('kind')
            content = (item.get('content') or '').strip()
            confidence = item.get(
                'confidence', InsightItem.CONFIDENCE_INTERPRETATION,
            )

            if kind not in valid_kinds:
                logger.error(
                    'Insight #%d: kind inválido. '
                    'Recebido=%r. Item completo=%r',
                    i, kind, item,
                )
                raise AIResponseError(f'Insight #{i}: kind inválido ({kind}).')

            if kind not in allowed:
                logger.error(
                    'Insight #%d: kind "%s" fora do target_kinds. '
                    'Permitidos=%r',
                    i, kind, sorted(allowed),
                )
                raise AIResponseError(
                    f'Insight #{i}: kind "{kind}" não solicitado nesta '
                    f'execução (target_kinds).'
                )

            if not content:
                raise AIResponseError(f'Insight #{i}: content vazio.')
            if confidence not in valid_confidences:
                logger.error(
                    'Insight #%d: confidence inválida. '
                    'Recebido=%r, permitidos=%r',
                    i, confidence, sorted(valid_confidences),
                )
                raise AIResponseError(
                    f'Insight #{i}: confidence inválida ({confidence}).'
                )

            evidences = item.get('evidences') or []
            if not isinstance(evidences, list):
                raise AIResponseError(f'Insight #{i}: evidences deve ser lista.')

            if kind in KINDS_REQUIRING_EVIDENCE and not evidences:
                logger.error(
                    'Insight #%d (%s): exige evidência, recebeu [].',
                    i, kind,
                )
                raise AIResponseError(
                    f'Insight #{i} ({kind}): evidência obrigatória ausente.'
                )

            validated.append({
                'kind': kind,
                'content': content,
                'confidence': confidence,
                'metadata': item.get('metadata') or {},
                'evidences': evidences,
            })

        return validated

    # ------------------------------------------------------------------
    # PERSISTÊNCIA
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_ai_results(run, ai_response, insights_data, duration_ms):
        latest_event = (
            InsightEvent.objects
            .filter(
                workspace=run.workspace,
                client=run.client,
                briefing=run.briefing,
            )
            .order_by('-created_at')
            .first()
        )
        if latest_event and latest_event.created_at > run.created_at:
            raise StaleAnalysisError(
                'Existe um evento mais recente que o run. Não publicar.'
            )

        run.input_tokens = ai_response.get('input_tokens') or 0
        run.output_tokens = ai_response.get('output_tokens') or 0
        run.duration_ms = duration_ms
        run.status = AnalysisRun.STATUS_COMPLETED
        run.completed_at = timezone.now()
        run.save()

        for item in insights_data:
            insight = InsightItem.objects.create(
                run=run,
                workspace=run.workspace,
                client=run.client,
                briefing=run.briefing,
                kind=item['kind'],
                content=item['content'],
                confidence=item['confidence'],
                metadata=item['metadata'],
            )
            AnalysisService._persist_evidences(
                insight=insight,
                raw_evidences=item.get('evidences') or [],
                workspace=run.workspace,
            )

    @staticmethod
    def _persist_evidences(insight, raw_evidences, workspace):
        from apps.briefings import public as briefings_public
        from apps.clients import public as clients_public

        for ev in raw_evidences:
            if not isinstance(ev, dict):
                continue
            source_type = ev.get('source_type')
            source_ref = (ev.get('source_ref') or '').strip()
            quote = (ev.get('quote') or '').strip()

            if source_type not in dict(InsightEvidence.SOURCE_TYPE_CHOICES):
                logger.warning(
                    'Evidência com source_type inválido ignorada: %s',
                    source_type,
                )
                continue
            if not source_ref:
                logger.warning('Evidência sem source_ref ignorada.')
                continue

            valid = False
            if source_type == InsightEvidence.SOURCE_TYPE_BRIEFING_ANSWER:
                snap = (
                    briefings_public.get_briefing_snapshot(insight.briefing_id)
                    if insight.briefing_id else None
                )
                if snap and any(
                    a['id'] == source_ref for a in snap['answers']
                ):
                    valid = True
            elif source_type == InsightEvidence.SOURCE_TYPE_BRIEFING_NOTE:
                snap = (
                    briefings_public.get_briefing_snapshot(insight.briefing_id)
                    if insight.briefing_id else None
                )
                if snap and any(
                    n['id'] == source_ref for n in snap['notes']
                ):
                    valid = True
            elif source_type == InsightEvidence.SOURCE_TYPE_CLIENT_CONTEXT:
                snap = clients_public.get_client_snapshot(insight.client_id)
                if snap:
                    valid = True

            if not valid:
                logger.warning(
                    'Evidência ignorada (fonte inexistente ou de outro '
                    'workspace): %s:%s',
                    source_type, source_ref,
                )
                continue

            InsightEvidence.objects.get_or_create(
                insight=insight,
                source_type=source_type,
                source_ref=source_ref,
                defaults={'quote': quote},
            )