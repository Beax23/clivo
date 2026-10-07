"""
Bootstrap do Console.

Cria o primeiro ConsoleMembership de forma explícita.

Uso:
    python manage.py bootstrap_console --email suporte@clivoos.com

Se o email não existir, cria um superuser com senha padrão.
Se existir, apenas garante o ConsoleMembership.

Este é o ÚNICO mecanismo oficial de criação de acesso ao Console.
Depois disso, um admin do Console pode adicionar outros via API.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.console.models import ConsoleMembership

User = get_user_model()


class Command(BaseCommand):
    help = 'Bootstrap do Console: cria o primeiro ConsoleMembership'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='Email do usuário que receberá acesso ao Console',
        )
        parser.add_argument(
            '--password',
            type=str,
            default='admin123456',
            help='Senha do superuser se precisar criá-lo (default: admin123456)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = User.normalize_email(options['email'])

        self.stdout.write(self.style.SUCCESS('🚀 Bootstrap do Console'))
        self.stdout.write(f'   Email: {email}')
        self.stdout.write('')

        # 1) Busca ou cria usuário
        user = User.objects.filter(email__iexact=email).first()
        user_was_created = False

        if not user:
            self.stdout.write('   Usuário não existe. Criando superuser...')
            user = User.objects.create_superuser(
                email=email,
                password=options['password'],
                first_name='Admin',
                last_name='Clivo',
            )
            user_was_created = True
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Superuser criado: {email}'
            ))
        else:
            self.stdout.write(f'   Usuário já existe: {email}')

        # 2) Cria ConsoleMembership se não existir
        membership, membership_created = ConsoleMembership.objects.get_or_create(
            user=user,
            defaults={'created_by': user},
        )

        if membership_created:
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ ConsoleMembership criado: {user.email}'
            ))
        else:
            self.stdout.write(
                f'   ✅ ConsoleMembership já existe: {user.email}'
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Bootstrap concluído!'))

        if user_was_created:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'⚠️  Guarde a senha: {options["password"]}'
            ))