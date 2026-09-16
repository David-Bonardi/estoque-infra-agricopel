from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import Asset, Balance, Branch, Item, Movement


@transaction.atomic
def record_movement(*, actor, kind, item, quantity, source=None, destination=None, asset=None, reason,
                    recipient='', recipient_department=''):
    if not actor.is_active or not actor.has_perm('inventory.add_movement'):
        raise PermissionDenied
    # Serialize movements of the same item, including creation of its first balance.
    item = Item.objects.select_for_update().get(pk=item.pk)
    if not item.active:
        raise ValidationError('Este tipo de item está inativo.')
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise ValidationError('Informe uma quantidade inteira maior que zero.')
    if kind not in Movement.Kind.values:
        raise ValidationError('Movimentação inválida.')
    if kind == Movement.Kind.ENTRY and (source or not destination):
        raise ValidationError('Entrada exige apenas a filial de destino.')
    if kind == Movement.Kind.EXIT and (not source or destination):
        raise ValidationError('Saída exige apenas a filial de origem.')
    if kind == Movement.Kind.TRANSFER and (not source or not destination or source.pk == destination.pk):
        raise ValidationError('Transferência exige origem e destino diferentes.')
    for branch in (source, destination):
        if branch and not Branch.objects.get(pk=branch.pk).active:
            raise ValidationError('A filial selecionada está inativa.')
    reason = reason.strip()
    if not reason:
        raise ValidationError('Informe o motivo ou chamado.')
    recipient = recipient.strip() if kind != Movement.Kind.ENTRY else ''
    recipient_department = recipient_department.strip() if kind != Movement.Kind.ENTRY else ''
    if item.tracking == Item.Tracking.INDIVIDUAL:
        if not asset or quantity != 1:
            raise ValidationError('Selecione um equipamento e informe quantidade 1.')
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        if asset.item_id != item.pk: # type: ignore
            raise ValidationError('O equipamento não pertence ao tipo de item informado.')
        if asset.branch_id != (source.pk if source else None): # type: ignore
            raise ValidationError('A origem não corresponde à localização atual do equipamento.')
        asset.branch = destination
        asset.location = ''
        asset.save(update_fields=['branch', 'location'])
    else:
        if asset:
            raise ValidationError('Itens por quantidade não usam patrimônio.')
        if source:
            balance, _ = Balance.objects.get_or_create(item=item, branch=source)
            if balance.quantity < quantity:
                raise ValidationError(f'Saldo insuficiente: há {balance.quantity} unidade(s) na origem.')
            balance.quantity -= quantity
            balance.save(update_fields=['quantity'])
        if destination:
            balance, _ = Balance.objects.get_or_create(item=item, branch=destination)
            balance.quantity += quantity
            # New units have not yet been checked against the condition of the old batch.
            balance.condition = 'unknown'
            balance.save(update_fields=['quantity', 'condition'])
    movement = Movement(kind=kind, item=item, asset=asset, quantity=quantity, source=source,
                        destination=destination, reason=reason, actor=actor,
                        recipient=recipient, recipient_department=recipient_department)
    movement.full_clean()
    movement.save()
    return movement
