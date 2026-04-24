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

class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=True)

class Clinica(ModeloBase):
    nombre = models.CharField(max_length=500, default='Symetricare')
    ruc = models.CharField(max_length=20, blank=True)
    razon_social = models.CharField(max_length=200, blank=True)
    nombre_comercial = models.CharField(max_length=150, blank=True)
    direccion = models.TextField(blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='clinica/', blank=True, null=True)
    color_primario = models.CharField(max_length=7, default='#0d6efd')
    ciudad = models.CharField(max_length=100, blank=True)
    pais = models.CharField(max_length=100, default='Ecuador')
    # SRI Ecuador
    contribuyente_especial = models.CharField(max_length=20, blank=True)
    obligado_contabilidad = models.BooleanField(default=False)
    serie_establecimiento = models.CharField(max_length=3, default='001')
    serie_punto_emision = models.CharField(max_length=3, default='001')
    sri_ambiente = models.CharField(max_length=1, choices=[('1','Pruebas'),('2','Produccion')], default='1')
    certificado_p12 = models.FileField(upload_to='certificados/', blank=True, null=True)
    clave_certificado = models.CharField(max_length=200, blank=True)
    firma_ec_jar = models.FileField(upload_to='certificados/', blank=True, null=True, verbose_name='FirmaElectronica.jar', help_text='Archivo FirmaElectronica.jar para firma XAdES-BES')
    java_home = models.CharField(max_length=300, blank=True, verbose_name='JAVA_HOME', help_text='Ruta al directorio de Java 8/17/21 (ej: /usr/lib/jvm/java-17-openjdk). ' 'Vacío = usar el Java del PATH del sistema.')

    class Meta:
        verbose_name = 'Clinica'

    def __str__(self):
        return self.nombre

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj