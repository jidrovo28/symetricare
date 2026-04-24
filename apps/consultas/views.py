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

from decimal import Decimal
from django.db.models import Sum

def get_visita_activa(consulta, servicio):
    visitas = (
        VisitaTratamiento.objects
        .filter(
            status=True,
            consulta=consulta,
            servicio=servicio,
            tipo_servicio=servicio.tipo,
            contabilizar_costo=True
        )
        .order_by('id')  # más antigua primero
    )

    for v in visitas:
        total_costo = Decimal(v.costo or 0)

        abonos_inicial = Decimal(v.get_total_abonos_visita(consulta) or 0)

        visitas_ids = VisitaTratamiento.objects.filter(
            status=True,
            siguiente_visita=v,
            consulta=consulta
        ).exclude(id=v.id).values_list('id', flat=True)

        abonos_posteriores = Decimal(
            AbonoConsulta.objects.filter(
                status=True,
                consulta=consulta,
                visita_id__in=visitas_ids, visita__contabilizar_costo=False
            ).aggregate(total=Sum('monto'))['total'] or 0
        )

        total_abonos = abonos_inicial + abonos_posteriores

        if total_abonos < total_costo:
            return v, total_costo, total_abonos  # 👈 visita activa

    return None, Decimal(0), Decimal(0)  # 👈 todo pagado

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
                visita_inicial, total_costo, total_abonos = get_visita_activa(consulta, srv)

                contabilizar_costo = True

                if visita_inicial:
                    contabilizar_costo = False

                    saldo_restante = total_costo - total_abonos
                    total_abonado_actual = total_abonos + Decimal(abono or 0)

                    if total_abonado_actual > total_costo:
                        return JsonResponse({
                            'result': False,
                            'msg': f"El total abonado supera el costo del tratamiento. "
                                   f"Saldo restante del servicio {srv.nombre}: ${saldo_restante:.2f}"
                        })


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
                if visita_inicial:
                    visita.siguiente_visita = visita_inicial
                    visita.save()
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
                abonos_ = AbonoConsulta.objects.filter(status=True, visita=visita)
                for abono in abonos_:
                    movimientos = MovimientoFinanciero.objects.filter(status=True, abono=abono).update(status=False)
                    abono.status = False
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
                visita_ = abono.visita
                if visita_:
                    abonos_visita = visita_.get_abonos().aggregate(t=Sum('monto'))['t'] or 0
                    visita_.abono = abonos_visita
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
                consulta.recalcular_totales()
                consulta.paciente.cuenta.recalcular()
                consulta.refresh_from_db(fields=['total', 'abono', 'saldo'])
                if consulta.saldo == 0:
                    visitas = VisitaTratamiento.objects.filter(status=True, consulta=consulta, contabilizar_costo=True)
                    for visita_ in visitas:
                        visita_.saldo_cuenta = True
                        visita_.save()
                return JsonResponse({'result': True,
                    'msg': 'Consulta finalizada'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'actualizar_finanzas':
            try:
                from apps.pacientes.models import Paciente
                from apps.finanzas.models import MovimientoFinanciero, CuentaPaciente
                pacientes = Paciente.objects.filter(status=True)
                for paciente_ in pacientes:
                    consultas = Consulta.objects.filter(status=True, paciente=paciente_)
                    for consulta in consultas:
                        consulta.recalcular_totales()
                        consulta.refresh_from_db(fields=['total', 'abono', 'saldo'])
                    cuentas = CuentaPaciente.objects.filter(status=True, paciente=paciente_)
                    for cuenta_ in cuentas:
                        cuenta_.recalcular()
                return JsonResponse({'result': True,
                    'msg': 'Estados financieros actualizados.'})
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
                abono_ = AbonoConsulta.objects.create(
                    consulta=consulta, monto=monto,
                    forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                    nota=request.POST.get('nota', ''),
                    adelantado=True,
                    usuario_creacion=request.user)
                MovimientoFinanciero.objects.create(
                    paciente=consulta.paciente, consulta=consulta, abono=abono_,
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

        elif action == 'abonartratamiento':
            try:
                with transaction.atomic():
                    from apps.finanzas.models import CuentaPaciente, MovimientoFinanciero
                    visita_ = VisitaTratamiento.objects.get(id=request.POST.get('id'))
                    abonos_visita = float(visita_.visitasconsulta.filter(status=True).aggregate(t=Sum('monto'))['t'] or 0)
                    consulta = visita_.consulta
                    monto = float(request.POST.get('monto', 0))
                    if monto <= 0:
                        return JsonResponse({'result': False, 'msg': 'Monto inválido'})

                    abono_total = monto + abonos_visita
                    if abono_total > visita_.costo:
                        return JsonResponse({'result': False, 'msg': f'El abono total ${abono_total} (${abonos_visita} abonados anteriormente + ${monto}) supera el costo del tratamiento ${visita_.costo}.'})

                    abonos_consulta = float(consulta.abonos.filter(status=True).aggregate(t=Sum('monto'))['t'] or 0)
                    abono_total = monto + abonos_consulta
                    deudatotal_consulta = float(consulta.visitas.filter(status=True, contabilizar_costo=True).aggregate(t=Sum('costo'))['t'] or 0)
                    if abono_total > deudatotal_consulta:
                        return JsonResponse({'result': False, 'msg': f'El abono total de la consulta ${abono_total} supera la deuda general ${deudatotal_consulta}.'})

                    abono_anterior = visita_.abono
                    nuevo_monto_abono = Decimal(abono_anterior) + Decimal(monto)
                    visita_.abono = nuevo_monto_abono
                    visita_.save()
                    visita_.registrar_historial()

                    abono_ = AbonoConsulta.objects.create(
                        consulta=consulta, monto=monto, visita=visita_, servicio=visita_.servicio, tipo_servicio=visita_.tipo_servicio,
                        forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                        nota=request.POST.get('nota', ''),
                        adelantado=False,
                        usuario_creacion=request.user)
                    MovimientoFinanciero.objects.create(
                        paciente=consulta.paciente, consulta=consulta, abono=abono_,
                        tipo='abono', monto=monto,
                        descripcion=f'Abono al tratamiento #{consulta.pk}',
                        forma_pago=request.POST.get('forma_pago', 'Efectivo'),
                        usuario_creacion=request.user)
                    cuenta, _ = CuentaPaciente.objects.get_or_create(
                        paciente=consulta.paciente,
                        defaults={'usuario_creacion': request.user})
                    cuenta.recalcular()
                    return JsonResponse({'result': True,
                        'msg': f'Abono de ${monto:.2f} al tratamiento {visita_.servicio.nombre} registrado'})
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
                no_puede_registrar = False
                for tratamiento_ in VisitaTratamiento.objects.filter(status=True, consulta=consulta, servicio_id=servicio, tipo_servicio=servicio.tipo, contabilizar_costo=True):
                    total_costo = tratamiento_.costo
                    abonos_visita_inicial = tratamiento_.get_total_abonos_visita(consulta)
                    visitas_posteriores = VisitaTratamiento.objects.filter(status=True, siguiente_visita=tratamiento_, consulta=consulta).values_list('id', flat=True)
                    abonos_visitas_posteriores = AbonoConsulta.objects.filter(status=True, consulta=consulta, visita_id__in=visitas_posteriores).aggregate(t=Sum('monto'))['t'] or 0
                    total_abonos = Decimal(abonos_visita_inicial) + Decimal(abonos_visitas_posteriores)
                    if Decimal(total_abonos) == Decimal(total_costo):
                        no_puede_registrar = False
                    else:
                        no_puede_registrar = True
                return JsonResponse({'result': no_puede_registrar})
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

        elif action == 'abonartratamiento':
            try:
                visita = get_object_or_404(VisitaTratamiento, pk=request.GET.get('id'))
                data['visita'] = visita
                data['id'] = visita.id
                data['con'] = visita.consulta
                tmpl = get_template('admin/consultas/modal/abonartratamiento.html')
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