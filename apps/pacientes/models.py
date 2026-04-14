from django.db import models
from apps.core.models import ModeloBase


class Paciente(ModeloBase):
    TIPO_CEDULA    = 'cedula'
    TIPO_PASAPORTE = 'pasaporte'
    TIPO_RUC       = 'ruc'
    TIPO_CHOICES   = [(TIPO_CEDULA,'Cédula'),(TIPO_PASAPORTE,'Pasaporte'),(TIPO_RUC,'RUC')]

    tipo_identificacion      = models.CharField(max_length=15, choices=TIPO_CHOICES, default=TIPO_CEDULA)
    identificacion           = models.CharField(max_length=20, unique=True)
    nombres                  = models.CharField(max_length=150)
    apellido1                = models.CharField(max_length=100)
    apellido2                = models.CharField(max_length=100, blank=True)
    telefono                 = models.CharField(max_length=20, blank=True)
    edad                     = models.IntegerField(null=True, blank=True)
    fecha_nacimiento         = models.DateField(null=True, blank=True)
    direccion                = models.TextField(blank=True)
    email                    = models.EmailField(blank=True)
    foto                     = models.ImageField(upload_to='pacientes/', null=True, blank=True)
    num_hijos                = models.IntegerField(default=0)
    observaciones_generales  = models.TextField(blank=True)

    class Meta:
        ordering = ['apellido1', 'nombres']

    def __str__(self):
        return f"{self.apellido1} {self.apellido2} {self.nombres} — {self.identificacion}".strip()

    @property
    def nombre_completo(self):
        return f"{self.apellido1} {self.apellido2} {self.nombres}".strip()

    def save(self, *args, **kwargs):
        if self.fecha_nacimiento and not self.edad:
            from datetime import date
            hoy = date.today()
            self.edad = hoy.year - self.fecha_nacimiento.year - (
                (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        super().save(*args, **kwargs)


# ── Modelos de antecedentes: vinculados a la CONSULTA ────────────────────────
# Cada consulta registra su propio estado clínico del paciente en ese momento.

class APF(ModeloBase):
    """Antecedente Patológico Familiar — registrado por consulta"""
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='apf', null=True, blank=True)
    descripcion = models.TextField()

    class Meta: ordering = ['-fecha_creacion']
    def __str__(self): return f"APF: {self.descripcion[:50]}"


class APP(ModeloBase):
    """Antecedente Patológico Personal — registrado por consulta"""
    consulta          = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='app', null=True, blank=True)
    descripcion       = models.TextField()
    fecha_diagnostico = models.DateField(null=True, blank=True)

    class Meta: ordering = ['-fecha_creacion']


class Alergia(ModeloBase):
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='alergias', null=True, blank=True)
    descripcion = models.CharField(max_length=300)
    class Meta: ordering = ['-fecha_creacion']


class Medicamento(ModeloBase):
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='medicamentos', null=True, blank=True)
    descripcion = models.CharField(max_length=300)
    class Meta: ordering = ['-fecha_creacion']


class Suplemento(ModeloBase):
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='suplementos', null=True, blank=True)
    descripcion = models.CharField(max_length=300)
    class Meta: ordering = ['-fecha_creacion']


class Habito(ModeloBase):
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='habitos', null=True, blank=True)
    descripcion = models.CharField(max_length=300)
    class Meta: ordering = ['-fecha_creacion']


class ActividadFisica(ModeloBase):
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='actividades_fisicas', null=True, blank=True)
    descripcion = models.CharField(max_length=300)
    class Meta: ordering = ['-fecha_creacion']


class TratamientoRealizado(ModeloBase):
    """Tratamientos ya realizados al momento de la consulta"""
    consulta    = models.ForeignKey('consultas.Consulta', on_delete=models.CASCADE, related_name='tratamientos_realizados', null=True, blank=True)
    descripcion = models.TextField()
    fecha       = models.DateField(null=True, blank=True)
    class Meta: ordering = ['-fecha_creacion']
