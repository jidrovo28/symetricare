import decimal
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.core.models import ModeloBase, ActiveManager, Clinica
from apps.pacientes.models import Paciente


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

class Factura(ModeloBase):
    ESTADO_CHOICES = [
        ('pendiente','Pendiente'),('pagada','Pagada'),
        ('anulada','Anulada'),('parcial','Pago Parcial'),
    ]
    METODO_CHOICES = [
        ('efectivo','Efectivo'),('tarjeta','Tarjeta de Credito/Debito'),
        ('transferencia','Transferencia Bancaria'),('cheque','Cheque'),
        ('otro','Otro'),
    ]
    SRI_ESTADO_CHOICES = [
        ('no_enviada','No enviada'),('enviada','Enviada'),
        ('autorizada','Autorizada'),('rechazada','Rechazada'),
        ('no_aplica','No aplica'),('xmlpendiente','Xml generado'),
        ('xmlgenerado','Xml generado'),('xmlfirmado', 'Xml firmado')
    ]

    numero = models.CharField(max_length=20, unique=True, blank=True)
    # Clave de acceso SRI (49 digitos)
    clave_acceso = models.CharField(max_length=49, blank=True, unique=True, null=True)
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='facturas', blank=True, null=True)
    fecha = models.DateField(default=timezone.now, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    subtotal_0 = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True , help_text='Subtotal con tarifa 0%')
    subtotal_iva = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True , help_text='Subtotal gravado con IVA')
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=15, blank=True, null=True , help_text='Porcentaje IVA Ecuador (15%)')
    iva = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='pendiente', blank=True, null=True)
    metodo_pago = models.CharField(max_length=20, choices=METODO_CHOICES, default='efectivo', blank=True, null=True)
    notas = models.TextField(blank=True, null=True)
    # SRI
    sri_estado = models.CharField(max_length=15, choices=SRI_ESTADO_CHOICES, default='xmlpendiente', blank=True, null=True)
    sri_numero_autorizacion = models.CharField(max_length=49, blank=True, null=True)
    sri_fecha_autorizacion = models.DateTimeField(blank=True, null=True)
    sri_xml = models.TextField(help_text='XML generado enviado al SRI', blank=True, null=True)
    sri_xml_firmado = models.TextField(blank=True, null=True, help_text='XML firmado enviado al SRI')
    sri_respuesta = models.TextField(blank=True, null=True, help_text='Respuesta del SRI')
    sri_ambiente = models.CharField(max_length=1, default='1')

    objects = models.Manager()
    activos = ActiveManager()

    class Meta:
        verbose_name = 'Factura'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"FAC-{self.numero} | {self.paciente}"

    def save(self, *args, **kwargs):
        if not self.numero:
            last = Factura.objects.order_by('-id').first()
            next_id = (last.id + 1) if last else 1
            self.numero = f"{next_id:09d}"
        super().save(*args, **kwargs)

    def calcular_totales(self, porcentaje_iva=None):
        if porcentaje_iva is not None:
            self.porcentaje_iva = porcentaje_iva

        detalles = list(self.detalles.all())
        total_items = sum(d.subtotal for d in detalles)

        descuento_total = Decimal(self.descuento or 0)

        # 🔥 distribuir descuento proporcionalmente
        for d in detalles:
            if total_items > 0:
                proporcion = Decimal(d.subtotal) / Decimal(total_items)
                d.descuento = (descuento_total * proporcion).quantize(Decimal('0.01'))
            else:
                d.descuento = Decimal('0.00')

            # recalcular subtotal del detalle
            d.subtotal = Decimal(d.precio_unitario) * Decimal(d.cantidad) - d.descuento
            d.save()

        # 🔥 recalcular totales correctos
        total_sin_impuestos = sum(d.subtotal for d in detalles)
        total_descuento = sum(d.descuento for d in detalles)

        self.subtotal = total_sin_impuestos
        self.subtotal_0 = total_sin_impuestos
        self.subtotal_iva = 0
        self.iva = 0
        self.total = total_sin_impuestos
        self.descuento = total_descuento

        self.save()

    @property
    def numero_formateado(self):
        from apps.core.models import Clinica
        c = Clinica.get()
        return f"{c.serie_establecimiento}-{c.serie_punto_emision}-{self.numero}"

class DetalleFactura(ModeloBase):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='detalles')
    descripcion = models.CharField(max_length=300)
    cantidad = models.PositiveSmallIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tiene_iva = models.BooleanField(default=False)
    codigo_principal = models.CharField(max_length=30, blank=True)

    objects = models.Manager()

    class Meta:
        verbose_name = 'Detalle de Factura'

    def save(self, *args, **kwargs):
        self.subtotal = (self.cantidad * self.precio_unitario) - self.descuento
        super().save(*args, **kwargs)

    def __str__(self):
        return self.descripcion

class ConsultaFactura(ModeloBase):
    factura = models.ForeignKey(Factura, on_delete=models.PROTECT, related_name='facturaconsulta')
    consulta = models.ForeignKey('consultas.Consulta', on_delete=models.PROTECT, related_name='consultafacturada')
    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.consulta}"

class TratamientoConsultaFactura(ModeloBase):
    consultafactura = models.ForeignKey(ConsultaFactura, on_delete=models.PROTECT, related_name='consultafactura', null=True, blank=True)
    visita = models.ForeignKey('consultas.VisitaTratamiento', on_delete=models.PROTECT, null=True, blank=True)
    servicio = models.ForeignKey('servicios.Servicio', on_delete=models.PROTECT, null=True, blank=True)
    tipo_servicio = models.ForeignKey('servicios.TipoServicio', null=True, blank=True, on_delete=models.SET_NULL)
    descripcion = models.TextField(null=True, blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.consulta}"
