from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from .forms import AssetForm, BranchForm, ItemForm, StockDetailsForm
from .models import Asset, Balance, Branch, Item


CATALOGS = {
    'filiais': {'model': Branch, 'form': BranchForm, 'title': 'Filiais', 'singular': 'filial',
                'description': 'Cadastre as unidades e mantenha sua identificação atualizada.',
                'search': ('code', 'name')},
    'itens': {'model': Item, 'form': ItemForm, 'title': 'Tipos de item', 'singular': 'tipo de item',
              'description': 'Defina quais materiais e equipamentos a equipe controla.',
              'search': ('name', 'category', 'notes')},
    'equipamentos': {'model': Asset, 'form': AssetForm, 'title': 'Equipamentos', 'singular': 'equipamento',
                     'description': 'Identifique cada equipamento por patrimônio e número de série.',
                     'search': ('tag', 'serial', 'item__name', 'item__category', 'branch__name', 'branch__code', 'location', 'notes')},
}


def configuration(request, kind, action):
    if kind not in CATALOGS:
        raise Http404
    config = CATALOGS[kind]
    model_name = config['model']._meta.model_name
    if not request.user.has_perm(f'inventory.{action}_{model_name}'):
        raise PermissionDenied
    tabs = [{'kind': key, 'title': value['title']} for key, value in CATALOGS.items()
            if request.user.has_perm(f'inventory.view_{value["model"]._meta.model_name}')]
    return {**config, 'kind': kind, 'tabs': tabs,
            'can_add': request.user.has_perm(f'inventory.add_{model_name}'),
            'can_change': request.user.has_perm(f'inventory.change_{model_name}')}


@login_required
def index(request):
    for kind, config in CATALOGS.items():
        if request.user.has_perm(f'inventory.view_{config["model"]._meta.model_name}'):
            return redirect('catalog-list', kind=kind)
    raise PermissionDenied


@login_required
def listing(request, kind):
    context = configuration(request, kind, 'view')
    records = context['model'].objects.all()
    if kind == 'equipamentos':
        records = records.select_related('item', 'branch')
    query = request.GET.get('q', '').strip()
    if query:
        filters = Q()
        for field in context['search']:
            filters |= Q(**{f'{field}__icontains': query})
        records = records.filter(filters)
    status = request.GET.get('status', '')
    if kind != 'equipamentos' and status in ('active', 'inactive'):
        records = records.filter(active=status == 'active')
    context.update(page=Paginator(records, 30).get_page(request.GET.get('page')), q=query, status=status)
    return render(request, 'inventory/catalog_list.html', context)


@login_required
@transaction.atomic
def edit(request, kind, pk=None):
    context = configuration(request, kind, 'change' if pk else 'add')
    # Lock the existing record while saving so a movement cannot overwrite an edit.
    instance = get_object_or_404(context['model'].objects.select_for_update(), pk=pk) if pk else None
    form = context['form'](request.POST if request.method == 'POST' else None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        record = form.save()
        LogEntry.objects.log_actions(user_id=request.user.pk, queryset=[record],
            action_flag=CHANGE if pk else ADDITION,
            change_message=[{'changed': {'fields': form.changed_data}}] if pk else [{'added': {}}])
        messages.success(request, 'Cadastro atualizado com sucesso.' if pk else 'Cadastro criado com sucesso.')
        if request.user.has_perm(f'inventory.view_{record._meta.model_name}'):
            return redirect('catalog-list', kind=kind)
        return redirect('catalog-new', kind=kind)
    context.update(form=form, record=instance)
    return render(request, 'inventory/catalog_form.html', context)


@login_required
@permission_required('inventory.change_balance', raise_exception=True)
@transaction.atomic
def stock_details(request, pk):
    balance = get_object_or_404(Balance.objects.select_for_update().select_related('branch', 'item'), pk=pk)
    form = StockDetailsForm(request.POST if request.method == 'POST' else None, instance=balance)
    if request.method == 'POST' and form.is_valid():
        record = form.save(commit=False)
        record.save(update_fields=['location', 'condition', 'notes'])
        LogEntry.objects.log_actions(user_id=request.user.pk, queryset=[record], action_flag=CHANGE,
            change_message=[{'changed': {'fields': form.changed_data}}])
        messages.success(request, 'Detalhes do estoque atualizados.')
        return redirect('dashboard')
    return render(request, 'inventory/stock_details.html', {'form': form, 'balance': balance})
