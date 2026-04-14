from django.urls import path
from . import views
urlpatterns = [
    path('',               views.view_citas,         name='citas'),
    path('calendario/',    views.view_calendario,     name='calendario'),
    path('disponibilidad/',views.view_disponibilidad, name='disponibilidad'),
]
