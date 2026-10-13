"""
Comando de limpeza de imagens órfãs de referências.

USO
---
    # Dry-run (padrão) — apenas reporta
    python manage.py cleanup_reference_orphans

    # Apagar de verdade
    python manage.py cleanup_reference_orphans --confirm

    # Filtrar report por workspace (a checagem de vivos é sempre
    # contra TODOS os workspaces; o filtro é só cosmético no output)
    python manage.py cleanup_reference_orphans --workspace=<uuid>

OPERAÇÃO
--------
A varredura é O(n) no storage. Não chame em requests. Rode via
cron / Celery beat. Sugestão: uma vez por dia, fora do horário
de pico.

Em caso de falha de rede no storage, o comando retorna código de
saída != 0 e imprime os erros. Configure o cron para capturar
esse código (por exemplo, com `|| echo "FALHA"` ou envio de e-mail).

SEGURANÇA
---------
A função `find_orphan_images` NUNCA retorna arquivos referenciados
por qualquer `Reference.image`, de qualquer workspace. Só devolve
o que não está em nenhum registro. Portanto, apagar o resultado
é seguro por construção.
"""

import sys

from django.core.management.base import BaseCommand, CommandError

from apps.references.services.orphan_cleanup import (
    find_orphan_images,
    delete_orphan_images,
)
from apps.workspaces.models import Workspace


class Command(BaseCommand):
    help = 'Detecta e remove imagens órfãs de referências.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace',
            type=str,
            default=None,
            help='UUID do workspace (apenas para rotular o report).',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Sem isso, apenas reporta (dry-run).',
        )
        parser.add_argument(
            '--max-print',
            type=int,
            default=50,
            help='Máximo de nomes a imprimir (default: 50).',
        )

    def handle(self, *args, **opts):
        workspace = None
        if opts['workspace']:
            workspace = Workspace.objects.filter(pk=opts['workspace']).first()
            if workspace is None:
                raise CommandError('Workspace não encontrado.')

        scope = f'workspace={workspace.pk}' if workspace else 'global'

        try:
            orphans = find_orphan_images(workspace=workspace)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f'[{scope}] Falha ao varrer o storage: {exc}'
            ))
            sys.exit(1)

        self.stdout.write(f'[{scope}] Órfãos encontrados: {len(orphans)}')

        max_print = max(0, int(opts['max_print']))
        for name in orphans[:max_print]:
            self.stdout.write(f'  - {name}')
        if len(orphans) > max_print:
            self.stdout.write(f'  ... (+{len(orphans) - max_print})')

        if not opts['confirm']:
            self.stdout.write(self.style.WARNING(
                'Dry-run. Nada foi apagado. Use --confirm para apagar.'
            ))
            return

        if not orphans:
            self.stdout.write(self.style.SUCCESS('Nada a apagar.'))
            return

        report = delete_orphan_images(orphans)
        self.stdout.write(self.style.SUCCESS(
            f"deleted={report['deleted']} failed={report['failed']}"
        ))

        if report['failed'] > 0:
            self.stderr.write(self.style.ERROR(
                f"{report['failed']} arquivo(s) não puderam ser removidos. "
                f"Veja o log para detalhes."
            ))
            sys.exit(1)