from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import get_template
from .helpers import adduserdata
from .models import Usuario


@login_required(redirect_field_name='ret', login_url='/login')
@transaction.atomic()
def view_usuarios(request):
    data = {}
    adduserdata(request, data)
    if not request.user.es_admin:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            try:
                username = request.POST.get('username','').strip()
                if Usuario.objects.filter(username=username).exists():
                    return JsonResponse({'result': False, 'msg': f'Usuario {username} ya existe'})
                u = Usuario.objects.create_user(
                    username   = username,
                    password   = request.POST.get('password','Admin1234!'),
                    first_name = request.POST.get('first_name',''),
                    last_name  = request.POST.get('last_name',''),
                    email      = request.POST.get('email',''),
                    rol        = request.POST.get('rol', Usuario.ROL_RECEPCION),
                    modulos_permitidos = request.POST.getlist('modulos'),
                )
                return JsonResponse({'result': True, 'msg': f'Usuario {username} creado'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'toggle':
            try:
                u = get_object_or_404(Usuario, pk=request.POST.get('id'))
                u.activo_sistema = not u.activo_sistema
                u.save(update_fields=['activo_sistema'])
                return JsonResponse({'result': True})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

        elif action == 'modulos':
            try:
                u = get_object_or_404(Usuario, pk=request.POST.get('id'))
                u.modulos_permitidos = request.POST.getlist('modulos')
                u.save(update_fields=['modulos_permitidos'])
                return JsonResponse({'result': True, 'msg': 'Permisos actualizados'})
            except Exception as ex:
                return JsonResponse({'result': False, 'msg': str(ex)})

    else:
        if 'action' in request.GET:
            action = request.GET['action']
            if action == 'add':
                data['modulos'] = Usuario.MODULOS
                tmpl = get_template('admin/config/modal/usuario_form.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})
            elif action == 'permisos':
                u = get_object_or_404(Usuario, pk=request.GET.get('id'))
                data['u']       = u
                data['modulos'] = Usuario.MODULOS
                tmpl = get_template('admin/config/modal/permisos_form.html')
                return JsonResponse({'result': True, 'data': tmpl.render(data, request)})

        else:
            data['title']   = 'Usuarios'
            data['listado'] = Usuario.objects.all().order_by('first_name')
    return render(request, 'admin/config/usuarios.html', data)
