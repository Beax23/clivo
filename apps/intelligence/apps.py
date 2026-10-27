from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IntelligenceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.intelligence'
    verbose_name = _('Inteligência')

    def ready(self):
        """
        Inicializa o módulo intelligence.

        Signals não são registrados por padrão. A ingestão de eventos
        é explícita, via `IngestService.ingest_change_event(...)`.
        Conectar `briefings` e `clients` a este serviço é
        responsabilidade dos módulos de origem.
        """
        pass