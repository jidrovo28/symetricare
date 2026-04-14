from datetime import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata, MiPaginador
from .models import (Paciente, APF, APP, Alergia, Medicamento,
                     Suplemento, Habito, ActividadFisica, TratamientoRealizado)


def _check(request):
    if not request.user.is_authenticated:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    return None


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_pacientes(request):
    data = {}
    adduserdata(request, data)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'buscar_cedula':
            try:
                cedula = request.POST.get('cedula','').strip()
                pac    = Paciente.objects.filter(identificacion=cedula, status=True).first()
                if pac:
                    return JsonResponse({'result': True, 'existe': True,
                        'paciente': {'id':pac.pk,'nombre':pac.nombre_completo,
                                      'identificacion':pac.identificacion,'telefono':pac.telefono}})
                return JsonResponse({'result': True, 'existe': False})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'add':
            try:
                ced = request.POST.get('identificacion','').strip()
                if Paciente.objects.filter(identificacion=ced, status=True).exists():
                    return JsonResponse({'result': False, 'msg': f'Ya existe un paciente con identificación {ced}'})
                pac = Paciente.objects.create(
                    tipo_identificacion = request.POST.get('tipo_identificacion','cedula'),
                    identificacion      = ced,
                    nombres             = request.POST.get('nombres',''),
                    apellido1           = request.POST.get('apellido1',''),
                    apellido2           = request.POST.get('apellido2',''),
                    telefono            = request.POST.get('telefono',''),
                    email               = request.POST.get('email',''),
                    fecha_nacimiento    = request.POST.get('fecha_nacimiento') or None,
                    edad                = request.POST.get('edad') or None,
                    direccion           = request.POST.get('direccion',''),
                    num_hijos           = int(request.POST.get('num_hijos',0)),
                    usuario_creacion    = request.user,
                )
                return JsonResponse({'result': True, 'msg': 'Paciente registrado', 'id': pac.pk})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'edit':
            try:
                pac = get_object_or_404(Paciente, pk=request.POST.get('id'))
                for c in ['nombres','apellido1','apellido2','telefono','email',
                           'fecha_nacimiento','edad','direccion','num_hijos']:
                    v = request.POST.get(c)
                    if v is not None: setattr(pac, c, v or (0 if c=='num_hijos' else None if c in ('fecha_nacimiento','edad') else ''))
                pac.usuario_modificacion = request.user
                pac.save()
                return JsonResponse({'result': True, 'msg': 'Datos actualizados'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'delete':
            try:
                obj = get_object_or_404(Paciente, pk=request.POST.get('id'))
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        # Antecedentes y datos relacionados
        elif action in ('add_apf','add_app','add_alergia','add_medicamento',
                        'add_suplemento','add_habito','add_actividad','add_tratamiento_realizado'):
            try:
                pac = get_object_or_404(Paciente, pk=request.POST.get('paciente_id'))
                modelo_map = {
                    'add_apf': APF, 'add_app': APP,
                    'add_alergia': Alergia, 'add_medicamento': Medicamento,
                    'add_suplemento': Suplemento, 'add_habito': Habito,
                    'add_actividad': ActividadFisica,
                    'add_tratamiento_realizado': TratamientoRealizado,
                }
                Model = modelo_map[action]
                kwargs = {'paciente': pac, 'descripcion': request.POST.get('descripcion',''),
                          'usuario_creacion': request.user}
                if action == 'add_app':
                    kwargs['fecha_diagnostico'] = request.POST.get('fecha_diagnostico') or None
                if action == 'add_tratamiento_realizado':
                    kwargs['fecha'] = request.POST.get('fecha') or None
                Model.objects.create(**kwargs)
                return JsonResponse({'result': True, 'msg': 'Guardado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'del_antecedente':
            try:
                tipo = request.POST.get('tipo')
                pk   = request.POST.get('id')
                modelo_map = {
                    'apf': APF, 'app': APP, 'alergia': Alergia,
                    'medicamento': Medicamento, 'suplemento': Suplemento,
                    'habito': Habito, 'actividad': ActividadFisica,
                    'tratamiento': TratamientoRealizado,
                }
                obj = get_object_or_404(modelo_map[tipo], pk=pk)
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        if 'action' in request.GET:
            action = request.GET['action']

            if action == 'add':
                tmpl = get_template('admin/pacientes/modal/form.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})

            elif action == 'edit':
                try:
                    pac = get_object_or_404(Paciente, pk=request.GET.get('id'))
                    data['pac'] = pac
                    tmpl = get_template('admin/pacientes/modal/form.html')
                    return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

            elif action == 'ficha':
                try:
                    pac = get_object_or_404(Paciente, pk=request.GET.get('id'))
                    return redirect_ficha(request, pac.pk)
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

            elif action == 'buscar':
                try:
                    q  = request.GET.get('q','')
                    qs = Paciente.objects.filter(status=True).filter(
                        Q(nombres__icontains=q)|Q(apellido1__icontains=q)|
                        Q(identificacion__icontains=q))[:10]
                    items = [{'id':p.pk,'nombre':p.nombre_completo,
                               'identificacion':p.identificacion,'telefono':p.telefono} for p in qs]
                    return JsonResponse({'result': True, 'data': items})
                except Exception as ex:
                    return JsonResponse({'result': False, 'msg': str(ex)})

        else:
            data['title'] = 'Pacientes'
            search   = request.GET.get('s','')
            filtro   = Q(status=True)
            url_vars = ''
            if search:
                filtro &= Q(nombres__icontains=search)|Q(apellido1__icontains=search)|Q(identificacion__icontains=search)
                url_vars = f'&s={search}'
                data['s'] = search
            listado = Paciente.objects.filter(filtro)
            paging  = MiPaginador(listado, 25)
            p_num   = int(request.GET.get('page',1))
            try: page = paging.page(p_num)
            except: p_num=1; page=paging.page(1)
            data.update({'paging':paging,'page':page,'listado':page.object_list,
                         'url_vars':url_vars,'rangospaging':paging.rangos_paginado(p_num)})
    return render(request, 'admin/pacientes/view.html', data)


def redirect_ficha(request, paciente_id):
    from django.shortcuts import redirect
    return redirect(f'/pacientes/{paciente_id}/ficha/')


@login_required(redirect_field_name='ret', login_url='/login')
def view_ficha(request, pk):
    data = {}
    adduserdata(request, data)
    pac = get_object_or_404(Paciente, pk=pk, status=True)
    data.update({
        'title':    f'Ficha — {pac.nombre_completo}',
        'pac':      pac,
        'apf':      pac.apf.filter(status=True),
        'app':      pac.app.filter(status=True),
        'alergias': pac.alergias.filter(status=True),
        'medicamentos': pac.medicamentos.filter(status=True),
        'suplementos':  pac.suplementos.filter(status=True),
        'habitos':      pac.habitos.filter(status=True),
        'actividades':  pac.actividades_fisicas.filter(status=True),
        'tratamientos_realizados': pac.tratamientos_realizados.filter(status=True),
        'consultas':    pac.consultas.filter(status=True).order_by('-fecha_creacion')[:10],
        'citas':        pac.citas.filter(status=True).order_by('-fecha')[:5],
    })
    try:
        data['cuenta'] = pac.cuenta
    except Exception:
        data['cuenta'] = None
    return render(request, 'admin/pacientes/ficha.html', data)
