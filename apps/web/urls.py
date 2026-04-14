from django.urls import path
from . import views
urlpatterns = [
    path('',          views.home,         name='home'),
    path('reservar/', views.reservar_cita, name='reservar'),
    path('api/slots/',views.slots_web,    name='slots_web'),
]
