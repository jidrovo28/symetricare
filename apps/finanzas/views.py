from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from .models import CuentaPaciente, MovimientoFinanciero


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
