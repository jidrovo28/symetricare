from django.db import models
from apps.core.models import ModeloBase


class Consulta(ModeloBase):
    PENDIENTE = 'pendiente'
    ATENDIDA  = 'atendida'
    CANCELADA = 'cancelada'
    ESTADO_CHOICES = [
        (PENDIENTE, 'Pendiente'),
        (ATENDIDA,  'Atendida'),
        (CANCELADA, 'Cancelada'),
    ]

    paciente        = models.ForeignKey('pacientes.Paciente',
                        on_delete=models.PROTECT, related_name='consultas')
    profesional     = models.ForeignKey('core.Usuario',
                        on_delete=models.SET_NULL, null=True, blank=True,
                        related_name='consultas')
    cita            = models.OneToOneField('citas.Cita', null=True, blank=True,
                        on_delete=models.SET_NULL, related_name='consulta')
    estado          = models.CharField(max_length=15,
                        choices=ESTADO_CHOICES, default=PENDIENTE)
    num_hijos       = models.IntegerField(default=0)
    motivo_consulta = models.TextField()
    observaciones   = models.TextField(blank=True)
    diagnostico     = models.TextField(blank=True)
    facturar        = models.BooleanField(default=False)

    # Totales — calculados a partir de VisitaTratamiento y AbonoConsulta
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento= models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    abono    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo    = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f'Consulta {self.pk} — {self.paciente.nombre_completo}'

    def recalcular_totales(self):
        """
        Recalcula totales a partir de VisitaTratamiento y AbonoConsulta.
        Se llama automáticamente en save()/delete() de ambos modelos.
        """
        from django.db.models import Sum
        subtotal = (self.visitas.filter(status=True)
                    .aggregate(t=Sum('costo'))['t'] or 0)
        abono    = (self.abonos.filter(status=True)
                    .aggregate(t=Sum('monto'))['t'] or 0)
        self.subtotal = round(float(subtotal), 2)
        self.total    = round(max(0, float(subtotal) - float(self.descuento)), 2)
        self.abono    = round(float(abono), 2)
        self.saldo    = round(max(0, float(self.total) - float(self.abono)), 2)
        self.save(update_fields=['subtotal', 'total', 'abono', 'saldo'])

    # Alias para compatibilidad con código que llame calcular_totales()
    def calcular_totales(self):
        self.recalcular_totales()

    def num_visitas(self):
        return self.visitas.filter(status=True).count()

    def get_tratamientos(self):
        return self.tratamientos.filter(status=True)

    def get_visitas(self):
        return self.visitas.filter(status=True)


class TratamientoPropuesto(ModeloBase):
    """Plan de tratamientos acordado en la consulta. NO genera deuda."""
    consulta      = models.ForeignKey(Consulta, on_delete=models.CASCADE,
                      related_name='tratamientos')
    servicio      = models.ForeignKey('servicios.Servicio',
                      on_delete=models.PROTECT)
    tipo_servicio = models.ForeignKey('servicios.TipoServicio',
                      null=True, blank=True, on_delete=models.SET_NULL)
    observacion   = models.TextField(blank=True)
    costo         = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        if self.servicio_id:
            if not self.costo:
                self.costo = self.servicio.precio
            if not self.tipo_servicio_id:
                self.tipo_servicio = self.servicio.tipo
        super().save(*args, **kwargs)


class VisitaTratamiento(ModeloBase):
    """
    Tratamiento realizado en una visita concreta.
    ESTE modelo genera la deuda — cada registro suma al total de la consulta.
    """
    consulta              = models.ForeignKey(Consulta, on_delete=models.CASCADE,
                              related_name='visitas')
    fecha                 = models.DateField()
    tratamiento_propuesto = models.ForeignKey(TratamientoPropuesto,
                              null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='visitas')
    servicio              = models.ForeignKey('servicios.Servicio',
                              on_delete=models.PROTECT)
    tipo_servicio         = models.ForeignKey('servicios.TipoServicio',
                              null=True, blank=True, on_delete=models.SET_NULL)
    descripcion           = models.TextField(blank=True)
    costo                 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    abono                 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    forma_pago            = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['-fecha', '-fecha_creacion']

    def __str__(self):
        return f'Visita {self.fecha} | {self.servicio.nombre} | ${self.costo}'

    def save(self, *args, **kwargs):
        if self.servicio_id:
            if not self.costo:
                self.costo = self.servicio.precio
            if not self.tipo_servicio_id:
                self.tipo_servicio = self.servicio.tipo
        super().save(*args, **kwargs)
        self.consulta.recalcular_totales()

    def delete(self, *args, **kwargs):
        consulta = self.consulta   # guardar ref antes de borrar
        super().delete(*args, **kwargs)
        consulta.recalcular_totales()


class AbonoConsulta(ModeloBase):
    """Pagos parciales del paciente."""
    consulta   = models.ForeignKey(Consulta, on_delete=models.CASCADE,
                   related_name='abonos')
    monto      = models.DecimalField(max_digits=10, decimal_places=2)
    forma_pago = models.CharField(max_length=50, default='Efectivo')
    nota       = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-fecha_creacion']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.consulta.recalcular_totales()

    def delete(self, *args, **kwargs):
        consulta = self.consulta
        super().delete(*args, **kwargs)
        consulta.recalcular_totales()
