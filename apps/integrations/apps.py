from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IntegrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.integrations'
    verbose_name = _('Integrações')

    def ready(self):
        """
        Registra os connectors de provider no ProviderRegistry.

        Idempotente. NÃO faz I/O externo.
        NÃO inicializa conexões. NÃO chama APIs.
        """
        # Import local — evita I/O em import time.
        from apps.integrations.providers.google.connector import GoogleConnector
        from apps.integrations.providers.registry import ProviderRegistry

        ProviderRegistry.register(GoogleConnector(), override=False)