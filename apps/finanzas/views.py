from datetime import date
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from django.shortcuts import render, get_object_or_404, redirect
from .models import CuentaPaciente, MovimientoFinanciero, Paciente
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.finanzas.models import Factura
from django.contrib import messages

@login_required(redirect_field_name='ret', login_url='/login')
def view_cuentas(request):
    data = {}
    adduserdata(request, data)
    search   = request.GET.get('s','')
    filtro   = Q(status=True)
    if search:
        filtro &= Q(paciente__nombres__icontains=search)|Q(paciente__identificacion__icontains=search)
        data['s'] = search
    listado  = CuentaPaciente.objects.filter(filtro).select_related('paciente').order_by('-saldo')
    if 'action' in request.GET and request.GET['action'] == 'detalle':
        try:
            cuenta = get_object_or_404(CuentaPaciente, pk=request.GET.get('id'))
            data['cuenta']    = cuenta
            data['movimientos'] = MovimientoFinanciero.objects.filter(
                status=True, paciente=cuenta.paciente).order_by('-fecha_creacion')[:30]
            tmpl = get_template('admin/finanzas/modal/detalle.html')
            return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
        except Exception as ex:
            return JsonResponse({'result': False, 'msg': str(ex)})

    elif request.GET['action'] == 'facturas_consulta':
        return _action_facturas_consulta(request, data, adduserdata)

    data.update({
        'title':   'Estado de Cuentas',
        'listado': listado,
        'total_cobrado': listado.aggregate(t=Sum('total_cobrado'))['t'] or 0,
        'total_pagado':  listado.aggregate(t=Sum('total_pagado'))['t'] or 0,
        'total_saldo':   listado.aggregate(t=Sum('saldo'))['t'] or 0,
    })
    return render(request, 'admin/finanzas/cuentas.html', data)


@login_required(redirect_field_name='ret', login_url='/login')
def view_movimientos(request):
    data = {}
    adduserdata(request, data)
    data['title']   = 'Movimientos Financieros'
    desde = request.GET.get('desde','')
    hasta = request.GET.get('hasta','')
    filtro = Q(status=True)
    if desde: filtro &= Q(fecha_creacion__date__gte=desde)
    if hasta: filtro &= Q(fecha_creacion__date__lte=hasta)
    listado = MovimientoFinanciero.objects.filter(filtro).select_related('paciente').order_by('-fecha_creacion')
    paging  = MiPaginador(listado, 30)
    p_num   = int(request.GET.get('page',1))
    try: page = paging.page(p_num)
    except: p_num=1; page=paging.page(1)
    data.update({'paging':paging,'page':page,'listado':page.object_list,
                 'rangospaging':paging.rangos_paginado(p_num),
                 'desde':desde,'hasta':hasta,
                 'total_abonos': listado.filter(Q(tipo='abono') | Q(tipo='abonoadelantado')).aggregate(t=Sum('monto'))['t'] or 0})
    return render(request, 'admin/finanzas/movimientos.html', data)

@login_required
def lista(request):
    from apps.finanzas.models import Factura
    q = request.GET.get('q', '')
    estado = request.GET.get('estado', '')
    facturas = Factura.objects.filter(status=True).select_related('paciente').order_by('-fecha', '-id')
    if q:
        facturas = facturas.filter(
            Q(paciente__nombres__icontains=q) | Q(paciente__apellido1__icontains=q) | Q(paciente__apellido2__icontains=q) |
            Q(numero__icontains=q)
        )
    if estado:
        facturas = facturas.filter(estado=estado)
    hoy = date.today()
    total_mes = Factura.objects.filter(
        status=True, fecha__month=hoy.month, fecha__year=hoy.year, estado='pagada'
    ).aggregate(t=Sum('total'))['t'] or 0
    pendiente = Factura.objects.filter(status=True, estado='pendiente').aggregate(t=Sum('total'))['t'] or 0
    return render(request, 'admin/finanzas/lista.html', {
        'facturas': facturas, 'total_mes': total_mes, 'pendiente': pendiente,
        'q': q, 'estado': estado,
    })

def nueva(request):
    """Vista para crear factura eligiendo paciente y seleccionando tratamientos."""
    paciente_id = request.GET.get('paciente_id') or request.POST.get('paciente_id')

    paciente = None
    consulta = None
    tratamientos_disponibles = []
    consultas_paciente = []

    if paciente_id:
        paciente = get_object_or_404(Paciente, pk=paciente_id)

    if request.method == 'POST':
        return _crear_factura(request, paciente)

    pacientes = Paciente.objects.filter(status=True).order_by('apellido1', 'apellido2', 'nombres')
    return render(request, 'admin/finanzas/nuevafactura.html', {
        'paciente': paciente,
        'consulta': consulta,
        'consultas_paciente': consultas_paciente,
        'tratamientos_disponibles': tratamientos_disponibles,
        'pacientes': pacientes,
        'hoy': date.today(),
    })

@login_required
def detalle(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    return render(request, 'admin/finanzas/detalle.html', {'factura': factura})

@login_required
def cambiar_estado(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    if request.method == 'POST':
        factura.estado = request.POST.get('estado', factura.estado)
        factura.metodo_pago = request.POST.get('metodo_pago', factura.metodo_pago)
        factura.save()
        messages.success(request, 'Estado actualizado.')
    return redirect('detalle_factura', pk=pk)


@login_required
@require_POST
def enviar_sri_view(request, pk):
    """Enviar/re-enviar al SRI manualmente."""
    from .sri_service import procesar_factura_sri
    factura = get_object_or_404(Factura, pk=pk)
    res = procesar_factura_sri(factura)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(res)
    if res['ok']:
        messages.success(request, f"✅ {res['mensaje']}")
    else:
        messages.error(request, f"❌ {res['mensaje']}")
    return redirect('detalle_factura', pk=pk)

def reiniciar_factura(request, pk):
    try:
        """Enviar/re-enviar al SRI manualmente."""
        from .sri_service import procesar_factura_sri
        factura = get_object_or_404(Factura, pk=pk)
        factura.clave_acceso = ''
        factura.sri_estado = 'xmlpendiente'
        factura.sri_numero_autorizacion = ''
        factura.sri_fecha_autorizacion = None
        factura.sri_xml = ''
        factura.sri_xml_firmado = ''
        factura.sri_xml_firmado = ''
        factura.sri_respuesta = ''
        factura.save()
        return JsonResponse({'ok': True, "mensaje": f"✅ Factura reiniciada."})
        messages.success(request, f"✅ Factura reiniciada.")
    except Exception as e:
        messages.error(request, f"❌ Factura no se reinició.")
        return JsonResponse({'ok': True, "mensaje": f"❌ Factura no se reinició."})

def _crear_factura(request, paciente):
    from datetime import datetime, date
    from apps.consultas.models import VisitaTratamiento, Consulta
    from .models import Factura, DetalleFactura, ConsultaFactura, TratamientoConsultaFactura

    # ── Datos generales ───────────────────────────────────────────────────────
    descuento   = float(request.POST.get('descuento') or 0)
    metodo_pago = request.POST.get('metodo_pago', 'efectivo')
    notas       = request.POST.get('notas', '')
    fecha_input = request.POST.get('fecha')
    enviar_sri  = request.POST.get('enviar_sri') == '1'

    fecha = (datetime.strptime(fecha_input, '%Y-%m-%d').date()
             if fecha_input else date.today())

    factura = Factura.objects.create(
        paciente    = paciente,
        fecha       = fecha,
        descuento   = descuento,
        metodo_pago = metodo_pago,
        notas       = notas,
        estado      = 'pendiente',
        sri_estado  = 'xmlpendiente',
        usuario_creacion = request.user,
    )

    # ── Cargar consultas origen y crear ConsultaFactura ───────────────────────
    # consulta_ids[] → pk de las consultas cuyo botón "Cargar tratamientos"
    # fue clicado en el formulario (enviados por el JS en el submit)
    consulta_ids = [int(c) for c in request.POST.getlist('consulta_ids') if c.isdigit()]
    consultas_map = {}   # { consulta_id: ConsultaFactura }

    for cid in consulta_ids:
        try:
            consulta = Consulta.objects.get(pk=cid, status=True)
        except Consulta.DoesNotExist:
            continue
        cf = ConsultaFactura.objects.create(
            factura          = factura,
            consulta         = consulta,
            usuario_creacion = request.user,
        )
        consultas_map[cid] = cf

    # ── Detalles desde VisitaTratamiento ─────────────────────────────────────
    # tr_ids[]       → pk de cada VisitaTratamiento seleccionado
    # tr_costo_<id>  → costo (abonado) que el usuario vio/editó en pantalla
    tr_ids = request.POST.getlist('tr_ids')
    for tr_id in tr_ids:
        try:
            vt = VisitaTratamiento.objects.select_related(
                'servicio', 'tipo_servicio', 'consulta'
            ).get(pk=tr_id, status=True, contabilizar_costo=True)
        except VisitaTratamiento.DoesNotExist:
            continue

        costo_editado = request.POST.get(f'tr_costo_{tr_id}')
        precio = (float(costo_editado)
                  if costo_editado not in (None, '', 'None')
                  else float(vt.costo or 0))

        if precio <= 0:
            continue

        # Descripción enriquecida para el DetalleFactura
        tipo_str  = f' [{vt.tipo_servicio.nombre}]' if vt.tipo_servicio else ''
        fecha_str = f' — {vt.fecha.strftime("%d/%m/%Y")}' if vt.fecha else ''
        descripcion = f'{vt.servicio.nombre}{tipo_str}{fecha_str}'
        if vt.descripcion:
            descripcion += f' — {vt.descripcion[:80]}'

        DetalleFactura.objects.create(
            factura         = factura,
            descripcion     = descripcion,
            cantidad        = 1,
            precio_unitario = precio,
            subtotal        = round(precio, 2),
            usuario_creacion = request.user,
        )

        # Vincular este VisitaTratamiento al ConsultaFactura correspondiente
        cf = consultas_map.get(vt.consulta_id)
        if cf:
            TratamientoConsultaFactura.objects.create(
                consultafactura  = cf,
                visita           = vt,
                servicio         = vt.servicio,
                tipo_servicio    = vt.tipo_servicio,
                descripcion      = descripcion,
                valor            = precio,
                usuario_creacion = request.user,
            )

    # ── Líneas manuales (no vinculan a consulta específica) ───────────────────
    descs      = request.POST.getlist('linea_desc')
    precios    = request.POST.getlist('linea_precio')
    cantidades = request.POST.getlist('linea_qty')

    for i, desc in enumerate(descs):
        if not desc.strip():
            continue
        try:
            precio = float(precios[i])  if i < len(precios)    else 0.0
            qty    = int(cantidades[i]) if i < len(cantidades)  else 1
        except (ValueError, IndexError):
            precio, qty = 0.0, 1

        precio = max(0.0, precio)
        qty    = max(1, qty)

        DetalleFactura.objects.create(
            factura          = factura,
            descripcion      = desc.strip(),
            cantidad         = qty,
            precio_unitario  = precio,
            subtotal         = round(qty * precio, 2),
            usuario_creacion = request.user,
        )

    # ── Recalcular y validar ──────────────────────────────────────────────────
    factura.calcular_totales()

    if factura.total <= 0:
        factura.delete()   # cascade elimina ConsultaFactura y TratamientoConsultaFactura
        messages.error(request, 'La factura no tiene ítems o el total es $0.00.')
        return redirect('nueva_factura')

    # ── SRI (hilo daemon) ─────────────────────────────────────────────────────
    if enviar_sri:
        import threading
        def _sri():
            try:
                from .sri_service import procesar_factura
                procesar_factura(factura)
            except Exception as e:
                import logging
                logging.getLogger('finanzas').error(
                    f'[SRI] Factura {factura.pk}: {e}')
        threading.Thread(target=_sri, daemon=True).start()
        messages.success(request,
            f'Factura #{factura.numero} creada — enviando al SRI en segundo plano.')
    else:
        messages.success(request,
            f'Factura #{factura.numero} creada correctamente.')

    return redirect('detalle_factura', pk=factura.pk)

def _action_facturas_consulta(request, data, adduserdata):
    """
    Devuelve el modal con todas las facturas vinculadas a una consulta.
    Llamar desde view_facturas como:
        elif action == 'facturas_consulta':
            return _action_facturas_consulta(request, data, adduserdata)
    """
    from apps.consultas.models import Consulta
    from .models import ConsultaFactura
    from django.template.loader import get_template

    consulta_id = request.GET.get('consulta_id')
    if not consulta_id:
        return JsonResponse({'result': False, 'msg': 'consulta_id requerido'})

    try:
        consulta = Consulta.objects.get(pk=consulta_id, status=True)
    except Consulta.DoesNotExist:
        return JsonResponse({'result': False, 'msg': 'Consulta no encontrada'})

    cfs = (ConsultaFactura.objects
           .filter(consulta=consulta, status=True)
           .select_related('factura')
           .prefetch_related(
               'consultafactura__visita',
               'consultafactura__servicio',
               'consultafactura__tipo_servicio',
           )
           .order_by('-factura__fecha', '-id'))

    facturas_data = []
    total_facturado = 0
    for cf in cfs:
        tratamientos = cf.consultafactura.filter(status=True).select_related(
            'visita', 'servicio', 'tipo_servicio')
        facturas_data.append({
            'factura':      cf.factura,
            'tratamientos': tratamientos,
        })
        total_facturado += float(cf.factura.total or 0)

    adduserdata(request, data)
    data.update({
        'consulta':        consulta,
        'facturas':        facturas_data,
        'total_facturado': round(total_facturado, 2),
    })
    tmpl = get_template('admin/finanzas/modal/facturas_consulta.html')
    return JsonResponse({'result': True, 'data': tmpl.render(data, request)})

