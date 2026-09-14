from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from .roles import DEFAULT_GROUP, INVENTORY_PERMISSIONS
from .models import Asset, Branch, Item


class DefaultUserAccessTests(TestCase):
    def test_new_user_can_register_stock_without_admin_access(self):
        user = get_user_model().objects.create_user('novo.usuario')
        self.assertTrue(user.has_perms([f'inventory.{code}' for code in INVENTORY_PERMISSIONS]))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_perm('auth.add_user'))
        self.assertFalse(user.has_perm('auth.change_user'))
        self.assertFalse(user.has_perm('auth.change_group'))
        self.client.force_login(user)
        self.assertEqual(self.client.post('/cadastros/filiais/novo/', {'code': 'F01', 'name': 'Filial', 'active': 'on'}).status_code, 302)
        self.assertTrue(Branch.objects.filter(code='F01').exists())
        self.assertEqual(self.client.post('/cadastros/itens/novo/', {'name': 'Monitor', 'tracking': 'individual', 'active': 'on'}).status_code, 302)
        item = Item.objects.get(name='Monitor')
        self.assertEqual(self.client.post('/cadastros/equipamentos/novo/', {'tag': 'MON-01', 'item': item.pk}).status_code, 302)
        self.assertTrue(Asset.objects.filter(tag='MON-01').exists())
        for url in ['/admin/', '/admin/auth/user/add/', '/admin/auth/group/']:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_admin_created_user_gets_default_group(self):
        admin = get_user_model().objects.create_superuser('tecnico', password='Test-password-892!')
        self.client.force_login(admin)
        response = self.client.post('/admin/auth/user/add/', {
            'username': 'via.admin', 'password1': 'New-test-password-892!',
            'password2': 'New-test-password-892!', 'usable_password': 'true', '_save': 'Salvar'})
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='via.admin')
        self.assertTrue(user.groups.filter(name=DEFAULT_GROUP).exists())
        self.assertTrue(user.has_perm('inventory.add_branch'))
        self.assertFalse(user.has_perm('auth.add_user'))
        self.assertFalse(user.is_staff)

    def test_existing_users_can_be_updated_idempotently(self):
        user = get_user_model().objects.create_user('existente')
        user.groups.clear()
        call_command('setup_roles', assign_users=True)
        call_command('setup_roles', assign_users=True)
        user.refresh_from_db()
        self.assertEqual(user.groups.filter(name=DEFAULT_GROUP).count(), 1)
        self.assertTrue(user.has_perm('inventory.add_asset'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.has_perm('auth.add_user'))

    def test_inactive_users_remain_blocked(self):
        user = get_user_model().objects.create_user('inativo', is_active=False)
        self.assertFalse(user.has_perm('inventory.add_asset'))
