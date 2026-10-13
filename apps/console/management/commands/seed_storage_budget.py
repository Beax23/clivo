"""
Seed do orçamento operacional de armazenamento.

Uso:
    python manage.py seed_storage_budget
    python manage.py seed_storage_budget --total 100GB
    python manage.py seed_storage_budget --reserve 30 --policy controlled

IDEMPOTENTE:
    - Se o orçamento NÃO existe, cria com os valores passados
      (default: 50 GiB, 20%, strict).
    - Se o orçamento JÁ existe, NÃO sobrescreve.
    - Use `--force` para sobrescrever explicitamente.

O seed grava a criação no histórico como um `StorageBudgetChange`
com `changed_by=None` e `reason="Criação inicial via seed"`.

Por que não criar via migration?
    Orçamento é decisão comercial/operacional. Criar via migration
    significaria que toda instalação (dev, staging, prod) teria o
    mesmo valor silenciosamente. Melhor forçar o operador a decidir
    explicitamente quando rodar o comando.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.console.models import StorageBudget, StorageBudgetChange


DEFAULT_TOTAL_GIB = 50
DEFAULT_RESERVE = 20
DEFAULT_POLICY = StorageBudget.POLICY_STRICT

GIB = 1024 ** 3


def _parse_size(raw: str) -> int:
    """
    Aceita formatos como:
        50GB
        50 GiB
        53687091200
        50gib
        1.5GB
    """
    if raw is None:
        raise ValueError('Tamanho vazio.')

    s = str(raw).strip().lower().replace(' ', '')

    suffixes = [
        ('gib', GIB),
        ('gb', GIB),   # tratamos GB e GiB como equivalentes aqui
        ('mib', 1024 ** 2),
        ('mb', 1024 ** 2),
        ('kib', 1024),
        ('kb', 1024),
        ('b', 1),
    ]

    for suffix, factor in suffixes:
        if s.endswith(suffix):
            number_part = s[:-len(suffix)]
            if not number_part:
                raise ValueError(f'Tamanho inválido: {raw}')
            return int(float(number_part) * factor)

    # Sem sufixo: assume bytes.
    return int(float(s))


class Command(BaseCommand):
    help = 'Cria o orçamento operacional de armazenamento (idempotente).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--total',
            type=str,
            default=f'{DEFAULT_TOTAL_GIB}GiB',
            help=(
                f'Tamanho total do orçamento. Aceita formatos como '
                f'"50GiB", "100GB", "53687091200". '
                f'Default: {DEFAULT_TOTAL_GIB}GiB.'
            ),
        )
        parser.add_argument(
            '--reserve',
            type=int,
            default=DEFAULT_RESERVE,
            help=(
                f'Percentual de reserva (0-100). '
                f'Default: {DEFAULT_RESERVE}.'
            ),
        )
        parser.add_argument(
            '--policy',
            choices=[StorageBudget.POLICY_STRICT, StorageBudget.POLICY_CONTROLLED],
            default=DEFAULT_POLICY,
            help=f'Política de alocação. Default: {DEFAULT_POLICY}.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help=(
                'Sobrescreve o orçamento existente. Sem esta flag, se '
                'já existir, o comando NÃO altera nada.'
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('💾 Seed do orçamento de armazenamento...')

        existing = StorageBudget.objects.first()

        if existing is not None and not options['force']:
            self.stdout.write(self.style.WARNING(
                '   ⚠️  Orçamento já existe. Nada foi alterado.'
            ))
            self.stdout.write(
                f'   total={existing.total_budget_bytes} B, '
                f'reserve={existing.reserve_percent}%, '
                f'policy={existing.allocation_policy}'
            )
            self.stdout.write(
                '   Use --force para sobrescrever.'
            )
            return

        try:
            total_bytes = _parse_size(options['total'])
        except (ValueError, TypeError) as e:
            raise CommandError(f'Tamanho inválido: {e}')

        reserve = options['reserve']
        policy = options['policy']

        if total_bytes < 0:
            raise CommandError('O total não pode ser negativo.')
        if not (0 <= reserve <= 100):
            raise CommandError('A reserva deve estar entre 0 e 100.')

        if existing is None:
            budget = StorageBudget.objects.create(
                singleton_key=StorageBudget.SINGLETON_KEY,
                total_budget_bytes=total_bytes,
                reserve_percent=reserve,
                allocation_policy=policy,
            )
            StorageBudgetChange.objects.create(
                budget=budget,
                previous_total_bytes=0,
                new_total_bytes=total_bytes,
                previous_reserve_percent=0,
                new_reserve_percent=reserve,
                previous_allocation_policy=policy,
                new_allocation_policy=policy,
                reason='Criação inicial via seed',
                changed_by=None,
            )
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Orçamento criado: '
                f'total={total_bytes} B, '
                f'reserve={reserve}%, '
                f'policy={policy}'
            ))
        else:
            previous_total = existing.total_budget_bytes
            previous_reserve = existing.reserve_percent
            previous_policy = existing.allocation_policy

            existing.total_budget_bytes = total_bytes
            existing.reserve_percent = reserve
            existing.allocation_policy = policy
            existing.save()

            StorageBudgetChange.objects.create(
                budget=existing,
                previous_total_bytes=previous_total,
                new_total_bytes=total_bytes,
                previous_reserve_percent=previous_reserve,
                new_reserve_percent=reserve,
                previous_allocation_policy=previous_policy,
                new_allocation_policy=policy,
                reason='Sobrescrito via seed --force',
                changed_by=None,
            )
            self.stdout.write(self.style.WARNING(
                f'   🔄 Orçamento sobrescrito (--force): '
                f'total={total_bytes} B, '
                f'reserve={reserve}%, '
                f'policy={policy}'
            ))