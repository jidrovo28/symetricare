from django.urls import path
from . import views
urlpatterns = [
    path('',             views.view_cuentas,     name='finanzas'),
    path('movimientos/', views.view_movimientos,  name='movimientos'),
]
