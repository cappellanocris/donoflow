"""Test di regressione per le regole di dominio e i permessi.

Ogni test corrisponde a un problema trovato nell'audit di settembre 2026:
se uno di questi fallisce, un bug già corretto è tornato.
"""
from datetime import time, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import services as S
from core.forms import SessionCreateForm
from core.models import (
    Appointment, DonationCenter, DonationSession, Donor, StandbyAvailability,
    WaitlistEntry, WaitlistOffer,
)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])  # solo per velocità
class BaseScenario(TestCase):
    """Una raccolta futura aperta con 8 slot (6 pubblici), due donatori e un admin."""

    def setUp(self):
        self.center = DonationCenter.objects.create(name='Sede', city='Carini')
        self.session = self.make_session(days=10)
        self.u1, self.d1 = self.make_donor('d1', 'a@example.it')
        self.u2, self.d2 = self.make_donor('d2', 'b@example.it')
        self.admin = User.objects.create_user('adm', password='x', is_staff=True)
        self.c1 = self.client_for(self.u1)
        self.c2 = self.client_for(self.u2)
        self.ca = self.client_for(self.admin)

    def make_session(self, days, status='OPEN', **kw):
        session = DonationSession.objects.create(
            center=self.center, date=timezone.localdate() + timedelta(days=days),
            start_time=time(8), end_time=time(10), slot_duration_minutes=15,
            capacity=8, public_slots=6, reserved_slots=2, status=status, **kw)
        S.generate_slots_for_session(session)
        return session

    def make_donor(self, username, email):
        user = User.objects.create_user(username, password='x')
        return user, Donor.objects.create(user=user, first_name=username, last_name='Test', email=email)

    @staticmethod
    def client_for(user):
        client = Client()
        client.force_login(user)
        return client

    def free_slot(self, session=None):
        return (session or self.session).slots.filter(status='FREE').order_by('time').first()


class BookingRulesTests(BaseScenario):
    def test_one_active_booking_per_donor_per_session(self):
        S.book_slot(self.free_slot(), self.d1)
        with self.assertRaises(S.DonoFlowError):
            S.book_slot(self.free_slot(), self.d1)

    def test_cannot_book_non_open_sessions(self):
        for status in ['CANCELLED', 'CLOSED', 'DRAFT']:
            self.session.status = status
            self.session.save()
            with self.subTest(status=status), self.assertRaises(S.DonoFlowError):
                S.book_slot(self.free_slot(), self.d1)

    def test_cannot_book_past_session(self):
        past = self.make_session(days=-3)
        with self.assertRaises(S.DonoFlowError):
            S.book_slot(self.free_slot(past), self.d1)

    def test_minimum_interval_between_donations(self):
        self.d1.last_donation_date = self.session.date - timedelta(days=30)
        self.d1.save()
        with self.assertRaises(S.DonoFlowError):
            S.book_slot(self.free_slot(), self.d1)
        self.d1.last_donation_date = self.session.date - timedelta(days=120)
        self.d1.save()
        S.book_slot(self.free_slot(), self.d1)

    def test_booking_error_is_shown_not_raised(self):
        S.book_slot(self.free_slot(), self.d1)
        response = self.c1.post(reverse('book_slot', args=[self.free_slot().pk]), follow=True)
        self.assertContains(response, 'Hai già una prenotazione attiva')

    def test_staff_booking_gets_message_not_403(self):
        response = self.ca.post(reverse('book_slot', args=[self.free_slot().pk]))
        self.assertEqual(response.status_code, 302)


class SessionStatusTests(BaseScenario):
    def test_generating_slots_keeps_draft_private(self):
        draft = self.make_session(days=20, status='DRAFT')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'DRAFT')

    def test_cancellation_does_not_reopen_closed_session(self):
        appointment = S.book_slot(self.free_slot(), self.d1)
        self.session.status = 'CLOSED'
        self.session.save()
        S.cancel_appointment(appointment)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'CLOSED')

    def test_full_and_open_still_toggle(self):
        for slot in list(self.session.slots.filter(status='FREE')):
            _, donor = self.make_donor(f'x{slot.pk}', f'x{slot.pk}@example.it')
            S.book_slot(slot, donor)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'FULL')
        S.cancel_appointment(Appointment.objects.filter(slot__session=self.session).first())
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'OPEN')

    def test_draft_detail_hidden_from_public(self):
        self.session.status = 'DRAFT'
        self.session.save()
        self.assertEqual(Client().get(reverse('session_detail', args=[self.session.pk])).status_code, 404)
        self.assertEqual(self.ca.get(reverse('session_detail', args=[self.session.pk])).status_code, 200)


class AppointmentTransitionTests(BaseScenario):
    def test_completed_donation_cannot_be_cancelled(self):
        appointment = S.book_slot(self.free_slot(), self.d1)
        S.mark_donation_completed(appointment)
        with self.assertRaises(S.DonoFlowError):
            S.cancel_appointment(appointment)
        appointment.slot.refresh_from_db()
        self.assertEqual(appointment.slot.status, 'COMPLETED')

    def test_checkin_does_not_revive_cancelled_booking(self):
        appointment = S.book_slot(self.free_slot(), self.d1)
        S.cancel_appointment(appointment)
        with self.assertRaises(S.DonoFlowError):
            S.mark_checkin(appointment)

    def test_double_no_show_penalises_once(self):
        appointment = S.book_slot(self.free_slot(), self.d1)
        S.mark_no_show(appointment)
        response = self.ca.post(reverse('operator_no_show', args=[appointment.pk]), follow=True)
        self.d1.refresh_from_db()
        self.assertEqual(self.d1.reliability_score, 70)
        self.assertContains(response, 'Impossibile registrare il no-show')

    def test_risk_requires_booked_slot(self):
        with self.assertRaises(S.DonoFlowError):
            S.mark_slot_risk(self.free_slot())


class StandbyOfferTests(BaseScenario):
    def setUp(self):
        super().setUp()
        for donor in (self.d1, self.d2):
            StandbyAvailability.objects.create(donor=donor, session=self.session, status='CONFIRMED',
                                               available_from=time(7), available_to=time(12), max_arrival_minutes=10)
            S.create_waitlist_entry(self.session, donor)
        _, self.d3 = self.make_donor('d3', 'c@example.it')
        self.slot = self.free_slot()
        S.book_slot(self.slot, self.d3)
        S.activate_standby_for_slot(self.slot)
        self.o1 = WaitlistOffer.objects.get(slot=self.slot, donor=self.d1)
        self.o2 = WaitlistOffer.objects.get(slot=self.slot, donor=self.d2)

    def test_closed_offer_cannot_be_accepted(self):
        S.respond_to_offer(self.o1, 'ACCEPT')
        S.assign_standby_offer(self.o1)
        self.o2.refresh_from_db()
        with self.assertRaises(S.DonoFlowError):
            S.respond_to_offer(self.o2, 'ACCEPT')

    def test_slot_cannot_be_assigned_twice(self):
        S.respond_to_offer(self.o1, 'ACCEPT')
        S.respond_to_offer(self.o2, 'ACCEPT')
        S.assign_standby_offer(self.o1)
        with self.assertRaises(S.DonoFlowError):
            S.assign_standby_offer(self.o2)
        self.assertEqual(Appointment.objects.filter(slot=self.slot, source='STANDBY').count(), 1)

    def test_expired_offer_cannot_be_accepted(self):
        self.o1.expires_at = timezone.now() - timedelta(minutes=1)
        self.o1.save()
        with self.assertRaises(S.DonoFlowError):
            S.respond_to_offer(self.o1, 'ACCEPT')
        self.o1.refresh_from_db()
        self.assertEqual(self.o1.status, 'EXPIRED')

    def test_waitlist_positions_are_unique_after_removal(self):
        WaitlistEntry.objects.filter(donor=self.d1).delete()
        _, d4 = self.make_donor('d4', 'd@example.it')
        entry = S.create_waitlist_entry(self.session, d4)
        positions = list(self.session.waitlist_entries.values_list('position', flat=True))
        self.assertEqual(len(positions), len(set(positions)), positions)
        self.assertEqual(entry.position, max(positions))

    def test_no_waitlist_on_cancelled_session(self):
        self.session.status = 'CANCELLED'
        self.session.save()
        _, d5 = self.make_donor('d5', 'e@example.it')
        with self.assertRaises(S.DonoFlowError):
            S.confirm_standby(self.session, d5)


class FormTests(BaseScenario):
    def session_data(self, **overrides):
        data = {'center': self.center.pk, 'date': str(timezone.localdate() + timedelta(days=5)),
                'start_time': '08:00', 'end_time': '10:00', 'slot_duration_minutes': 15,
                'expected_arrival_minutes': 15, 'donation_type': 'WHOLE_BLOOD', 'capacity': 8,
                'public_slots': 8, 'reserved_slots': 0, 'standby_slots': 0, 'status': 'OPEN'}
        data.update(overrides)
        return data

    def test_date_inputs_render_iso_format(self):
        """<input type=date> vuole AAAA-MM-GG: col formato italiano il campo appariva vuoto."""
        html = str(SessionCreateForm(instance=self.session)['date'])
        self.assertIn(f'value="{self.session.date:%Y-%m-%d}"', html)
        self.d1.birth_date = timezone.localdate().replace(year=1990)
        self.d1.save()
        page = self.c1.get(reverse('profile')).content.decode()
        self.assertIn(f'value="{self.d1.birth_date:%Y-%m-%d}"', page)

    def test_zero_slot_duration_rejected(self):
        self.assertFalse(SessionCreateForm(self.session_data(slot_duration_minutes=0)).is_valid())

    def test_new_session_in_past_rejected_but_existing_editable(self):
        self.assertFalse(SessionCreateForm(self.session_data(date='2020-01-01')).is_valid())
        past = self.make_session(days=-3)
        form = SessionCreateForm(self.session_data(date=str(past.date)), instance=past)
        self.assertTrue(form.is_valid(), form.errors)

    def test_standby_time_range_validated(self):
        response = self.c1.post(reverse('confirm_standby', args=[self.session.pk]), {
            'available_from': '11:00', 'available_to': '08:00', 'minimum_notice_minutes': 15,
            'max_arrival_minutes': 20, 'preferred_channel': 'EMAIL'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StandbyAvailability.objects.filter(donor=self.d1).exists())

    def test_registration_requires_strong_password_and_unique_email(self):
        base = {'username': 'nuovo', 'first_name': 'N', 'last_name': 'N', 'phone': '1',
                'preferred_channel': 'EMAIL'}
        Client().post(reverse('register'), {**base, 'email': 'new@example.it', 'password1': '1', 'password2': '1'})
        self.assertFalse(User.objects.filter(username='nuovo').exists())
        Client().post(reverse('register'), {**base, 'email': 'A@example.it',
                                            'password1': 'Robusta-2026!', 'password2': 'Robusta-2026!'})
        self.assertFalse(User.objects.filter(username='nuovo').exists())


class PermissionTests(BaseScenario):
    def test_donor_cannot_cancel_someone_else(self):
        appointment = S.book_slot(self.free_slot(), self.d1)
        self.assertEqual(self.c2.post(reverse('cancel_appointment', args=[appointment.pk])).status_code, 404)

    def test_donor_gets_403_on_operator_areas(self):
        for name, args in [('operator_dashboard', []), ('management_sessions', []),
                           ('operator_session', [self.session.pk])]:
            with self.subTest(name=name):
                self.assertEqual(self.c1.get(reverse(name, args=args)).status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = Client().get(reverse('operator_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_group_operator_sees_operator_menu_but_not_management(self):
        user = User.objects.create_user('op', password='x')
        user.groups.add(Group.objects.get_or_create(name='operatori')[0])
        client = self.client_for(user)
        home = client.get('/').content.decode()
        self.assertIn(reverse('operator_dashboard'), home)
        self.assertNotIn(reverse('management_sessions'), home)
        console = client.get(reverse('operator_session', args=[self.session.pk])).content.decode()
        self.assertNotIn(reverse('management_appointments', args=[self.session.pk]), console)


class ReviewFindingsTests(StandbyOfferTests):
    """Problemi emersi dalla revisione indipendente delle correzioni."""

    def test_second_standby_round_on_same_slot(self):
        S.respond_to_offer(self.o1, 'ACCEPT')
        S.assign_standby_offer(self.o1)
        # Anche il sostituto è in ritardo: nuovo giro di standby sullo stesso slot.
        S.activate_standby_for_slot(self.slot)
        offer = WaitlistOffer.objects.get(slot=self.slot, donor=self.d2)
        self.assertEqual(offer.status, 'SENT')
        S.respond_to_offer(offer, 'ACCEPT')
        S.assign_standby_offer(offer)
        self.assertEqual(self.slot.appointments.filter(status__in=Appointment.ACTIVE_STATUSES).get().donor, self.d2)

    def test_checked_in_donor_is_not_replaced(self):
        S.respond_to_offer(self.o1, 'ACCEPT')
        S.mark_checkin(self.slot.appointments.get(donor=self.d3))
        self.o1.refresh_from_db()
        self.assertEqual(self.o1.status, 'CANCELLED')
        with self.assertRaises(S.DonoFlowError):
            S.assign_standby_offer(self.o1)

    def test_operator_confirm_respects_rules(self):
        cancelled = self.slot.appointments.get(donor=self.d3)
        S.cancel_appointment(cancelled)
        other = S.book_slot(self.free_slot(), self.d3)  # stesso donatore, altro slot
        with self.assertRaises(S.DonoFlowError):
            S.confirm_appointment_by_operator(cancelled)
        S.cancel_appointment(other)
        _, d6 = self.make_donor('d6', 'f@example.it')
        rebooked = S.book_slot(self.slot, d6)
        S.mark_donation_completed(rebooked)
        with self.assertRaises(S.DonoFlowError):
            S.confirm_appointment_by_operator(cancelled)  # non sovrascrive la donazione completata

    def test_seed_demo_can_run_twice(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('seed_demo', stdout=StringIO())
        main = DonationSession.objects.filter(center__name='Oleificio Failla').order_by('date')[1]
        S.cancel_appointment(Appointment.objects.filter(slot__session=main).first())
        main.status = 'CLOSED'
        main.save()
        call_command('seed_demo', stdout=StringIO())  # non deve sollevare eccezioni
