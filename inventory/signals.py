from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .roles import assign_inventory_access


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='inventory_default_user_access')
def default_user_access(sender, instance, created, raw=False, using='default', **kwargs):
    if created and not raw and not instance.is_superuser:
        assign_inventory_access(instance, using=using)
