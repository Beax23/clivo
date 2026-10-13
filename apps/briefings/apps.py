from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BriefingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.briefings'
    verbose_name = _('Briefings')

    def ready(self):
        """
        Inicializa o módulo briefings.

        Signals não são registrados por padrão. O módulo emite eventos
        internamente via services. Integrações com `timeline` ou
        `intelligence` serão conectadas quando esses módulos existirem.
        """
        # import apps.briefings.signals  # noqa: F401
        pass