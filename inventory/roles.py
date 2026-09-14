from django.contrib.auth.models import Group, Permission

DEFAULT_GROUP = 'Gestão de estoque'
INVENTORY_PERMISSIONS = (
    'view_branch', 'add_branch', 'change_branch',
    'view_item', 'add_item', 'change_item',
    'view_asset', 'add_asset', 'change_asset',
    'view_balance', 'view_movement', 'add_movement',
)


def assign_inventory_access(user, using='default'):
    group, _ = Group.objects.using(using).get_or_create(name=DEFAULT_GROUP)
    group.permissions.add(*Permission.objects.using(using).filter(
        content_type__app_label='inventory', codename__in=INVENTORY_PERMISSIONS))
    user.groups.add(group)
