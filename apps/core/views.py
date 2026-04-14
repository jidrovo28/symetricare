from datetime import date
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from .helpers import adduserdata


def login_view(request):
    data = {}
    if request.user.is_authenticated:
        return redirect('/dashboard')
    if request.method == 'POST':
        user = authenticate(request,
            username=request.POST.get('username',''),
            password=request.POST.get('password',''))
        if user and user.activo_sistema:
            login(request, user)
            return redirect('/dashboard')
        data['error'] = 'Usuario o contraseña incorrectos'
    return render(request, 'auth/login.html', data)


def logout_view(request):
    request.session.flush()
    logout(request)
    return redirect('/login')


@login_required(redirect_field_name='ret', login_url='/login')
def dashboard(request):
    data = {}
    adduserdata(request, data)
    from apps.pacientes.models import Paciente
    from apps.consultas.models import Consulta
    from apps.citas.models      import Cita

    hoy = date.today()
    mes = hoy.replace(day=1)

    data.update({
        'title':            'Dashboard',
        'total_pacientes':  Paciente.objects.filter(status=True).count(),
        'consultas_hoy':    Consulta.objects.filter(status=True, fecha_creacion__date=hoy).count(),
        'consultas_mes':    Consulta.objects.filter(status=True, fecha_creacion__date__gte=mes).count(),
        'citas_hoy':        Cita.objects.filter(status=True, fecha=hoy).count(),
        'citas_pendientes': Cita.objects.filter(status=True, fecha__gte=hoy, estado='pendiente').count(),
        'ultimas_consultas':Consulta.objects.filter(status=True).select_related('paciente').order_by('-fecha_creacion')[:8],
        'citas_proximas':   Cita.objects.filter(status=True, fecha__gte=hoy, estado='pendiente').select_related('paciente').order_by('fecha','hora')[:8],
        'ingresos_hoy':     Consulta.objects.filter(status=True, fecha_creacion__date=hoy).aggregate(t=Sum('abono'))['t'] or 0,
        'ingresos_mes':     Consulta.objects.filter(status=True, fecha_creacion__date__gte=mes).aggregate(t=Sum('abono'))['t'] or 0,
    })
    return render(request, 'admin/dashboard/view.html', data)
