from django.urls import path
from . import views
urlpatterns = [
    path('login',    views.login_view,   name='login'),
    path('logout',   views.logout_view,  name='logout'),
    path('dashboard',views.dashboard,    name='dashboard'),
]

from . import config_views
from django.urls import path as _path
urlpatterns += [
    _path('config/usuarios/', config_views.view_usuarios, name='config_usuarios'),
    _path('config/clinica/', views.config_clinica, name='config_clinica'),
    _path('config/firma/', views.config_firma, name='config_firma'),
]
