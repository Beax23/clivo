"""
Contrato público do módulo `briefings` para consumidores externos.

REGRA
-----
Nenhum consumidor externo (ex.: `intelligence`) deve importar models
de `briefings` diretamente. Toda leitura passa por funções deste
módulo, que devolvem estruturas serializáveis (dicts), sem expor
detalhes internos.

MULTIMODAL
----------
`get_reference_document_payloads` resolve IDs de `documents` para
payloads com URL acessível, filtrando por workspace. O módulo
`briefings` NÃO acessa o storage diretamente — usa `Document.file.url`,
que é o contrato que o app `documents` já oferece. Se a URL não
puder ser resolvida, o documento é omitido — NUNCA inventamos
descrição de imagem a partir de ID.

ESCOPO E PERMISSÃO
------------------
Toda função que retorna dados recebe `workspace` explicitamente.
Documentos e briefings de outro workspace são descartados. Não
vaza ID nem URL cross-tenant.
"""

from typing import Optional, Dict, List, Any

from apps.briefings.models import Briefing, BriefingAnswer, BriefingNote


# =========================================================================
# SNAPSHOT
# =========================================================================

def get_briefing_snapshot(briefing_id) -> Optional[Dict[str, Any]]:
    """
    Devolve um snapshot serializável do briefing, com estrutura,
    respostas e notas. Apenas dados brutos; nenhuma interpretação.
    """
    try:
        briefing = (
            Briefing.objects
            .select_related('client', 'workspace')
            .filter(id=briefing_id)
            .first()
        )
    except (ValueError, TypeError):
        return None
    if briefing is None:
        return None

    answers = list(
        BriefingAnswer.objects
        .filter(briefing=briefing)
        .select_related('latest_audio')
        .order_by('created_at')
    )
    notes = list(
        BriefingNote.objects
        .filter(briefing=briefing)
        .select_related('author')
        .order_by('created_at')
    )

    return {
        'id': str(briefing.id),
        'workspace_id': str(briefing.workspace_id),
        'client_id': str(briefing.client_id),
        'title': briefing.title,
        'status': briefing.status,
        'intro_message': briefing.intro_message or '',
        'structure_snapshot': briefing.structure_snapshot or {},
        'answers': [
            {
                'id': str(a.id),
                'question_id': str(a.question_id),
                'state': a.state,
                'content': a.latest_content or '',
                'transcription': a.latest_transcription or '',
                'audio_document_id': (
                    str(a.latest_audio_id) if a.latest_audio_id else None
                ),
                'attachments': [str(d.id) for d in a.attachments.all()],
                'updated_at': a.updated_at.isoformat(),
            }
            for a in answers
        ],
        'notes': [
            {
                'id': str(n.id),
                'question_id': str(n.question_id) if n.question_id else None,
                'author_email': n.author.email if n.author else None,
                'content': n.content,
                'updated_at': n.updated_at.isoformat(),
            }
            for n in notes
        ],
    }


def get_question_text(briefing_id, question_id) -> Optional[str]:
    """
    Resolve o enunciado de uma pergunta a partir do snapshot do briefing.
    """
    try:
        briefing = Briefing.objects.filter(
            id=briefing_id,
        ).only('structure_snapshot').first()
    except (ValueError, TypeError):
        return None
    if briefing is None:
        return None
    for section in (briefing.structure_snapshot or {}).get('sections', []):
        for q in section.get('questions', []):
            if str(q.get('id')) == str(question_id):
                return q.get('text')
    return None


def get_events_for_briefing(briefing_id, limit: int = 500) -> List[Dict]:
    """
    Devolve os eventos do histórico do briefing em formato serializável.
    Mantido por compatibilidade — `get_recent_events` é preferível para
    chamadores novos (filtro por workspace).
    """
    from apps.briefings.models import BriefingEvent
    try:
        qs = (
            BriefingEvent.objects
            .filter(briefing_id=briefing_id)
            .order_by('-created_at')[:limit]
        )
    except (ValueError, TypeError):
        return []
    return [
        {
            'id': str(e.id),
            'kind': e.kind,
            'question_id': str(e.question_id) if e.question_id else None,
            'content': e.content or {},
            'created_at': e.created_at.isoformat(),
        }
        for e in qs
    ]


# =========================================================================
# MULTIMODAL — documentos resolvidos para URLs acessíveis
# =========================================================================

def get_reference_document_payloads(
    document_ids: List[str],
    workspace,
) -> List[Dict[str, Any]]:
    """
    Resolve uma lista de IDs de `documents.Document` para payloads
    com URL acessível, filtrando por workspace.

    Retorna lista de:
        {
            'id': str,
            'name': str,
            'mime_type': str,
            'url': str,           # já resolvida via Document.file.url
            'source': 'briefing', # rótulo para auditoria
        }

    Regras:
        - IDs vazios ou inválidos são ignorados sem erro.
        - Documentos de outro workspace são DESCARTADOS.
        - Documentos sem `file` ou cuja URL não puder ser resolvida
          são DESCARTADOS (não inventamos URL nem descrição).
        - Nunca levanta para IDs individuais inválidos. Só levanta
          se o app `documents` estiver indisponível (ImportError),
          e nesse caso o chamador deve tratar.
    """
    if not document_ids:
        return []

    if workspace is None:
        return []

    # Import local — mantém a fronteira de importação explícita.
    # `briefings` não importa models de `documents` em tempo de módulo.
    from apps.documents.models import Document

    # Normaliza IDs para strings, descarta vazios.
    clean_ids = []
    for raw in document_ids:
        if not raw:
            continue
        s = str(raw).strip()
        if s:
            clean_ids.append(s)

    if not clean_ids:
        return []

    try:
        docs = (
            Document.objects
            .filter(
                id__in=clean_ids,
                workspace=workspace,
            )
            .only('id', 'name', 'mime_type', 'file')
        )
    except Exception:
        # ID malformado (UUID inválido) — não deveria chegar aqui
        # com `clean_ids` validado, mas protegemos.
        return []

    result: List[Dict[str, Any]] = []
    for doc in docs:
        if not doc.file:
            continue
        try:
            url = doc.file.url
        except Exception:
            # URL não resolvível — descarta o documento silenciosamente.
            continue
        if not url:
            continue
        result.append({
            'id': str(doc.id),
            'name': doc.name or '',
            'mime_type': doc.mime_type or '',
            'url': url,
            'source': 'briefing',
        })
    return result


# =========================================================================
# CONSULTAS AUXILIARES
# =========================================================================

def get_recent_events(
    briefing_id,
    workspace,
    limit: int = 200,
) -> List[Dict]:
    """
    Eventos recentes do briefing, filtrados por workspace.

    Diferente de `get_events_for_briefing` (que só filtra por ID),
    esta função valida que o briefing pertence ao workspace. É a
    versão recomendada para consumidores externos.
    """
    from apps.briefings.models import BriefingEvent

    if workspace is None:
        return []

    try:
        exists = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).exists()
    except (ValueError, TypeError):
        return []
    if not exists:
        return []

    qs = (
        BriefingEvent.objects
        .filter(briefing_id=briefing_id)
        .order_by('-created_at')[:limit]
    )
    return [
        {
            'id': str(e.id),
            'kind': e.kind,
            'question_id': str(e.question_id) if e.question_id else None,
            'content': e.content or {},
            'created_at': e.created_at.isoformat(),
        }
        for e in qs
    ]


def get_briefing_ids_for_client(client_id, workspace_id) -> List[str]:
    """
    Lista IDs de briefings do cliente no workspace.

    Usado pelo `intelligence` para reconciliar conhecimento
    acumulado (saber se o briefing de origem ainda existe).
    """
    try:
        qs = (
            Briefing.objects
            .filter(client_id=client_id, workspace_id=workspace_id)
            .values_list('id', flat=True)
        )
    except (ValueError, TypeError):
        return []
    return [str(bid) for bid in qs]