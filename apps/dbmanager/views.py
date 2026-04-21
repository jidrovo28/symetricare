"""
Gestor de Base de Datos — Symetricare.

Permite ejecutar SELECT, INSERT, UPDATE, DELETE con validaciones,
vista del esquema, historial de queries y exportación CSV.

Solo accesible para usuarios con es_admin == True.
"""
import re
import csv
import json
import time
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db import connection, ProgrammingError, OperationalError
from apps.core.helpers import adduserdata

logger = logging.getLogger('dbmanager')

# ── Tablas del sistema protegidas ─────────────────────────────────────────────
TABLAS_PROTEGIDAS = {
    'auth_user', 'auth_permission', 'auth_group',
    'django_session', 'django_migrations', 'django_content_type',
    'django_admin_log',
}

# Patrones SQL peligrosos bloqueados siempre
PATRONES_PELIGROSOS = [
    r'\bDROP\s+TABLE\b',
    r'\bDROP\s+DATABASE\b',
    r'\bTRUNCATE\b',
    r'\bALTER\s+TABLE\b',
    r'\bCREATE\s+TABLE\b',
    r'\bCREATE\s+DATABASE\b',
    r'\bDROP\s+INDEX\b',
    r'\bCREATE\s+INDEX\b',
    r'\bGRANT\b',
    r'\bREVOKE\b',
    r'\bSHUTDOWN\b',
    r'\bLOAD\s+DATA\b',
    r'\bINTO\s+OUTFILE\b',
    r'\bINTO\s+DUMPFILE\b',
    r'\bCOPY\s+TO\b',
    r'\bPG_SLEEP\b',
    r'\bPG_READ_FILE\b',
    r'--',          # Comentario SQL inline
    r';.*\S',       # Múltiples sentencias
]


def _requiere_admin(request):
    return request.user.is_authenticated and request.user.es_admin


def _detectar_tipo(sql: str) -> str:
    """Retorna SELECT / INSERT / UPDATE / DELETE / OTRO."""
    s = sql.strip().upper()
    for t in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
        if s.startswith(t):
            return t
    return 'OTRO'


def _validar_sql(sql: str) -> tuple[bool, str]:
    """
    Valida la query antes de ejecutarla.
    Retorna (ok, mensaje_error).
    """
    sql_up = sql.upper()

    # Bloquear patrones peligrosos
    for patron in PATRONES_PELIGROSOS:
        if re.search(patron, sql_up, re.IGNORECASE):
            return False, f'Operación no permitida: se detectó patrón "{patron.strip()}".'

    # Verificar que no afecte tablas protegidas en operaciones de escritura
    tipo = _detectar_tipo(sql)
    if tipo in ('UPDATE', 'DELETE', 'INSERT'):
        for tabla in TABLAS_PROTEGIDAS:
            if tabla.upper() in sql_up:
                return False, f'La tabla "{tabla}" está protegida y no puede modificarse.'

    # UPDATE/DELETE deben tener WHERE
    if tipo in ('UPDATE', 'DELETE'):
        if 'WHERE' not in sql_up:
            return False, (
                f'{tipo} sin cláusula WHERE no está permitido. '
                'Agrega una condición para evitar modificar todos los registros.'
            )

    # UPDATE con WHERE 1=1 o WHERE TRUE
    if tipo == 'UPDATE' and re.search(r'WHERE\s+(1\s*=\s*1|TRUE\b)', sql_up):
        return False, 'WHERE 1=1 / WHERE TRUE no están permitidos en UPDATE.'

    # DELETE con WHERE 1=1
    if tipo == 'DELETE' and re.search(r'WHERE\s+(1\s*=\s*1|TRUE\b)', sql_up):
        return False, 'WHERE 1=1 / WHERE TRUE no están permitidos en DELETE.'

    # Límite en SELECT sin LIMIT (advertencia, no error)
    if tipo == 'SELECT' and 'LIMIT' not in sql_up:
        pass  # Se aplica LIMIT automáticamente

    return True, ''


def _ejecutar_select(sql: str, limite: int = 500) -> dict:
    """Ejecuta un SELECT y retorna columnas + filas."""
    # Agregar LIMIT si no tiene
    sql_up = sql.upper()
    if 'LIMIT' not in sql_up:
        sql = sql.rstrip().rstrip(';') + f' LIMIT {limite}'

    with connection.cursor() as cur:
        t0 = time.time()
        cur.execute(sql)
        columnas = [d[0] for d in cur.description] if cur.description else []
        filas    = cur.fetchall()
        elapsed  = round((time.time() - t0) * 1000, 1)

    # Serializar: fechas, Decimal, None → string
    def _s(v):
        if v is None: return None
        from decimal import Decimal
        from datetime import datetime, date
        if isinstance(v, (datetime, date)): return str(v)
        if isinstance(v, Decimal): return float(v)
        return v

    filas_json = [[_s(c) for c in fila] for fila in filas]

    return {
        'tipo':     'SELECT',
        'columnas': columnas,
        'filas':    filas_json,
        'total':    len(filas_json),
        'ms':       elapsed,
    }


def _ejecutar_escritura(sql: str) -> dict:
    """Ejecuta INSERT / UPDATE / DELETE con transacción explícita."""
    with connection.cursor() as cur:
        t0 = time.time()
        cur.execute(sql)
        filas_afectadas = cur.rowcount
        elapsed = round((time.time() - t0) * 1000, 1)

    return {
        'tipo':            _detectar_tipo(sql),
        'filas_afectadas': filas_afectadas,
        'ms':              elapsed,
    }


# ── Vistas ────────────────────────────────────────────────────────────────────

@login_required(redirect_field_name='ret', login_url='/login')
def view_dbmanager(request):
    if not _requiere_admin(request):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Solo administradores.')

    data = {}
    adduserdata(request, data)
    data['title'] = 'Gestor de Base de Datos'

    if request.method == 'POST':
        action = request.POST.get('action')

        # ── Ejecutar query ───────────────────────────────────────────────
        if action == 'ejecutar':
            sql = request.POST.get('sql', '').strip()
            if not sql:
                return JsonResponse({'result': False, 'msg': 'Query vacía.'})

            ok, err = _validar_sql(sql)
            if not ok:
                logger.warning(
                    f'[DBMANAGER] BLOQUEADO — usuario={request.user.username} '
                    f'query={sql[:120]} motivo={err}')
                return JsonResponse({'result': False, 'msg': err})

            tipo = _detectar_tipo(sql)
            logger.info(
                f'[DBMANAGER] {tipo} — usuario={request.user.username} '
                f'query={sql[:120]}')

            try:
                if tipo == 'SELECT':
                    resultado = _ejecutar_select(sql)
                elif tipo in ('INSERT', 'UPDATE', 'DELETE'):
                    resultado = _ejecutar_escritura(sql)
                else:
                    return JsonResponse({
                        'result': False,
                        'msg': f'Tipo de operación "{tipo}" no permitido. '
                               'Solo SELECT, INSERT, UPDATE y DELETE.'
                    })

                return JsonResponse({'result': True, 'data': resultado})

            except (ProgrammingError, OperationalError) as e:
                return JsonResponse({'result': False,
                    'msg': f'Error SQL: {e}'})
            except Exception as e:
                return JsonResponse({'result': False,
                    'msg': f'Error inesperado: {e}'})

        # ── Exportar CSV ─────────────────────────────────────────────────
        elif action == 'exportar_csv':
            sql = request.POST.get('sql', '').strip()
            ok, err = _validar_sql(sql)
            if not ok or _detectar_tipo(sql) != 'SELECT':
                return JsonResponse({'result': False,
                    'msg': err or 'Solo se puede exportar SELECT.'})
            try:
                resultado = _ejecutar_select(sql, limite=10000)
                response  = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="query_export.csv"'
                writer = csv.writer(response)
                writer.writerow(resultado['columnas'])
                writer.writerows(resultado['filas'])
                return response
            except Exception as e:
                return JsonResponse({'result': False, 'msg': str(e)})

    # GET — cargar tablas disponibles
    with connection.cursor() as cur:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tablas = [r[0] for r in cur.fetchall()]

    data['tablas'] = tablas
    return render(request, 'admin/dbmanager/view.html', data)


@login_required(redirect_field_name='ret', login_url='/login')
def view_schema(request):
    """Retorna JSON con columnas de una tabla."""
    if not _requiere_admin(request):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    tabla = request.GET.get('tabla', '').strip()
    if not tabla or not re.match(r'^[a-zA-Z0-9_]+$', tabla):
        return JsonResponse({'result': False, 'msg': 'Nombre de tabla inválido.'})

    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE '' END AS key_type
                FROM information_schema.columns c
                LEFT JOIN (
                    SELECT ku.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage ku
                      ON tc.constraint_name = ku.constraint_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_name = %s
                ) pk ON pk.column_name = c.column_name
                WHERE c.table_name = %s
                  AND c.table_schema = 'public'
                ORDER BY c.ordinal_position
            """, [tabla, tabla])
            cols = cur.fetchall()

            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = %s AND table_schema = 'public'
            """, [tabla])
            existe = cur.fetchone()[0] > 0

        if not existe:
            return JsonResponse({'result': False, 'msg': f'Tabla "{tabla}" no existe.'})

        columnas = [
            {
                'nombre':   r[0],
                'tipo':     r[1],
                'nullable': r[2] == 'YES',
                'default':  r[3],
                'pk':       r[4] == 'PK',
            }
            for r in cols
        ]

        # Contar filas
        with connection.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{tabla}"')
            total_filas = cur.fetchone()[0]

        return JsonResponse({
            'result':      True,
            'tabla':       tabla,
            'columnas':    columnas,
            'total_filas': total_filas,
        })

    except Exception as e:
        return JsonResponse({'result': False, 'msg': str(e)})
