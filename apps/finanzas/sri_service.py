"""
DentixPro — Modulo SRI Ecuador
Facturacion Electronica: generacion XML, firma XAdES-BES y envio al SRI

Requisitos: lxml, cryptography
Instalar: pip install lxml cryptography
"""
import hashlib
import base64
import datetime
import random
import requests
from lxml import etree

WSDL_RECEPCION = {
    '1': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
    '2': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
}
WSDL_AUTORIZACION = {
    '1': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
    '2': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
}
# ── URLs SRI ─────────────────────────────────────────────────────────────────
SRI_URLS = {
    '1': {  # Pruebas
        'recepcion': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline',
        'autorizacion': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline',
    },
    '2': {  # Produccion
        'recepcion': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline',
        'autorizacion': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline',
    },
}

# ── Codigos SRI ───────────────────────────────────────────────────────────────
TIPO_COMPROBANTE = '01'  # Factura
TIPO_IDENTIFICACION = {
    'ruc': '04', 'cedula': '05', 'pasaporte': '06', 'consumidor_final': '07',
}
FORMA_PAGO = {
    'efectivo': '01', 'cheque': '02', 'tarjeta': '16', 'transferencia': '17', 'otro': '20',
}


# ── Clave de acceso (49 digitos) ──────────────────────────────────────────────
def generar_clave_acceso(fecha, tipo_comprobante, ruc, ambiente, serie, secuencial, codigo_num=None):

    # 🔒 NORMALIZAR CAMPOS
    import datetime
    from datetime import datetime
    # Fecha
    if isinstance(fecha, str):
        fecha = datetime.fromisoformat(fecha)

    fecha_str = fecha.strftime('%d%m%Y')

    # Tipo comprobante (2 dígitos)
    tipo_comprobante = str(tipo_comprobante).zfill(2)

    # Ambiente (1 dígito)
    ambiente = str(ambiente).strip()[0]

    # RUC (13)
    ruc = str(ruc).strip()
    if len(ruc) == 10:
        ruc += '001'
    if len(ruc) != 13:
        raise ValueError(f"RUC inválido: {ruc}")

    # Serie (6 → 3 + 3)
    serie = str(serie).zfill(6)
    estab = serie[:3]
    pto   = serie[3:]

    # Secuencial (9)
    try:
        secuencial = f"{int(secuencial):09d}"
    except:
        raise ValueError(f"Secuencial inválido: {secuencial}")

    # Código numérico (8)
    if codigo_num is None:
        codigo_num = f"{random.randint(10000000, 99999999)}"
    else:
        codigo_num = str(codigo_num).zfill(8)[:8]

    # 🔑 CONSTRUIR CLAVE
    clave = (
        fecha_str +
        tipo_comprobante +
        ruc +
        ambiente +
        estab +
        pto +
        secuencial +
        codigo_num +
        "1"
    )

    # 🧪 DEBUG REAL (esto te va a salvar)
    if len(clave) != 48:
        raise ValueError(
            f"ERROR CLAVE ACCESO:\n"
            f"fecha: {fecha_str} ({len(fecha_str)})\n"
            f"tipo: {tipo_comprobante} ({len(tipo_comprobante)})\n"
            f"ruc: {ruc} ({len(ruc)})\n"
            f"ambiente: {ambiente} ({len(ambiente)})\n"
            f"estab: {estab} ({len(estab)})\n"
            f"pto: {pto} ({len(pto)})\n"
            f"secuencial: {secuencial} ({len(secuencial)})\n"
            f"codigo: {codigo_num} ({len(codigo_num)})\n"
            f"TOTAL: {len(clave)} (debe ser 48)"
        )

    # ✅ módulo 11
    digito = _modulo11(clave)

    return clave + str(digito)


def _modulo11(clave):
    factores = [2, 3, 4, 5, 6, 7]
    total = 0
    for i, c in enumerate(reversed(clave)):
        total += int(c) * factores[i % len(factores)]
    residuo = total % 11
    if residuo == 0:
        return 0
    elif residuo == 1:
        return 1
    return 11 - residuo


# ── Generacion XML Factura (via Django template) ─────────────────────────────
def generar_xml_factura(factura, clinica):
    """
    Genera el XML de la factura usando Django template (templates/xml/factura.html).
    Misma logica que crear_representacion_xml_factura del sistema de referencia.
    Retorna el XML como string y lo guarda en factura.sri_xml.
    """
    from django.template.loader import get_template

    # Normalizar RUC a 13 digitos
    ruc = str(clinica.ruc).strip()
    if len(ruc) == 10:
        ruc = ruc + '001'
    if not ruc or len(ruc) != 13:
        raise ValueError(
            f"RUC invalido: '{ruc}'. Ve a Configuracion > Clinica y corrige el RUC."
        )

    # Generar clave de acceso si no tiene
    if not factura.clave_acceso:
        clave = generar_clave_acceso(
            factura.fecha, TIPO_COMPROBANTE, ruc,
            clinica.sri_ambiente,
            f"{clinica.serie_establecimiento}{clinica.serie_punto_emision}",
            int(factura.numero),
        )
        factura.clave_acceso = clave
        factura.sri_ambiente = clinica.sri_ambiente
        factura.save(update_fields=['clave_acceso', 'sri_ambiente', 'fecha_modificacion'])

    # Tipo de identificacion del comprador
    paciente = factura.paciente
    cedula = (paciente.identificacion or '').strip()
    if cedula and len(cedula) == 13:
        tipo_id_comprador = '04'   # RUC
        identificacion_comprador = cedula
    elif cedula and len(cedula) == 10:
        tipo_id_comprador = '05'   # Cedula
        identificacion_comprador = cedula
    elif not cedula:
        tipo_id_comprador = '07'   # Consumidor final
        identificacion_comprador = '9999999999999'
    else:
        tipo_id_comprador = '06'   # Pasaporte
        identificacion_comprador = cedula

    # Codigo de forma de pago SRI
    codigo_forma_pago = FORMA_PAGO.get(factura.metodo_pago, '01')

    template = get_template('admin/finanzas/xml/factura.html')
    context = {
        'factura': factura,
        'clinica': clinica,
        'ruc': ruc,
        'tipo_id_comprador': tipo_id_comprador,
        'identificacion_comprador': identificacion_comprador,
        'codigo_forma_pago': codigo_forma_pago,
    }
    xml_content = template.render(context).strip()  # strip: {% load %} adds leading \n

    # Guardar XML sin firma
    factura.sri_xml = xml_content
    factura.sri_estado = 'xmlgenerado'
    factura.save(update_fields=['sri_estado','sri_xml', 'fecha_modificacion'])

    return xml_content.encode('utf-8')


# ── Firma XAdES-BES con FIRMA_EC.jar ─────────────────────────────────────────
def _api_firmadigital_disponible(timeout=3):
    """Verifica si api.firmadigital.gob.ec está accesible."""
    try:
        import urllib.request
        urllib.request.urlopen(
            'https://api.firmadigital.gob.ec/api/fecha-hora',
            timeout=timeout
        )
        return True
    except Exception:
        return False


def firmar_xml(xml_bytes, p12_path, p12_password, jar_path=None, java_home_conf=''):
    """
    Firma el XML XAdES-BES para el SRI Ecuador usando Python (cryptography).
    El IssuerName se genera en formato RFC 4514 (CN primero) que requiere el SRI.
    """
    # Usar firma Python: genera IssuerName en RFC 4514 (CN primero) que acepta el SRI
    # El jar FirmaElectronica.jar puede generar DER order (C primero) → SRI rechaza [39]
    # return _firmar_con_python(xml_bytes, p12_path, p12_password)
    return _firmar_con_jar(xml_bytes, p12_path, p12_password, jar_path=jar_path, java_home_conf=java_home_conf)


def _get_java_cmd(java_home_configurado=''):
    """
    Devuelve el comando java a usar.
    Prioridad: java_home configurado en Clinica > JAVA_HOME env > PATH.
    En Windows busca automaticamente en Program Files si el PATH falla.
    """
    import subprocess, os, platform

    def java_valido(cmd):
        try:
            r = subprocess.run([cmd, '-version'], capture_output=True, timeout=8)
            return r.returncode == 0
        except Exception:
            return False

    def version_java(cmd):
        """Retorna el numero de version mayor (8, 11, 17, 21, etc.)"""
        try:
            r = subprocess.run([cmd, '-version'], capture_output=True, timeout=8)
            out = (r.stderr or r.stdout or b'').decode('utf-8', errors='replace')
            import re
            # "version 17.0.x" o "version 1.8.0_xxx"
            m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
            if m:
                major = int(m.group(1))
                if major == 1:  # Java 8 se reporta como "1.8"
                    major = int(m.group(2) or 8)
                return major
        except Exception:
            pass
        return 0

    # 1. Usar java_home configurado en Clinica (equivalente a JAVA_18_HOME)
    if java_home_configurado:
        cmd = os.path.join(java_home_configurado, 'bin', 'java')
        if os.name == 'nt':
            cmd += '.exe'
        if java_valido(cmd):
            return cmd

    # 2. JAVA_HOME del entorno
    # java_home_env = os.environ.get('JAVA_HOME', '')
    # if java_home_env:
    #     cmd = os.path.join(java_home_env, 'bin', 'java')
    #     if java_valido(cmd):
    #         return cmd
    #
    # # 3. java del PATH
    # if java_valido('java'):
    #     return 'java'

    # 4. Buscar en rutas comunes de Windows
    if platform.system() == 'Windows':
        import glob
        rutas = [
            r'C:\Program Files\Java\jdk*\bin\java.exe',
            r'C:\Program Files\Eclipse Adoptium\jdk-*\bin\java.exe',
            r'C:\Program Files\Microsoft\jdk-*\bin\java.exe',
            r'C:\Program Files\Eclipse Foundation\jdk-*\bin\java.exe',
        ]
        # Ordenar de mayor a menor version
        candidatos = []
        for patron in rutas:
            candidatos.extend(glob.glob(patron))
        candidatos.sort(reverse=True)
        for cmd in candidatos:
            if java_valido(cmd):
                return cmd

    # 5. Buscar en Linux/Mac
    import glob
    rutas_unix = [
        '/usr/lib/jvm/java-*/bin/java',
        '/usr/local/java/jdk*/bin/java',
        '/opt/java/*/bin/java',
    ]
    candidatos = []
    for patron in rutas_unix:
        candidatos.extend(glob.glob(patron))
    candidatos.sort(reverse=True)
    for cmd in candidatos:
        if java_valido(cmd):
            return cmd

    raise RuntimeError(
        'Java no encontrado. Instala Java 11+ y configura JAVA_HOME '
        'en Configuracion > Firma Electronica.'
    )


def _firmar_con_jar(xml_bytes, p12_path, p12_password, jar_path, java_home_conf=''):
    """
    Firma usando FirmaElectronica.jar (compatible SRI).
    FIXES:
    - Escritura/lectura en binario (NO romper encoding)
    - Evita doble ejecución del jar
    - Manejo limpio de errores
    """

    import subprocess
    import os
    import logging
    import uuid

    java_cmd = _get_java_cmd(java_home_conf)

    temp_dir = '/tmp/dentixpro_firma'
    os.makedirs(temp_dir, exist_ok=True)

    nombre_base = f"factura_{uuid.uuid4().hex}"
    ruta_xml_sin_firma = os.path.join(temp_dir, f"{nombre_base}_sinfirma.xml")
    ruta_xml_firmado = os.path.join(temp_dir, f"{nombre_base}_firmado.xml")

    try:
        # ✅ CRÍTICO: escribir en binario (NO decode)
        with open(ruta_xml_sin_firma, 'wb') as f:
            f.write(xml_bytes)
        from config import settings
        jar_path = os.path.join(
            settings.BASE_DIR,
            'thirdparty',
            'signcli',
            'xades',
            'FirmaElectronica',
            'FirmaElectronica.jar'
        )
        # Construir comando
        command = [
            java_cmd,
            '-jar', jar_path,
            ruta_xml_sin_firma,
            p12_path,
            p12_password,
            ruta_xml_firmado,
        ]

        # Ejecutar UNA sola vez
        p = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(os.path.abspath(jar_path))
        )

        stdout, _ = p.communicate()
        output = stdout or b''

        # DEBUG opcional
        logging.info("FIRMA_EC output: %s", output.decode(errors='replace')[:500])

        # ✅ Validar archivo firmado primero (regla SRI)
        if os.path.exists(ruta_xml_firmado) and os.path.getsize(ruta_xml_firmado) > 200:
            # ✅ CRÍTICO: leer en binario (NO encoding)
            with open(ruta_xml_firmado, 'rb') as f:
                xml_firmado = f.read()

            return xml_firmado

        # Si no generó archivo → error real
        if output:
            raise RuntimeError(output.decode('utf-8', errors='replace').strip())

        raise RuntimeError("FIRMA_EC.jar no generó el XML firmado")

    except Exception as e:
        logging.error("Error firmando con jar: %s", str(e))
        raise

    finally:
        # limpieza
        for f in [ruta_xml_sin_firma, ruta_xml_firmado]:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except Exception:
                pass


def _parsear_error_java(stderr, returncode):
    """Convierte el stack trace de Java en un mensaje legible."""
    if not stderr:
        return f'FIRMA_EC.jar terminó sin output (código {returncode}).'

    ERRORES_CONOCIDOS = {
        'ArrayIndexOutOfBounds': (
            'Argumentos incorrectos para el jar. '
            'Verifica que el FIRMA_EC.jar sea el correcto del SRI Ecuador.'
        ),
        'certificadoEsValido': (
            'El certificado P12 no pudo ser validado. Causas:\n'
            '• Certificado no emitido por BCE, Security Data, ANF o Uanataca\n'
            '• Certificado vencido\n'
            '• El servidor no tiene acceso a los servidores OCSP de la CA'
        ),
        'password': 'Contraseña del certificado P12 incorrecta.',
        'contraseña': 'Contraseña del certificado P12 incorrecta.',
        'FileNotFoundException': 'Archivo XML o P12 no encontrado.',
        'OutOfMemoryError': 'Java sin memoria. Agrega -Xmx512m al inicio del comando.',
        'UnsupportedClassVersionError': 'Versión de Java incompatible. Requiere Java 8+.',
        'ClassNotFoundException': 'FIRMA_EC.jar corrupto o incompleto.',
        'SAXParseException': 'El XML tiene errores de estructura.',
    }

    for clave, msg in ERRORES_CONOCIDOS.items():
        if clave.lower() in stderr.lower():
            return msg

    import re
    m = re.search(r'(?:RuntimeException|Exception)[^\n]*:\s*(.+)', stderr)
    if m:
        return m.group(1).strip()[:400]

    # Solo la primera línea sin stack trace
    lineas = [
        l.strip() for l in stderr.splitlines()
        if l.strip() and not l.strip().startswith('at ')
    ]
    return ' | '.join(lineas[:3]) if lineas else f'Error código {returncode}'





def _firmar_con_python(xml_bytes, p12_path, p12_password):
    """
    Firma XAdES-BES usando la API de lxml (sin strings con newlines).
    Estructura validada contra XML autorizado por el SRI Ecuador.
    """
    import base64, hashlib, datetime, random
    from lxml import etree
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    DS   = 'http://www.w3.org/2000/09/xmldsig#'
    ETSI = 'http://uri.etsi.org/01903/v1.3.2#'
    C14N = 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
    RSA_SHA1 = 'http://www.w3.org/2000/09/xmldsig#rsa-sha1'
    SHA1     = 'http://www.w3.org/2000/09/xmldsig#sha1'
    ENV_SIG  = 'http://www.w3.org/2000/09/xmldsig#enveloped-signature'
    SP_TYPE  = 'http://uri.etsi.org/01903#SignedProperties'
    NSMAP    = {'ds': DS, 'etsi': ETSI}

    def E(tag, ns=DS, attribs=None, text=None):
        e = etree.Element(f'{{{ns}}}{tag}', nsmap=NSMAP)
        if attribs:
            for k, v in attribs.items(): e.set(k, v)
        if text is not None: e.text = text
        return e

    def S(parent, tag, ns=DS, attribs=None, text=None):
        e = etree.SubElement(parent, f'{{{ns}}}{tag}')
        if attribs:
            for k, v in attribs.items(): e.set(k, v)
        if text is not None: e.text = text
        return e

    def c14n(el):
        return etree.tostring(el, method='c14n', exclusive=False)

    def sha1b64(data):
        return base64.b64encode(hashlib.sha1(data).digest()).decode()

    # ── Cargar P12 ─────────────────────────────────────────────────────────
    with open(p12_path, 'rb') as f:
        p12_data = f.read()
    pwd = p12_password.encode() if isinstance(p12_password, str) else p12_password
    private_key, certificate, _ = pkcs12.load_key_and_certificates(p12_data, pwd)

    cert_der = certificate.public_bytes(Encoding.DER)
    cert_b64 = base64.b64encode(cert_der).decode()

    pub = certificate.public_key().public_numbers()
    def n2b64(n):
        return base64.b64encode(n.to_bytes((n.bit_length()+7)//8, 'big')).decode()
    modulus_b64  = n2b64(pub.n)
    exponent_b64 = n2b64(pub.e)

    # ── Parsear documento ──────────────────────────────────────────────────
    root = etree.fromstring(xml_bytes)

    # ── IDs ────────────────────────────────────────────────────────────────
    r = lambda: random.randint(100000, 999999)
    sig_id    = f'Signature{r()}'
    si_id     = f'Signature-SignedInfo{r()}'
    sp_ref_id = f'SignedPropertiesID{r()}'
    doc_ref_id= f'Reference-ID-{r()}'
    sv_id     = f'SignatureValue{r()}'
    ki_id     = f'Certificate{r()}'
    obj_id    = f'{sig_id}-Object{r()}'
    sp_id     = f'{sig_id}-SignedProperties{r()}'
    ts        = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    # ── Issuer RFC 4514 (CN primero) ────────────────────────────────────────
    OID_MAP = {'2.5.4.3':'CN','2.5.4.5':'SERIALNUMBER','2.5.4.6':'C',
               '2.5.4.7':'L','2.5.4.8':'ST','2.5.4.10':'O','2.5.4.11':'OU'}
    issuer_name = ','.join(
        f"{OID_MAP.get(a.oid.dotted_string, a.oid._name or a.oid.dotted_string)}={a.value}"
        for a in reversed(list(certificate.issuer))
    )

    # ── 1. Digest documento (antes de agregar firma) ────────────────────────
    doc_digest = sha1b64(c14n(root))

    # ── 2. Construir KeyInfo con lxml API (sin whitespace) ──────────────────
    ki = E('KeyInfo', DS, {'Id': ki_id})
    x509d = S(ki, 'X509Data', DS)
    S(x509d, 'X509Certificate', DS, text=cert_b64)
    kv = S(ki, 'KeyValue', DS)
    rsa = S(kv, 'RSAKeyValue', DS)
    S(rsa, 'Modulus', DS, text=modulus_b64)
    S(rsa, 'Exponent', DS, text=exponent_b64)
    ki_digest = sha1b64(c14n(ki))

    # ── 3. Construir SignedProperties con lxml API ──────────────────────────
    sp = E('SignedProperties', ETSI, {'Id': sp_id})
    ssp = S(sp, 'SignedSignatureProperties', ETSI)
    S(ssp, 'SigningTime', ETSI, text=ts)
    sc = S(ssp, 'SigningCertificate', ETSI)
    cert_el = S(sc, 'Cert', ETSI)
    cd = S(cert_el, 'CertDigest', ETSI)
    dm = S(cd, 'DigestMethod', DS, {'Algorithm': SHA1})
    S(cd, 'DigestValue', DS, text=sha1b64(cert_der))
    isr = S(cert_el, 'IssuerSerial', ETSI)
    S(isr, 'X509IssuerName', DS, text=issuer_name)
    S(isr, 'X509SerialNumber', DS, text=str(certificate.serial_number))
    sdop = S(sp, 'SignedDataObjectProperties', ETSI)
    dof = S(sdop, 'DataObjectFormat', ETSI, {'ObjectReference': f'#{doc_ref_id}'})
    S(dof, 'Description', ETSI, text='contenido comprobante')
    S(dof, 'MimeType', ETSI, text='text/xml')
    sp_digest = sha1b64(c14n(sp))

    # ── 4. SignedInfo con 3 referencias: SP, Certificate, documento ──────────
    si = E('SignedInfo', DS, {'Id': si_id})
    S(si, 'CanonicalizationMethod', DS, {'Algorithm': C14N})
    S(si, 'SignatureMethod', DS, {'Algorithm': RSA_SHA1})
    # Ref 1: SignedProperties
    r1 = S(si, 'Reference', DS, {'Id': sp_ref_id, 'Type': SP_TYPE, 'URI': f'#{sp_id}'})
    S(r1, 'DigestMethod', DS, {'Algorithm': SHA1})
    S(r1, 'DigestValue', DS, text=sp_digest)
    # Ref 2: Certificate (KeyInfo)
    r2 = S(si, 'Reference', DS, {'URI': f'#{ki_id}'})
    S(r2, 'DigestMethod', DS, {'Algorithm': SHA1})
    S(r2, 'DigestValue', DS, text=ki_digest)
    # Ref 3: Documento
    r3 = S(si, 'Reference', DS, {'Id': doc_ref_id, 'URI': '#comprobante'})
    tr = S(r3, 'Transforms', DS)
    S(tr, 'Transform', DS, {'Algorithm': ENV_SIG})
    S(r3, 'DigestMethod', DS, {'Algorithm': SHA1})
    S(r3, 'DigestValue', DS, text=doc_digest)

    # ── 5. Firmar SignedInfo ────────────────────────────────────────────────
    sig_val = private_key.sign(c14n(si), padding.PKCS1v15(), hashes.SHA1())
    sig_b64 = base64.b64encode(sig_val).decode()

    # ── 6. Ensamblar Signature completa ─────────────────────────────────────
    sig = E('Signature', DS, {'Id': sig_id})
    sig.append(si)
    S(sig, 'SignatureValue', DS, {'Id': sv_id}, text=sig_b64)
    sig.append(ki)
    obj = S(sig, 'Object', DS, {'Id': obj_id})
    qp = etree.SubElement(obj, f'{{{ETSI}}}QualifyingProperties',
                          {'Target': f'#{sig_id}'})
    qp.append(sp)

    root.append(sig)
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8')


def _get_zeep_client(wsdl_url):
    """Crea cliente zeep con timeout configurable."""
    try:
        from zeep import Client
        from zeep.transports import Transport
        from requests import Session
        session = Session()
        session.timeout = 30
        transport = Transport(session=session, timeout=30, operation_timeout=30)
        return Client(wsdl_url, transport=transport)
    except ImportError:
        raise ImportError(
            "Instala zeep: pip install zeep  "
            "(necesario para comunicación con el SRI via WSDL)"
        )


def enviar_sri(factura, xml_firmado_bytes, ambiente='1'):
    """
    Envía el XML firmado al SRI via WSDL (zeep).
    Adaptado de enviar_sri del sistema de referencia.

    Verifica estado RECIBIDA o mensajes de ya-enviado (id 43/45).
    Retorna dict con: ok, estado, mensaje
    """
    from datetime import datetime

    wsdl = WSDL_RECEPCION.get(ambiente, WSDL_RECEPCION['1'])

    try:
        client = _get_zeep_client(wsdl)

        # validarComprobante espera xsd:base64Binary
        # zeep codifica base64 automaticamente cuando recibe bytes
        if isinstance(xml_firmado_bytes, str):
            xml_firmado_bytes = xml_firmado_bytes.encode('utf-8')

        respuesta = client.service.validarComprobante(xml_firmado_bytes)

        estado       = ''
        mensajes_err = []
        ya_enviado   = False

        # Igual que el sistema de referencia: revisar comprobantes y mensajes
        if respuesta.comprobantes:
            for comp in respuesta.comprobantes.comprobante:
                for m in comp.mensajes.mensaje:
                    identificador = str(m.identificador or '')
                    # ids 43='clave registrada' y 45='comprobante en proceso': considerar como OK
                    if identificador in ('43', '45'):
                        ya_enviado = True
                    else:
                        txt = str(m.mensaje or '')
                        adicional = ''
                        try:
                            adicional = str(m.informacionAdicional or '')
                        except Exception:
                            pass
                        if txt:
                            mensajes_err.append(f"[{identificador}] {txt}" + (f" → {adicional}" if adicional else ''))

        try:
            estado = str(respuesta.estado or '')
        except Exception:
            pass

        if estado == 'RECIBIDA' or ya_enviado:
            return {'ok': True, 'estado': 'enviada', 'mensaje': 'Comprobante recibido por el SRI'}

        msg = ' | '.join(mensajes_err) if mensajes_err else f'Estado SRI: {estado or "sin respuesta"}'
        return {'ok': False, 'estado': 'rechazada', 'mensaje': msg}

    except ImportError as e:
        return {'ok': False, 'estado': 'error', 'mensaje': str(e)}
    except Exception as e:
        return {'ok': False, 'estado': 'error', 'mensaje': f'Error al enviar al SRI: {e}'}


def autorizar_sri(clave_acceso, ambiente='1'):
    """
    Consulta autorización del comprobante al SRI via WSDL (zeep).
    Adaptado de autorizacion_comprobante_factura del sistema de referencia.

    Retorna dict con: ok, estado, numero_autorizacion, fecha_autorizacion, mensaje
    """
    wsdl = WSDL_AUTORIZACION.get(ambiente, WSDL_AUTORIZACION['1'])

    try:
        client = _get_zeep_client(wsdl)
        respuesta = client.service.autorizacionComprobante(claveAccesoComprobante=clave_acceso)

        if not respuesta.numeroComprobantes or int(respuesta.numeroComprobantes) == 0:
            return {
                'ok': False, 'estado': 'pendiente',
                'mensaje': 'Sin respuesta de autorización del SRI',
                'numero_autorizacion': '', 'fecha_autorizacion': None,
            }

        autorizacion = respuesta.autorizaciones.autorizacion[0]
        estado = str(autorizacion.estado or '')

        if estado == 'AUTORIZADO':
            numero = str(autorizacion.numeroAutorizacion or '')
            fecha  = autorizacion.fechaAutorizacion  # zeep lo devuelve como datetime
            return {
                'ok': True,
                'estado': 'autorizada',
                'numero_autorizacion': numero,
                'fecha_autorizacion': fecha,
                'mensaje': f'Comprobante autorizado. N° {numero}',
            }

        # NO AUTORIZADO — extraer mensajes de error (igual que sistema de referencia)
        mensajes_err = []
        try:
            from zeep.helpers import serialize_object
            for m in autorizacion.mensajes.mensaje:
                txt      = str(m.mensaje or '')
                adicional = ''
                try:
                    adicional = str(m.informacionAdicional or '')
                except Exception:
                    pass
                ident = str(m.identificador or '')
                if txt:
                    mensajes_err.append(f"[{ident}] {txt}" + (f" → {adicional}" if adicional else ''))
        except Exception:
            pass

        msg = ' | '.join(mensajes_err) if mensajes_err else f'Estado: {estado}'
        return {
            'ok': False, 'estado': 'rechazada',
            'mensaje': msg,
            'numero_autorizacion': '', 'fecha_autorizacion': None,
        }

    except ImportError as e:
        return {
            'ok': False, 'estado': 'error', 'mensaje': str(e),
            'numero_autorizacion': '', 'fecha_autorizacion': None,
        }
    except Exception as e:
        return {
            'ok': False, 'estado': 'error',
            'mensaje': f'Error al consultar autorización SRI: {e}',
            'numero_autorizacion': '', 'fecha_autorizacion': None,
        }

def procesar_firmar(clinica, xml_bytes):
    import os
    xml_firmado = xml_bytes
    tiene_certificado = (
            clinica.certificado_p12 and
            clinica.clave_certificado and
            os.path.exists(clinica.certificado_p12.path)
    )
    if tiene_certificado:
        # Determinar método de firma: FIRMA_EC.jar (preferido) o Python
        # Buscar jar: 1) subido en Clinica, 2) ruta fija en el proyecto
        jar_path = None
        if clinica.firma_ec_jar:
            try:
                p = clinica.firma_ec_jar.path
                if os.path.exists(p):
                    jar_path = p
            except Exception:
                pass

        if not jar_path:
            # Ruta fija dentro del proyecto (igual que el sistema de referencia)
            from django.conf import settings
            jar_default = os.path.join(
                settings.BASE_DIR,
                'thirdparty', 'FirmaElectronica', 'FirmaElectronica.jar'
            )
            if os.path.exists(jar_default):
                jar_path = jar_default

        # JAVA_HOME configurado en Clinica
        if hasattr(clinica, 'java_home') and clinica.java_home:
            os.environ['JAVA_HOME'] = clinica.java_home

        try:
            xml_firmado = firmar_xml(
                xml_bytes,
                clinica.certificado_p12.path,
                clinica.clave_certificado,
                jar_path=clinica.java_home,
                java_home_conf=getattr(clinica, 'java_home', ''),
            )
            return {'ok': True, 'xml_firmado': xml_firmado}
        except RuntimeError as e:
            return {'ok': False, 'paso': 'firma', 'mensaje': str(e)}
        except ImportError:
            return {
                'ok': False, 'paso': 'firma',
                'mensaje': 'Falta instalar: pip install lxml cryptography',
            }
        except Exception as e:
            return {'ok': False, 'paso': 'firma', 'mensaje': f'Error firmando XML: {e}'}
    else:
        return {
            'ok': False, 'paso': 'certificado',
            'mensaje': 'No hay certificado P12 configurado. Ve a Configuración → Firma Electrónica.',
            'xml_generado': xml_bytes.decode('utf-8'),
        }

# ── Proceso completo ──────────────────────────────────────────────────────────
def procesar_factura_sri(factura):
    """
    Proceso completo:
    1. Generar XML
    2. Firmar (si hay certificado P12)
    3. Enviar al SRI
    4. Consultar autorizacion
    5. Actualizar factura
    Retorna dict con resultado.
    """
    from apps.core.models import Clinica
    import os

    clinica = Clinica.get()

    if not clinica.ruc:
        return {
            'ok': False,
            'paso': 'config',
            'mensaje': 'El RUC de la clinica no esta configurado. Ir a Configuracion.',
        }

    # GENERACIÓN DE XML
    if factura.sri_estado == 'xmlpendiente':
        try:
            xml_bytes = generar_xml_factura(factura, clinica)
        except Exception as e:
            import traceback
            return {'ok': False, 'paso': 'xml', 'mensaje': f'Error generando XML: {e}', 'detalle': traceback.format_exc()}

    xml_firmado = procesar_firmar(clinica, xml_bytes)
    if not xml_firmado['ok']:
        return xml_firmado

    xml_firmado = xml_firmado['xml_firmado']
    factura.sri_estado = 'xmlfirmado'
    factura.save(update_fields=['sri_estado', 'fecha_modificacion'])

    # Nunca pasar el XML firmado por DB antes de enviarlo:
    # Django puede alterar whitespace/encoding → invalida firma XAdES → error SRI [39]
    if isinstance(xml_firmado, str):
        xml_firmado_bytes = xml_firmado.encode('utf-8')
    else:
        xml_firmado_bytes = xml_firmado

    if factura.sri_estado == 'xmlfirmado':
        res_envio = enviar_sri(factura, xml_firmado_bytes, clinica.sri_ambiente)
        if not res_envio['ok']:
            factura.sri_estado = res_envio.get('estado', 'rechazada')
            factura.sri_respuesta = res_envio['mensaje']
            factura.save(update_fields=['sri_estado', 'fecha_modificacion'])
            return {
                'ok': False, 'paso': 'envio',
                'mensaje': res_envio['mensaje'],
                'xml_generado': xml_firmado_bytes.decode('utf-8'),
            }
        factura.sri_xml_firmado = xml_firmado_bytes.decode('utf-8')
        factura.sri_estado = 'enviada'
        factura.save(update_fields=['sri_xml', 'sri_estado', 'fecha_modificacion'])

    if factura.sri_estado == 'enviada':

        # 4. Autorizar (con reintentos)
        import time
        res_auth = None
        for intento in range(3):
            res_auth = autorizar_sri(factura.clave_acceso, clinica.sri_ambiente)
            if res_auth['ok'] or res_auth.get('estado') == 'rechazada':
                break

        if res_auth and res_auth['ok']:
            factura.sri_estado = 'autorizada'
            factura.sri_numero_autorizacion = res_auth['numero_autorizacion']
            factura.sri_fecha_autorizacion = res_auth['fecha_autorizacion']
            factura.sri_respuesta = res_auth['mensaje']
            factura.save(update_fields=['sri_estado', 'sri_numero_autorizacion',
                                        'sri_fecha_autorizacion', 'sri_respuesta', 'fecha_modificacion'])
            return {
                'ok': True, 'paso': 'autorizada',
                'mensaje': f"Factura autorizada. N° {res_auth['numero_autorizacion']}",
                'numero_autorizacion': res_auth['numero_autorizacion'],
            }
        else:
            msg = res_auth['mensaje'] if res_auth else 'Sin respuesta de autorización'
            xml_debug = res_auth.get('_xml_respuesta', '') if res_auth else ''
            factura.sri_estado = res_auth.get('estado', 'enviada') if res_auth else 'enviada'
            factura.sri_respuesta = msg
            if xml_debug:
                factura.sri_xml = (factura.sri_xml or '') + '\n\n<!-- RESPUESTA AUTORIZACION SRI -->\n' + xml_debug[:3000]
            factura.save(update_fields=['sri_estado', 'sri_respuesta', 'sri_xml', 'fecha_modificacion'])
            return {
                'ok': False,
                'paso': 'autorizacion',
                'mensaje': msg,
                'xml_generado': xml_firmado_bytes.decode('utf-8'),
            }
