from django.db import models
from django.core.validators import MinValueValidator
from apps.core.models import ModeloBase


class Consulta(ModeloBase):
    PENDIENTE  = 'pendiente'
    ATENDIDA   = 'atendida'
    CANCELADA  = 'cancelada'
    ESTADO_CHOICES = [(PENDIENTE,'Pendiente'),(ATENDIDA,'Atendida'),(CANCELADA,'Cancelada')]

    paciente          = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='consultas')
    profesional       = models.ForeignKey('core.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='consultas')
    cita = models.ForeignKey('citas.Cita', on_delete=models.PROTECT, related_name='cita', null=True, blank=True)
    estado            = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ATENDIDA)
    num_hijos         = models.IntegerField(default=0)
    motivo_consulta   = models.TextField()
    observaciones     = models.TextField(blank=True)
    diagnostico       = models.TextField(blank=True)
    descuento         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total             = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    abono             = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo             = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    facturar          = models.BooleanField(default=False)
    cita              = models.OneToOneField('citas.Cita', null=True, blank=True,
                         on_delete=models.SET_NULL, related_name='consulta')

    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Consulta {self.pk} — {self.paciente.nombre_completo}"

    def calcular_totales(self):
        sub = sum(float(t.costo) for t in self.tratamientos.filter(status=True))
        self.subtotal = round(sub, 2)
        self.total    = round(max(0, sub - float(self.descuento)), 2)
        self.saldo    = round(max(0, float(self.total) - float(self.abono)), 2)
        self.save(update_fields=['subtotal','total','saldo'])


class TratamientoPropuesto(ModeloBase):
    consulta     = models.ForeignKey(Consulta, on_delete=models.CASCADE,
                    related_name='tratamientos')
    servicio     = models.ForeignKey('servicios.Servicio', on_delete=models.PROTECT)
    tipo_servicio = models.ForeignKey('servicios.TipoServicio', null=True, blank=True,
                    on_delete=models.SET_NULL)
    observacion  = models.TextField(blank=True)
    costo        = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        if not self.costo and self.servicio_id:
            self.costo = self.servicio.precio
        if not self.tipo_servicio_id and self.servicio_id:
            self.tipo_servicio = self.servicio.tipo
        super().save(*args, **kwargs)
