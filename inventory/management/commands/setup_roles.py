from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from inventory.roles import DEFAULT_GROUP, INVENTORY_PERMISSIONS, assign_inventory_access


class Command(BaseCommand):
    help = 'Cria os grupos Consulta, Operação e Gestão de estoque, sem criar usuários.'

    def add_arguments(self, parser):
        parser.add_argument('--assign-users', action='store_true', help='Habilita cadastros e movimentações para os usuários comuns existentes.')

    def handle(self, *args, **options):
        permissions = Permission.objects.filter(content_type__app_label='inventory')
        for name, codes in {
            'Consulta': ['view_branch', 'view_item', 'view_asset', 'view_balance', 'view_movement'],
            'Operação': ['view_branch', 'view_item', 'view_asset', 'view_balance', 'view_movement', 'add_movement'],
            DEFAULT_GROUP: INVENTORY_PERMISSIONS,
        }.items():
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set(permissions.filter(codename__in=codes))
        if options['assign_users']:
            users = get_user_model().objects.filter(is_superuser=False)
            count = 0
            for user in users:
                assign_inventory_access(user)
                count += 1
            self.stdout.write(f'Acesso ao estoque atribuído a {count} usuário(s).')
        self.stdout.write(self.style.SUCCESS('Grupos configurados.'))
