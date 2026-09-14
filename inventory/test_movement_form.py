from django.test import TestCase
from .forms import MovementForm
from .models import Asset, Branch, Item


class ConditionalMovementFormTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(code='001', name='Matriz')
        self.mouse = Item.objects.create(name='Mouse Dell', tracking='quantity')
        self.notebook = Item.objects.create(name='Notebook', tracking='individual')
        self.asset = Asset.objects.create(item=self.notebook, tag='PAT-001')

    def test_entry_ignores_hidden_origin_and_asset(self):
        form = MovementForm({'kind': 'entry', 'item': self.mouse.pk, 'quantity': 5,
            'destination': self.branch.pk, 'source': 'invalid', 'asset': 'invalid', 'reason': 'Entrada'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['source'])
        self.assertIsNone(form.cleaned_data['asset'])

    def test_individual_quantity_defaults_to_one_without_posted_field(self):
        form = MovementForm({'kind': 'entry', 'item': self.notebook.pk, 'asset': self.asset.pk,
            'destination': self.branch.pk, 'reason': 'Patrimônio'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['quantity'], 1)

    def test_exit_ignores_hidden_destination_but_requires_origin(self):
        form = MovementForm({'kind': 'exit', 'item': self.mouse.pk, 'quantity': 1,
            'destination': 'invalid', 'reason': 'Saída'})
        self.assertFalse(form.is_valid())
        self.assertIn('source', form.errors)
        self.assertNotIn('destination', form.errors)

    def test_transfer_requires_both_branches(self):
        form = MovementForm({'kind': 'transfer', 'item': self.mouse.pk, 'quantity': 1, 'reason': 'Transferência'})
        self.assertFalse(form.is_valid())
        self.assertIn('source', form.errors)
        self.assertIn('destination', form.errors)

    def test_individual_requires_asset_and_quantity_item_requires_count(self):
        for item, required in [(self.notebook, 'asset'), (self.mouse, 'quantity')]:
            form = MovementForm({'kind': 'entry', 'item': item.pk, 'destination': self.branch.pk, 'reason': 'Entrada'})
            self.assertFalse(form.is_valid())
            self.assertIn(required, form.errors)
