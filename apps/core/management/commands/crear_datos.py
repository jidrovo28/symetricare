from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Crea datos iniciales de Symetricare'

    def handle(self, *args, **kwargs):
        from apps.core.models import Usuario
        from apps.servicios.models import TipoServicio, Servicio
        from apps.citas.models import DisponibilidadHoraria

        # Admin
        if not Usuario.objects.filter(username='admin').exists():
            Usuario.objects.create_superuser(
                username='admin', password='Admin1234!',
                email='admin@symetricare.com',
                first_name='Admin', last_name='Symetricare',
                rol=Usuario.ROL_ADMIN)
            self.stdout.write(self.style.SUCCESS('✅ admin / Admin1234!'))

        # Tipos de servicio
        tipos = [('Consulta','#6366f1'),('Tratamiento','#10b981'),('Diagnóstico','#f59e0b')]
        for nombre, color in tipos:
            obj, created = TipoServicio.objects.get_or_create(nombre=nombre, defaults={
                'color': color, 'status': True})
            if created:
                self.stdout.write(f'  Tipo: {nombre}')

        # Servicios de ejemplo
        tipo_con = TipoServicio.objects.filter(nombre='Consulta').first()
        tipo_tra = TipoServicio.objects.filter(nombre='Tratamiento').first()
        servicios = [
            ('Consulta General', tipo_con, 30.00, 60),
            ('Consulta de Seguimiento', tipo_con, 25.00, 45),
            ('Terapia Nutricional', tipo_tra, 50.00, 90),
            ('Control de Peso', tipo_tra, 35.00, 60),
            ('Plan Alimenticio', tipo_tra, 60.00, 60),
        ]
        for nombre, tipo, precio, dur in servicios:
            Servicio.objects.get_or_create(nombre=nombre, defaults={
                'tipo': tipo, 'precio': precio, 'duracion_min': dur, 'status': True})

        # Disponibilidad (Lun-Vie 8am-5pm, 60min)
        for dia in range(5):
            DisponibilidadHoraria.objects.get_or_create(
                dia_semana=dia, hora_inicio='08:00', hora_fin='17:00',
                defaults={'duracion_min': 60, 'activo': True, 'status': True})

        self.stdout.write(self.style.SUCCESS('\n✅ Datos iniciales creados'))
        self.stdout.write(self.style.SUCCESS('   admin / Admin1234!'))
        self.stdout.write(self.style.SUCCESS('   http://localhost:8000/login'))
