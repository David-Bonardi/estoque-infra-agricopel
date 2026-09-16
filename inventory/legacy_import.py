"""Atomic one-time import of a reviewed legacy stock snapshot."""
import re
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from .models import Asset, Balance, Branch, Item, Movement
from .services import record_movement


def validate_rows(report):
    if not re.fullmatch(r'[0-9a-f]{64}', report.get('sha256', '')):
        raise ValidationError('Identificador da planilha inválido.')
    rows = report.get('items', [])
    if not rows or len(rows) != report.get('item_count'):
        raise ValidationError('Quantidade de linhas da prévia inválida.')
    names, numbers = set(), set()
    for row in rows:
        name = row['name_proposed'].strip()
        quantity = row['calculated_quantity']
        if not name or name.casefold() in names or row['source_row'] in numbers:
            raise ValidationError('Item ou linha repetidos na prévia.')
        if type(quantity) is not int or quantity <= 0:
            raise ValidationError('Esta importação exige saldos inteiros positivos.')
        if quantity != row['initial_quantity'] + row['entries'] - row['exits'] or quantity != row['cached_quantity']:
            raise ValidationError('Saldo não reconciliado na prévia.')
        names.add(name.casefold())
        numbers.add(row['source_row'])
    return rows


@transaction.atomic
def import_snapshot(*, report, branch, actor, expected_test_balances=(), expected_test_assets=()):
    rows = validate_rows(report)
    if not actor.is_active or not actor.is_superuser:
        raise ValidationError('A importação inicial exige um administrador técnico.')
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int.from_bytes(bytes.fromhex(report['sha256'])[:8], signed=True)])
    branch = Branch.objects.select_for_update().get(pk=branch.pk)
    if not branch.active:
        raise ValidationError('Filial inativa.')
    marker = f'Excel:{report["sha256"]} '
    existing = Movement.objects.filter(reason__startswith=marker)
    if existing.exists():
        if existing.count() == len(rows) and not existing.exclude(destination=branch).exists():
            return {'already_imported': True, 'items': len(rows), 'units': sum(r['calculated_quantity'] for r in rows)}
        raise ValidationError('Importação anterior divergente. Nenhuma nova entrada foi registrada.')

    # Refuse to overwrite or add to an existing item silently.
    for row in rows:
        if Item.objects.filter(name__iexact=row['name_proposed'].strip()).exists():
            raise ValidationError(f'O item {row["name_proposed"]} já existe. Revise a correspondência antes de importar.')
    test_item_ids = {r['item_id'] for r in expected_test_balances} | {r['item_id'] for r in expected_test_assets}
    list(Item.objects.select_for_update().filter(pk__in=test_item_ids).order_by('pk'))
    actual_balances = list(Balance.objects.filter(item_id__in=test_item_ids, quantity__gt=0)
                           .order_by('pk').values('id', 'branch_id', 'item_id', 'quantity'))
    actual_assets = list(Asset.objects.filter(item_id__in=test_item_ids, branch__isnull=False)
                         .order_by('pk').values('id', 'item_id', 'branch_id', 'tag'))
    if actual_balances != list(expected_test_balances) or actual_assets != list(expected_test_assets):
        raise ValidationError('Os dados de teste mudaram desde a conferência. Importação cancelada.')
    retired = 0
    for expected in expected_test_balances:
        balance = Balance.objects.select_related('item', 'branch').get(pk=expected['id'])
        record_movement(actor=actor, kind='exit', item=balance.item, quantity=balance.quantity,
                        source=balance.branch, reason='Encerramento de saldo de teste antes da importação da planilha, autorizado pelo administrador.')
        retired += 1
    for expected in expected_test_assets:
        asset = Asset.objects.select_related('item', 'branch').get(pk=expected['id'])
        record_movement(actor=actor, kind='exit', item=asset.item, asset=asset, quantity=1,
                        source=asset.branch, reason='Retirada de patrimônio de teste antes da importação da planilha, autorizada pelo administrador.')
        retired += 1
    Item.objects.filter(pk__in=test_item_ids).update(active=False)

    for row in rows:
        item = Item(name=row['name_proposed'].strip(), category=row['category'], tracking='quantity')
        item.full_clean()
        item.save()
        quantity = row['calculated_quantity']
        record_movement(actor=actor, kind='entry', item=item, quantity=quantity, destination=branch,
            reason=f'{marker}L{row["source_row"]}: saldo final da planilha até {report["last_recorded_movement"]}; carga inicial por quantidade.')
        balance = Balance.objects.get(item=item, branch=branch)
        balance.location = row['location_proposed']
        balance.notes = row['notes_proposed']
        flag = str(row['working_original'] or '').strip().upper()
        balance.condition = {'S': 'working', 'N': 'defective'}.get(flag, 'unknown')
        balance.full_clean()
        balance.save(update_fields=['location', 'notes', 'condition'])
    return {'already_imported': False, 'items': len(rows), 'units': sum(r['calculated_quantity'] for r in rows), 'retired_test_movements': retired}
