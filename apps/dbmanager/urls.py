from django.urls import path
from apps.dbmanager import views
urlpatterns = [
    path('',        views.view_dbmanager, name='dbmanager'),
    path('schema/', views.view_schema,    name='dbmanager_schema'),
]
