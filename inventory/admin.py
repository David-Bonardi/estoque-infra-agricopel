from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .roles import assign_inventory_access
from .models import Asset, Balance, Branch, Item, Movement


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class InventoryUserAdmin(UserAdmin):
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Admin forms save group choices after post_save; retain the default on creation.
        if not change and not form.instance.is_superuser:
            assign_inventory_access(form.instance, using=form.instance._state.db)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'active')
    search_fields = ('code', 'name')
    list_filter = ('active',)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'tracking', 'active')
    search_fields = ('name',)
    list_filter = ('tracking', 'active')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('tag', 'item', 'serial', 'branch')
    search_fields = ('tag', 'serial', 'item__name')
    list_filter = ('branch', 'item')
    readonly_fields = ('branch',)

    def get_readonly_fields(self, request, obj=None):
        return ('branch', 'item') if obj else ('branch',)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Balance)
class BalanceAdmin(ReadOnlyAdmin):
    list_display = ('branch', 'item', 'quantity')
    list_filter = ('branch',)
    search_fields = ('item__name', 'branch__name', 'branch__code')


@admin.register(Movement)
class MovementAdmin(ReadOnlyAdmin):
    list_display = ('created_at', 'kind', 'item', 'asset', 'quantity', 'source', 'destination', 'actor', 'reason')
    list_filter = ('kind', 'source', 'destination', 'created_at')
    search_fields = ('item__name', 'asset__tag', 'actor__username', 'reason')


admin.site.site_header = 'Estoque Infra — Administração'
admin.site.site_title = 'Estoque Infra'
