from django import forms
from .models import Asset, Balance, Branch, Item, Movement


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ('code', 'name', 'active')


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ('name', 'category', 'tracking', 'notes', 'active')
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        item = self.instance
        if item.pk and (item.movements.exists() or item.assets.exists() or item.balances.exists()):
            self.fields['tracking'].disabled = True
            self.fields['tracking'].help_text = 'O controle fica fixo depois que o item é utilizado.'


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ('item', 'tag', 'serial', 'location', 'condition', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['item'].disabled = True
            self.fields['item'].queryset = Item.objects.filter(pk=self.instance.item_id)
        else:
            self.fields['item'].queryset = Item.objects.filter(active=True, tracking=Item.Tracking.INDIVIDUAL)
        self.fields['tag'].help_text = 'Identificação única do patrimônio da empresa.'
        self.fields['condition'].required = False
        self.fields['location'].help_text = 'Ex.: prateleira A, bancada ou escritório. Preencha após alocar em uma filial.'
        if not self.instance.branch_id:
            self.fields['location'].disabled = True

    def clean_condition(self):
        return self.cleaned_data.get('condition') or 'unknown'


class StockDetailsForm(forms.ModelForm):
    class Meta:
        model = Balance
        fields = ('location', 'condition', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}
        help_texts = {
            'location': 'Local dentro desta filial, por exemplo: prateleira C ou armário do escritório.',
            'condition': 'Descreve o conjunto de unidades. Se houver condições diferentes, selecione Condições variadas e detalhe nas observações.',
        }


class InventorySelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if hasattr(value, 'instance'):
            obj = value.instance
            if isinstance(obj, Item):
                option['attrs']['data-tracking'] = obj.tracking
            elif isinstance(obj, Asset):
                option['attrs']['data-item'] = str(obj.item_id)
                option['attrs']['data-branch'] = str(obj.branch_id or '')
        return option


class MovementForm(forms.Form):
    kind = forms.ChoiceField(label='Movimentação', choices=Movement.Kind.choices)
    item = forms.ModelChoiceField(label='Tipo de item', queryset=Item.objects.filter(active=True), widget=InventorySelect)
    asset = forms.ModelChoiceField(label='Equipamento', queryset=Asset.objects.select_related('item'), required=False,
                                  widget=InventorySelect, help_text='Selecione o patrimônio que será movimentado.')
    quantity = forms.IntegerField(label='Quantidade', min_value=1, initial=1)
    source = forms.ModelChoiceField(label='Filial de origem', queryset=Branch.objects.filter(active=True), required=False)
    destination = forms.ModelChoiceField(label='Filial de destino', queryset=Branch.objects.filter(active=True), required=False)
    reason = forms.CharField(label='Motivo / chamado', max_length=300, widget=forms.Textarea(attrs={'rows': 3}))
    recipient = forms.CharField(label='Colaborador destinatário', max_length=150, required=False,
                                help_text='Pessoa que recebe o material, se aplicável. Não precisa ter login no sistema.')
    recipient_department = forms.CharField(label='Setor do destinatário', max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(['kind', 'item', 'source', 'destination', 'asset', 'quantity', 'recipient', 'recipient_department', 'reason'])
        if not self.is_bound:
            return
        kind = self.data.get(self.add_prefix('kind'))
        if kind == Movement.Kind.ENTRY:
            self.fields['recipient'].disabled = True
            self.fields['recipient_department'].disabled = True
        for name, relevant in [('source', kind in ('exit', 'transfer')), ('destination', kind in ('entry', 'transfer'))]:
            self.fields[name].required = relevant
            self.fields[name].disabled = not relevant
        item_id = self.data.get(self.add_prefix('item'), '')
        item = Item.objects.filter(pk=int(item_id)).first() if str(item_id).isdigit() and len(str(item_id)) < 19 else None
        if item:
            individual = item.tracking == Item.Tracking.INDIVIDUAL
            self.fields['asset'].required = individual
            self.fields['asset'].disabled = not individual
            self.fields['quantity'].disabled = individual
            if individual:
                self.fields['quantity'].initial = 1
