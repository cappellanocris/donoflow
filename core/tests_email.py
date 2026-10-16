"""Test dell'invio email: consegna dopo il commit, esito registrato, notifiche coperte.

Nei test Django usa il backend locmem (mail.outbox), quindi l'esito "normale" è
"Simulata"; per l'esito "Inviata" e gli errori SMTP si simula il backend SMTP.
"""
from datetime import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core import mail
from django.db import transaction
from django.test import override_settings
from django.urls import reverse

from core import services as S
from core.models import Notification, StandbyAvailability, WaitlistOffer
from core.tests_rules import BaseScenario
from donoflow.settings import load_env_file

SMTP = 'django.core.mail.backends.smtp.EmailBackend'


def emails(donor):
    return Notification.objects.filter(donor=donor, channel='EMAIL').order_by('pk')


class EmailDeliveryTests(BaseScenario):
    def test_booking_email_sent_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            S.book_slot(self.free_slot(), self.d1)
            self.assertEqual(len(mail.outbox), 0)  # niente invio dentro la transazione
            self.assertEqual(emails(self.d1).get().status, 'QUEUED')
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['a@example.it'])
        self.assertIn('Prenotazione confermata', mail.outbox[0].subject)
        self.assertEqual(emails(self.d1).get().status, 'SIMULATED')

    def test_no_email_when_operation_rolls_back(self):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    S.book_slot(self.free_slot(), self.d1)
                    raise RuntimeError('errore successivo')
            except RuntimeError:
                pass
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND=SMTP)
    def test_real_smtp_marks_email_sent(self):
        with mock.patch('core.services.send_mail', return_value=1) as send, \
                self.captureOnCommitCallbacks(execute=True):
            S.book_slot(self.free_slot(), self.d1)
        send.assert_called_once()
        self.assertEqual(emails(self.d1).get().status, 'SENT')

    @override_settings(EMAIL_BACKEND=SMTP)
    def test_smtp_error_recorded_and_booking_kept(self):
        with mock.patch('core.services.send_mail', side_effect=OSError('Connection refused')), \
                self.captureOnCommitCallbacks(execute=True):
            appointment = S.book_slot(self.free_slot(), self.d1)
        record = emails(self.d1).get()
        self.assertEqual(record.status, 'FAILED')
        self.assertIn('Connection refused', record.message)
        self.assertTrue(type(appointment).objects.filter(pk=appointment.pk).exists())

    def test_missing_address_recorded_as_failed(self):
        self.d1.email = ''
        self.d1.save()
        self.u1.email = ''
        self.u1.save()
        with self.captureOnCommitCallbacks(execute=True):
            S.book_slot(self.free_slot(), self.d1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(emails(self.d1).get().status, 'FAILED')

    @override_settings(DONOFLOW_SITE_URL='https://donoflow.example.it')
    def test_email_contains_dashboard_link(self):
        with self.captureOnCommitCallbacks(execute=True):
            S.book_slot(self.free_slot(), self.d1)
        self.assertIn('https://donoflow.example.it/dashboard/', mail.outbox[0].body)


class NotificationEmailCoverageTests(BaseScenario):
    """Le notifiche al donatore che prima erano solo simulate ora arrivano anche via email."""

    def test_waitlist_and_standby_send_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            S.create_waitlist_entry(self.session, self.d1)
            S.confirm_standby(self.session, self.d1, available_from=time(7), available_to=time(12))
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any('lista d’attesa' in s for s in subjects), subjects)
        self.assertTrue(any('standby confermata' in s for s in subjects), subjects)

    def test_urgent_offer_and_assignment_send_email(self):
        for donor in (self.d1, self.d2):
            StandbyAvailability.objects.create(donor=donor, session=self.session, status='CONFIRMED',
                                               available_from=time(7), available_to=time(12), max_arrival_minutes=10)
            S.create_waitlist_entry(self.session, donor)
        _, d3 = self.make_donor('d3', 'c@example.it')
        slot = self.free_slot()
        S.book_slot(slot, d3)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            S.activate_standby_for_slot(slot)
        offer_mails = [m for m in mail.outbox if 'Posto disponibile' in m.subject]
        self.assertEqual(sorted(m.to[0] for m in offer_mails), ['a@example.it', 'b@example.it'])

        o1 = WaitlistOffer.objects.get(slot=slot, donor=self.d1)
        o2 = WaitlistOffer.objects.get(slot=slot, donor=self.d2)
        S.respond_to_offer(o1, 'ACCEPT')
        S.respond_to_offer(o2, 'ACCEPT')
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            S.assign_standby_offer(o1)
        by_recipient = {m.to[0]: m.subject for m in mail.outbox}
        self.assertIn('last-minute', by_recipient['a@example.it'])
        self.assertIn('altro donatore', by_recipient['b@example.it'])


    def test_email_preferred_channel_not_duplicated(self):
        self.d1.preferred_channel = 'EMAIL'
        self.d1.save()
        with self.captureOnCommitCallbacks(execute=True):
            S.book_slot(self.free_slot(), self.d1)
            S.create_waitlist_entry(self.make_session(days=20), self.d1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(emails(self.d1).count(), 2)
        self.assertEqual(set(emails(self.d1).values_list('status', flat=True)), {'SIMULATED'})  # backend locmem


class SeedDemoEmailTests(BaseScenario):
    @override_settings(EMAIL_BACKEND=SMTP)
    def test_seed_demo_never_sends_real_email(self):
        from io import StringIO
        from django.core.management import call_command
        with mock.patch('django.core.mail.backends.smtp.EmailBackend.send_messages') as smtp, \
                self.captureOnCommitCallbacks(execute=True):
            call_command('seed_demo', stdout=StringIO())
        smtp.assert_not_called()
        self.assertTrue(Notification.objects.filter(channel='EMAIL').exists())


class ManualEmailViewTests(BaseScenario):
    def setUp(self):
        super().setUp()
        self.appointment = S.book_slot(self.free_slot(), self.d1)

    def send(self):
        url = reverse('management_send_appointment_email', args=[self.appointment.pk])
        return [str(m) for m in self.ca.post(url, follow=True).context['messages']]

    def test_console_backend_warns_email_is_simulated(self):
        self.assertIn('simulata', self.send()[0])

    @override_settings(EMAIL_BACKEND=SMTP)
    def test_smtp_success_and_failure_messages(self):
        with mock.patch('core.services.send_mail', return_value=1):
            self.assertIn('inviata a a@example.it', self.send()[0])
        with mock.patch('core.services.send_mail', side_effect=OSError('auth failed')):
            self.assertIn('non inviata', self.send()[0])


class EnvFileTests(BaseScenario):
    def test_env_file_parsing_does_not_override_exported_values(self):
        with TemporaryDirectory() as tmp:
            env = Path(tmp) / '.env'
            env.write_text(
                '# commento\n'
                'DONOFLOW_TEST_A=uno\n'
                'export DONOFLOW_TEST_B="due con spazi"\n'
                "DONOFLOW_TEST_C='abc=def'\n"
                'DONOFLOW_TEST_D=dal-file\n', encoding='utf-8')
            with mock.patch.dict('os.environ', {'DONOFLOW_TEST_D': 'esportato'}):
                load_env_file(env)
                import os
                self.assertEqual(os.environ['DONOFLOW_TEST_A'], 'uno')
                self.assertEqual(os.environ['DONOFLOW_TEST_B'], 'due con spazi')
                self.assertEqual(os.environ['DONOFLOW_TEST_C'], 'abc=def')
                self.assertEqual(os.environ['DONOFLOW_TEST_D'], 'esportato')
