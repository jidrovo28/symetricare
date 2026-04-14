from django.urls import path
from . import views
urlpatterns = [
    path('',             views.view_pacientes, name='pacientes'),
    path('<int:pk>/ficha/', views.view_ficha,  name='ficha_paciente'),
]
