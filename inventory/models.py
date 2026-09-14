from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Branch(models.Model):
    code = models.CharField('código', max_length=30, unique=True)
    name = models.CharField('nome', max_length=150)
    active = models.BooleanField('ativa', default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'filial'
        verbose_name_plural = 'filiais'

    def __str__(self):
        return f'{self.code} — {self.name}'


class Item(models.Model):
    class Tracking(models.TextChoices):
        QUANTITY = 'quantity', 'Quantidade'
        INDIVIDUAL = 'individual', 'Patrimônio individual'

    name = models.CharField('nome', max_length=150, unique=True)
    tracking = models.CharField('controle', max_length=15, choices=Tracking.choices)
    active = models.BooleanField('ativo', default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'tipo de item'
        verbose_name_plural = 'tipos de item'

    def clean(self):
        if self.pk:
            original = Item.objects.get(pk=self.pk)
            if original.tracking != self.tracking and (
                self.movements.exists() or self.assets.exists() or self.balances.exists()
            ):
                raise ValidationError('O controle não pode mudar após o uso do item.')

    def __str__(self):
        return self.name


class Asset(models.Model):
    item = models.ForeignKey(Item, verbose_name='tipo de item', on_delete=models.PROTECT, related_name='assets')
    tag = models.CharField('patrimônio', max_length=80, unique=True)
    serial = models.CharField('número de série', max_length=120, unique=True, null=True, blank=True)
    branch = models.ForeignKey(Branch, verbose_name='filial atual', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['tag']
        verbose_name = 'equipamento'
        verbose_name_plural = 'equipamentos'

    def clean(self):
        self.serial = self.serial.strip() or None if self.serial else None
        if self.item_id and self.item.tracking != Item.Tracking.INDIVIDUAL:
            raise ValidationError('Equipamentos exigem um tipo de item com controle individual.')
        if self.pk and Asset.objects.get(pk=self.pk).item_id != self.item_id:
            raise ValidationError('O tipo de um equipamento cadastrado não pode ser alterado.')

    def __str__(self):
        return f'{self.tag} — {self.item}'


class Balance(models.Model):
    branch = models.ForeignKey(Branch, verbose_name='filial', on_delete=models.PROTECT)
    item = models.ForeignKey(Item, verbose_name='item', on_delete=models.PROTECT, related_name='balances')
    quantity = models.PositiveIntegerField('quantidade', default=0)

    class Meta:
        verbose_name = 'saldo'
        verbose_name_plural = 'saldos'
        constraints = [
            models.UniqueConstraint(fields=['branch', 'item'], name='unique_branch_item'),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name='nonnegative_balance'),
        ]


class Movement(models.Model):
    class Kind(models.TextChoices):
        ENTRY = 'entry', 'Entrada'
        EXIT = 'exit', 'Saída'
        TRANSFER = 'transfer', 'Transferência'

    kind = models.CharField('movimentação', max_length=10, choices=Kind.choices)
    item = models.ForeignKey(Item, verbose_name='item', on_delete=models.PROTECT, related_name='movements')
    asset = models.ForeignKey(Asset, verbose_name='equipamento', on_delete=models.PROTECT, blank=True, null=True)
    quantity = models.PositiveIntegerField('quantidade')
    source = models.ForeignKey(Branch, verbose_name='origem', on_delete=models.PROTECT, related_name='outgoing', null=True, blank=True)
    destination = models.ForeignKey(Branch, verbose_name='destino', on_delete=models.PROTECT, related_name='incoming', null=True, blank=True)
    reason = models.CharField('motivo / chamado', max_length=300)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='responsável', on_delete=models.PROTECT)
    created_at = models.DateTimeField('data', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'movimentação'
        verbose_name_plural = 'movimentações'
        default_permissions = ('add', 'view')
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='positive_movement_quantity')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('O histórico não pode ser editado. Registre uma nova movimentação de correção.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Movimentações não podem ser excluídas.')
