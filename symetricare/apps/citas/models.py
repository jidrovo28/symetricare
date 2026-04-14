from django.db import models
from apps.core.models import ModeloBase


class DisponibilidadHoraria(ModeloBase):
    """Configura los días y horarios en que se atiende."""
    LUNES = 0; MARTES = 1; MIERCOLES = 2; JUEVES = 3
    VIERNES = 4; SABADO = 5; DOMINGO = 6
    DIA_CHOICES = [
        (LUNES,'Lunes'),(MARTES,'Martes'),(MIERCOLES,'Miércoles'),
        (JUEVES,'Jueves'),(VIERNES,'Viernes'),(SABADO,'Sábado'),(DOMINGO,'Domingo'),
    ]
    dia_semana   = models.IntegerField(choices=DIA_CHOICES)
    hora_inicio  = models.TimeField()
    hora_fin     = models.TimeField()
    duracion_min = models.IntegerField(default=60, help_text='Duración de cada slot en minutos')
    activo       = models.BooleanField(default=True)
    profesional  = models.ForeignKey('core.Usuario', null=True, blank=True,
                    on_delete=models.SET_NULL, related_name='disponibilidades')

    class Meta:
        ordering = ['dia_semana','hora_inicio']

    def __str__(self):
        return f"{self.get_dia_semana_display()} {self.hora_inicio}–{self.hora_fin}"


class BloqueoFecha(ModeloBase):
    """Fechas específicas bloqueadas (feriados, vacaciones)."""
    fecha       = models.DateField()
    motivo      = models.CharField(max_length=200, blank=True)
    profesional = models.ForeignKey('core.Usuario', null=True, blank=True,
                   on_delete=models.SET_NULL)

    class Meta:
        ordering = ['fecha']


class Cita(ModeloBase):
    PENDIENTE   = 'pendiente'
    CONFIRMADA  = 'confirmada'
    ATENDIDA    = 'atendida'
    CANCELADA   = 'cancelada'
    NO_ASISTIO  = 'no_asistio'
    ESTADO_CHOICES = [
        (PENDIENTE,  'Pendiente'),
        (CONFIRMADA, 'Confirmada'),
        (ATENDIDA,   'Atendida'),
        (CANCELADA,  'Cancelada'),
        (NO_ASISTIO, 'No asistió'),
    ]

    paciente    = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT,
                   related_name='citas')
    profesional = models.ForeignKey('core.Usuario', null=True, blank=True,
                   on_delete=models.SET_NULL, related_name='citas')
    servicio    = models.ForeignKey('servicios.Servicio', null=True, blank=True,
                   on_delete=models.SET_NULL)
    fecha       = models.DateField()
    hora        = models.TimeField()
    duracion_min = models.IntegerField(default=60)
    estado      = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=PENDIENTE)
    notas       = models.TextField(blank=True)
    reservado_web = models.BooleanField(default=False)
    nombre_web  = models.CharField(max_length=200, blank=True)
    email_web   = models.CharField(max_length=200, blank=True)
    telefono_web = models.CharField(max_length=20, blank=True)
    token_confirmacion = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['fecha','hora']

    def __str__(self):
        return f"{self.fecha} {self.hora} — {self.paciente.nombre_completo if self.paciente_id else self.nombre_web}"
