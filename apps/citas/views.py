import json
from datetime import datetime, date, timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from .models import Cita, DisponibilidadHoraria, BloqueoFecha


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_citas(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            try:
                from apps.pacientes.models import Paciente
                pac  = get_object_or_404(Paciente, pk=request.POST.get('paciente_id'))
                fecha = request.POST.get('fecha')
                hora  = request.POST.get('hora')
                # Verificar disponibilidad
                if Cita.objects.filter(status=True, fecha=fecha, hora=hora,
                                        estado__in=['pendiente','confirmada']).exists():
                    return JsonResponse({'result': False, 'msg': 'Horario ya ocupado'})
                cita = Cita.objects.create(
                    paciente   = pac,
                    profesional = request.user,
                    fecha      = fecha,
                    hora       = hora,
                    servicio_id = request.POST.get('servicio_id') or None,
                    notas      = request.POST.get('notas',''),
                    estado     = Cita.PENDIENTE,
                    usuario_creacion = request.user,
                )
                return JsonResponse({'result': True, 'msg': f'Cita agendada para {fecha} {hora}', 'id': cita.pk})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'cambiar_estado':
            try:
                cita = get_object_or_404(Cita, pk=request.POST.get('id'))
                cita.estado = request.POST.get('estado', cita.estado)
                cita.usuario_modificacion = request.user
                cita.save(update_fields=['estado','usuario_modificacion','fecha_modificacion'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                obj = get_object_or_404(Cita, pk=request.POST.get('id'))
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'slots_disponibles':
            try:
                fecha_str = request.POST.get('fecha','')
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                dia_sem   = fecha_obj.weekday()
                bloqueado = BloqueoFecha.objects.filter(status=True, fecha=fecha_obj).exists()
                if bloqueado:
                    return JsonResponse({'result': True, 'slots': [], 'msg': 'Fecha bloqueada'})
                disponibles = DisponibilidadHoraria.objects.filter(status=True, activo=True, dia_semana=dia_sem)
                ocupados    = set(Cita.objects.filter(status=True, fecha=fecha_obj,
                                                       estado__in=['pendiente','confirmada'])
                                  .values_list('hora', flat=True))
                slots = []
                for d in disponibles:
                    h = datetime.combine(fecha_obj, d.hora_inicio)
                    fin = datetime.combine(fecha_obj, d.hora_fin)
                    while h < fin:
                        ht = h.time()
                        slots.append({'hora': ht.strftime('%H:%M'),
                                       'libre': ht not in ocupados})
                        h += timedelta(minutes=d.duracion_min)
                return JsonResponse({'result': True, 'slots': slots})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        if 'action' in request.GET:
            action = request.GET['action']

            if action == 'add':
                from apps.pacientes.models import Paciente
                from apps.servicios.models import Servicio
                data['servicios'] = Servicio.objects.filter(status=True, activo=True)
                tmpl = get_template('admin/citas/modal/form.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})

            elif action == 'detalle':
                try:
                    cita = get_object_or_404(Cita, pk=request.GET.get('id'))
                    data['cita'] = cita
                    tmpl = get_template('admin/citas/modal/detalle.html')
                    return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

            elif action == 'calendario_data':
                try:
                    year  = int(request.GET.get('year',  date.today().year))
                    month = int(request.GET.get('month', date.today().month))
                    citas = Cita.objects.filter(status=True,
                        fecha__year=year, fecha__month=month).select_related('paciente').order_by('fecha','hora')
                    events = [{'id':c.pk,'fecha':str(c.fecha),'hora':str(c.hora)[:5],
                                'nombre': c.paciente.nombre_completo if c.paciente_id else c.nombre_web,
                                'estado': c.estado} for c in citas]
                    return JsonResponse({'result': True, 'events': events})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

        else:
            data['title'] = 'Gestión de Citas'
            hoy   = date.today()
            filtro = Q(status=True, fecha__gte=hoy)
            estado = request.GET.get('estado','')
            if estado: filtro &= Q(estado=estado)
            from django.db.models import Case, When, Value, IntegerField

            listado = Cita.objects.filter(filtro).select_related('paciente', 'servicio').annotate(
                orden_estado=Case(
                    When(estado='pendiente', then=Value(1)),
                    When(estado='confirmada', then=Value(2)),
                    When(estado='atendida', then=Value(3)),
                    When(estado='cancelada', then=Value(4)),
                    When(estado='no_asistio', then=Value(5)),
                    default=Value(99),
                    output_field=IntegerField()
                )
            ).order_by('orden_estado', 'fecha', 'hora')
            paging  = MiPaginador(listado, 30)
            p_num   = int(request.GET.get('page',1))
            try: page = paging.page(p_num)
            except: p_num=1; page=paging.page(1)
            data.update({'paging':paging,'page':page,'listado':page.object_list,
                         'rangospaging':paging.rangos_paginado(p_num),
                         'estado':estado,'estados':Cita.ESTADO_CHOICES,
                         'today': hoy.isoformat()})
    return render(request, 'admin/citas/view.html', data)


@login_required(redirect_field_name='ret', login_url='/login')
def view_calendario(request):
    data = {}
    adduserdata(request, data)
    data['title'] = 'Calendario de Citas'
    hoy = date.today()
    data.update({'year': hoy.year, 'month': hoy.month, 'today': hoy.isoformat()})
    return render(request, 'admin/citas/calendario.html', data)


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_disponibilidad(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            try:
                DisponibilidadHoraria.objects.create(
                    dia_semana   = int(request.POST.get('dia_semana')),
                    hora_inicio  = request.POST.get('hora_inicio'),
                    hora_fin     = request.POST.get('hora_fin'),
                    duracion_min = int(request.POST.get('duracion_min', 60)),
                    activo       = True,
                    usuario_creacion = request.user,
                )
                return JsonResponse({'result': True, 'msg': 'Horario configurado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'toggle':
            try:
                obj = get_object_or_404(DisponibilidadHoraria, pk=request.POST.get('id'))
                obj.activo = not obj.activo
                obj.save(update_fields=['activo'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                obj = get_object_or_404(DisponibilidadHoraria, pk=request.POST.get('id'))
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'bloqueo':
            try:
                fecha = request.POST.get('fecha')
                motivo = request.POST.get('motivo')
                if not fecha and not motivo:
                    return JsonResponse({'result': False, 'msg': 'Por favor, seleccione fecha e ingrese el motivo.'})
                BloqueoFecha.objects.create(
                    fecha  = fecha,
                    motivo = motivo,
                    usuario_creacion = request.user)
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        data['title'] = 'Disponibilidad Horaria'
        data['horarios']     = DisponibilidadHoraria.objects.filter(status=True).order_by('dia_semana','hora_inicio')
        data['bloqueos']     = BloqueoFecha.objects.filter(status=True, fecha__gte=date.today()).order_by('fecha')
        data['dia_choices']  = DisponibilidadHoraria.DIA_CHOICES
    return render(request, 'admin/citas/disponibilidad.html', data)
