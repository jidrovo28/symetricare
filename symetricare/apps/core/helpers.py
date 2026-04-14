from django.core.paginator import Paginator


class MiPaginador(Paginator):
    def rangos_paginado(self, pagina, rango=5):
        total  = self.num_pages
        inicio = max(1, pagina - rango // 2)
        fin    = min(total, inicio + rango - 1)
        inicio = max(1, fin - rango + 1)
        return range(inicio, fin + 1)


def adduserdata(request, data):
    data['usuario'] = request.user
    if not request.session.get('persona') and request.user.is_authenticated:
        request.session['persona'] = {
            'id':       request.user.pk,
            'username': request.user.username,
            'nombre':   request.user.nombre_completo,
            'rol':      request.user.rol,
        }
    data['persona'] = request.session.get('persona', {})
    from django.conf import settings
    data['empresa_nombre'] = settings.EMPRESA_NOMBRE
    data['empresa_color']  = settings.EMPRESA_COLOR
    return data
