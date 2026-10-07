"""
Emissor de eventos de domínio do módulo clients.

REGRA ARQUITETURAL
------------------
O domínio de origem SABE quais eventos produz.
A timeline transversal SABE como os persiste.

Este emitter:

    - publica um Signal Django (`client_event`)
    - NÃO persiste timeline local
    - NÃO conhece a implementação da timeline transversal

Consumidores futuros (timeline, notificações, intelligence) se
conectam a `apps.clients.events.client_event`.

Eventos representam fatos ocorridos, não estado calculado.

    CORRETO:   client.created
    INCORRETO: client.is_healthy

    CORRETO:   portal.opened
    INCORRETO: client.needs_attention
"""

from django.dispatch import Signal
from django.utils import timezone


# Signal genérico do módulo
client_event = Signal()


class ClientEventEmitter:
    """
    Ponto único de emissão de eventos do domínio clients.

    Cada método corresponde a um fato relevante do domínio.
    """

    # ------------------------------------------------------------------
    # CLIENT
    # ------------------------------------------------------------------

    @staticmethod
    def client_created(client, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='client.created',
            payload={'public_code': client.public_code},
            request=request,
        )

    @staticmethod
    def client_updated(client, changes: dict, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='client.updated',
            payload={'changes': list(changes.keys())},
            request=request,
        )

    @staticmethod
    def client_deleted(client_id, client_name, actor=None, request=None):
        client_event.send(
            sender=ClientEventEmitter,
            signal_name='client.deleted',
            client_id=str(client_id),
            client_name=client_name,
            actor_email=actor.email if actor else '',
            occurred_at=timezone.now(),
        )

    # ------------------------------------------------------------------
    # NOTE
    # ------------------------------------------------------------------

    @staticmethod
    def note_created(client, note, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='note.created',
            payload={'note_id': str(note.id)},
            request=request,
        )

    @staticmethod
    def note_updated(client, note, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='note.updated',
            payload={'note_id': str(note.id)},
            request=request,
        )

    @staticmethod
    def note_deleted(client, note_id, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='note.deleted',
            payload={'note_id': str(note_id)},
            request=request,
        )

    # ------------------------------------------------------------------
    # PORTAL
    # ------------------------------------------------------------------

    @staticmethod
    def portal_invitation_sent(client, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='portal.invitation_sent',
            payload={'note': 'Acesso ao Portal enviado por email'},
            request=request,
        )

    @staticmethod
    def portal_opened(client, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='portal.opened',
            payload={},
            request=request,
        )

    @staticmethod
    def portal_context_confirmed(client, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='portal.context_confirmed',
            payload={},
            request=request,
        )

    @staticmethod
    def portal_context_edited(client, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='portal.context_edited',
            payload={},
            request=request,
        )

    @staticmethod
    def portal_feedback_received(client, feedback, actor=None, request=None):
        ClientEventEmitter._emit(
            client=client,
            actor=actor,
            signal_name='portal.feedback_received',
            payload={
                'note': f'Feedback recebido ({feedback.kind})',
                'feedback_id': str(feedback.id),
            },
            request=request,
        )

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    @staticmethod
    def _emit(client, actor, signal_name: str, payload: dict, request=None):
        """
        Publica o evento via Signal Django.

        NÃO persiste nada localmente. A timeline transversal é
        responsável por consumir e armazenar.
        """
        client_event.send(
            sender=ClientEventEmitter,
            signal_name=signal_name,
            client_id=str(client.id),
            client_name=client.name,
            actor_email=actor.email if actor and actor.is_authenticated else '',
            occurred_at=timezone.now(),
            **payload,
        )