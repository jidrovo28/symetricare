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
        """
        Calcula los totales directamente desde las fuentes:
        - total_cobrado → suma de VisitaTratamiento (lo que se ha realizado)
        - total_pagado  → suma de AbonoConsulta (lo que el paciente ha pagado)
        - saldo         → diferencia entre ambos
        """
        from apps.consultas.models import VisitaTratamiento, AbonoConsulta
        from django.db.models import Sum

        consultas_ids = self.paciente.consultas.filter(
            status=True).values_list('pk', flat=True)

        self.total_cobrado = (
                VisitaTratamiento.objects
                .filter(status=True, consulta_id__in=consultas_ids, contabilizar_costo=True)
                .aggregate(t=Sum('costo'))['t'] or 0
        )
        self.total_pagado = (
                AbonoConsulta.objects
                .filter(status=True, consulta_id__in=consultas_ids)
                .aggregate(t=Sum('monto'))['t'] or 0
        )
        total_saldo = 0
        if float(self.total_pagado) <= float(self.total_cobrado):
            total_saldo = float(self.total_cobrado) - float(self.total_pagado)
        self.saldo = total_saldo
        self.save(update_fields=['total_cobrado', 'total_pagado', 'saldo'])


class MovimientoFinanciero(ModeloBase):
    """Cada pago o cargo registrado."""
    COBRO   = 'cobro'
    ABONO   = 'abono'
    ABONOADELANTADO   = 'abonoadelantado'
    TIPO_CHOICES = [(COBRO,'Cobro'),(ABONO,'Abono'), (ABONOADELANTADO, 'Abono Adelantado')]

    paciente  = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT,
                 related_name='movimientos')
    consulta  = models.ForeignKey('consultas.Consulta', null=True, blank=True, on_delete=models.SET_NULL, related_name='movimientos')
    abono  = models.ForeignKey('consultas.AbonoConsulta', null=True, blank=True, on_delete=models.SET_NULL, related_name='abonos')
    tipo      = models.CharField(max_length=20, choices=TIPO_CHOICES, blank=True, null=True)
    monto     = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.CharField(max_length=300, blank=True)
    forma_pago  = models.CharField(max_length=50, default='Efectivo',
                   choices=[('Efectivo','Efectivo'),('Transferencia','Transferencia'),
                             ('Tarjeta','Tarjeta'),('Cheque','Cheque')])
    referencia  = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-fecha_creacion']
