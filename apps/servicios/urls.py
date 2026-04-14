from django.urls import path
from . import views
urlpatterns = [
    path('',      views.view_servicios, name='servicios'),
    path('tipos/',views.view_tipos,     name='tipos_servicio'),
]
