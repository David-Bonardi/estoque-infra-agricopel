from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.admin.models import LogEntry
from django.core.management import call_command
from django.test import Client, TestCase
from .models import Asset, Branch, Item


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles', verbosity=0)
        cls.manager = get_user_model().objects.create_user('gestor')
        cls.manager.groups.add(Group.objects.get(name='Gestão de estoque'))
        cls.viewer = get_user_model().objects.create_user('leitor', is_staff=True)
        cls.viewer.groups.set([Group.objects.get(name='Consulta')])
        cls.branch = Branch.objects.create(code='001', name='Matriz')
        cls.item = Item.objects.create(name='Notebook', tracking='individual')
        cls.asset = Asset.objects.create(item=cls.item, tag='PAT-001', branch=cls.branch)

    def test_manager_uses_custom_pages_without_staff(self):
        self.assertFalse(self.manager.is_staff)
        self.client.force_login(self.manager)
        self.assertRedirects(self.client.get('/cadastros/'), '/cadastros/filiais/')
        for kind in ('filiais', 'itens', 'equipamentos'):
            response = self.client.get(f'/cadastros/{kind}/')
            self.assertContains(response, 'Novo cadastro')
            self.assertNotContains(response, 'href="/admin/')
            self.assertContains(self.client.get(f'/cadastros/{kind}/novo/'), 'Salvar cadastro')

    def test_branch_create_edit_search_and_audit(self):
        self.client.force_login(self.manager)
        response = self.client.post('/cadastros/filiais/novo/', {'code': '060', 'name': 'Filial sessenta', 'active': 'on'})
        self.assertRedirects(response, '/cadastros/filiais/')
        branch = Branch.objects.get(code='060')
        self.client.post(f'/cadastros/filiais/{branch.pk}/editar/', {'code': '060', 'name': 'Filial atualizada'})
        branch.refresh_from_db()
        self.assertFalse(branch.active)
        self.assertEqual(branch.name, 'Filial atualizada')
        self.assertEqual(LogEntry.objects.filter(user=self.manager).count(), 2)
        self.assertContains(self.client.get('/cadastros/filiais/', {'q': 'atualizada'}), 'Filial atualizada')
        self.assertNotContains(self.client.get('/cadastros/filiais/', {'status': 'active'}), 'Filial atualizada')

    def test_duplicate_code_returns_form_error(self):
        self.client.force_login(self.manager)
        response = self.client.post('/cadastros/filiais/novo/', {'code': '001', 'name': 'Duplicada', 'active': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(Branch.objects.count(), 1)

    def test_viewer_cannot_create_or_edit_even_by_post(self):
        self.client.force_login(self.viewer)
        for kind, pk in [('filiais', self.branch.pk), ('itens', self.item.pk), ('equipamentos', self.asset.pk)]:
            self.assertNotContains(self.client.get(f'/cadastros/{kind}/'), 'Novo cadastro')
            for url in [f'/cadastros/{kind}/novo/', f'/cadastros/{kind}/{pk}/editar/']:
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {'name': 'Ataque'}).status_code, 403)

    def test_admin_blocked_even_for_staff_and_admin_login_post(self):
        self.client.force_login(self.viewer)
        for url in ['/admin/', '/admin/login/', '/admin/inventory/branch/', '/admin/auth/user/', '/admin/jsi18n/']:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/admin/').status_code, 403)

    def test_anonymous_admin_and_catalog_use_normal_login(self):
        for url in ['/admin/', '/admin/login/', '/cadastros/filiais/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/login/'))

    def test_asset_form_cannot_change_location_or_item(self):
        self.client.force_login(self.manager)
        mouse = Item.objects.create(name='Mouse', tracking='quantity')
        other = Branch.objects.create(code='002', name='Outra')
        response = self.client.post(f'/cadastros/equipamentos/{self.asset.pk}/editar/', {
            'item': mouse.pk, 'tag': 'PAT-001', 'serial': 'SN-123', 'branch': other.pk})
        self.assertEqual(response.status_code, 302)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.item, self.item)
        self.assertEqual(self.asset.branch, self.branch)
        self.assertEqual(self.asset.serial, 'SN-123')
        response = self.client.post('/cadastros/equipamentos/novo/', {
            'item': self.item.pk, 'tag': 'PAT-002', 'serial': '', 'branch': other.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Asset.objects.get(tag='PAT-002').branch)

    def test_used_item_tracking_is_locked(self):
        self.client.force_login(self.manager)
        self.client.post(f'/cadastros/itens/{self.item.pk}/editar/', {
            'name': 'Notebook atualizado', 'tracking': 'quantity', 'active': 'on'})
        self.item.refresh_from_db()
        self.assertEqual(self.item.tracking, 'individual')
        self.assertEqual(self.item.name, 'Notebook atualizado')

    def test_catalog_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        self.assertEqual(client.post('/cadastros/filiais/novo/', {'code': '999', 'name': 'Falha'}).status_code, 403)
        self.assertFalse(Branch.objects.filter(code='999').exists())
