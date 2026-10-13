from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ReferencesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.references'
    verbose_name = _('Referências')

    def ready(self):
        """
        Inicializa o módulo references.

        Signals não são registrados por padrão. O módulo `references`
        emite eventos de domínio quando os services existirem
        (fase seguinte). No P0, é apenas CRUD + histórico local.
        """
        # import apps.references.signals  # noqa: F401
        pass