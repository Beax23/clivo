"""
Signals do módulo clients.

V1: nenhum signal ativo por padrão.
O módulo emite eventos via `ClientEventEmitter` (django.dispatch.Signal).
Consumidores futuros (Intelligence, Notifications, JARVIS) podem se
conectar a `apps.clients.events.client_event`.
"""

# Exemplo de conexão futura (comentado):
#
# from apps.clients.events import client_event
# from django.dispatch import receiver
#
# @receiver(client_event)
# def on_client_event(sender, signal_name, client_id, **kwargs):
#     ...