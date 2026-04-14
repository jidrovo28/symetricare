from django.db import models
from apps.core.models import ModeloBase


class CuentaPaciente(ModeloBase):
    """Resumen financiero por paciente."""
    paciente      = models.OneToOneField('pacientes.Paciente', on_delete=models.CASCADE,
                     related_name='cuenta')
    total_cobrado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_pagado  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo         = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['-fecha_creacion']

    def recalcular(self):
        from apps.consultas.models import Consulta
        qs = Consulta.objects.filter(status=True, paciente=self.paciente)
        from django.db.models import Sum
        self.total_cobrado = qs.aggregate(t=Sum('total'))['t'] or 0
        self.total_pagado  = qs.aggregate(t=Sum('abono'))['t'] or 0
        self.saldo         = float(self.total_cobrado) - float(self.total_pagado)
        self.save(update_fields=['total_cobrado','total_pagado','saldo'])


class MovimientoFinanciero(ModeloBase):
    """Cada pago o cargo registrado."""
    COBRO   = 'cobro'
    ABONO   = 'abono'
    TIPO_CHOICES = [(COBRO,'Cobro'),(ABONO,'Abono')]

    paciente  = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT,
                 related_name='movimientos')
    consulta  = models.ForeignKey('consultas.Consulta', null=True, blank=True,
                 on_delete=models.SET_NULL, related_name='movimientos')
    tipo      = models.CharField(max_length=10, choices=TIPO_CHOICES)
    monto     = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.CharField(max_length=300, blank=True)
    forma_pago  = models.CharField(max_length=50, default='Efectivo',
                   choices=[('Efectivo','Efectivo'),('Transferencia','Transferencia'),
                             ('Tarjeta','Tarjeta'),('Cheque','Cheque')])
    referencia  = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-fecha_creacion']
