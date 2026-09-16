from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from .forms import MovementForm
from .models import Asset, Balance, Branch, Item, Movement
from .services import record_movement


@login_required
@permission_required(('inventory.view_balance', 'inventory.view_asset'), raise_exception=True) # type: ignore
def dashboard(request):
    query = request.GET.get('q', '').strip()
    branch = request.GET.get('branch', '')
    balances = Balance.objects.select_related('item', 'branch').filter(quantity__gt=0)
    assets = Asset.objects.select_related('item', 'branch').all()
    if query:
        balances = balances.filter(Q(item__name__icontains=query) | Q(item__category__icontains=query) | Q(location__icontains=query))
        assets = assets.filter(Q(item__name__icontains=query) | Q(tag__icontains=query) | Q(serial__icontains=query)
                               | Q(item__category__icontains=query) | Q(location__icontains=query))
    category = request.GET.get('category', '')
    if category:
        balances = balances.filter(item__category=category)
        assets = assets.filter(item__category=category)
    if branch.isdigit():
        balances = balances.filter(branch_id=branch)
        assets = assets.filter(branch_id=branch)
    return render(request, 'inventory/dashboard.html', {
        'balances': Paginator(balances.order_by('branch__code', 'item__name'), 30).get_page(request.GET.get('materials_page')),
        'assets': Paginator(assets, 30).get_page(request.GET.get('assets_page')),
        'branches': Branch.objects.all(), 'q': query, 'selected_branch': branch,
        'categories': Item.objects.exclude(category='').order_by('category').values_list('category', flat=True).distinct(),
        'selected_category': category,
        'material_total': balances.aggregate(total=Sum('quantity'))['total'] or 0,
        'asset_total': assets.filter(branch__isnull=False).count(),
        'asset_summary': assets.filter(branch__isnull=False).values('branch__code', 'branch__name', 'item__name').annotate(total=Count('id')).order_by('branch__code', 'item__name'),
    })


@login_required
@permission_required('inventory.add_movement', raise_exception=True)
def move(request):
    form = MovementForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            record_movement(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Movimentação registrada com sucesso.')
            return redirect('movement-new')
    return render(request, 'inventory/move.html', {'form': form})


@login_required
@permission_required('inventory.view_movement', raise_exception=True)
def history(request):
    movements = Movement.objects.select_related('item', 'asset', 'source', 'destination', 'actor')
    query = request.GET.get('q', '').strip()
    if query:
        movements = movements.filter(Q(item__name__icontains=query) | Q(asset__tag__icontains=query)
                                    | Q(reason__icontains=query) | Q(actor__username__icontains=query)
                                    | Q(recipient__icontains=query) | Q(recipient_department__icontains=query))
    branch = request.GET.get('branch', '')
    if branch.isdigit():
        movements = movements.filter(Q(source_id=branch) | Q(destination_id=branch))
    return render(request, 'inventory/history.html', {'page': Paginator(movements, 30).get_page(request.GET.get('page')),
        'q': query, 'branches': Branch.objects.all(), 'selected_branch': branch})
