from datetime import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from .models import Consulta, TratamientoPropuesto


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_consultas(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            try:
                from apps.pacientes.models import Paciente
                from apps.servicios.models import Servicio
                from apps.finanzas.models   import CuentaPaciente, MovimientoFinanciero

                pac = get_object_or_404(Paciente, pk=request.POST.get('paciente_id'))

                consulta = Consulta.objects.create(
                    paciente        = pac,
                    profesional     = request.user,
                    motivo_consulta = request.POST.get('motivo_consulta',''),
                    observaciones   = request.POST.get('observaciones',''),
                    diagnostico     = request.POST.get('diagnostico',''),
                    num_hijos       = int(request.POST.get('num_hijos', pac.num_hijos)),
                    descuento       = float(request.POST.get('descuento',0)),
                    abono           = float(request.POST.get('abono',0)),
                    facturar        = request.POST.get('facturar') == 'on',
                    usuario_creacion= request.user,
                )

                # Tratamientos propuestos
                srv_ids  = request.POST.getlist('servicio_id[]')
                costos   = request.POST.getlist('costo_trat[]')
                obs_list = request.POST.getlist('observacion_trat[]')
                for sid, costo, obs in zip(srv_ids, costos, obs_list):
                    srv = get_object_or_404(Servicio, pk=sid)
                    TratamientoPropuesto.objects.create(
                        consulta=consulta, servicio=srv, tipo_servicio=srv.tipo,
                        costo=float(costo), observacion=obs,
                        usuario_creacion=request.user)

                consulta.calcular_totales()

                # Actualizar num_hijos del paciente si cambió
                if int(request.POST.get('num_hijos',pac.num_hijos)) != pac.num_hijos:
                    pac.num_hijos = int(request.POST.get('num_hijos',pac.num_hijos))
                    pac.save(update_fields=['num_hijos'])

                # Registrar movimiento financiero
                if float(consulta.abono) > 0:
                    MovimientoFinanciero.objects.create(
                        paciente=pac, consulta=consulta,
                        tipo='cobro', monto=float(consulta.total),
                        descripcion=f'Consulta #{consulta.pk}',
                        usuario_creacion=request.user)
                    MovimientoFinanciero.objects.create(
                        paciente=pac, consulta=consulta,
                        tipo='abono', monto=float(consulta.abono),
                        descripcion=f'Abono consulta #{consulta.pk}',
                        forma_pago=request.POST.get('forma_pago','Efectivo'),
                        usuario_creacion=request.user)

                # Actualizar cuenta del paciente
                cuenta, _ = CuentaPaciente.objects.get_or_create(
                    paciente=pac, defaults={'usuario_creacion': request.user})
                cuenta.recalcular()

                # TODO: Facturar si facturar=True (integrar con módulo de facturación)

                return JsonResponse({'result': True,
                    'msg': f'Consulta registrada. Total: ${consulta.total} | Saldo: ${consulta.saldo}',
                    'consulta_id': consulta.pk})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'abonar':
            try:
                from apps.finanzas.models import CuentaPaciente, MovimientoFinanciero
                consulta = get_object_or_404(Consulta, pk=request.POST.get('id'))
                monto    = float(request.POST.get('monto', 0))
                if monto <= 0:
                    return JsonResponse({'result': False, 'msg': 'Monto inválido'})
                if monto > float(consulta.saldo):
                    return JsonResponse({'result': False, 'msg': f'Monto supera el saldo (${consulta.saldo})'})
                consulta.abono = float(consulta.abono) + monto
                consulta.saldo = float(consulta.total) - float(consulta.abono)
                consulta.save(update_fields=['abono','saldo'])
                MovimientoFinanciero.objects.create(
                    paciente=consulta.paciente, consulta=consulta,
                    tipo='abono', monto=monto,
                    descripcion=f'Abono consulta #{consulta.pk}',
                    forma_pago=request.POST.get('forma_pago','Efectivo'),
                    usuario_creacion=request.user)
                cuenta, _ = CuentaPaciente.objects.get_or_create(
                    paciente=consulta.paciente, defaults={'usuario_creacion': request.user})
                cuenta.recalcular()
                return JsonResponse({'result': True, 'msg': f'Abono de ${monto:.2f} registrado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                obj = get_object_or_404(Consulta, pk=request.POST.get('id'))
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        if 'action' in request.GET:
            action = request.GET['action']

            if action == 'nueva':
                from apps.servicios.models import Servicio, TipoServicio
                from apps.pacientes.models import Paciente
                paciente_id = request.GET.get('paciente_id')
                data['pac'] = get_object_or_404(Paciente, pk=paciente_id) if paciente_id else None
                data['servicios']     = Servicio.objects.filter(status=True, activo=True).select_related('tipo')
                data['tipos_servicio'] = TipoServicio.objects.filter(status=True)
                return render(request, 'admin/consultas/nueva.html', data)

            elif action == 'detalle':
                try:
                    con = get_object_or_404(Consulta, pk=request.GET.get('id'))
                    data['con']          = con
                    data['tratamientos'] = con.tratamientos.filter(status=True).select_related('servicio')
                    tmpl = get_template('admin/consultas/modal/detalle.html')
                    return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

            elif action == 'abonar':
                try:
                    con = get_object_or_404(Consulta, pk=request.GET.get('id'))
                    data['con'] = con
                    tmpl = get_template('admin/consultas/modal/abonar.html')
                    return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

        else:
            data['title']  = 'Consultas'
            search   = request.GET.get('s','')
            filtro   = Q(status=True)
            url_vars = ''
            if search:
                filtro &= Q(paciente__nombres__icontains=search)|Q(paciente__identificacion__icontains=search)
                url_vars = f'&s={search}'
                data['s'] = search
            listado = Consulta.objects.filter(filtro).select_related('paciente','profesional')
            paging  = MiPaginador(listado, 25)
            p_num   = int(request.GET.get('page',1))
            try: page = paging.page(p_num)
            except: p_num=1; page=paging.page(1)
            data.update({'paging':paging,'page':page,'listado':page.object_list,
                         'url_vars':url_vars,'rangospaging':paging.rangos_paginado(p_num)})
    return render(request, 'admin/consultas/view.html', data)
