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

class TipoIva(ModeloBase):
    """
    Tarifas de IVA configurables. Ecuador maneja 0%, 5%, 12%, 15%.
    El código SRI: 0=0%, 2=12%, 3=14%, 4=15%, 5=5%
    """
    descripcion  = models.CharField(max_length=100)
    porcentaje   = models.DecimalField(max_digits=5, decimal_places=2,
                     help_text='Ej: 15.00 para IVA del 15%')
    codigo_sri   = models.CharField(max_length=5, blank=True,
                     help_text='Código del SRI: 0, 2, 3, 4, 5')
    es_default   = models.BooleanField(default=False,
                     help_text='IVA que se aplica por defecto al crear ítems')

    class Meta:
        ordering = ['porcentaje']
        verbose_name = 'Tipo de IVA'

    def __str__(self):
        return f'{self.descripcion} ({self.porcentaje}%)'

    def save(self, *args, **kwargs):
        # Solo puede haber un default
        if self.es_default:
            TipoIva.objects.exclude(pk=self.pk).update(es_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls):
        return cls.objects.filter(es_default=True).first()

class Factura(ModeloBase):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('pagada',    'Pagada'),
        ('anulada',   'Anulada'),
        ('parcial',   'Pago Parcial'),
    ]
    METODO_CHOICES = [
        ('efectivo',       'Efectivo'),
        ('tarjeta',        'Tarjeta de Crédito/Débito'),
        ('transferencia',  'Transferencia Bancaria'),
        ('cheque',         'Cheque'),
        ('otro',           'Otro'),
    ]
    SRI_ESTADO_CHOICES = [
        ('no_enviada',  'No enviada'),
        ('enviada',     'Enviada'),
        ('autorizada',  'Autorizada'),
        ('rechazada',   'Rechazada'),
        ('no_aplica',   'No aplica'),
        ('xmlpendiente','XML pendiente de firma'),
        ('xmlgenerado', 'XML generado'),
        ('xmlfirmado',  'XML firmado'),
    ]

    numero       = models.CharField(max_length=20, unique=True, blank=True)
    clave_acceso = models.CharField(max_length=49, blank=True, unique=True, null=True)
    paciente     = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT,
                     related_name='facturas', null=True, blank=True)
    fecha        = models.DateField(default=timezone.now, null=True, blank=True)

    # ── Totales ───────────────────────────────────────────────────────────────
    subtotal_0   = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                     help_text='Suma de bases gravadas al 0%')
    subtotal_iva = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                     help_text='Suma de bases gravadas con IVA > 0%')
    subtotal     = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                     help_text='subtotal_0 + subtotal_iva (sin IVA ni descuento)')
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=15,
                     help_text='% IVA aplicado (15% Ecuador)')
    iva          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total        = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                     help_text='subtotal + iva − descuento')

    # ── Datos ─────────────────────────────────────────────────────────────────
    estado      = models.CharField(max_length=15, choices=ESTADO_CHOICES,
                    default='pendiente', null=True, blank=True)
    metodo_pago = models.CharField(max_length=20, choices=METODO_CHOICES,
                    default='efectivo', null=True, blank=True)
    notas       = models.TextField(blank=True, null=True)

    # ── SRI ───────────────────────────────────────────────────────────────────
    sri_estado              = models.CharField(max_length=15,
                               choices=SRI_ESTADO_CHOICES,
                               default='xmlpendiente', null=True, blank=True)
    sri_numero_autorizacion = models.CharField(max_length=49, blank=True, null=True)
    sri_fecha_autorizacion  = models.DateTimeField(blank=True, null=True)
    sri_xml                 = models.TextField(blank=True, null=True,
                               help_text='XML sin firma enviado al SRI')
    sri_xml_firmado         = models.TextField(blank=True, null=True,
                               help_text='XML firmado enviado al SRI')
    sri_respuesta           = models.TextField(blank=True, null=True,
                               help_text='Respuesta del SRI')
    sri_ambiente            = models.CharField(max_length=1, default='1')

    objects = models.Manager()
    activos = ActiveManager()

    class Meta:
        verbose_name = 'Factura'
        ordering    = ['-fecha', '-id']

    def __str__(self):
        return f'FAC-{self.numero} | {self.paciente}'

    def save(self, *args, **kwargs):
        if not self.numero:
            last = Factura.objects.order_by('-id').first()
            self.numero = f'{(last.id + 1) if last else 1:09d}'
        super().save(*args, **kwargs)

    def calcular_totales(self):
        from decimal import Decimal, ROUND_HALF_UP
        from django.db.models import Sum
        Q2 = lambda v: v.quantize(Decimal('0.01'), ROUND_HALF_UP)

        dets = self.detalles.filter(status=True)

        # subtotal_sin_imp = base extraída (precio / (1 + pct))
        sub0 = Q2(dets.filter(aplica_iva=False)
                  .aggregate(t=Sum('subtotal_sin_imp'))['t'] or Decimal('0'))
        subI = Q2(dets.filter(aplica_iva=True)
                  .aggregate(t=Sum('subtotal_sin_imp'))['t'] or Decimal('0'))
        iva = Q2(dets.aggregate(t=Sum('iva'))['t'] or Decimal('0'))

        # subtotal = suma de precios con IVA incluido = sub0 + subI + iva
        subtotal = Q2(sub0 + subI + iva)
        desc = Q2(self.descuento or Decimal('0'))
        total = Q2(max(Decimal('0'), subtotal - desc))

        self.subtotal_0 = sub0
        self.subtotal_iva = subI
        self.iva = iva
        self.subtotal = subtotal
        self.total = total
        self.save(update_fields=['subtotal_0', 'subtotal_iva', 'iva', 'subtotal', 'total'])

    @property
    def numero_formateado(self):
        from apps.core.models import Clinica
        c = Clinica.get()
        return f'{c.serie_establecimiento}-{c.serie_punto_emision}-{self.numero}'

class DetalleFactura(ModeloBase):
    factura          = models.ForeignKey(Factura, on_delete=models.CASCADE,
                         related_name='detalles')
    descripcion      = models.CharField(max_length=300)
    cantidad         = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    precio_unitario  = models.DecimalField(max_digits=10, decimal_places=4,
                         help_text='Precio sin IVA')
    subtotal_sin_imp = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                         help_text='cantidad × precio_unitario, sin IVA')
    aplica_iva       = models.BooleanField(default=False)
    tipo_iva         = models.ForeignKey(TipoIva, null=True, blank=True,
                         on_delete=models.SET_NULL,
                         help_text='Tarifa de IVA aplicada a este ítem')
    iva              = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                         help_text='Valor del IVA = subtotal_sin_imp × porcentaje/100')
    subtotal         = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                         help_text='subtotal_sin_imp + iva')

    class Meta:
        ordering = ['id']
        verbose_name = 'Detalle de Factura'

    def __str__(self):
        return f'{self.descripcion} × {self.cantidad}'

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
