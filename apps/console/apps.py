from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConsoleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.console'
    verbose_name = _('Console')

    def ready(self):
        """Inicializa o módulo console."""
        # Importa signals se houver
        # import apps.console.signals  # noqa: F401
        pass