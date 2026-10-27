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

`AnalysisService` é responsável por:
    - preparar input (via contratos públicos),
    - validar a saída da IA,
    - persistir insights, evidências e histórico,
    - alocar custo aos insights produzidos,
    - marcar insights anteriores como stale.

ANÁLISE PARCIAL
---------------
`AnalysisJob.target_kinds` define quais kinds devem ser produzidos.
Quando vazio, produz o conjunto completo padrão. Quando preenchido,
o prompt é instruído a produzir APENAS esses kinds, e a validação
rejeita kinds fora da lista.

MULTIMODAL
----------
Se `briefings.public.get_reference_document_payloads()` devolver
imagens acessíveis, o payload inclui entradas `images` que a ponte
`console.public.call_ai` encaminha ao provider. Se a interface não
estiver disponível, o input degrada para texto sem inventar imagens.
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


# Kinds que EXIGEM evidência para serem publicados.
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


# Conjunto padrão de kinds por escopo de job (quando target_kinds vazio).
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
        """
        Executa o fluxo completo.

        A chamada à IA acontece FORA de qualquer transação — não
        bloqueia o banco durante a latência do provider.
        """
        with transaction.atomic():
            run = AnalysisService._create_analysis_run(job)
            if run is None:
                return None

        try:
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

            # Alocação de custo e staleness — fora da transação principal
            # para não bloquear o commit dos insights.
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
            with transaction.atomic():
                run.status = AnalysisRun.STATUS_SKIPPED_STALE
                run.is_stale = True
                run.completed_at = timezone.now()
                run.save(update_fields=[
                    'status', 'is_stale', 'completed_at', 'updated_at',
                ])
            raise

        except Exception as exc:
            logger.exception('Falha na execução da análise (Run=%s)', run.id)
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
        """
        Resolve quais kinds este run deve produzir.

        Prioridade:
            1. `job.target_kinds` (definido pelo agendador, ex.: análise
               parcial de um container específico).
            2. Default por escopo (com ou sem briefing).
        """
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
    # CRIAÇÃO DO RUN
    # ------------------------------------------------------------------

    @staticmethod
    def _create_analysis_run(job: AnalysisJob) -> Optional[AnalysisRun]:
        """
        Cria o run aplicando idempotência por `input_hash`.

        O `input_hash` inclui workspace + prompt + provider + model +
        payload + target_kinds. Isso diferencia análises parciais
        (kinds distintos) de re-execuções completas.
        """
        input_payload = AnalysisService._prepare_input(job)
        if not input_payload:
            raise AnalysisInputError('Falha ao preparar input para hashing.')

        model = getattr(settings, 'INTELLIGENCE_MODEL', 'gpt-4o-mini')
        prompt_version = getattr(settings, 'INTELLIGENCE_PROMPT_VERSION', 'v1')
        provider = getattr(settings, 'INTELLIGENCE_PROVIDER', 'openai')

        target_kinds = AnalysisService._resolve_target_kinds_from_job(job)
        payload_hash = hashlib.sha256(
            json.dumps(
                {'input': input_payload, 'kinds': sorted(target_kinds)},
                sort_keys=True, default=str,
            ).encode('utf-8')
        ).hexdigest()

        composite = '|'.join([
            str(job.workspace_id),
            prompt_version,
            provider,
            model,
            payload_hash,
        ])
        input_hash = hashlib.sha256(composite.encode('utf-8')).hexdigest()

        existing = AnalysisRun.objects.filter(
            input_hash=input_hash,
            status=AnalysisRun.STATUS_COMPLETED,
        ).first()
        if existing:
            logger.info(
                'Run idêntico já concluído (hash=%s). Ignorando.', input_hash,
            )
            return None

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
    # INPUT (via contratos públicos)
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_input(job_or_run) -> Optional[Dict[str, Any]]:
        """
        Monta o payload a partir dos contratos públicos.
        Nenhum import direto de models de `briefings`/`clients`.
        """
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

            # Multimodal: tenta obter imagens via contrato público.
            # Se a interface não existir ou devolver vazio, o input
            # degrada para texto SEM inventar imagens.
            images = AnalysisService._collect_images(
                briefings_public, briefing_snap,
            )
            if images:
                payload['images'] = images

        return payload

    @staticmethod
    def _collect_images(briefings_public, briefing_snap: dict) -> List[Dict]:
        """
        Coleta imagens acessíveis do briefing via contrato público.

        Regra: se `get_reference_document_payloads` não existir ou
        devolver payloads sem URL acessível, retorna lista vazia.
        NUNCA inventa descrição de imagem a partir do ID.
        """
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
    # IA — via ponte do console
    # ------------------------------------------------------------------

    @staticmethod
    def _call_ai_via_console(run: AnalysisRun, input_data: dict) -> dict:
        """
        Chama a ponte `console.public.call_ai`, que executa o provider
        real e registra uso/custo. Devolve payload normalizado.
        """
        from apps.console import public as console_public

        call_ai = getattr(console_public, 'call_ai', None)
        if call_ai is None:
            raise AIProviderError(
                'A ponte console.public.call_ai não está disponível. '
                'A inteligência não pode executar IA sem passar pelo '
                'Console (governança + custo).'
            )

        system_prompt = get_prompt()
        user_message = (
            "Analise os dados abaixo e produza insights no formato JSON:\n\n"
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
        """
        Valida o JSON. Exige 'insights' (lista) com 'kind' válido,
        'content' não vazio e 'confidence' válida.

        Se `target_kinds` for fornecido, rejeita kinds fora da lista
        (análise parcial não pode produzir o que não foi pedido).

        Rejeita `evidences=[]` para kinds que exigem evidência.
        """
        raw = ai_response.get('raw_content') or ''
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIResponseError(f'Resposta da IA não é JSON válido: {exc}')

        if not isinstance(data, dict) or 'insights' not in data:
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
                raise AIResponseError(f'Insight #{i} não é um objeto.')
            kind = item.get('kind')
            content = (item.get('content') or '').strip()
            confidence = item.get(
                'confidence', InsightItem.CONFIDENCE_INTERPRETATION,
            )

            if kind not in valid_kinds:
                raise AIResponseError(f'Insight #{i}: kind inválido ({kind}).')
            if kind not in allowed:
                raise AIResponseError(
                    f'Insight #{i}: kind "{kind}" não solicitado nesta '
                    f'execução (target_kinds).'
                )
            if not content:
                raise AIResponseError(f'Insight #{i}: content vazio.')
            if confidence not in valid_confidences:
                raise AIResponseError(
                    f'Insight #{i}: confidence inválida ({confidence}).'
                )

            evidences = item.get('evidences') or []
            if not isinstance(evidences, list):
                raise AIResponseError(f'Insight #{i}: evidences deve ser lista.')

            if kind in KINDS_REQUIRING_EVIDENCE and not evidences:
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
        """
        Persiste os insights e evidências, e atualiza as métricas do run.
        Detecta stale comparando a data de criação do run com o
        `created_at` do último `InsightEvent` do alvo.
        """
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
        """
        Persiste as evidências, validando que cada fonte pertence ao
        mesmo workspace do insight. Fontes inválidas são descartadas
        com log, nunca silenciosamente aceitas.
        """
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