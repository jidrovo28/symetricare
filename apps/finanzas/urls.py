from django.urls import path
from . import views
urlpatterns = [
    path('iva/', views.view_tipo_iva, name='tipo_iva'),
    path('',             views.view_cuentas,     name='finanzas'),
    path('movimientos/', views.view_movimientos,  name='movimientos'),
    path('facturas/', views.lista, name='lista_facturas'),
    path('nueva/', views.nueva_factura, name='nueva_factura'),
    path('<int:pk>/', views.detalle, name='detalle_factura'),
    path('<int:pk>/estado/', views.cambiar_estado, name='cambiar_estado_factura'),
    path('<int:pk>/sri/', views.enviar_sri_view, name='enviar_sri_factura'),
    path('<int:pk>/reiniciar/', views.reiniciar_factura, name='reiniciar_factura'),
]
