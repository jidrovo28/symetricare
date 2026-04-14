from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import get_template
from apps.core.helpers import adduserdata
from .models import Servicio, TipoServicio


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_servicios(request):
    data = {}
    adduserdata(request, data)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            try:
                Servicio.objects.create(
                    tipo_id    = request.POST.get('tipo_id') or None,
                    nombre     = request.POST.get('nombre'),
                    descripcion= request.POST.get('descripcion',''),
                    precio     = request.POST.get('precio',0),
                    duracion_min=int(request.POST.get('duracion_min',60)),
                    usuario_creacion=request.user)
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})
        elif action == 'edit':
            try:
                obj = get_object_or_404(Servicio, pk=request.POST.get('id'))
                for c in ['nombre','descripcion','precio','duracion_min']:
                    v = request.POST.get(c)
                    if v: setattr(obj,c,v)
                obj.tipo_id = request.POST.get('tipo_id') or None
                obj.activo  = request.POST.get('activo') == 'on'
                obj.usuario_modificacion = request.user
                obj.save()
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})
        elif action == 'delete':
            try:
                obj = get_object_or_404(Servicio, pk=request.POST.get('id'))
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})
    else:
        if 'action' in request.GET:
            action = request.GET['action']
            if action == 'add':
                data['tipos'] = TipoServicio.objects.filter(status=True)
                tmpl = get_template('admin/servicios/modal/form.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
            elif action == 'edit':
                obj = get_object_or_404(Servicio, pk=request.GET.get('id'))
                data['obj']   = obj
                data['tipos'] = TipoServicio.objects.filter(status=True)
                tmpl = get_template('admin/servicios/modal/form.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
        else:
            data['title']   = 'Servicios'
            data['listado'] = Servicio.objects.filter(status=True).select_related('tipo')
            data['tipos']   = TipoServicio.objects.filter(status=True)
    return render(request, 'admin/servicios/view.html', data)


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_tipos(request):
    data = {}
    adduserdata(request, data)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            try:
                TipoServicio.objects.create(
                    nombre=request.POST.get('nombre'),
                    color=request.POST.get('color','#6366f1'),
                    usuario_creacion=request.user)
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})
        elif action == 'delete':
            try:
                obj = get_object_or_404(TipoServicio, pk=request.POST.get('id'))
                obj.status = False; obj.save(update_fields=['status'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})
    else:
        data['title']   = 'Tipos de Servicio'
        data['listado'] = TipoServicio.objects.filter(status=True)
    return render(request, 'admin/servicios/tipos.html', data)
