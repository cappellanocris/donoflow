"""Service layer di DonoFlow: tutta la logica di business vive qui.

Le view restano sottili (validazione richiesta + messaggio) e delegano a queste
funzioni, che si occupano di transizioni di stato, notifiche, email e audit log.
Convenzione: le funzioni che toccano più record sono avvolte in una transazione.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import (
    Appointment,
    DonationSession,
    AuditLog,
    CheckIn,
    DonationOutcome,
    Notification,
    Slot,
    StandbyAvailability,
    WaitlistEntry,
    WaitlistOffer,
)

logger = logging.getLogger(__name__)

# Alias locali per leggibilità: la fonte di verità è il modello Appointment.
ACTIVE_APPOINTMENT_STATUSES = Appointment.ACTIVE_STATUSES
FINAL_APPOINTMENT_STATUSES = Appointment.FINAL_STATUSES

# Intervallo minimo (giorni) tra due donazioni, per tipo. Valori prudenziali da
# far verificare al direttore sanitario; sovrascrivibili in settings.
DEFAULT_MIN_DONATION_INTERVAL_DAYS = {'WHOLE_BLOOD': 90, 'PLASMA': 14, 'PLATELETS': 14}


class DonoFlowError(ValueError):
    """Operazione non consentita dallo stato attuale: il messaggio è mostrato all'utente."""


def require_status(appointment, allowed, action):
    """Blocca transizioni non valide (es. check-in su prenotazione annullata)."""
    if appointment.status not in allowed:
        raise DonoFlowError(
            f'Impossibile {action}: la prenotazione è in stato "{appointment.get_status_display()}".'
        )


def min_interval_days(donation_type):
    intervals = getattr(settings, 'DONOFLOW_MIN_DONATION_INTERVAL_DAYS', DEFAULT_MIN_DONATION_INTERVAL_DAYS)
    return intervals.get(donation_type, 0)


def log_action(user, action, obj=None, notes=''):
    AuditLog.objects.create(
        user=user if getattr(user, 'is_authenticated', False) else None,
        action=action,
        object_type=obj.__class__.__name__ if obj else '',
        object_id=str(getattr(obj, 'pk', '')) if obj else '',
        notes=notes,
    )


def create_notification(donor=None, appointment=None, channel='DASHBOARD', template='INFO', message='', status='SIMULATED'):
    return Notification.objects.create(
        donor=donor,
        appointment=appointment,
        channel=channel,
        template=template,
        message=message,
        status=status,
    )


# Backend che non consegnano davvero il messaggio: l'email viene registrata come "Simulata".
SIMULATED_EMAIL_BACKENDS = (
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.locmem.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
    'django.core.mail.backends.filebased.EmailBackend',
)


def email_delivery_is_simulated(backend=None):
    return (backend or settings.EMAIL_BACKEND) in SIMULATED_EMAIL_BACKENDS


def _deliver_email(notification_id, recipient, subject, body, backend):
    """Spedisce l'email e aggiorna la notifica con l'esito (Inviata / Simulata / Fallita)."""
    record = f'A: {recipient}\nOggetto: {subject}\n\n{body}'
    try:
        sent_count = send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
            connection=get_connection(backend),
        )
    except Exception as exc:  # SMTP non raggiungibile, credenziali errate, ecc.
        logger.warning('Invio email a %s fallito: %s', recipient, exc)
        status, message = 'FAILED', f'Errore invio email: {exc}\n{record}'
    else:
        if not sent_count:
            status = 'FAILED'
        else:
            status = 'SIMULATED' if email_delivery_is_simulated(backend) else 'SENT'
        message = record
    Notification.objects.filter(pk=notification_id).update(status=status, message=message, sent_at=timezone.now())
    return status


def send_informative_email(donor, subject, body, appointment=None, template='EMAIL_INFO', defer=True):
    """Invia una mail informativa e registra sempre l'esito nello storico email del donatore.

    Senza SMTP configurato (backend console, predefinito in locale) l'email appare nel
    terminale di `runserver` e viene registrata come "Simulata". Con SMTP configurato in
    .env viene spedita davvero. Dentro una transazione l'invio avviene solo dopo il
    commit, così un SMTP lento non tiene bloccato il database e un'operazione annullata
    non manda email. Con ``defer=False`` l'invio è immediato (per mostrare subito l'esito).

    Restituisce lo stato: 'SENT', 'SIMULATED', 'FAILED' oppure 'QUEUED' (invio dopo il commit).
    """
    recipient = ''
    if donor:
        recipient = (donor.email or '').strip()
        if not recipient and donor.user_id:
            recipient = (getattr(donor.user, 'email', '') or '').strip()

    if not recipient:
        create_notification(
            donor=donor,
            appointment=appointment,
            channel='EMAIL',
            template=template,
            message=f'Email non inviata: indirizzo mancante.\n\nOggetto: {subject}\n\n{body}',
            status='FAILED',
        )
        return 'FAILED'

    notification = create_notification(
        donor=donor,
        appointment=appointment,
        channel='EMAIL',
        template=template,
        message=f'A: {recipient}\nOggetto: {subject}\n\n{body}',
        status='QUEUED',
    )
    # Il backend si fissa ora: l'invio differito usa la configurazione attiva al momento della richiesta.
    backend = settings.EMAIL_BACKEND
    if defer and transaction.get_connection().in_atomic_block:
        transaction.on_commit(lambda: _deliver_email(notification.pk, recipient, subject, body, backend))
        return 'QUEUED'
    return _deliver_email(notification.pk, recipient, subject, body, backend)


def site_link(url_name, *args):
    return settings.DONOFLOW_SITE_URL + reverse(url_name, args=args)


def donor_email_body(donor, text):
    return (
        f'Ciao {donor.first_name},\n\n'
        f'{text}\n\n'
        f'Gestisci le tue prenotazioni: {site_link("dashboard")}\n\n'
        f'Questa è una comunicazione informativa generata da DonoFlow.\n'
    )


def notify_donor(donor, template, message, email_subject=None, channel=None):
    """Notifica al donatore sul canale preferito e, se indicato l'oggetto, la stessa comunicazione via email."""
    channel = channel or donor.preferred_channel
    # Se il canale preferito è l'email, la notifica è l'email stessa: niente doppione simulato.
    if not (email_subject and channel == 'EMAIL'):
        create_notification(donor=donor, channel=channel, template=template, message=message)
    if email_subject:
        send_informative_email(donor, email_subject, donor_email_body(donor, message), template=f'EMAIL_{template}')


def appointment_email_body(appointment, intro):
    slot = appointment.slot
    session = slot.session
    donor = appointment.donor
    return (
        f'Ciao {donor.first_name},\n\n'
        f'{intro}\n\n'
        f'Dettagli raccolta:\n'
        f'- Data: {session.date:%d/%m/%Y}\n'
        f'- Sede: {session.center.name}, {session.center.city}\n'
        f'- Indirizzo: {session.center.address or "non indicato"}\n'
        f'- Orario prenotazione: {slot.time:%H:%M}\n'
        f'- Arrivo richiesto entro: {slot.expected_arrival_time:%H:%M}\n\n'
        f'Gestisci le tue prenotazioni: {site_link("dashboard")}\n\n'
        f'Questa è una comunicazione informativa generata da DonoFlow.\n'
    )


def notify_appointment(appointment, template, message, email_subject=None, email_intro=None, email_extra=''):
    """Invia al donatore la notifica sul canale preferito e, se richiesto, l'email riepilogativa.

    Il template email è derivato per convenzione: ``EMAIL_<template>``.
    Centralizza il pattern notifica+email ripetuto in tutte le transizioni di stato.
    """
    donor = appointment.donor
    sends_email = bool(email_subject and email_intro)
    # Se il canale preferito è l'email, la notifica è l'email stessa: niente doppione simulato.
    if not (sends_email and donor.preferred_channel == 'EMAIL'):
        create_notification(
            donor=donor,
            appointment=appointment,
            channel=donor.preferred_channel,
            template=template,
            message=message,
        )
    if sends_email:
        send_informative_email(
            donor,
            email_subject,
            appointment_email_body(appointment, email_intro) + email_extra,
            appointment=appointment,
            template=f'EMAIL_{template}',
        )


def release_slot_if_unbooked(slot, exclude_appointment=None):
    """Riporta lo slot a FREE se non restano altre prenotazioni attive."""
    others = slot.appointments.filter(status__in=ACTIVE_APPOINTMENT_STATUSES)
    if exclude_appointment is not None:
        others = others.exclude(pk=exclude_appointment.pk)
    if not others.exists():
        slot.status = 'FREE'
        slot.donor = None
        slot.save(update_fields=['status', 'donor', 'updated_at'])


def update_session_status(session):
    """Riallinea OPEN <-> FULL in base agli slot liberi.

    Bozze, raccolte chiuse e annullate NON vengono mai toccate: prima una
    prenotazione o un annullamento potevano riaprirle (o pubblicare una bozza).
    """
    if session.status not in DonationSession.PUBLIC_STATUSES:
        return
    new_status = 'FULL' if session.slots.exists() and session.available_count() == 0 else 'OPEN'
    if new_status != session.status:
        session.status = new_status
        session.save(update_fields=['status', 'updated_at'])


def desired_slot_times(session):
    """Calcola gli orari teorici degli slot: dall'inizio alla fine, a passi di durata slot."""
    start = datetime.combine(session.date, session.start_time)
    end = datetime.combine(session.date, session.end_time)
    current = start
    times = []
    while current < end and len(times) < session.capacity:
        times.append(current)
        current += timedelta(minutes=session.slot_duration_minutes)
    return times


def generate_slots_for_session(session, reset_free=False):
    """Genera o aggiorna gli slot secondo capacità, slot pubblici e slot riservati.

    - I primi `public_slots` sono liberi e prenotabili online.
    - Gli slot successivi fino alla capacità sono bloccati/riservati da operatore.
    - Con `reset_free=True` vengono riallineati gli slot senza prenotazioni attive.
    """
    created = 0
    updated = 0
    desired_times = desired_slot_times(session)
    desired_time_values = [dt.time() for dt in desired_times]

    if reset_free:
        for slot in session.slots.all():
            has_active = slot.appointments.filter(status__in=ACTIVE_APPOINTMENT_STATUSES).exists()
            if not has_active and slot.time not in desired_time_values:
                slot.delete()

    for index, current in enumerate(desired_times):
        initial_status = 'FREE' if index < session.public_slots else 'LOCKED'
        expected_arrival = (current - timedelta(minutes=session.expected_arrival_minutes)).time()
        slot, was_created = Slot.objects.get_or_create(
            session=session,
            time=current.time(),
            defaults={
                'expected_arrival_time': expected_arrival,
                'duration_minutes': session.slot_duration_minutes,
                'donation_type': session.donation_type,
                'status': initial_status,
            },
        )
        if was_created:
            created += 1
            continue

        has_active = slot.appointments.filter(status__in=ACTIVE_APPOINTMENT_STATUSES).exists()
        if reset_free and not has_active:
            slot.expected_arrival_time = expected_arrival
            slot.duration_minutes = session.slot_duration_minutes
            slot.donation_type = session.donation_type
            slot.status = initial_status
            slot.donor = None
            slot.save(update_fields=['expected_arrival_time', 'duration_minutes', 'donation_type', 'status', 'donor', 'updated_at'])
            updated += 1

    update_session_status(session)
    return {'created': created, 'updated': updated, 'total_desired': len(desired_times)}


@transaction.atomic
def book_slot(slot, donor, source='WEB'):
    """Prenota uno slot libero applicando tutte le regole di dominio."""
    slot = Slot.objects.select_for_update().select_related('session').get(pk=slot.pk)
    session = slot.session
    if not session.accepts_bookings:
        raise DonoFlowError('Questa raccolta non accetta prenotazioni.')
    if slot.status != 'FREE':
        raise DonoFlowError('Slot non disponibile.')
    if Appointment.objects.filter(slot=slot, status__in=ACTIVE_APPOINTMENT_STATUSES).exists():
        raise DonoFlowError('Esiste già una prenotazione attiva per questo slot.')
    if Appointment.objects.filter(donor=donor, slot__session=session, status__in=ACTIVE_APPOINTMENT_STATUSES).exists():
        raise DonoFlowError('Hai già una prenotazione attiva per questa raccolta.')
    interval = min_interval_days(slot.donation_type)
    if donor.last_donation_date and interval and (session.date - donor.last_donation_date).days < interval:
        raise DonoFlowError(
            f'Devono trascorrere almeno {interval} giorni dall’ultima donazione '
            f'({donor.last_donation_date:%d/%m/%Y}).'
        )
    appointment = Appointment.objects.create(
        donor=donor,
        slot=slot,
        status='CONFIRMED',
        confirmed_at=timezone.now(),
        source=source,
    )
    slot.donor = donor
    slot.status = 'BOOKED'
    slot.save(update_fields=['donor', 'status', 'updated_at'])
    CheckIn.objects.create(appointment=appointment, expected_arrival_time=slot.expected_arrival_time)
    notify_appointment(
        appointment,
        template='PRENOTAZIONE_CONFERMATA',
        message=f'Prenotazione confermata per il {slot.session.date:%d/%m/%Y} alle {slot.time:%H:%M}. Arrivo richiesto entro le {slot.expected_arrival_time:%H:%M}.',
        email_subject='DonoFlow - Prenotazione confermata',
        email_intro='La tua prenotazione è stata confermata.',
    )
    update_session_status(slot.session)
    return appointment


@transaction.atomic
def _cancel_appointment(appointment, status, template, message, email_subject, email_intro, log_message, user=None, reason=''):
    """Core condiviso per l'annullamento (lato donatore o lato operatore)."""
    require_status(appointment, ACTIVE_APPOINTMENT_STATUSES, 'annullare')
    appointment.status = status
    appointment.cancelled_at = timezone.now()
    appointment.cancellation_reason = reason
    appointment.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])
    slot = appointment.slot
    release_slot_if_unbooked(slot, exclude_appointment=appointment)
    notify_appointment(
        appointment,
        template=template,
        message=message,
        email_subject=email_subject,
        email_intro=email_intro,
        email_extra=(f'\nMotivo: {reason}\n' if reason else ''),
    )
    update_session_status(slot.session)
    log_action(user, log_message, appointment, notes=reason)
    return appointment


def cancel_appointment(appointment, user=None, reason=''):
    """Annullamento richiesto dal donatore: lo slot torna prenotabile."""
    slot = appointment.slot
    return _cancel_appointment(
        appointment,
        status='CANCELLED_BY_DONOR',
        template='PRENOTAZIONE_ANNULLATA',
        message=f'Prenotazione del {slot.session.date:%d/%m/%Y} alle {slot.time:%H:%M} annullata.',
        email_subject='DonoFlow - Prenotazione annullata',
        email_intro='La tua prenotazione è stata annullata.',
        log_message='Annullamento prenotazione',
        user=user,
        reason=reason,
    )


def create_waitlist_entry(session, donor, **kwargs):
    """Inserisce (o riattiva) il donatore in lista d'attesa, in coda alla posizione corrente."""
    if not session.accepts_waitlist:
        raise DonoFlowError('Questa raccolta non accetta iscrizioni in lista d’attesa.')
    # max+1 invece di count+1: dopo una cancellazione count+1 creava posizioni duplicate.
    last = session.waitlist_entries.order_by('-position').values_list('position', flat=True).first()
    position = (last or 0) + 1
    entry, created = WaitlistEntry.objects.get_or_create(
        donor=donor,
        session=session,
        defaults={
            'center': session.center,
            'donation_type': session.donation_type,
            'date_from': session.date,
            'date_to': session.date,
            'position': position,
            **kwargs,
        },
    )
    if not created:
        for key, value in kwargs.items():
            setattr(entry, key, value)
        entry.status = 'ACTIVE'
        entry.save()
    notify_donor(
        donor,
        template='LISTA_ATTESA',
        message=f'Sei stato inserito in lista d’attesa per la raccolta del {session.date:%d/%m/%Y} presso {session.center.name}. Ti avviseremo se si libera un posto.',
        email_subject='DonoFlow - Iscrizione in lista d’attesa',
    )
    return entry


def confirm_standby(session, donor, **kwargs):
    """Registra la disponibilità standby del donatore e aggiorna la lista d'attesa."""
    if not session.accepts_waitlist:
        raise DonoFlowError('Questa raccolta non accetta disponibilità standby.')
    standby, _ = StandbyAvailability.objects.update_or_create(
        donor=donor,
        session=session,
        defaults={
            'status': 'CONFIRMED',
            'last_confirmed_at': timezone.now(),
            **kwargs,
        },
    )
    WaitlistEntry.objects.filter(donor=donor, session=session).update(status='STANDBY_CONFIRMED')
    notify_donor(
        donor,
        template='STANDBY_CONFERMATO',
        message=f'Disponibilità standby confermata per il {session.date:%d/%m/%Y} presso {session.center.name}, dalle {standby.available_from:%H:%M} alle {standby.available_to:%H:%M}.',
        email_subject='DonoFlow - Disponibilità standby confermata',
        channel=standby.preferred_channel,
    )
    return standby


def is_time_range_compatible(entry, slot):
    """Verifica che l'orario dello slot rientri nella fascia preferita del donatore in lista."""
    hour = slot.time.hour + slot.time.minute / 60
    if entry.preferred_time_range == 'ANY':
        return True
    if entry.preferred_time_range == 'EARLY':
        return 7.5 <= hour < 9
    if entry.preferred_time_range == 'MID':
        return 9 <= hour < 10.5
    if entry.preferred_time_range == 'LATE':
        return 10.5 <= hour <= 12
    return True


def rank_standby_candidates(slot, limit=3):
    """Ranking greedy dei candidati standby per uno slot a rischio.

    Punteggio pesato: 40% velocità di arrivo (ETA), 20% posizione in lista,
    20% affidabilità storica del donatore, 10% compatibilità, 10% priorità operativa.
    Restituisce al massimo ``limit`` candidati ordinati per punteggio decrescente.
    """
    entries = WaitlistEntry.objects.select_related('donor').filter(
        session=slot.session,
        status__in=['ACTIVE', 'STANDBY_CONFIRMED', 'OFFER_SENT', 'ACCEPTED'],
    ).order_by('position')
    ranked = []
    for entry in entries:
        standby = StandbyAvailability.objects.filter(
            donor=entry.donor,
            session=slot.session,
            status='CONFIRMED',
            available_from__lte=slot.time,
            available_to__gte=slot.time,
        ).first()
        if not standby:
            continue
        eta = standby.max_arrival_minutes or entry.max_arrival_minutes
        if not is_time_range_compatible(entry, slot):
            continue
        time_score = max(0, 100 - eta * 3)
        order_score = max(0, 100 - (entry.position - 1) * 15)
        reliability_score = min(100, entry.donor.reliability_score)
        compatibility_score = 100
        operational_score = entry.priority_score
        total = (
            Decimal('0.40') * Decimal(time_score) +
            Decimal('0.20') * Decimal(order_score) +
            Decimal('0.20') * Decimal(reliability_score) +
            Decimal('0.10') * Decimal(compatibility_score) +
            Decimal('0.10') * Decimal(operational_score)
        )
        ranked.append({
            'entry': entry,
            'donor': entry.donor,
            'standby': standby,
            'eta': eta,
            'score': total.quantize(Decimal('0.01')),
        })
    ranked.sort(key=lambda item: (-item['score'], item['eta'], item['entry'].position))
    return ranked[:limit]


@transaction.atomic
def mark_slot_risk(slot, user=None):
    """Marca slot e prenotazione come "ritardo critico" e avvisa il responsabile in dashboard."""
    if slot.active_appointment is None or slot.active_appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
        raise DonoFlowError('Lo slot non ha una prenotazione attiva da segnalare.')
    slot.status = 'RISK'
    slot.save(update_fields=['status', 'updated_at'])
    appointment = slot.active_appointment
    if appointment:
        appointment.status = 'RISK'
        appointment.save(update_fields=['status', 'updated_at'])
        create_notification(
            appointment=appointment,
            channel='DASHBOARD',
            template='ALERT_RESPONSABILE',
            message=f'ATTENZIONE: slot {slot.time:%H:%M} senza check-in. Donatore: {appointment.donor}. Arrivo previsto: {slot.expected_arrival_time:%H:%M}.',
        )
    log_action(user, 'Slot marcato a rischio', slot)
    return appointment


@transaction.atomic
def activate_standby_for_slot(slot, user=None, limit=3, timeout_minutes=3):
    """Rende lo slot sostituibile e invia l'offerta urgente ai migliori candidati standby."""
    slot = Slot.objects.select_for_update().select_related('session__center').get(pk=slot.pk)
    if slot.status not in ['BOOKED', 'RISK', 'REPLACEABLE']:
        raise DonoFlowError('Lo standby si attiva solo su slot prenotati o a rischio.')
    slot.status = 'REPLACEABLE'
    slot.save(update_fields=['status', 'updated_at'])
    appointment = slot.active_appointment
    if appointment:
        appointment.status = 'REPLACEABLE'
        appointment.save(update_fields=['status', 'updated_at'])
    ranked = rank_standby_candidates(slot, limit=limit)
    offers = []
    for item in ranked:
        offer, _ = WaitlistOffer.objects.update_or_create(
            slot=slot,
            donor=item['donor'],
            defaults={
                'sent_at': timezone.now(),
                'expires_at': timezone.now() + timedelta(minutes=timeout_minutes),
                'response': 'PENDING',
                'estimated_arrival_minutes': item['eta'],
                'score': item['score'],
                'status': 'SENT',
            },
        )
        WaitlistEntry.objects.filter(donor=item['donor'], session=slot.session).update(status='OFFER_SENT')
        notify_donor(
            item['donor'],
            template='OFFERTA_URGENTE',
            message=(
                f'Si potrebbe liberare un posto alle {slot.time:%H:%M} presso {slot.session.center.name}. '
                f'Puoi arrivare entro {item["eta"]} minuti? Rispondi entro {timeout_minutes} minuti dalla tua dashboard.'
            ),
            email_subject=f'DonoFlow - Posto disponibile alle {slot.time:%H:%M}: rispondi subito',
        )
        offers.append(offer)
    log_action(user, 'Attivazione standby', slot, notes=f'Offerte create: {len(offers)}')
    return offers


def respond_to_offer(offer, response):
    """Registra la risposta del donatore a un'offerta urgente (ACCEPT/LATE/DECLINE)."""
    offer.refresh_from_db()
    if offer.status != 'SENT':
        raise DonoFlowError('Questa offerta non è più attiva.')
    if offer.expires_at and offer.expires_at < timezone.now():
        # Salvato fuori da ogni transazione: l'errore sollevato subito dopo
        # non deve annullare il passaggio a EXPIRED.
        offer.status = 'EXPIRED'
        offer.save(update_fields=['status', 'updated_at'])
        raise DonoFlowError('Offerta scaduta: il tempo per rispondere è terminato.')
    with transaction.atomic():
        return _apply_offer_response(offer, response)


def _apply_offer_response(offer, response):
    offer.response = response
    if response == 'ACCEPT':
        offer.status = 'ACCEPTED'
        WaitlistEntry.objects.filter(donor=offer.donor, session=offer.slot.session).update(status='ACCEPTED')
    elif response == 'DECLINE':
        offer.status = 'REJECTED'
        WaitlistEntry.objects.filter(donor=offer.donor, session=offer.slot.session).update(status='REJECTED')
    elif response == 'LATE':
        offer.status = 'ACCEPTED'
    offer.save(update_fields=['response', 'status', 'updated_at'])
    return offer


@transaction.atomic
def assign_standby_offer(offer, user=None):
    """Il responsabile conferma il sostituto: sostituisce la vecchia prenotazione,
    crea quella nuova, chiude le altre offerte e comunica l'esito a tutti."""
    slot = Slot.objects.select_for_update().get(pk=offer.slot.pk)
    offer.refresh_from_db()
    # Un'assegnazione chiude (CANCELLED) le altre offerte dello stesso giro, quindi
    # il solo controllo su ACCEPTED impedisce la doppia assegnazione senza bloccare
    # un secondo giro di standby sullo stesso slot.
    if offer.status != 'ACCEPTED':
        raise DonoFlowError('Si può assegnare solo un’offerta accettata dal donatore.')
    if slot.status not in ['RISK', 'REPLACEABLE']:
        raise DonoFlowError('Lo slot non è più sostituibile (il donatore potrebbe essere arrivato).')
    if any(a.is_checked_in for a in slot.appointments.filter(status__in=ACTIVE_APPOINTMENT_STATUSES)):
        raise DonoFlowError('Il donatore prenotato ha già fatto il check-in: sostituzione non necessaria.')
    donor = offer.donor
    old_appointments = slot.appointments.filter(status__in=ACTIVE_APPOINTMENT_STATUSES)
    for appointment in old_appointments:
        appointment.status = 'SUBSTITUTED'
        appointment.save(update_fields=['status', 'updated_at'])
    appointment = Appointment.objects.create(
        donor=donor,
        slot=slot,
        status='CONFIRMED',
        confirmed_at=timezone.now(),
        source='STANDBY',
    )
    CheckIn.objects.create(appointment=appointment, expected_arrival_time=slot.expected_arrival_time)
    slot.donor = donor
    slot.status = 'BOOKED'
    slot.save(update_fields=['donor', 'status', 'updated_at'])
    offer.status = 'ASSIGNED'
    offer.save(update_fields=['status', 'updated_at'])
    WaitlistEntry.objects.filter(donor=donor, session=slot.session).update(status='CONVERTED')
    others = list(slot.offers.exclude(pk=offer.pk).filter(status__in=['SENT', 'ACCEPTED']).select_related('donor'))
    slot.offers.filter(pk__in=[o.pk for o in others]).update(status='CANCELLED')
    for other in others:
        notify_donor(
            other.donor,
            template='POSTO_ASSEGNATO_ALTRO',
            message='Grazie per la disponibilità. Il posto è stato assegnato a un altro donatore. Resti in standby per eventuali altri posti.',
            email_subject='DonoFlow - Posto assegnato a un altro donatore',
        )
    notify_appointment(
        appointment,
        template='CONFERMA_LAST_MINUTE',
        message=f'Posto confermato per te. Presentati presso {slot.session.center.name} entro le ore {slot.time:%H:%M}.',
        email_subject='DonoFlow - Posto confermato last-minute',
        email_intro='Il responsabile ha confermato un posto per te come sostituto last-minute.',
    )
    log_action(user, 'Assegnazione standby', offer, notes=f'Slot {slot.pk} assegnato a {donor}')
    return appointment


def send_appointment_status_email(appointment, user=None):
    """Invia manualmente al donatore un riepilogo email dello stato prenotazione."""
    sent = send_informative_email(
        appointment.donor,
        'DonoFlow - Riepilogo prenotazione',
        appointment_email_body(
            appointment,
            f'Riepilogo aggiornato della tua prenotazione. Stato attuale: {appointment.get_status_display()}.'
        ),
        appointment=appointment,
        template='EMAIL_RIEPILOGO_PRENOTAZIONE',
        defer=False,
    )
    log_action(user, 'Invio email riepilogo prenotazione', appointment, notes=dict(Notification.STATUS_CHOICES).get(sent, sent))
    return sent


@transaction.atomic
def mark_checkin(appointment, user=None):
    """Registra l'arrivo del donatore e riconferma la prenotazione."""
    require_status(appointment, ACTIVE_APPOINTMENT_STATUSES, 'registrare il check-in')
    checkin, _ = CheckIn.objects.get_or_create(appointment=appointment, defaults={'expected_arrival_time': appointment.slot.expected_arrival_time})
    checkin.actual_checkin_time = timezone.now()
    checkin.status = 'CHECKED_IN'
    checkin.operator = user if getattr(user, 'is_authenticated', False) else None
    checkin.save(update_fields=['actual_checkin_time', 'status', 'operator', 'updated_at'])
    appointment.status = 'RECONFIRMED'
    appointment.reconfirmed_at = timezone.now()
    appointment.save(update_fields=['status', 'reconfirmed_at', 'updated_at'])
    # Il donatore è arrivato: lo slot torna "prenotato" e le offerte standby aperte decadono.
    slot = appointment.slot
    if slot.status in ['RISK', 'REPLACEABLE']:
        slot.status = 'BOOKED'
        slot.save(update_fields=['status', 'updated_at'])
    slot.offers.filter(status__in=['SENT', 'ACCEPTED']).update(status='CANCELLED')
    log_action(user, 'Check-in registrato', appointment)
    return checkin


@transaction.atomic
def mark_no_show(appointment, user=None):
    """Mancata presentazione: slot perso e penalità di affidabilità al donatore (-10)."""
    # La guardia impedisce anche la doppia penalità da doppio click.
    require_status(appointment, ACTIVE_APPOINTMENT_STATUSES, 'registrare il no-show')
    appointment.status = 'NO_SHOW'
    appointment.save(update_fields=['status', 'updated_at'])
    slot = appointment.slot
    slot.status = 'LOST'
    slot.save(update_fields=['status', 'updated_at'])
    checkin, _ = CheckIn.objects.get_or_create(appointment=appointment, defaults={'expected_arrival_time': slot.expected_arrival_time})
    checkin.status = 'NO_SHOW'
    checkin.operator = user if getattr(user, 'is_authenticated', False) else None
    checkin.save(update_fields=['status', 'operator', 'updated_at'])
    appointment.donor.reliability_score = max(0, appointment.donor.reliability_score - 10)
    appointment.donor.save(update_fields=['reliability_score', 'updated_at'])
    notify_appointment(
        appointment,
        template='NO_SHOW',
        message=f'La prenotazione del {slot.session.date:%d/%m/%Y} alle {slot.time:%H:%M} è stata registrata come no-show.',
        email_subject='DonoFlow - Mancata presentazione registrata',
        email_intro='La prenotazione è stata registrata come mancata presentazione. Per chiarimenti contatta il responsabile della raccolta.',
    )
    log_action(user, 'No-show registrato', appointment)
    return appointment


@transaction.atomic
def confirm_appointment_by_operator(appointment, user=None):
    """Conferma (o ripristino) manuale della prenotazione da parte dell'operatore."""
    if appointment.status in ['COMPLETED', 'NOT_DONE', 'NO_SHOW', 'SUBSTITUTED']:
        raise DonoFlowError(f'Impossibile confermare: la prenotazione è "{appointment.get_status_display()}".')
    # Rilettura con lock: l'oggetto in memoria può avere uno stato dello slot superato.
    slot = Slot.objects.select_for_update().select_related('session').get(pk=appointment.slot_id)
    appointment.slot = slot
    if slot.session.status == 'CANCELLED':
        raise DonoFlowError('La raccolta è annullata.')
    if slot.appointments.exclude(pk=appointment.pk).filter(status__in=ACTIVE_APPOINTMENT_STATUSES).exists():
        raise DonoFlowError('Lo slot è già occupato da un’altra prenotazione attiva.')
    if not appointment.is_active and slot.status != 'FREE':
        # Ripristino di una prenotazione annullata: solo se lo slot è davvero libero
        # (altrimenti si sovrascriverebbe, ad esempio, una donazione già completata).
        raise DonoFlowError('Lo slot non è più libero: impossibile ripristinare la prenotazione.')
    if Appointment.objects.filter(donor=appointment.donor, slot__session=slot.session,
                                  status__in=ACTIVE_APPOINTMENT_STATUSES).exclude(pk=appointment.pk).exists():
        raise DonoFlowError('Il donatore ha già un’altra prenotazione attiva in questa raccolta.')
    appointment.status = 'CONFIRMED'
    appointment.confirmed_at = timezone.now()
    appointment.cancelled_at = None
    appointment.cancellation_reason = ''
    appointment.save(update_fields=['status', 'confirmed_at', 'cancelled_at', 'cancellation_reason', 'updated_at'])
    slot = appointment.slot
    slot.status = 'BOOKED'
    slot.donor = appointment.donor
    slot.save(update_fields=['status', 'donor', 'updated_at'])
    CheckIn.objects.get_or_create(appointment=appointment, defaults={'expected_arrival_time': slot.expected_arrival_time})
    notify_appointment(
        appointment,
        template='PRENOTAZIONE_CONFERMATA_OPERATORE',
        message=f'La tua prenotazione del {slot.session.date:%d/%m/%Y} alle {slot.time:%H:%M} è stata confermata dall’operatore.',
        email_subject='DonoFlow - Prenotazione confermata',
        email_intro='La tua prenotazione è stata confermata dall’operatore.',
    )
    update_session_status(slot.session)
    log_action(user, 'Conferma prenotazione da gestione', appointment)
    return appointment


def cancel_appointment_by_operator(appointment, user=None, reason=''):
    """Annullamento deciso dall'operatore: identico al flusso donatore, cambia solo la comunicazione."""
    slot = appointment.slot
    return _cancel_appointment(
        appointment,
        status='CANCELLED_BY_OPERATOR',
        template='PRENOTAZIONE_ANNULLATA_OPERATORE',
        message=f'La tua prenotazione del {slot.session.date:%d/%m/%Y} alle {slot.time:%H:%M} è stata annullata dall’operatore.',
        email_subject='DonoFlow - Prenotazione annullata',
        email_intro='La tua prenotazione è stata annullata dall’operatore.',
        log_message='Annullamento prenotazione da gestione',
        user=user,
        reason=reason,
    )


@transaction.atomic
def mark_donation_completed(appointment, user=None, notes=''):
    """Registra la donazione come effettuata: esito, check-in implicito e data ultima donazione."""
    require_status(appointment, ACTIVE_APPOINTMENT_STATUSES, 'registrare la donazione')
    appointment.status = 'COMPLETED'
    appointment.save(update_fields=['status', 'updated_at'])
    slot = appointment.slot
    slot.status = 'COMPLETED'
    slot.donor = appointment.donor
    slot.save(update_fields=['status', 'donor', 'updated_at'])
    checkin, _ = CheckIn.objects.get_or_create(appointment=appointment, defaults={'expected_arrival_time': slot.expected_arrival_time})
    if checkin.status != 'CHECKED_IN':
        checkin.status = 'CHECKED_IN'
        checkin.actual_checkin_time = timezone.now()
        checkin.operator = user if getattr(user, 'is_authenticated', False) else None
        checkin.save(update_fields=['status', 'actual_checkin_time', 'operator', 'updated_at'])
    DonationOutcome.objects.update_or_create(
        appointment=appointment,
        defaults={
            'outcome': 'COMPLETED',
            'checkin_at': checkin.actual_checkin_time,
            'completed_at': timezone.now(),
            'notes': notes,
        },
    )
    appointment.donor.last_donation_date = slot.session.date
    appointment.donor.save(update_fields=['last_donation_date', 'updated_at'])
    notify_appointment(
        appointment,
        template='DONAZIONE_EFFETTUATA',
        message=f'Donazione registrata come effettuata per il {slot.session.date:%d/%m/%Y}. Grazie per il tuo contributo.',
        email_subject='DonoFlow - Donazione effettuata',
        email_intro='La tua donazione risulta registrata come effettuata. Grazie per il tuo contributo.',
    )
    log_action(user, 'Donazione effettuata', appointment, notes=notes)
    return appointment


@transaction.atomic
def mark_donation_not_done(appointment, user=None, notes=''):
    """Il donatore si è presentato ma la donazione non è avvenuta (es. non idoneo)."""
    require_status(appointment, ACTIVE_APPOINTMENT_STATUSES, 'registrare l’esito')
    appointment.status = 'NOT_DONE'
    appointment.save(update_fields=['status', 'updated_at'])
    slot = appointment.slot
    slot.status = 'LOST'
    slot.save(update_fields=['status', 'updated_at'])
    DonationOutcome.objects.update_or_create(
        appointment=appointment,
        defaults={
            'outcome': 'NOT_DONE',
            'checkin_at': getattr(getattr(appointment, 'checkin', None), 'actual_checkin_time', None),
            'completed_at': timezone.now(),
            'notes': notes,
        },
    )
    notify_appointment(
        appointment,
        template='DONAZIONE_NON_EFFETTUATA',
        message=f'La donazione del {slot.session.date:%d/%m/%Y} è stata registrata come non effettuata.',
        email_subject='DonoFlow - Donazione non effettuata',
        email_intro='La donazione è stata registrata come non effettuata.',
        email_extra=(f'\nNote: {notes}\n' if notes else ''),
    )
    log_action(user, 'Donazione non effettuata', appointment, notes=notes)
    return appointment
