from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login


class TechnicalAdminOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.resolver_match and 'admin' in request.resolver_match.namespaces:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.is_active or not request.user.is_superuser:
                raise PermissionDenied
