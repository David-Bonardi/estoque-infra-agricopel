from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from .legacy_import import import_snapshot
from .models import Balance, Branch, Item, Movement


class LegacyImportTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser('tecnico')
        self.branch = Branch.objects.create(code='00', name='Base')
        self.report = {'sha256': 'a' * 64, 'item_count': 1, 'last_recorded_movement': '2026-07-06', 'items': [
            {'source_row': 2, 'name_proposed': 'Mouses com fio', 'category': 'Periféricos', 'calculated_quantity': 21,
             'cached_quantity': 21, 'initial_quantity': 20, 'entries': 2, 'exits': 1, 'location_proposed': 'C',
             'notes_proposed': 'Testar', 'working_original': '-'}]}

    def test_import_metadata_and_idempotency(self):
        first = import_snapshot(report=self.report, branch=self.branch, actor=self.actor)
        second = import_snapshot(report=self.report, branch=self.branch, actor=self.actor)
        self.assertFalse(first['already_imported'])
        self.assertTrue(second['already_imported'])
        self.assertEqual(Movement.objects.count(), 1)
        balance = Balance.objects.get()
        self.assertEqual(balance.quantity, 21)
        self.assertEqual(balance.location, 'C')
        self.assertEqual(balance.condition, 'unknown')
        self.assertEqual(balance.notes, 'Testar')

    def test_test_data_retired_through_history(self):
        item = Item.objects.create(name='Teste', tracking='quantity')
        balance = Balance.objects.create(item=item, branch=self.branch, quantity=5)
        expected = list(Balance.objects.values('id', 'branch_id', 'item_id', 'quantity'))
        import_snapshot(report=self.report, branch=self.branch, actor=self.actor, expected_test_balances=expected)
        balance.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(balance.quantity, 0)
        self.assertFalse(item.active)
        self.assertEqual(Movement.objects.filter(kind='exit', quantity=5).count(), 1)

    def test_changed_test_data_prevents_import(self):
        item = Item.objects.create(name='Teste', tracking='quantity')
        balance = Balance.objects.create(item=item, branch=self.branch, quantity=5)
        expected = list(Balance.objects.values('id', 'branch_id', 'item_id', 'quantity'))
        balance.quantity = 6
        balance.save()
        with self.assertRaises(ValidationError):
            import_snapshot(report=self.report, branch=self.branch, actor=self.actor, expected_test_balances=expected)
        self.assertEqual(Movement.objects.count(), 0)

    def test_bad_metadata_rolls_back_test_retirement_and_new_stock(self):
        item = Item.objects.create(name='Teste', tracking='quantity')
        balance = Balance.objects.create(item=item, branch=self.branch, quantity=5)
        expected = list(Balance.objects.values('id', 'branch_id', 'item_id', 'quantity'))
        self.report['items'][0]['location_proposed'] = 'x' * 121
        with self.assertRaises(ValidationError):
            import_snapshot(report=self.report, branch=self.branch, actor=self.actor, expected_test_balances=expected)
        balance.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(balance.quantity, 5)
        self.assertTrue(item.active)
        self.assertEqual(Item.objects.count(), 1)
        self.assertFalse(Movement.objects.exists())

    def test_existing_name_is_not_merged(self):
        Item.objects.create(name='Mouses com fio', tracking='quantity')
        with self.assertRaises(ValidationError):
            import_snapshot(report=self.report, branch=self.branch, actor=self.actor)
        self.assertFalse(Movement.objects.exists())
