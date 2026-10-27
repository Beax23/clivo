from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BriefingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.briefings'
    verbose_name = _('Briefings')

    def ready(self):
        """
        Registra os signals do módulo.

        SEM este import, os receivers `post_save(BriefingEvent)` e
        `pre_delete(Briefing)` NUNCA são conectados, e a ponte
        `briefings → intelligence` fica inativa em runtime — os
        eventos são criados, mas nunca chegam ao `IngestService`.
        """
        import apps.briefings.signals  # noqa: F401