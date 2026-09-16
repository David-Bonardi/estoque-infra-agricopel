from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from .forms import AssetForm, BranchForm
from .models import Asset, Branch, Item


class OptionalEquipmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.item = Item.objects.create(name='Notebook individual', tracking='individual')
        cls.user = get_user_model().objects.create_superuser('tecnico', password='test-only')

    def test_multiple_equipment_with_only_item_can_be_created(self):
        self.client.force_login(self.user)
        for _ in range(2):
            response = self.client.post('/cadastros/equipamentos/novo/', {'item': self.item.pk})
            self.assertEqual(response.status_code, 302)
        equipment = list(Asset.objects.all())
        self.assertEqual(len(equipment), 2)
        for asset in equipment:
            self.assertIsNone(asset.tag)
            self.assertIsNone(asset.serial)
            self.assertEqual(asset.condition, 'unknown')
            self.assertIn(f'cadastro #{asset.pk}', str(asset))
        page = self.client.get('/cadastros/equipamentos/')
        for asset in equipment:
            self.assertContains(page, asset.display_identifier)

    def test_only_item_is_required_and_blank_identifiers_become_null(self):
        form = AssetForm()
        self.assertEqual([name for name, field in form.fields.items() if field.required], ['item'])
        self.assertFalse(AssetForm({}).is_valid())
        form = AssetForm({'item': self.item.pk, 'tag': '   ', 'serial': '  '})
        self.assertTrue(form.is_valid(), form.errors)
        asset = form.save()
        self.assertIsNone(asset.tag)
        self.assertIsNone(asset.serial)

    def test_identifiers_can_be_added_later_but_not_duplicated(self):
        first = Asset.objects.create(item=self.item)
        second = Asset.objects.create(item=self.item)
        form = AssetForm({'tag': 'PAT-100', 'serial': 'SN-100'}, instance=first)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        first.refresh_from_db()
        self.assertEqual(first.tag, 'PAT-100')
        self.assertEqual(first.serial, 'SN-100')
        duplicate = AssetForm({'tag': 'PAT-100', 'serial': 'SN-100'}, instance=second)
        self.assertFalse(duplicate.is_valid())
        self.assertIn('tag', duplicate.errors)
        self.assertIn('serial', duplicate.errors)


class NumericBranchTests(TestCase):
    def test_rejects_letters_punctuation_and_non_ascii_digits(self):
        for code in ('ABC', '01A', '1.5', '-1', '+1', '1e3', '1 2', '１２', '١٢'):
            with self.subTest(code=code):
                form = BranchForm({'code': code, 'name': 'Filial'})
                self.assertFalse(form.is_valid())
                self.assertIn('code', form.errors)
                with self.assertRaises(ValidationError):
                    Branch(code=code, name='Filial').full_clean()

    def test_preserves_leading_zeroes_and_uniqueness(self):
        form = BranchForm({'code': '001', 'name': 'Filial'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().code, '001')
        duplicate = BranchForm({'code': '001', 'name': 'Outra'})
        self.assertFalse(duplicate.is_valid())
        self.assertIn('code', duplicate.errors)

    def test_post_cannot_bypass_numeric_validation(self):
        user = get_user_model().objects.create_superuser('tecnico', password='test-only')
        self.client.force_login(user)
        response = self.client.post('/cadastros/filiais/novo/', {'code': 'AA', 'name': 'Filial'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Branch.objects.exists())
        self.assertContains(response, 'Informe somente números')
        self.assertContains(response, 'inputmode="numeric"')
        self.assertContains(response, 'branch_code.js')
