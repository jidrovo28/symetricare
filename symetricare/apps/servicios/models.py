from django.db import models
from apps.core.models import ModeloBase


class TipoServicio(ModeloBase):
    nombre      = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=300, blank=True)
    color       = models.CharField(max_length=7, default='#6366f1')

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Servicio(ModeloBase):
    tipo        = models.ForeignKey(TipoServicio, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='servicios')
    nombre      = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio      = models.DecimalField(max_digits=10, decimal_places=2)
    activo      = models.BooleanField(default=True)
    duracion_min = models.IntegerField(default=60, help_text='Duración en minutos')

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} — ${self.precio}"
