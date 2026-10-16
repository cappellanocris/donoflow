from datetime import date, time, timedelta

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Appointment, CheckIn, DonationCenter, DonationOutcome, DonationSession, Donor,
    Notification, Slot, StandbyAvailability, WaitlistEntry, WaitlistOffer
)
from core.services import DonoFlowError, book_slot, create_waitlist_entry, generate_slots_for_session, confirm_standby



def ensure_demo_featured_image():
    image_dir = settings.MEDIA_ROOT / 'session_images'
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / 'raccolta_carini_demo.png'
    if not image_path.exists():
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (1200, 630), '#b91c1c')
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 420, 1200, 630), fill='#7f1d1d')
            draw.ellipse((820, 60, 1080, 320), fill='#fecaca')
            draw.text((70, 90), 'DonoFlow', fill='white')
            draw.text((70, 170), 'Raccolta sangue', fill='white')
            draw.text((70, 250), 'Carini · Oleificio Failla', fill='white')
            draw.text((70, 465), 'Autoemoteca · 07:30 - 12:00', fill='white')
            img.save(image_path)
        except Exception:
            image_path.write_bytes(b'')
    return 'session_images/raccolta_carini_demo.png'


class Command(BaseCommand):
    help = 'Crea dati demo per lo scenario Carini / Oleificio Failla.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Cancella i dati demo prima di ricrearli')

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Reset dati demo...')
            # Ordine esplicito per evitare vincoli PROTECT durante la cancellazione.
            WaitlistOffer.objects.all().delete()
            Notification.objects.all().delete()
            DonationOutcome.objects.all().delete()
            CheckIn.objects.all().delete()
            Appointment.objects.all().delete()
            WaitlistEntry.objects.all().delete()
            StandbyAvailability.objects.all().delete()
            Slot.objects.all().delete()
            DonationSession.objects.all().delete()
            DonationCenter.objects.all().delete()
            Donor.objects.all().delete()
            User.objects.exclude(username='admin').delete()

        operator_group, _ = Group.objects.get_or_create(name='operatori')
        admin, created = User.objects.get_or_create(username='admin', defaults={
            'is_staff': True,
            'is_superuser': True,
            'first_name': 'Responsabile',
            'last_name': 'Demo',
            'email': 'admin@example.local',
        })
        if created:
            admin.set_password('admin12345')
            admin.save()
        admin.groups.add(operator_group)

        center, _ = DonationCenter.objects.get_or_create(
            name='Oleificio Failla',
            city='Carini',
            defaults={'address': 'Sede demo autoemoteca', 'notes': 'Scenario dimostrativo per raccolte sangue.'},
        )

        featured_image = ensure_demo_featured_image()
        # Date relative a oggi: con date fisse la demo "scadeva" e home ed elenco
        # raccolte risultavano vuoti dopo poche settimane.
        today = timezone.localdate()
        session_dates = [today + timedelta(days=offset) for offset in (3, 9, 16, 24)]
        sessions = []
        for d in session_dates:
            session, _ = DonationSession.objects.get_or_create(
                center=center,
                date=d,
                defaults={
                    'title': f'Raccolta sangue Carini - {d:%d/%m/%Y}',
                    'start_time': time(7, 30),
                    'end_time': time(12, 0),
                    'capacity': 18,
                    'public_slots': 18,
                    'status': 'OPEN',
                    'featured_image': featured_image,
                    'public_description': 'Giornata di raccolta sangue con autoemoteca presso Oleificio Failla, Carini. Prenotazione obbligatoria con possibilità di lista d’attesa e standby last-minute.',
                    'public_instructions': 'Presentarsi almeno 15 minuti prima dello slot assegnato con documento di riconoscimento e tessera sanitaria. In caso di impossibilità, annullare la prenotazione dalla dashboard.',
                    'notes': 'Raccolta demo con autoemoteca.',
                },
            )
            session.title = session.title or f'Raccolta sangue Carini - {d:%d/%m/%Y}'
            session.featured_image = session.featured_image or featured_image
            session.public_description = session.public_description or 'Giornata di raccolta sangue con autoemoteca presso Oleificio Failla, Carini. Prenotazione obbligatoria con possibilità di lista d’attesa e standby last-minute.'
            session.public_instructions = session.public_instructions or 'Presentarsi almeno 15 minuti prima dello slot assegnato con documento di riconoscimento e tessera sanitaria. In caso di impossibilità, annullare la prenotazione dalla dashboard.'
            session.save(update_fields=['title', 'featured_image', 'public_description', 'public_instructions', 'updated_at'])
            generate_slots_for_session(session)
            sessions.append(session)

        # Scenario principale: la seconda raccolta, completamente prenotata.
        target = DonationSession.objects.get(center=center, date=session_dates[1])

        booked_demo_people = [
            ('mario', 'Mario', 'Rossi', '3331111100', 'mario.rossi@example.local', 82),
            ('donatore1', 'Giuseppe', 'Sala', '3331111101', 'giuseppe.sala@example.local', 77),
            ('donatore2', 'Francesca', 'Costa', '3331111102', 'francesca.costa@example.local', 91),
            ('donatore3', 'Roberto', 'Greco', '3331111103', 'roberto.greco@example.local', 75),
            ('donatore4', 'Elena', 'Marino', '3331111104', 'elena.marino@example.local', 88),
            ('donatore5', 'Davide', 'Vitale', '3331111105', 'davide.vitale@example.local', 80),
            ('donatore6', 'Chiara', 'Conti', '3331111106', 'chiara.conti@example.local', 86),
            ('donatore7', 'Alessio', 'Amato', '3331111107', 'alessio.amato@example.local', 79),
            ('donatore8', 'Valeria', 'Ferri', '3331111108', 'valeria.ferri@example.local', 83),
            ('donatore9', 'Marco', 'Lombardo', '3331111109', 'marco.lombardo@example.local', 76),
            ('donatore10', 'Silvia', 'Morello', '3331111110', 'silvia.morello@example.local', 90),
            ('donatore11', 'Andrea', 'Parisi', '3331111111', 'andrea.parisi@example.local', 85),
            ('donatore12', 'Laura', 'Fontana', '3331111112', 'laura.fontana@example.local', 87),
            ('donatore13', 'Nino', 'Gallo', '3331111113', 'nino.gallo@example.local', 78),
            ('donatore14', 'Serena', 'Caruso', '3331111114', 'serena.caruso@example.local', 82),
            ('donatore15', 'Pietro', 'Rizzo', '3331111115', 'pietro.rizzo@example.local', 74),
            ('donatore16', 'Marta', 'Palmeri', '3331111116', 'marta.palmeri@example.local', 86),
            ('donatore17', 'Enrico', 'Bruno', '3331111117', 'enrico.bruno@example.local', 81),
        ]
        standby_demo_people = [
            ('luca', 'Luca', 'Bianchi', '3332222221', 'luca.bianchi@example.local', 92),
            ('anna', 'Anna', 'Verdi', '3332222222', 'anna.verdi@example.local', 84),
            ('paolo', 'Paolo', 'Russo', '3332222223', 'paolo.russo@example.local', 78),
            ('giulia', 'Giulia', 'Romano', '3332222224', 'giulia.romano@example.local', 81),
            ('salvatore', 'Salvatore', 'Messina', '3332222225', 'salvatore.messina@example.local', 74),
        ]
        donors_data = booked_demo_people + standby_demo_people
        donors = {}
        for username, first, last, phone, email, reliability in donors_data:
            user, created = User.objects.get_or_create(username=username, defaults={
                'first_name': first,
                'last_name': last,
                'email': email,
            })
            if created:
                user.set_password('demo12345')
                user.save()
            donor, _ = Donor.objects.update_or_create(
                user=user,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'phone': phone,
                    'email': email,
                    'blood_group': '0+',
                    'preferred_channel': 'WHATSAPP',
                    'reliability_score': reliability,
                },
            )
            donors[username] = donor

        # Prenotazioni demo: tutti gli slot della raccolta principale sono occupati.
        # Mario Rossi è fissato nello slot critico delle 07:45.
        slot_times = [slot.time for slot in target.slots.order_by('time')]
        slot_usernames = ['donatore1'] * len(slot_times)
        booked_usernames = [person[0] for person in booked_demo_people if person[0] != 'mario']
        idx = 0
        for pos, slot_time in enumerate(slot_times):
            if slot_time == time(7, 45):
                slot_usernames[pos] = 'mario'
            else:
                slot_usernames[pos] = booked_usernames[idx]
                idx += 1
        for slot_time, username in zip(slot_times, slot_usernames):
            slot = target.slots.get(time=slot_time)
            if slot.status == 'FREE':
                try:
                    book_slot(slot, donors[username], source='OPERATOR')
                except DonoFlowError as exc:
                    # Rilanciando il seed su un DB già usato alcune regole possono
                    # impedire la prenotazione demo: la si salta invece di fermarsi.
                    self.stdout.write(self.style.WARNING(f'Slot {slot_time:%H:%M} saltato: {exc}'))
        target.status = 'FULL'
        target.save(update_fields=['status', 'updated_at'])

        standby_data = [
            ('luca', 1, 8, 0, 92),
            ('anna', 2, 12, 0, 84),
            ('paolo', 3, 25, 0, 78),
            ('giulia', 4, 35, 0, 81),
            ('salvatore', 5, 30, 0, 74),
        ]
        for username, pos, eta, min_notice, priority in standby_data:
            entry, _ = WaitlistEntry.objects.update_or_create(
                donor=donors[username],
                session=target,
                defaults={
                    'center': center,
                    'donation_type': target.donation_type,
                    'date_from': target.date,
                    'date_to': target.date,
                    'preferred_time_range': 'ANY',
                    'minimum_notice_minutes': min_notice,
                    'max_arrival_minutes': eta,
                    'position': pos,
                    'priority_score': priority,
                    'status': 'STANDBY_CONFIRMED',
                },
            )
            confirm_standby(
                target,
                donors[username],
                available_from=time(7, 30),
                available_to=time(12, 0),
                minimum_notice_minutes=min_notice,
                max_arrival_minutes=eta,
                preferred_channel='WHATSAPP',
            )

        self.stdout.write(self.style.SUCCESS('Dati demo creati.'))
        self.stdout.write('Account admin: admin / admin12345')
        self.stdout.write('Account donatore demo: mario / demo12345, luca / demo12345, anna / demo12345')
        self.stdout.write(f'Scenario test: accedi come admin, apri la raccolta del {target.date:%d/%m/%Y}, marca lo slot 07:45 come ritardo critico e attiva standby.')
