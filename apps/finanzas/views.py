from datetime import date
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from apps.finanzas.models import Factura
from django.template.loader import get_template
from django.views.decorators.http import require_POST
from apps.core.helpers import adduserdata, MiPaginador
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import CuentaPaciente, MovimientoFinanciero, Paciente, TipoIva

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

    elif request.GET.get('action', '') == 'facturas_consulta':
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

@login_required(redirect_field_name='ret', login_url='/login')
def view_tipo_iva(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            try:
                pct = float(request.POST.get('porcentaje', 0))
                if TipoIva.objects.filter(
                        porcentaje=pct, status=True).exists():
                    return JsonResponse({'result': False,
                        'msg': f'Ya existe un tipo de IVA con {pct}%'})
                es_default = request.POST.get('es_default') == 'on'
                TipoIva.objects.create(
                    descripcion  = request.POST.get('descripcion', '').strip(),
                    porcentaje   = pct,
                    codigo_sri   = request.POST.get('codigo_sri', '').strip(),
                    es_default   = es_default,
                    usuario_creacion = request.user,
                )
                return JsonResponse({'result': True,
                    'msg': f'IVA {pct}% creado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'edit':
            try:
                obj = get_object_or_404(TipoIva,
                    pk=request.POST.get('id'), status=True)
                obj.descripcion = request.POST.get('descripcion',
                                    obj.descripcion).strip()
                obj.porcentaje  = float(request.POST.get('porcentaje',
                                    obj.porcentaje))
                obj.codigo_sri  = request.POST.get('codigo_sri',
                                    obj.codigo_sri).strip()
                obj.es_default  = request.POST.get('es_default') == 'on'
                obj.usuario_modificacion = request.user
                obj.save()
                return JsonResponse({'result': True,
                    'msg': 'IVA actualizado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'set_default':
            try:
                obj = get_object_or_404(TipoIva,
                    pk=request.POST.get('id'), status=True)
                TipoIva.objects.filter(status=True).update(
                    es_default=False)
                obj.es_default = True
                obj.save(update_fields=['es_default'])
                return JsonResponse({'result': True,
                    'msg': f'{obj.descripcion} es ahora el IVA por defecto'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                obj = get_object_or_404(TipoIva,
                    pk=request.POST.get('id'), status=True)
                if obj.servicios.filter(status=True).exists():
                    return JsonResponse({'result': False,
                        'msg': 'No se puede eliminar: tiene servicios asociados'})
                obj.status = False
                obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})
        return JsonResponse({
            'result': False,
            'msg': f'Acción inválida: {action}'
        })
    else:
        action = request.GET.get('action', '')
        if action == 'edit':
            obj = get_object_or_404(TipoIva,
                pk=request.GET.get('id'), status=True)
            data['obj']   = obj
            data['codes'] = [
                ('0','Tarifa 0%'), ('2','Tarifa 12%'), ('3','Tarifa 14%'),
                ('4','Tarifa 15%'), ('5','Tarifa 5%'),
                ('6','No objeto de IVA'), ('7','Exento de IVA'),
            ]
            tmpl = get_template('admin/finanzas/modal/tipo_iva_form.html')
            return JsonResponse({'result': True,
                'data': tmpl.render(data, request)})

    from apps.servicios.models import Servicio
    data.update({
        'title':    'Tipos de IVA',
        'listado':  TipoIva.objects.filter(status=True),
        # Servicios que aún no tienen IVA asignado
        'servicios_sin_iva': Servicio.objects.filter(
            status=True, activo=True, tipo_iva__isnull=True
        ).select_related('tipo').order_by('nombre'),
    })
    return render(request, 'admin/finanzas/tipoiva_view.html', data)

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

@login_required(redirect_field_name='ret', login_url='/login')
def nueva_factura(request, paciente_id=None):
    from datetime import date
    from apps.pacientes.models import Paciente

    data = {}
    adduserdata(request, data)

    # Resolver paciente desde URL, GET o POST
    paciente = None
    pid = paciente_id or request.POST.get('paciente_id') or request.GET.get('paciente_id')
    if pid:
        paciente = get_object_or_404(Paciente, pk=pid, status=True)

    # ── POST: crear la factura ────────────────────────────────────────────
    if request.method == 'POST':
        if not paciente:
            messages.error(request, 'Selecciona un paciente.')
            return redirect('nueva_factura')
        return _crear_factura(request, paciente)

    # ── GET: mostrar el formulario ────────────────────────────────────────
    data.update({
        'title':     'Nueva Factura',
        'paciente':  paciente,
        'hoy':       date.today(),
        'tipos_iva': TipoIva.objects.filter(status=True).order_by('porcentaje'),
    })
    return render(request, 'admin/finanzas/nuevafactura.html', data)

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
    from decimal import Decimal, ROUND_HALF_UP
    from apps.consultas.models import VisitaTratamiento, Consulta
    from .models import Factura, DetalleFactura, ConsultaFactura, TratamientoConsultaFactura

    Q2 = lambda v: Decimal(str(v)).quantize(Decimal('0.01'), ROUND_HALF_UP)

    descuento   = Q2(request.POST.get('descuento') or '0')
    metodo_pago = request.POST.get('metodo_pago', 'efectivo')
    notas       = request.POST.get('notas', '')
    fecha_input = request.POST.get('fecha')
    enviar_sri  = request.POST.get('enviar_sri') == '1'
    fecha       = (datetime.strptime(fecha_input, '%Y-%m-%d').date()
                   if fecha_input else date.today())

    pct_factura = Decimal('15')

    factura = Factura.objects.create(
        paciente       = paciente,
        fecha          = fecha,
        descuento      = descuento,
        metodo_pago    = metodo_pago,
        notas          = notas,
        estado         = 'pendiente',
        sri_estado     = 'xmlpendiente',
        porcentaje_iva = pct_factura,
        usuario_creacion = request.user,
    )

    # ── Consultas origen ──────────────────────────────────────────────────────
    consulta_ids = [int(c) for c in request.POST.getlist('consulta_ids') if c.isdigit()]
    consultas_map = {}
    for cid in consulta_ids:
        try:
            c_obj = Consulta.objects.get(pk=cid, status=True)
        except Consulta.DoesNotExist:
            continue
        cf = ConsultaFactura.objects.create(
            factura=factura, consulta=c_obj,
            usuario_creacion=request.user)
        consultas_map[cid] = cf

    # ── Helper: precio YA INCLUYE IVA → extraer base e IVA ───────────────────
    def _iva_info(precio_con_iva: Decimal, tipo_iva_obj):
        """
        precio_con_iva: lo que el paciente paga (precio del servicio, IVA incluido).
        Retorna (aplica_iva, base_sin_imp, valor_iva)

        Fórmula:
            base       = precio_con_iva / (1 + pct/100)
            valor_iva  = precio_con_iva - base
        """
        nonlocal pct_factura
        if not tipo_iva_obj:
            return False, precio_con_iva, Decimal('0')
        pct = Decimal(str(tipo_iva_obj.porcentaje or 0))
        if pct <= 0:
            return False, precio_con_iva, Decimal('0')
        pct_factura = pct
        base      = Q2(precio_con_iva / (1 + pct / 100))
        valor_iva = Q2(precio_con_iva - base)
        return True, base, valor_iva

    # ── Detalles desde VisitaTratamiento ─────────────────────────────────────
    # tr_costo_<id> = precio CON IVA (lo que el frontend muestra al usuario)
    tr_ids = request.POST.getlist('tr_ids')
    for tr_id in tr_ids:
        try:
            vt = VisitaTratamiento.objects.select_related(
                'servicio', 'servicio__tipo_iva',
                'tipo_servicio', 'consulta',
            ).get(pk=tr_id, status=True, contabilizar_costo=True)
        except VisitaTratamiento.DoesNotExist:
            continue

        raw = request.POST.get(f'tr_costo_{tr_id}')
        precio_con_iva = Q2(raw if raw not in (None, '', 'None')
                            else str(vt.costo or 0))
        if precio_con_iva <= 0:
            continue

        tipo_iva_obj              = getattr(vt.servicio, 'tipo_iva', None)
        aplica_iva, base, val_iva = _iva_info(precio_con_iva, tipo_iva_obj)

        tipo_str  = f' [{vt.tipo_servicio.nombre}]' if vt.tipo_servicio else ''
        fecha_str = f' — {vt.fecha.strftime("%d/%m/%Y")}' if vt.fecha else ''
        desc      = f'{vt.servicio.nombre}{tipo_str}{fecha_str}'
        if vt.descripcion:
            desc += f' — {vt.descripcion[:80]}'

        DetalleFactura.objects.create(
            factura          = factura,
            descripcion      = desc,
            cantidad         = 1,
            precio_unitario  = precio_con_iva,   # precio que ve el usuario
            subtotal_sin_imp = base,             # base extraída
            aplica_iva       = aplica_iva,
            tipo_iva         = tipo_iva_obj,
            iva              = val_iva,
            subtotal         = precio_con_iva,   # = base + iva
            usuario_creacion = request.user,
        )

        cf = consultas_map.get(vt.consulta_id)
        if cf:
            TratamientoConsultaFactura.objects.create(
                consultafactura=cf, visita=vt,
                servicio=vt.servicio, tipo_servicio=vt.tipo_servicio,
                descripcion=desc, valor=precio_con_iva,
                usuario_creacion=request.user)

    # ── Líneas manuales ───────────────────────────────────────────────────────
    descs      = request.POST.getlist('linea_desc')
    precios    = request.POST.getlist('linea_precio')
    cantidades = request.POST.getlist('linea_qty')
    iva_ids    = request.POST.getlist('linea_iva_id')

    for i, desc in enumerate(descs):
        if not desc.strip():
            continue
        try:
            precio = Q2(str(max(0.0, float(precios[i]))))
            qty    = max(1, int(cantidades[i]))
        except (ValueError, IndexError):
            precio, qty = Decimal('0'), 1

        precio_con_iva = Q2(precio * qty)   # precio total con IVA incluido

        tipo_iva_obj = None
        try:
            iva_id = iva_ids[i] if i < len(iva_ids) else ''
            if iva_id:
                from apps.finanzas.models import TipoIva
                tipo_iva_obj = TipoIva.objects.get(pk=iva_id)
        except Exception:
            pass

        aplica_iva, base, val_iva = _iva_info(precio_con_iva, tipo_iva_obj)

        DetalleFactura.objects.create(
            factura          = factura,
            descripcion      = desc.strip(),
            cantidad         = qty,
            precio_unitario  = precio,
            subtotal_sin_imp = base,
            aplica_iva       = aplica_iva,
            tipo_iva         = tipo_iva_obj,
            iva              = val_iva,
            subtotal         = precio_con_iva,
            usuario_creacion = request.user,
        )

    factura.calcular_totales()

    if factura.porcentaje_iva != pct_factura and factura.iva > 0:
        factura.porcentaje_iva = pct_factura
        factura.save(update_fields=['porcentaje_iva'])

    if factura.total <= 0:
        factura.delete()
        messages.error(request, 'La factura no tiene ítems o el total es $0.00.')
        return redirect('nueva_factura')

    if enviar_sri:
        import threading
        def _sri():
            try:
                from .sri_service import procesar_factura
                procesar_factura(factura)
            except Exception as e:
                import logging
                logging.getLogger('finanzas').error(f'[SRI] {factura.pk}: {e}')
        threading.Thread(target=_sri, daemon=True).start()
        messages.success(request,
            f'Factura #{factura.numero_formateado} creada — enviando al SRI.')
    else:
        messages.success(request,
            f'Factura #{factura.numero_formateado} creada correctamente.')

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

