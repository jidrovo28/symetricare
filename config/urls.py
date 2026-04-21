from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('apps.web.urls')),
    path('', include('apps.core.urls')),
    path('pacientes/', include('apps.pacientes.urls')),
    path('consultas/', include('apps.consultas.urls')),
    path('servicios/', include('apps.servicios.urls')),
    path('citas/', include('apps.citas.urls')),
    path('finanzas/', include('apps.finanzas.urls')),
    path('dbmanager/', include('apps.dbmanager.urls')),
    path('db/', include('apps.dbmanager.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
