from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from .models import Paciente


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_pacientes(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            try:
                ced = request.POST.get('identificacion', '').strip()
                if Paciente.objects.filter(identificacion=ced).exists():
                    return JsonResponse({'result': False,
                        'msg': f'Ya existe un paciente con identificación {ced}'})
                p = Paciente.objects.create(
                    tipo_identificacion=request.POST.get('tipo_identificacion', 'cedula'),
                    identificacion=ced,
                    nombres=request.POST.get('nombres', ''),
                    apellido1=request.POST.get('apellido1', ''),
                    apellido2=request.POST.get('apellido2', ''),
                    telefono=request.POST.get('telefono', ''),
                    celular=request.POST.get('celular', ''),
                    fecha_nacimiento=request.POST.get('fecha_nacimiento') or None,
                    edad=request.POST.get('edad') or None,
                    direccion=request.POST.get('direccion', ''),
                    email=request.POST.get('email', ''),
                    num_hijos=int(request.POST.get('num_hijos', 0)),
                    usuario_creacion=request.user,
                )
                return JsonResponse({'result': True, 'msg': 'Paciente registrado',
                    'id': p.pk, 'nombre': p.nombre_completo,
                    'identificacion': p.identificacion})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'edit':
            try:
                p = get_object_or_404(Paciente, pk=request.POST.get('id'))
                for campo in ['nombres','apellido1','apellido2','telefono',
                              'celular','direccion','email','num_hijos']:
                    if campo in request.POST:
                        setattr(p, campo, request.POST.get(campo))
                if request.POST.get('fecha_nacimiento'):
                    p.fecha_nacimiento = request.POST.get('fecha_nacimiento')
                if request.POST.get('edad'):
                    p.edad = int(request.POST.get('edad'))
                p.usuario_modificacion = request.user
                p.save()
                return JsonResponse({'result': True, 'msg': 'Paciente actualizado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                p = get_object_or_404(Paciente, pk=request.POST.get('id'))
                p.status = False
                p.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        action = request.GET.get('action', '')

        if action in ('add', 'edit'):
            pac = None
            if action == 'edit':
                pac = get_object_or_404(Paciente, pk=request.GET.get('id'))
            data['pac'] = pac
            tmpl = get_template('admin/pacientes/modal/form.html')
            return JsonResponse({'result': True, 'data': tmpl.render(data, request)})

        elif action == 'buscar':
            q = request.GET.get('q', '')
            qs = Paciente.objects.filter(status=True).filter(
                Q(nombres__icontains=q) | Q(apellido1__icontains=q) |
                Q(apellido2__icontains=q) | Q(identificacion__icontains=q))[:10]
            return JsonResponse({'result': True, 'data': [
                {'id': p.pk, 'nombre': p.nombre_completo,
                 'identificacion': p.identificacion,
                 'telefono': p.telefono}
                for p in qs]})

        elif action == 'get_consultas_paciente':
            from apps.consultas.models import Consulta
            paciente_id = request.GET.get('paciente_id')
            consultas = Consulta.objects.filter(
                status=True, paciente_id=paciente_id, estado='atendida'
            ).order_by('-fecha_creacion')
            result = []
            for c in consultas:
                n_visitas = c.visitas.filter(status=True).count()
                result.append({
                    'id':             c.id,
                    'fecha_creacion': c.fecha_creacion.strftime('%d/%m/%Y'),
                    'motivo':         c.motivo_consulta or '',
                    'detalle':        c.observaciones or '',
                    'n_visitas':      n_visitas,
                    'total':          str(c.abono),
                    'estado':         c.estado,
                    'estado_display':         c.get_estado_display(),
                })
            return JsonResponse({'data': result})


        elif action == 'get_tratamientos_consulta':
            from apps.consultas.models import Consulta, VisitaTratamiento
            from django.db.models import Sum
            from decimal import Decimal
            consulta_id = request.GET.get('consulta_id')
            if not consulta_id:
                return JsonResponse({'result': False, 'msg': 'consulta_id requerido'})
            try:
                consulta = Consulta.objects.get(pk=consulta_id, status=True)
            except Consulta.DoesNotExist:
                return JsonResponse({'result': False, 'msg': 'Consulta no encontrada'})
            tratos = (VisitaTratamiento.objects.filter(status=True, consulta=consulta,
                                                       contabilizar_costo=True).select_related('servicio', 'tipo_servicio').order_by('id'))
            result = []
            for t in tratos:
                total_costo = Decimal(t.costo or 0)
                abonos_inicial = Decimal(t.get_total_abonos_visita(consulta) or 0)
                visitas_ids = VisitaTratamiento.objects.filter(status=True, siguiente_visita=t, consulta=consulta).values_list('id', flat=True)
                abonos_posteriores = Decimal(consulta.abonos.filter(status=True, visita_id__in=visitas_ids).aggregate(total=Sum('monto'))['total'] or 0)
                total_abonos = abonos_inicial + abonos_posteriores
                saldo = total_costo - total_abonos
                if total_abonos > 0:
                    result.append({'id': t.pk, 'nombre': t.servicio.nombre,
                                   'tipo': t.tipo_servicio.nombre if t.tipo_servicio else '',
                                   'color': t.tipo_servicio.color if t.tipo_servicio else '#6366f1',
                        'abonado': Decimal(total_abonos), 'fecha_visita': t.fecha.strftime('%d/%m/%Y'), 'descripcion': t.descripcion or '',})

            return JsonResponse({'result': True, 'motivo': consulta.motivo_consulta, 'data': result,})

        else:
            search = request.GET.get('s', '')
            filtro = Q(status=True)
            if search:
                filtro &= (Q(nombres__icontains=search) |
                           Q(apellido1__icontains=search) |
                           Q(identificacion__icontains=search))
                data['s'] = search
            listado = Paciente.objects.filter(filtro)
            paging  = MiPaginador(listado, 25)
            p_num   = int(request.GET.get('page', 1))
            try: page = paging.page(p_num)
            except: p_num = 1; page = paging.page(1)
            data.update({
                'title': 'Pacientes', 'paging': paging, 'page': page,
                'listado': page.object_list,
                'url_vars': f'&s={search}' if search else '',
                'rangospaging': paging.rangos_paginado(p_num),
            })
    return render(request, 'admin/pacientes/view.html', data)


@login_required(redirect_field_name='ret', login_url='/login')
def view_ficha(request, pk):
    data = {}
    adduserdata(request, data)
    pac = get_object_or_404(Paciente, pk=pk, status=True)

    consultas = pac.consultas.filter(status=True).prefetch_related(
        'tratamientos__servicio',
        'visitas__servicio',
        'visitas__tipo_servicio',
        'apf', 'app', 'alergias', 'medicamentos',
        'suplementos', 'habitos', 'actividades_fisicas',
        'tratamientos_realizados',
    ).order_by('-fecha_creacion')[:30]

    todos_apf = []; todos_app = []; todas_alg = []; todos_med = []
    todos_sup = []; todos_hab = []; todos_act = []; todos_tr  = []

    for c in consultas:
        for a in c.apf.filter(status=True):             todos_apf.append((c, a))
        for a in c.app.filter(status=True):             todos_app.append((c, a))
        for a in c.alergias.filter(status=True):        todas_alg.append((c, a))
        for m in c.medicamentos.filter(status=True):    todos_med.append((c, m))
        for s in c.suplementos.filter(status=True):     todos_sup.append((c, s))
        for h in c.habitos.filter(status=True):         todos_hab.append((c, h))
        for a in c.actividades_fisicas.filter(status=True): todos_act.append((c, a))
        for t in c.tratamientos_realizados.filter(status=True): todos_tr.append((c, t))

    data.update({
        'title':     f'Ficha — {pac.nombre_completo}',
        'pac':       pac,
        'consultas': consultas,
        'citas':     pac.citas.filter(status=True).order_by('-fecha')[:10],
        'todos_apf': todos_apf, 'todos_app': todos_app,
        'todas_alg': todas_alg, 'todos_med': todos_med,
        'todos_sup': todos_sup, 'todos_hab': todos_hab,
        'todos_act': todos_act, 'todos_tr':  todos_tr,
    })
    try:
        pac.cuenta.recalcular()
        data['cuenta'] = pac.cuenta
    except Exception:
        data['cuenta'] = None

    return render(request, 'admin/pacientes/ficha.html', data)