from django.db import models
from django.contrib.auth.models import AbstractUser


class ModeloBase(models.Model):
    status               = models.BooleanField(default=True)
    fecha_creacion       = models.DateTimeField(auto_now_add=True)
    fecha_modificacion   = models.DateTimeField(auto_now=True)
    usuario_creacion     = models.ForeignKey('core.Usuario', null=True, blank=True,
                            on_delete=models.SET_NULL, related_name='%(app_label)s_%(class)s_creados')
    usuario_modificacion = models.ForeignKey('core.Usuario', null=True, blank=True,
                            on_delete=models.SET_NULL, related_name='%(app_label)s_%(class)s_modificados')

    class Meta:
        abstract = True
        ordering = ['-fecha_creacion']

    def delete(self, *args, **kwargs):
        self.status = False
        self.save(update_fields=['status', 'fecha_modificacion'])


class Usuario(AbstractUser):
    ROL_ADMIN     = 'admin'
    ROL_MEDICO    = 'medico'
    ROL_RECEPCION = 'recepcion'
    ROL_CHOICES = [
        (ROL_ADMIN,     'Administrador'),
        (ROL_MEDICO,    'Médico/Especialista'),
        (ROL_RECEPCION, 'Recepción'),
    ]
    MODULOS = [
        ('pacientes',  'Pacientes'),
        ('consultas',  'Consultas'),
        ('citas',      'Citas'),
        ('servicios',  'Servicios'),
        ('finanzas',   'Finanzas'),
        ('config',     'Configuración'),
    ]

    rol      = models.CharField(max_length=15, choices=ROL_CHOICES, default=ROL_RECEPCION)
    telefono = models.CharField(max_length=20, blank=True)
    activo_sistema = models.BooleanField(default=True)
    modulos_permitidos = models.JSONField(default=list, blank=True,
                          help_text='Lista de módulos a los que tiene acceso')

    @property
    def nombre_completo(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def es_admin(self):
        return self.rol == self.ROL_ADMIN or self.is_superuser

    def tiene_acceso(self, modulo):
        if self.es_admin: return True
        if not self.modulos_permitidos: return False
        return modulo in self.modulos_permitidos

    def __str__(self):
        return f"{self.nombre_completo} [{self.get_rol_display()}]"
