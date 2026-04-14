from datetime import datetime, date, timedelta
from django.shortcuts import render
from django.http import JsonResponse
from django.db import transaction


def home(request):
    from apps.servicios.models import Servicio, TipoServicio
    return render(request, 'web/home.html', {
        'servicios': Servicio.objects.filter(status=True, activo=True).select_related('tipo')[:12],
        'tipos':     TipoServicio.objects.filter(status=True),
    })


@transaction.atomic()
def reservar_cita(request):
    if request.method == 'POST':
        try:
            from apps.citas.models import Cita
            from apps.pacientes.models import Paciente
            import uuid

            nombre   = request.POST.get('nombre','').strip()
            email    = request.POST.get('email','').strip()
            telefono = request.POST.get('telefono','').strip()
            cedula   = request.POST.get('cedula','').strip()
            fecha    = request.POST.get('fecha','')
            hora     = request.POST.get('hora','')
            srv_id   = request.POST.get('servicio_id')
            notas    = request.POST.get('notas','')

            if not all([nombre, fecha, hora]):
                return JsonResponse({'result': False, 'msg': 'Completa nombre, fecha y hora'})

            # Verificar disponibilidad
            if Cita.objects.filter(status=True, fecha=fecha, hora=hora,
                                    estado__in=['pendiente','confirmada']).exists():
                return JsonResponse({'result': False, 'msg': 'Ese horario ya está ocupado. Escoge otro.'})

            # Buscar paciente existente
            pac = None
            if cedula:
                pac = Paciente.objects.filter(identificacion=cedula, status=True).first()

            if not pac:
                partes = nombre.split()
                nombres = " ".join(partes[:-2])
                apellido1 = partes[-2]
                apellido2 = partes[-1]
                pac = Paciente.objects.create(
                    tipo_identificacion=request.POST.get('tipo_identificacion', 'cedula'),
                    identificacion=cedula,
                    nombres=nombres,
                    apellido1=apellido1,
                    apellido2=apellido2,
                    telefono=telefono,
                    email=email,
                    direccion=request.POST.get('direccion', ''),
                )

            cita = Cita.objects.create(
                paciente      = pac,
                fecha         = fecha,
                hora          = hora,
                servicio_id   = srv_id or None,
                notas         = notas,
                estado        = Cita.PENDIENTE,
                reservado_web = True,
                nombre_web    = nombre,
                email_web     = email,
                telefono_web  = telefono,
                token_confirmacion = uuid.uuid4().hex[:16],
            )
            return JsonResponse({'result': True,
                'msg': f'¡Cita reservada! Te esperamos el {fecha} a las {hora}.'})
        except Exception as ex:
            return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        if 'action' in request.GET:
            action = request.GET['action']

            if action == 'consulta_paciente':
                try:
                    from apps.pacientes.models import Paciente
                    data = {}
                    identificacion = request.GET['identificacion']
                    paciente = Paciente.objects.filter(status=True, identificacion=identificacion).first()
                    if not paciente:
                        return JsonResponse({'result': True, 'data': data})
                    data['nombres'] = nombres = f"{paciente.nombres} {paciente.apellido1} {paciente.apellido2}"
                    data['telefono'] = telefono = paciente.telefono
                    data['email'] = email = paciente.email
                    return JsonResponse({'result': True, 'data': data})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})
        else:
            # GET: render form
            from apps.citas.models import DisponibilidadHoraria
            from apps.servicios.models import Servicio
            return render(request, 'web/reservar.html', {
                'servicios': Servicio.objects.filter(status=True, activo=True),
            })


def slots_web(request):
    """AJAX: devuelve slots disponibles para una fecha."""
    try:
        from apps.citas.models import Cita, DisponibilidadHoraria, BloqueoFecha
        fecha_str = request.GET.get('fecha','')
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        if fecha_obj < date.today():
            return JsonResponse({'result': False, 'msg': 'Fecha en el pasado'})
        bloqueo_ = BloqueoFecha.objects.filter(status=True, fecha=fecha_obj)
        if bloqueo_.exists():
            bloqueo_ = bloqueo_.first()
            return JsonResponse({'result': True, 'slots': [], 'msg': f"Fecha no disponible - {bloqueo_.motivo}"})
        dia_sem     = fecha_obj.weekday()
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
                if ht not in ocupados:
                    slots.append({'hora': ht.strftime('%H:%M')})
                h += timedelta(minutes=d.duracion_min)
        return JsonResponse({'result': True, 'slots': slots})
    except Exception as ex:
        return JsonResponse({'result': False, 'msg': str(ex)})
