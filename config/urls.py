"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from inventory import views
from inventory import catalog
from django.urls import path

urlpatterns = [
    path('estoque/<int:pk>/detalhes/', catalog.stock_details, name='stock-details'),
    path('cadastros/', catalog.index, name='catalog-index'),
    path('cadastros/<slug:kind>/', catalog.listing, name='catalog-list'),
    path('cadastros/<slug:kind>/novo/', catalog.edit, name='catalog-new'),
    path('cadastros/<slug:kind>/<int:pk>/editar/', catalog.edit, name='catalog-edit'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('movimentacoes/nova/', views.move, name='movement-new'),
    path('movimentacoes/', views.history, name='history'),
    path('admin/', admin.site.urls),
]
