from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkspacesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.workspaces'
    verbose_name = _('Workspaces')

    def ready(self):
        # Registra signals (aceite automático de convites no login)
        import apps.workspaces.signals  # noqa: F401