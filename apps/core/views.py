from datetime import date
from django.contrib import messages
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

@login_required
def config_clinica(request):
    from apps.core.models import Clinica
    clinica = Clinica.get()
    if request.method == 'POST':
        for campo in ['nombre','ruc','razon_social','nombre_comercial','direccion',
                      'telefono','email','ciudad','color_primario',
                      'contribuyente_especial','serie_establecimiento',
                      'serie_punto_emision','sri_ambiente']:
            setattr(clinica, campo, request.POST.get(campo, '') or getattr(clinica, campo, ''))
        clinica.obligado_contabilidad = request.POST.get('obligado_contabilidad') == 'on'
        if 'logo' in request.FILES:
            clinica.logo = request.FILES['logo']
        clinica.save()
        messages.success(request, 'Configuración de clínica guardada.')
        return redirect('config_clinica')
    return render(request, 'admin/config/clinica.html', {'clinica': clinica})

@login_required
def config_firma(request):
    from apps.core.models import Clinica
    """Configuración de firma electrónica (certificado P12 para SRI)."""
    clinica = Clinica.get()
    if request.method == 'POST':
        if 'certificado_p12' in request.FILES:
            clinica.certificado_p12 = request.FILES['certificado_p12']
        if 'firma_ec_jar' in request.FILES:
            clinica.firma_ec_jar = request.FILES['firma_ec_jar']
        clave = request.POST.get('clave_certificado', '').strip()
        if clave:
            clinica.clave_certificado = clave
        clinica.sri_ambiente = request.POST.get('sri_ambiente', '1')
        clinica.java_home = request.POST.get('java_home', '').strip()
        clinica.save()

        # Verificar el certificado P12 si se subió
        if clinica.certificado_p12:
            try:
                import os
                from cryptography.hazmat.primitives.serialization import pkcs12
                p12_path = clinica.certificado_p12.path
                if os.path.exists(p12_path):
                    pwd = clinica.clave_certificado.encode()
                    with open(p12_path, 'rb') as f:
                        pkcs12.load_key_and_certificates(f.read(), pwd)
                    messages.success(request, '✅ Certificado P12 verificado y guardado correctamente.')
                else:
                    messages.success(request, 'Configuración de firma guardada.')
            except Exception as e:
                messages.warning(request, f'Certificado guardado pero error al verificar: {e}')
        else:
            messages.success(request, 'Configuración SRI guardada.')
        return redirect('config_firma')

    # Info del certificado actual
    cert_info = None
    if clinica.certificado_p12:
        try:
            import os
            from cryptography.hazmat.primitives.serialization import pkcs12
            p12_path = clinica.certificado_p12.path
            if os.path.exists(p12_path) and clinica.clave_certificado:
                with open(p12_path, 'rb') as f:
                    priv, cert, _ = pkcs12.load_key_and_certificates(
                        f.read(), clinica.clave_certificado.encode()
                    )
                if cert:
                    cert_info = {
                        'subject': cert.subject.rfc4514_string(),
                        'issuer': cert.issuer.rfc4514_string(),
                        'valid_from': cert.not_valid_before_utc,
                        'valid_to': cert.not_valid_after_utc,
                        'serial': cert.serial_number,
                    }
        except Exception as e:
            cert_info = {'error': str(e)}

    return render(request, 'admin/config/firma_electronica.html', {
        'clinica': clinica,
        'cert_info': cert_info,
    })