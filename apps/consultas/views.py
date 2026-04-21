import decimal
from decimal import Decimal
from datetime import date
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from .models import Consulta, TratamientoPropuesto, VisitaTratamiento, AbonoConsulta
from apps.finanzas.models import MovimientoFinanciero


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_consultas(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')

        # ── Crear consulta (sin deuda) ────────────────────────────────────
        if action == 'add':
            try:
                from apps.pacientes.models import (
                    Paciente, APF, APP, Alergia, Medicamento,
                    Suplemento, Habito, ActividadFisica, TratamientoRealizado)
                from apps.servicios.models import Servicio

                pac = get_object_or_404(Paciente,
                    pk=request.POST.get('paciente_id'))

                consulta = Consulta.objects.create(
                    paciente         = pac,
                    profesional      = request.user,
                    motivo_consulta  = request.POST.get('motivo_consulta', ''),
                    observaciones    = request.POST.get('observaciones', ''),
                    diagnostico      = request.POST.get('diagnostico', ''),
                    num_hijos        = int(request.POST.get('num_hijos', pac.num_hijos)),
                    usuario_creacion = request.user,
                )

                # Antecedentes vinculados a esta consulta
                for desc in request.POST.getlist('apf[]'):
                    if desc.strip():
                        APF.objects.create(consulta=consulta,
                            descripcion=desc.strip(), usuario_creacion=request.user)
                for desc, fec in zip(request.POST.getlist('app_desc[]'),
                                     request.POST.getlist('app_fecha[]')):
                    if desc.strip():
                        APP.objects.create(consulta=consulta,
                            descripcion=desc.strip(), fecha_diagnostico=fec or None,
                            usuario_creacion=request.user)
                for desc in request.POST.getlist('alergias[]'):
                    if desc.strip():
                        Alergia.objects.create(consulta=consulta,
                            descripcion=desc.strip(), usuario_creacion=request.user)
                for desc in request.POST.getlist('medicamentos[]'):
                    if desc.strip():
                        Medicamento.objects.create(consulta=consulta,
                            descripcion=desc.strip(), usuario_creacion=request.user)
                for desc in request.POST.getlist('suplementos[]'):
                    if desc.strip():
                        Suplemento.objects.create(consulta=consulta,
                            descripcion=desc.strip(), usuario_creacion=request.user)
                for desc in request.POST.getlist('habitos[]'):
                    if desc.strip():
                        Habito.objects.create(consulta=consulta,
                            descripcion=desc.strip(), usuario_creacion=request.user)
                for desc in request.POST.getlist('actividades[]'):
                    if desc.strip():
                        ActividadFisica.objects.create(consulta=consulta,
                            descripcion=desc.strip(), usuario_creacion=request.user)
                for desc, fec in zip(request.POST.getlist('trat_realizado_desc[]'),
                                     request.POST.getlist('trat_realizado_fecha[]')):
                    if desc.strip():
                        TratamientoRealizado.objects.create(
                            consulta=consulta, descripcion=desc.strip(),
                            fecha=fec or None, usuario_creacion=request.user)

                # Tratamientos propuestos — solo plan, NO generan deuda
                for sid, costo, obs in zip(
                        request.POST.getlist('servicio_id[]'),
                        request.POST.getlist('costo_trat[]'),
                        request.POST.getlist('observacion_trat[]')):
                    srv = get_object_or_404(Servicio, pk=sid)
                    TratamientoPropuesto.objects.create(
                        consulta=consulta, servicio=srv,
                        tipo_servicio=srv.tipo,
                        costo=float(costo), observacion=obs,
                        usuario_creacion=request.user)

                nuevo_hijos = int(request.POST.get('num_hijos', pac.num_hijos))
                if nuevo_hijos != pac.num_hijos:
                    pac.num_hijos = nuevo_hijos
                    pac.save(update_fields=['num_hijos'])

                # total=0 al crear — la deuda se acumula con las visitas
                return JsonResponse({
                    'result':      True,
                    'msg':         'Consulta registrada. Registra visitas para generar deuda.',
                    'consulta_id': consulta.pk,
                    'paciente_id': pac.pk,
                })
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        # ── Agregar tratamiento realizado en una visita ──────────────────
        elif action == 'add_visita':
            try:
                from apps.servicios.models import Servicio
                from apps.finanzas.models import CuentaPaciente, MovimientoFinanciero
                consulta = get_object_or_404(Consulta,
                    pk=request.POST.get('consulta_id'))

                if consulta.estado == Consulta.ATENDIDA:
                    return JsonResponse({'result': False,
                        'msg': 'La consulta ya fue finalizada'})

                srv = get_object_or_404(Servicio,
                    pk=request.POST.get('servicio_id'))

                trat_prop = None
                trat_prop_id = request.POST.get('tratamiento_propuesto_id') or None
                if trat_prop_id:
                    trat_prop = TratamientoPropuesto.objects.filter(
                        pk=trat_prop_id, consulta=consulta, status=True).first()

                costo = request.POST.get('costo', '')
                abono = request.POST.get('abono', 0)
                contabilizar_costo = True
                tiene_mismo_tratamiento = VisitaTratamiento.objects.filter(status=True, consulta=consulta,
                                                                           servicio=srv, tipo_servicio=srv.tipo).first()
                if tiene_mismo_tratamiento:
                    total_costo = tiene_mismo_tratamiento.costo
                    total_abonado = (consulta.visitas.filter(status=True, servicio=srv, tipo_servicio=srv.tipo).aggregate(t=Sum('abono'))['t'] or 0)
                    if Decimal(total_abonado) < Decimal(total_costo):
                        contabilizar_costo = False
                    saldo_restante = Decimal(total_costo) - Decimal(total_abonado)
                    total_abonado_actual = Decimal(total_abonado) + Decimal(abono)
                    if total_abonado_actual > Decimal(total_costo):
                        mensaje = f"El total abonado supera el costo del tratamiento. Saldo restante del servicio {srv.nombre} ${saldo_restante}"
                        return JsonResponse({'result': False,
                                             'msg': mensaje})

                visita = VisitaTratamiento.objects.create(
                    consulta              = consulta,
                    fecha                 = request.POST.get('fecha') or date.today(),
                    tratamiento_propuesto = trat_prop,
                    servicio              = srv,
                    tipo_servicio         = srv.tipo,
                    descripcion           = request.POST.get('descripcion', ''),
                    costo                 = float(costo) if costo else srv.precio,
                    abono                 = float(abono) if abono else 0,
                    forma_pago            = request.POST.get('forma_pago', ''),
                    contabilizar_costo    = contabilizar_costo,
                    usuario_creacion      = request.user,
                )
                visita.registrar_historial()
                # recalcular_totales() se llama en VisitaTratamiento.save()
                monto = float(request.POST.get('abono', 0))
                if monto > 0 and monto <= float(consulta.saldo):
                    abono_ = AbonoConsulta.objects.create(
                        consulta=consulta, visita=visita, servicio=srv, tipo_servicio=srv.tipo,
                        monto=monto,
                        forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                        nota=request.POST.get('nota', ''),
                        usuario_creacion=request.user)
                    MovimientoFinanciero.objects.create(
                        paciente=consulta.paciente, consulta=consulta, abono=abono_,
                        tipo='abono', monto=monto,
                        descripcion=f'Abono consulta #{consulta.pk}',
                        forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                        usuario_creacion=request.user)
                    cuenta, _ = CuentaPaciente.objects.get_or_create(
                        paciente=consulta.paciente,
                        defaults={'usuario_creacion': request.user})
                    cuenta.recalcular()

                consulta.refresh_from_db(fields=['total', 'abono', 'saldo'])

                return JsonResponse({
                    'result':     True,
                    'msg':        f'{srv.nombre} registrado — ${visita.costo:.2f}',
                    'visita_id':  visita.pk,
                    'nuevo_total': f'{consulta.total:.2f}',
                    'nuevo_saldo': f'{consulta.saldo:.2f}',
                })
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        # ── Eliminar tratamiento realizado → reduce la deuda ─────────────
        elif action == 'delete_visita':
            try:
                from apps.finanzas.models import MovimientoFinanciero
                visita = get_object_or_404(VisitaTratamiento,
                    pk=request.POST.get('id'))
                if visita.consulta.estado == Consulta.ATENDIDA:
                    return JsonResponse({'result': False,
                        'msg': 'La consulta ya fue finalizada'})
                visita.status = False
                visita.save(update_fields=['status'])
                # recalcular_totales() se llama en save() via la señal
                abono = AbonoConsulta.objects.filter(status=True, visita=visita).first()
                if abono:
                    movimientos = MovimientoFinanciero.objects.filter(status=True, abono=abono).update(status=False)
                    abono.status=False
                    abono.save()
                visita.consulta.recalcular_totales()
                visita.consulta.paciente.cuenta.recalcular()
                visita.consulta.refresh_from_db(fields=['total', 'abono', 'saldo'])
                return JsonResponse({
                    'result':     True,
                    'nuevo_total': f'{visita.consulta.total:.2f}',
                    'nuevo_saldo': f'{visita.consulta.saldo:.2f}',
                })
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete_abono':
            try:
                from apps.finanzas.models import MovimientoFinanciero
                abono = get_object_or_404(AbonoConsulta, pk=request.POST.get('id'))
                if abono.consulta.estado == Consulta.ATENDIDA:
                    return JsonResponse({'result': False, 'msg': 'La consulta ya fue finalizada'})
                abono.status = False
                abono.save(update_fields=['status'])
                if abono.visita:
                    visita_ = abono.visita
                    visita_.status = False
                    visita_.save()
                movimientos = MovimientoFinanciero.objects.filter(status=True, abono=abono).update(status=False)
                abono.consulta.recalcular_totales()
                abono.consulta.paciente.cuenta.recalcular()
                abono.consulta.refresh_from_db(fields=['total', 'abono', 'saldo'])
                return JsonResponse({
                    'result':     True,
                    'nuevo_total': f'{abono.consulta.total:.2f}',
                    'nuevo_saldo': f'{abono.consulta.saldo:.2f}',
                })
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        # ── Finalizar consulta ────────────────────────────────────────────
        elif action == 'finalizar':
            try:
                consulta = get_object_or_404(Consulta,
                    pk=request.POST.get('id'))
                if consulta.estado == Consulta.ATENDIDA:
                    return JsonResponse({'result': False,
                        'msg': 'La consulta ya estaba finalizada'})
                consulta.estado = Consulta.ATENDIDA
                consulta.save(update_fields=['estado'])
                return JsonResponse({'result': True,
                    'msg': 'Consulta finalizada'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        # ── Registrar abono ───────────────────────────────────────────────
        elif action == 'abonar':
            try:
                from apps.finanzas.models import CuentaPaciente, MovimientoFinanciero
                consulta = get_object_or_404(Consulta,
                    pk=request.POST.get('id'))
                monto = float(request.POST.get('monto', 0))
                if monto <= 0:
                    return JsonResponse({'result': False, 'msg': 'Monto inválido'})
                if monto > float(consulta.saldo):
                    return JsonResponse({'result': False,
                        'msg': f'Monto supera el saldo (${consulta.saldo:.2f})'})
                AbonoConsulta.objects.create(
                    consulta=consulta, monto=monto,
                    forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                    nota=request.POST.get('nota', ''),
                    usuario_creacion=request.user)
                MovimientoFinanciero.objects.create(
                    paciente=consulta.paciente, consulta=consulta,
                    tipo='abono', monto=monto,
                    descripcion=f'Abono consulta #{consulta.pk}',
                    forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                    usuario_creacion=request.user)
                cuenta, _ = CuentaPaciente.objects.get_or_create(
                    paciente=consulta.paciente,
                    defaults={'usuario_creacion': request.user})
                cuenta.recalcular()
                return JsonResponse({'result': True,
                    'msg': f'Abono de ${monto:.2f} registrado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'abonaradelanto':
            try:
                from apps.finanzas.models import CuentaPaciente, MovimientoFinanciero
                consulta = get_object_or_404(Consulta,
                    pk=request.POST.get('id'))
                monto = float(request.POST.get('monto', 0))
                if monto <= 0:
                    return JsonResponse({'result': False, 'msg': 'Monto inválido'})
                AbonoConsulta.objects.create(
                    consulta=consulta, monto=monto,
                    forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                    nota=request.POST.get('nota', ''),
                    adelantado=True,
                    usuario_creacion=request.user)
                MovimientoFinanciero.objects.create(
                    paciente=consulta.paciente, consulta=consulta,
                    tipo='abonoadelantado', monto=monto,
                    descripcion=f'Abono consulta por adelantado #{consulta.pk}',
                    forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                    usuario_creacion=request.user)
                cuenta, _ = CuentaPaciente.objects.get_or_create(
                    paciente=consulta.paciente,
                    defaults={'usuario_creacion': request.user})
                cuenta.recalcular()
                return JsonResponse({'result': True,
                    'msg': f'Abono adelantado de ${monto:.2f} registrado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                obj = get_object_or_404(Consulta, pk=request.POST.get('id'))
                visitas = VisitaTratamiento.objects.filter(status=True, consulta=obj).exists()
                if visitas:
                    return JsonResponse({'result': False, 'msg': 'No puede eliminar la consulta debido a que tiene tratamientos registrados.'})
                obj.status = False
                obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    # ── GET ───────────────────────────────────────────────────────────────
    else:
        data['action'] = action = request.GET.get('action', '')

        if action == 'nueva':
            from apps.servicios.models import Servicio, TipoServicio
            from apps.pacientes.models import Paciente
            pac_id = request.GET.get('paciente_id')
            data['pac']            = get_object_or_404(Paciente, pk=pac_id) if pac_id else None
            data['servicios']      = Servicio.objects.filter(status=True, activo=True).select_related('tipo')
            data['tipos_servicio'] = TipoServicio.objects.filter(status=True)
            return render(request, 'admin/consultas/nueva.html', data)

        elif action == 'modal_visita':
            # Modal para agregar tratamiento realizado en una visita
            try:
                from apps.servicios.models import Servicio, TipoServicio
                consulta = get_object_or_404(Consulta, pk=request.GET.get('id'))
                data['consulta']       = consulta
                data['propuestos']     = consulta.tratamientos.filter(status=True).select_related('servicio','tipo_servicio')
                data['servicios']      = Servicio.objects.filter(status=True, activo=True).select_related('tipo')
                data['tipos_servicio'] = TipoServicio.objects.filter(status=True)
                tmpl = get_template('admin/consultas/modal/add_visita.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})


        elif action == 'tiene_tratamiento_registrado':
            try:
                from apps.servicios.models import Servicio
                consulta = get_object_or_404(Consulta, pk=request.GET.get('id'))
                servicio = Servicio.objects.get(pk=request.GET.get('idservicio'))
                tiene_mismo_tratamiento = VisitaTratamiento.objects.filter(
                    status=True,
                    consulta=consulta,
                    servicio_id=servicio,
                    tipo_servicio=servicio.tipo
                ).exists()
                return JsonResponse({'result': tiene_mismo_tratamiento})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'detalle':
            try:
                con = get_object_or_404(Consulta, pk=request.GET.get('id'))
                data['con']             = con
                data['tratamientos']    = con.tratamientos.filter(status=True).select_related('servicio')
                data['visitas']         = con.visitas.filter(status=True).select_related('servicio','tipo_servicio')
                data['apf']             = con.apf.filter(status=True)
                data['app']             = con.app.filter(status=True)
                data['alergias']        = con.alergias.filter(status=True)
                data['medicamentos']    = con.medicamentos.filter(status=True)
                data['suplementos']     = con.suplementos.filter(status=True)
                data['habitos']         = con.habitos.filter(status=True)
                data['actividades']     = con.actividades_fisicas.filter(status=True)
                data['trat_realizados'] = con.tratamientos_realizados.filter(status=True)
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

        elif action == 'abonaradelanto':
            try:
                con = get_object_or_404(Consulta, pk=request.GET.get('id'))
                data['con'] = con
                tmpl = get_template('admin/consultas/modal/abonar.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        else:
            search   = request.GET.get('s', '')
            filtro   = Q(status=True)
            url_vars = ''
            if search:
                filtro &= (Q(paciente__nombres__icontains=search) |
                           Q(paciente__identificacion__icontains=search))
                url_vars = f'&s={search}'
                data['s'] = search
            listado = Consulta.objects.filter(filtro).select_related('paciente', 'profesional')
            paging  = MiPaginador(listado, 25)
            p_num   = int(request.GET.get('page', 1))
            try: page = paging.page(p_num)
            except: p_num = 1; page = paging.page(1)
            data.update({
                'title': 'Consultas', 'paging': paging, 'page': page,
                'listado': page.object_list, 'url_vars': url_vars,
                'rangospaging': paging.rangos_paginado(p_num),
            })
    return render(request, 'admin/consultas/view.html', data)