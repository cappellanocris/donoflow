"""Modelli di dominio di DonoFlow.

Struttura principale:
- ``Donor`` / ``DonationCenter``: anagrafiche di donatori e sedi.
- ``DonationSession`` / ``Slot``: una giornata di raccolta e i suoi slot orari.
- ``Appointment`` / ``CheckIn`` / ``DonationOutcome``: ciclo di vita della prenotazione.
- ``WaitlistEntry`` / ``StandbyAvailability`` / ``WaitlistOffer``: recupero slot a rischio.
- ``Notification`` / ``AuditLog``: comunicazioni simulate e tracciamento azioni.
- ``CmsPage`` / ``FooterSection``: contenuti editoriali gestibili da admin.
"""

from datetime import time

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Base astratta: aggiunge i timestamp di creazione/aggiornamento a ogni modello."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Donor(TimeStampedModel):
    STATUS_CHOICES = [
        ('ACTIVE', 'Attivo'),
        ('SUSPENDED', 'Sospeso'),
        ('INACTIVE', 'Non attivo'),
    ]
    CHANNEL_CHOICES = [
        ('EMAIL', 'Email'),
        ('SMS', 'SMS'),
        ('WHATSAPP', 'WhatsApp'),
    ]
    BLOOD_GROUP_CHOICES = [
        ('', 'Non indicato'),
        ('0-', '0-'), ('0+', '0+'), ('A-', 'A-'), ('A+', 'A+'),
        ('B-', 'B-'), ('B+', 'B+'), ('AB-', 'AB-'), ('AB+', 'AB+'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='donor_profile', null=True, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    fiscal_code = models.CharField(max_length=16, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES, blank=True)
    donor_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    preferred_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='WHATSAPP')
    last_donation_date = models.DateField(null=True, blank=True)
    reliability_score = models.PositiveSmallIntegerField(default=80, help_text='Da 0 a 100')

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Donatore'
        verbose_name_plural = 'Donatori'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class DonationCenter(TimeStampedModel):
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['city', 'name']
        verbose_name = 'Sede raccolta'
        verbose_name_plural = 'Sedi raccolta'

    def __str__(self):
        return f'{self.name} - {self.city}'


class DonationSession(TimeStampedModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Bozza'),
        ('OPEN', 'Aperta'),
        ('FULL', 'Completa'),
        ('CLOSED', 'Chiusa'),
        ('CANCELLED', 'Annullata'),
    ]
    DONATION_TYPE_CHOICES = [
        ('WHOLE_BLOOD', 'Sangue intero'),
        ('PLASMA', 'Plasma'),
        ('PLATELETS', 'Piastrine'),
    ]

    center = models.ForeignKey(DonationCenter, on_delete=models.PROTECT, related_name='sessions')
    date = models.DateField()
    # Default come oggetti time: le stringhe rompevano generate_slots_for_session
    # quando la raccolta veniva creata da codice (seed, script, shell).
    start_time = models.TimeField(default=time(7, 30))
    end_time = models.TimeField(default=time(12, 0))
    slot_duration_minutes = models.PositiveIntegerField(default=15, help_text='Durata di ogni slot in minuti')
    expected_arrival_minutes = models.PositiveIntegerField(default=15, help_text='Minuti di anticipo richiesti per il check-in')
    donation_type = models.CharField(max_length=30, choices=DONATION_TYPE_CHOICES, default='WHOLE_BLOOD')
    title = models.CharField(max_length=180, blank=True, help_text='Titolo pubblico della giornata di raccolta')
    featured_image = models.ImageField(upload_to='session_images/', null=True, blank=True, help_text='Immagine in evidenza mostrata nella scheda pubblica')
    public_description = models.TextField(blank=True, help_text='Descrizione pubblica della raccolta')
    public_instructions = models.TextField(blank=True, help_text='Indicazioni per i donatori: documenti, orari, parcheggio, contatti')
    capacity = models.PositiveIntegerField(default=18)
    public_slots = models.PositiveIntegerField(default=18)
    reserved_slots = models.PositiveIntegerField(default=0)
    standby_slots = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date', 'start_time']
        verbose_name = 'Raccolta'
        verbose_name_plural = 'Raccolte'

    def __str__(self):
        return f'{self.center.name} - {self.date:%d/%m/%Y}'

    # --- Conteggi di comodo usati da template e service layer -------------
    def slots_count(self):
        return self.slots.count()

    def booked_count(self):
        return self.slots.filter(status__in=Slot.OCCUPIED_STATUSES).count()

    def available_count(self):
        return self.slots.filter(status='FREE').count()

    def get_absolute_url(self):
        return reverse('session_detail', args=[self.pk])

    # Stati in cui la raccolta è visibile al pubblico e accetta iscrizioni.
    PUBLIC_STATUSES = ['OPEN', 'FULL']

    @property
    def is_upcoming(self):
        return self.date >= timezone.localdate()

    @property
    def accepts_bookings(self):
        """Unica regola di prenotabilità: raccolta aperta e non ancora passata."""
        return self.status == 'OPEN' and self.is_upcoming

    @property
    def accepts_waitlist(self):
        """Lista d'attesa e standby hanno senso solo per raccolte pubbliche e future."""
        return self.status in self.PUBLIC_STATUSES and self.is_upcoming


class Slot(TimeStampedModel):
    STATUS_CHOICES = [
        ('FREE', 'Libero'),
        ('LOCKED', 'Bloccato'),
        ('BOOKED', 'Prenotato'),
        ('RISK', 'A rischio'),
        ('REPLACEABLE', 'Sostituibile'),
        ('COMPLETED', 'Completato'),
        ('LOST', 'Perso'),
        ('CANCELLED', 'Annullato'),
    ]
    DONATION_TYPE_CHOICES = DonationSession.DONATION_TYPE_CHOICES

    # Stati che contano come "slot occupato" nei conteggi di riepilogo.
    OCCUPIED_STATUSES = ['BOOKED', 'RISK', 'REPLACEABLE', 'COMPLETED']

    session = models.ForeignKey(DonationSession, on_delete=models.CASCADE, related_name='slots')
    time = models.TimeField()
    expected_arrival_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=15)
    donation_type = models.CharField(max_length=30, choices=DONATION_TYPE_CHOICES, default='WHOLE_BLOOD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='FREE')
    donor = models.ForeignKey(Donor, on_delete=models.SET_NULL, null=True, blank=True, related_name='slots')
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['session__date', 'time']
        unique_together = [('session', 'time')]
        verbose_name = 'Slot'
        verbose_name_plural = 'Slot'

    def __str__(self):
        return f'{self.session.date:%d/%m/%Y} {self.time:%H:%M}'

    @property
    def active_appointment(self):
        """Prenotazione più recente ancora rilevante per lo slot (esclude annullate/sostituite)."""
        return self.appointments.exclude(
            status__in=['CANCELLED_BY_DONOR', 'CANCELLED_BY_OPERATOR', 'SUBSTITUTED'],
        ).order_by('-created_at').first()


class Appointment(TimeStampedModel):
    STATUS_CHOICES = [
        ('CREATED', 'Creata'),
        ('CONFIRMED', 'Confermata'),
        ('TO_RECONFIRM', 'Da riconfermare'),
        ('RECONFIRMED', 'Riconfermata'),
        ('RISK', 'In ritardo critico'),
        ('REPLACEABLE', 'Sostituibile'),
        ('SUBSTITUTED', 'Sostituita'),
        ('CANCELLED_BY_DONOR', 'Annullata dal donatore'),
        ('CANCELLED_BY_OPERATOR', 'Annullata da operatore'),
        ('NO_SHOW', 'No-show'),
        ('COMPLETED', 'Completata'),
        ('NOT_DONE', 'Non effettuata'),
    ]
    SOURCE_CHOICES = [
        ('WEB', 'Web'),
        ('OPERATOR', 'Operatore'),
        ('STANDBY', 'Standby'),
    ]

    # Stati "vivi": la prenotazione occupa ancora lo slot.
    ACTIVE_STATUSES = ['CREATED', 'CONFIRMED', 'TO_RECONFIRM', 'RECONFIRMED', 'RISK', 'REPLACEABLE']
    # Stati terminali: la prenotazione non evolve più.
    FINAL_STATUSES = ['CANCELLED_BY_DONOR', 'CANCELLED_BY_OPERATOR', 'SUBSTITUTED', 'NO_SHOW', 'COMPLETED', 'NOT_DONE']

    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name='appointments')
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name='appointments')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='CONFIRMED')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    reconfirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='WEB')

    class Meta:
        ordering = ['slot__session__date', 'slot__time']
        verbose_name = 'Prenotazione'
        verbose_name_plural = 'Prenotazioni'

    def __str__(self):
        return f'{self.donor} - {self.slot}'

    @property
    def is_active(self):
        """True se la prenotazione occupa ancora lo slot e accetta azioni operative."""
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_checked_in(self):
        checkin = getattr(self, 'checkin', None)
        return bool(checkin and checkin.status == 'CHECKED_IN')

    @classmethod
    def next_for_donor(cls, donor):
        """Prossima prenotazione attiva del donatore (da oggi in poi), o None."""
        return cls.objects.filter(
            donor=donor,
            slot__session__date__gte=timezone.localdate(),
            status__in=cls.ACTIVE_STATUSES,
        ).select_related('slot__session__center').order_by('slot__session__date', 'slot__time').first()


class WaitlistEntry(TimeStampedModel):
    STATUS_CHOICES = [
        ('ACTIVE', 'Attiva'),
        ('STANDBY_REQUESTED', 'Standby richiesto'),
        ('STANDBY_CONFIRMED', 'Standby confermato'),
        ('OFFER_SENT', 'Offerta inviata'),
        ('ACCEPTED', 'Accettata'),
        ('REJECTED', 'Rifiutata'),
        ('EXPIRED', 'Scaduta'),
        ('CONVERTED', 'Convertita'),
        ('CANCELLED', 'Annullata'),
    ]
    TIME_RANGE_CHOICES = [
        ('ANY', 'Qualsiasi orario'),
        ('EARLY', '07:30-09:00'),
        ('MID', '09:00-10:30'),
        ('LATE', '10:30-12:00'),
    ]

    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='waitlist_entries')
    session = models.ForeignKey(DonationSession, on_delete=models.CASCADE, related_name='waitlist_entries')
    center = models.ForeignKey(DonationCenter, on_delete=models.PROTECT, related_name='waitlist_entries')
    donation_type = models.CharField(max_length=30, choices=DonationSession.DONATION_TYPE_CHOICES, default='WHOLE_BLOOD')
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    preferred_time_range = models.CharField(max_length=20, choices=TIME_RANGE_CHOICES, default='ANY')
    minimum_notice_minutes = models.PositiveIntegerField(default=15)
    max_arrival_minutes = models.PositiveIntegerField(default=30)
    position = models.PositiveIntegerField(default=1)
    priority_score = models.PositiveSmallIntegerField(default=50)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='ACTIVE')

    class Meta:
        ordering = ['session', 'position']
        unique_together = [('donor', 'session')]
        verbose_name = 'Lista d’attesa'
        verbose_name_plural = 'Liste d’attesa'

    def __str__(self):
        return f'{self.position}. {self.donor} - {self.session}'


class StandbyAvailability(TimeStampedModel):
    STATUS_CHOICES = [
        ('REQUESTED', 'Richiesta'),
        ('CONFIRMED', 'Confermata'),
        ('DECLINED', 'Rifiutata'),
        ('EXPIRED', 'Scaduta'),
    ]

    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='standby_availabilities')
    session = models.ForeignKey(DonationSession, on_delete=models.CASCADE, related_name='standby_availabilities')
    available_from = models.TimeField(default=time(7, 30))
    available_to = models.TimeField(default=time(12, 0))
    minimum_notice_minutes = models.PositiveIntegerField(default=15)
    max_arrival_minutes = models.PositiveIntegerField(default=30)
    preferred_channel = models.CharField(max_length=20, choices=Donor.CHANNEL_CHOICES, default='WHATSAPP')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='REQUESTED')
    last_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['session', 'available_from']
        unique_together = [('donor', 'session')]
        verbose_name = 'Disponibilità standby'
        verbose_name_plural = 'Disponibilità standby'

    def __str__(self):
        return f'{self.donor} standby {self.session}'


class WaitlistOffer(TimeStampedModel):
    RESPONSE_CHOICES = [
        ('PENDING', 'In attesa'),
        ('ACCEPT', 'Accetta'),
        ('LATE', 'Arriva più tardi'),
        ('DECLINE', 'Rifiuta'),
    ]
    STATUS_CHOICES = [
        ('SENT', 'Inviata'),
        ('ACCEPTED', 'Accettata'),
        ('REJECTED', 'Rifiutata'),
        ('EXPIRED', 'Scaduta'),
        ('SELECTED', 'Selezionata'),
        ('ASSIGNED', 'Assegnata'),
        ('CANCELLED', 'Annullata'),
    ]

    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name='offers')
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='offers')
    sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    response = models.CharField(max_length=20, choices=RESPONSE_CHOICES, default='PENDING')
    estimated_arrival_minutes = models.PositiveIntegerField(default=15)
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SENT')

    class Meta:
        ordering = ['-score', 'estimated_arrival_minutes', 'created_at']
        unique_together = [('slot', 'donor')]
        verbose_name = 'Offerta standby'
        verbose_name_plural = 'Offerte standby'

    def __str__(self):
        return f'Offerta {self.slot} -> {self.donor}'

    @property
    def is_expired(self):
        """Offerta ancora "inviata" ma oltre il tempo di risposta."""
        return self.status == 'SENT' and self.expires_at is not None and self.expires_at < timezone.now()


class CheckIn(TimeStampedModel):
    STATUS_CHOICES = [
        ('EXPECTED', 'Atteso'),
        ('CHECKED_IN', 'Arrivato'),
        ('LATE', 'In ritardo'),
        ('NO_SHOW', 'No-show'),
    ]

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='checkin')
    expected_arrival_time = models.TimeField()
    actual_checkin_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='EXPECTED')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='checkins')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['appointment__slot__time']
        verbose_name = 'Check-in'
        verbose_name_plural = 'Check-in'

    def __str__(self):
        return f'{self.appointment} - {self.status}'


class Notification(TimeStampedModel):
    CHANNEL_CHOICES = Donor.CHANNEL_CHOICES + [('DASHBOARD', 'Dashboard')]
    STATUS_CHOICES = [
        ('QUEUED', 'In coda'),
        ('SENT', 'Inviata'),
        ('READ', 'Letta'),
        ('FAILED', 'Fallita'),
        ('SIMULATED', 'Simulata'),
    ]

    donor = models.ForeignKey(Donor, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='DASHBOARD')
    template = models.CharField(max_length=80)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SIMULATED')
    sent_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Notifica'
        verbose_name_plural = 'Notifiche'

    def __str__(self):
        return f'{self.template} - {self.status}'


class DonationOutcome(TimeStampedModel):
    OUTCOME_CHOICES = [
        ('COMPLETED', 'Donazione completata'),
        ('NOT_ELIGIBLE', 'Non idoneo in sede'),
        ('NOT_DONE', 'Non effettuata'),
    ]

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='outcome')
    outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES)
    checkin_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Esito donazione'
        verbose_name_plural = 'Esiti donazione'

    def __str__(self):
        return f'{self.appointment} - {self.outcome}'


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit log'
        verbose_name_plural = 'Audit log'

    def __str__(self):
        return f'{self.timestamp:%d/%m/%Y %H:%M} - {self.action}'



class CmsPage(TimeStampedModel):
    title = models.CharField(max_length=180, verbose_name='Titolo')
    slug = models.SlugField(max_length=180, unique=True, verbose_name='Slug URL')
    menu_label = models.CharField(max_length=80, blank=True, verbose_name='Etichetta menu')
    summary = models.CharField(max_length=300, blank=True, verbose_name='Breve descrizione')
    content = models.TextField(
        verbose_name='Contenuto HTML',
        help_text='Puoi usare HTML semplice: titoli, paragrafi, elenchi e link.',
    )
    is_published = models.BooleanField(default=True, verbose_name='Pubblicata')
    show_in_navigation = models.BooleanField(default=False, verbose_name='Mostra nel menu principale')
    show_in_footer = models.BooleanField(default=True, verbose_name='Mostra nel footer')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Ordine')

    class Meta:
        ordering = ['sort_order', 'title']
        verbose_name = 'Pagina informativa'
        verbose_name_plural = 'Pagine informative'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        named_pages = {
            'come-funziona': 'how_it_works',
            'privacy': 'privacy_page',
            'info': 'info_page',
        }
        if self.slug in named_pages:
            return reverse(named_pages[self.slug])
        return reverse('public_page', kwargs={'slug': self.slug})


class FooterSection(TimeStampedModel):
    KEY_CHOICES = [
        ('ABOUT', 'Presentazione'),
        ('LINKS', 'Link utili'),
        ('CONTACTS', 'Contatti'),
    ]

    key = models.CharField(max_length=20, choices=KEY_CHOICES, unique=True, verbose_name='Sezione')
    title = models.CharField(max_length=100, verbose_name='Titolo')
    content = models.TextField(
        verbose_name='Contenuto HTML',
        help_text='Puoi usare HTML semplice, inclusi paragrafi, elenchi e link.',
    )
    is_active = models.BooleanField(default=True, verbose_name='Visibile nel footer')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Ordine')

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Sezione footer'
        verbose_name_plural = 'Sezioni footer'

    def __str__(self):
        return self.title
