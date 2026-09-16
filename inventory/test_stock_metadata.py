from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from .models import Asset, Balance, Branch, Item, Movement
from .services import record_movement


class StockMetadataTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('equipe')
        self.a = Branch.objects.create(code='A', name='Matriz')
        self.b = Branch.objects.create(code='B', name='Filial')
        self.item = Item.objects.create(name='Mouse', category='Periféricos', tracking='quantity')
        self.balance = Balance.objects.create(item=self.item, branch=self.a, quantity=10)
        self.client.force_login(self.user)

    def test_metadata_edit_cannot_change_balance_item_or_branch(self):
        response = self.client.post(f'/estoque/{self.balance.pk}/detalhes/', {
            'location': 'Prateleira C', 'condition': 'incomplete', 'notes': 'Sem receptor USB',
            'quantity': 999, 'branch': self.b.pk, 'item': 999})
        self.assertEqual(response.status_code, 302)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, 10)
        self.assertEqual(self.balance.branch, self.a)
        self.assertEqual(self.balance.location, 'Prateleira C')
        self.assertEqual(self.balance.condition, 'incomplete')
        response = self.client.get('/', {'category': 'Periféricos'})
        self.assertContains(response, 'Prateleira C')
        self.assertContains(response, 'Sem receptor USB')
        self.assertNotContains(self.client.get('/', {'category': 'Cabos'}), '<td>Mouse')

    def test_transfer_recipient_is_separate_from_actor_and_searchable(self):
        response = self.client.post('/movimentacoes/nova/', {'kind': 'transfer', 'item': self.item.pk,
            'quantity': 2, 'source': self.a.pk, 'destination': self.b.pk, 'reason': 'Entrega',
            'recipient': 'Pessoa destinatária', 'recipient_department': 'Financeiro', 'actor': 999})
        self.assertEqual(response.status_code, 302)
        movement = Movement.objects.get()
        self.assertEqual(movement.actor, self.user)
        self.assertEqual(movement.recipient, 'Pessoa destinatária')
        self.assertContains(self.client.get('/movimentacoes/', {'q': 'Financeiro'}), 'Pessoa destinatária')

    def test_entry_ignores_hidden_recipient(self):
        self.client.post('/movimentacoes/nova/', {'kind': 'entry', 'item': self.item.pk,
            'quantity': 2, 'destination': self.a.pk, 'reason': 'Entrega',
            'recipient': 'Nome anterior', 'recipient_department': 'Setor anterior'})
        movement = Movement.objects.get()
        self.assertEqual(movement.recipient, '')
        self.assertEqual(movement.recipient_department, '')

    def test_asset_transfer_clears_old_shelf_but_preserves_condition_and_notes(self):
        item = Item.objects.create(name='Notebook', tracking='individual')
        asset = Asset.objects.create(item=item, tag='001', branch=self.a,
            location='Prateleira A', condition='testing', notes='Testar bateria')
        record_movement(actor=self.user, kind='transfer', item=item, quantity=1, asset=asset,
                        source=self.a, destination=self.b, reason='Envio')
        asset.refresh_from_db()
        self.assertEqual(asset.branch, self.b)
        self.assertEqual(asset.location, '')
        self.assertEqual(asset.condition, 'testing')
        self.assertEqual(asset.notes, 'Testar bateria')

    def test_new_batch_requires_condition_review(self):
        self.balance.condition = 'working'
        self.balance.save()
        record_movement(actor=self.user, kind='entry', item=self.item, quantity=2, destination=self.a, reason='Novo lote')
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.condition, 'unknown')
        self.assertEqual(self.balance.quantity, 12)

    def test_view_only_user_cannot_edit_metadata(self):
        call_command('setup_roles')
        self.user.groups.set([Group.objects.get(name='Consulta')])
        for method in (self.client.get, self.client.post):
            self.assertEqual(method(f'/estoque/{self.balance.pk}/detalhes/').status_code, 403)
