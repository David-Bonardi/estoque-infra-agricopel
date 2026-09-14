from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.db import close_old_connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from .models import Asset, Balance, Branch, Item, Movement
from .services import record_movement


class InventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles', verbosity=0)
        cls.user = get_user_model().objects.create_user('operador', password='test-only-password')
        cls.user.groups.set([Group.objects.get(name='Operação')])
        cls.a = Branch.objects.create(code='001', name='Matriz')
        cls.b = Branch.objects.create(code='060', name='Filial 60')
        cls.mouse = Item.objects.create(name='Mouse', tracking='quantity')
        cls.notebook = Item.objects.create(name='Notebook', tracking='individual')
        cls.asset = Asset.objects.create(item=cls.notebook, tag='PAT-001', serial='SN-001')

    def move(self, **kwargs):
        data = dict(actor=self.user, kind='entry', item=self.mouse, quantity=10, destination=self.a, reason='CH-123')
        data.update(kwargs)
        return record_movement(**data)

    def test_transfer_and_exit_keep_balances_and_actor(self):
        self.move()
        movement = self.move(kind='transfer', quantity=4, source=self.a, destination=self.b)
        self.move(kind='exit', quantity=1, source=self.b, destination=None)
        self.assertEqual(Balance.objects.get(branch=self.a).quantity, 6)
        self.assertEqual(Balance.objects.get(branch=self.b).quantity, 3)
        self.assertEqual(movement.actor, self.user)
        self.assertEqual(Movement.objects.count(), 3)

    def test_insufficient_stock_rolls_back(self):
        self.move()
        with self.assertRaises(ValidationError):
            self.move(kind='transfer', quantity=11, source=self.a, destination=self.b)
        self.assertEqual(Balance.objects.get(branch=self.a).quantity, 10)
        self.assertFalse(Balance.objects.filter(branch=self.b).exists())
        self.assertEqual(Movement.objects.count(), 1)

    def test_asset_lifecycle(self):
        self.move(item=self.notebook, asset=self.asset, quantity=1)
        self.move(item=self.notebook, asset=self.asset, quantity=1, kind='transfer', source=self.a, destination=self.b)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.branch, self.b)
        self.move(item=self.notebook, asset=self.asset, quantity=1, kind='exit', source=self.b, destination=None)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.branch)
        self.assertFalse(Balance.objects.exists())

    def test_asset_duplicate_entry_and_wrong_origin_rejected(self):
        self.move(item=self.notebook, asset=self.asset, quantity=1)
        with self.assertRaises(ValidationError):
            self.move(item=self.notebook, asset=self.asset, quantity=1)
        with self.assertRaises(ValidationError):
            self.move(item=self.notebook, asset=self.asset, quantity=1, kind='exit', source=self.b, destination=None)
        self.assertEqual(Movement.objects.count(), 1)

    def test_invalid_inputs_leave_no_stock(self):
        for changes in [dict(quantity=0), dict(reason=' '), dict(kind='transfer', source=self.a),
                        dict(item=self.notebook), dict(asset=self.asset), dict(kind='exit')]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.move(**changes)
        self.assertFalse(Balance.objects.exists())
        self.assertFalse(Movement.objects.exists())

    def test_validation_failure_rolls_back_balance_update(self):
        with self.assertRaises(ValidationError):
            self.move(reason='x' * 301)
        self.assertFalse(Balance.objects.exists())

    def test_history_cannot_be_changed_or_deleted(self):
        movement = self.move()
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()

    def test_login_permissions_and_csrf(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        viewer = get_user_model().objects.create_user('consulta')
        viewer.groups.set([Group.objects.get(name='Consulta')])
        self.client.force_login(viewer)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/movimentacoes/nova/').status_code, 403)
        with self.assertRaises(PermissionDenied):
            self.move(actor=viewer)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post('/movimentacoes/nova/', {}).status_code, 403)

    def test_pages_forms_and_filters(self):
        self.client.force_login(self.user)
        response = self.client.post('/movimentacoes/nova/', {'kind': 'entry', 'item': self.mouse.pk,
            'quantity': 5, 'destination': self.a.pk, 'reason': 'Entrega inicial'})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get('/'), 'Mouse')
        self.assertContains(self.client.get('/movimentacoes/'), 'Entrega inicial')
        self.assertContains(self.client.get('/movimentacoes/nova/'), 'Registrar movimentação')
        self.assertNotContains(self.client.get('/', {'branch': self.b.pk}), '<td>Mouse</td>')
        self.assertContains(self.client.get('/login/'), 'Acesse o estoque')
        self.assertEqual(self.client.post('/logout/').status_code, 302)

    def test_invalid_form_displays_error_without_movement(self):
        self.client.force_login(self.user)
        response = self.client.post('/movimentacoes/nova/', {'kind': 'exit', 'item': self.mouse.pk,
            'quantity': 5, 'source': self.a.pk, 'reason': 'Sem saldo'})
        self.assertContains(response, 'Saldo insuficiente')
        self.assertFalse(Movement.objects.exists())

    def test_inactive_item_or_branch_rejected(self):
        self.a.active = False
        self.a.save()
        with self.assertRaises(ValidationError):
            self.move()

    def test_admin_cannot_edit_stock_or_history(self):
        user = get_user_model().objects.create_superuser('admin', password='test-only-password')
        self.client.force_login(user)
        movement = self.move()
        self.assertEqual(self.client.post(f'/admin/inventory/movement/{movement.pk}/change/', {}).status_code, 403)
        self.assertEqual(self.client.post(f'/admin/inventory/movement/{movement.pk}/delete/', {}).status_code, 403)
        self.assertContains(self.client.get('/admin/inventory/asset/add/'), 'Patrimônio')


class ConcurrentMovementTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_simultaneous_exits_cannot_spend_same_stock(self):
        user = get_user_model().objects.create_superuser('concurrency', password='test-only-password')
        branch = Branch.objects.create(code='001', name='Matriz')
        item = Item.objects.create(name='Mouse', tracking='quantity')
        record_movement(actor=user, kind='entry', item=item, quantity=1, destination=branch, reason='Inicial')
        barrier = Barrier(2)

        def attempt_exit():
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                record_movement(actor=actor, kind='exit', item=item, quantity=1, source=branch, reason='Concorrente')
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt_exit) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Balance.objects.get(item=item, branch=branch).quantity, 0)
        self.assertEqual(Movement.objects.count(), 2)
