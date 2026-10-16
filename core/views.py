"""View di DonoFlow.

Le view sono volutamente sottili: validano la richiesta, delegano al service layer
(`core.services`) e mostrano un messaggio all'utente. Le decine di azioni operative
su prenotazioni/slot/offerte sono generate da piccole factory (vedi in fondo al
file) per evitare duplicazione: ogni azione differisce solo per funzione di
servizio, messaggio e pagina di ritorno.
"""

from django.contrib import messages
from django.contrib.auth import login
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CmsPageForm,
    DonationCenterForm,
    DonorProfileForm,
    DonorRegistrationForm,
    FooterSectionForm,
    SessionCreateForm,
    StandbyAvailabilityForm,
    WaitlistForm,
)
from .models import (
    Appointment,
    CmsPage,
    DonationCenter,
    DonationSession,
    Donor,
    FooterSection,
    Notification,
    Slot,
    StandbyAvailability,
    WaitlistEntry,
    WaitlistOffer,
)
from .services import (
    DonoFlowError,
    activate_standby_for_slot,
    assign_standby_offer,
    book_slot,
    cancel_appointment,
    cancel_appointment_by_operator,
    confirm_appointment_by_operator,
    confirm_standby,
    create_waitlist_entry,
    generate_slots_for_session,
    mark_checkin,
    mark_donation_completed,
    mark_donation_not_done,
    mark_no_show,
    mark_slot_risk,
    respond_to_offer,
    send_appointment_status_email,
)

MONTHS_IT = [
    (1, 'Gennaio'), (2, 'Febbraio'), (3, 'Marzo'), (4, 'Aprile'),
    (5, 'Maggio'), (6, 'Giugno'), (7, 'Luglio'), (8, 'Agosto'),
    (9, 'Settembre'), (10, 'Ottobre'), (11, 'Novembre'), (12, 'Dicembre'),
]


# ---------------------------------------------------------------------------
# Permessi e helper condivisi
# ---------------------------------------------------------------------------

def is_operator(user):
    """Operatore = staff, superuser o membro dei gruppi 'operatori'/'responsabili'."""
    return user.is_staff or user.is_superuser or user.groups.filter(name__in=['operatori', 'responsabili']).exists()


def is_admin_user(user):
    return user.is_staff or user.is_superuser


def user_passes_test(test):
    """Come il decoratore Django, ma chi è già autenticato e non ha i permessi
    riceve un 403 esplicito invece di essere rimandato al login (loop confuso)."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not test(request.user):
                raise PermissionDenied('Non hai i permessi per accedere a questa sezione.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def run_service(request, func, *args, **kwargs):
    """Esegue un'azione di servizio; se lo stato non la consente mostra l'errore.

    Restituisce il risultato del servizio, oppure None se l'azione è stata rifiutata.
    """
    try:
        return func(*args, **kwargs)
    except DonoFlowError as exc:
        messages.error(request, str(exc))
        return None


def get_donor_or_raise(user):
    """Profilo donatore dell'utente autenticato, o 403 se l'account non ne ha uno."""
    try:
        return user.donor_profile
    except Donor.DoesNotExist:
        raise PermissionDenied('Questo account non è collegato a un profilo donatore.')


def _handle_model_form(request, form_class, template, redirect_name, *,
                       instance=None, success_message='Salvataggio completato.',
                       extra_context=None, with_files=False):
    """Gestione standard di un ModelForm (create/update): valida, salva, redirige.

    ``success_message`` può contenere ``{obj}``, sostituito con l'istanza salvata.
    """
    if request.method == 'POST':
        form = form_class(request.POST, request.FILES if with_files else None, instance=instance)
        if form.is_valid():
            obj = form.save()
            messages.success(request, success_message.format(obj=obj))
            return redirect(redirect_name), obj
    else:
        form = form_class(instance=instance)
    context = {'form': form, **(extra_context or {})}
    return render(request, template, context), None


# ---------------------------------------------------------------------------
# Pagine pubbliche
# ---------------------------------------------------------------------------

def home(request):
    """Homepage: prossime raccolte aperte e, per il donatore loggato, la sua prossima prenotazione."""
    today = timezone.localdate()
    sessions_qs = DonationSession.objects.filter(
        status__in=['OPEN', 'FULL'], date__gte=today,
    ).select_related('center').order_by('date', 'start_time')

    next_appointment = None
    if request.user.is_authenticated and not is_operator(request.user):
        try:
            next_appointment = Appointment.next_for_donor(request.user.donor_profile)
        except Donor.DoesNotExist:
            pass

    return render(request, 'core/home.html', {
        'sessions': sessions_qs[:4],
        'next_session': sessions_qs.first(),
        'next_appointment': next_appointment,
    })


def public_page(request, slug):
    """Pagina CMS pubblica (come funziona, privacy, ecc.)."""
    page = get_object_or_404(CmsPage, slug=slug, is_published=True)
    return render(request, 'core/public_page.html', {'page': page})


def sessions_list(request):
    """Elenco raccolte future prenotabili, con filtri per sede, mese e anno."""
    today = timezone.localdate()
    base_sessions = DonationSession.objects.select_related('center').prefetch_related('slots').filter(
        status__in=['OPEN', 'FULL'], date__gte=today,
    )

    # Opzioni filtro calcolate sulle raccolte effettivamente disponibili.
    available_centers = DonationCenter.objects.filter(
        sessions__in=base_sessions, active=True,
    ).distinct().order_by('city', 'name')
    available_years = list(
        base_sessions.order_by('date__year').values_list('date__year', flat=True).distinct()
    )

    selected_center = request.GET.get('center', '').strip()
    selected_month = request.GET.get('month', '').strip()
    selected_year = request.GET.get('year', '').strip()

    sessions = base_sessions
    if selected_center.isdigit():
        sessions = sessions.filter(center_id=int(selected_center))
    if selected_month.isdigit() and 1 <= int(selected_month) <= 12:
        sessions = sessions.filter(date__month=int(selected_month))
    if selected_year.isdigit():
        sessions = sessions.filter(date__year=int(selected_year))

    return render(request, 'core/sessions_list.html', {
        'sessions': sessions.order_by('date', 'start_time'),
        'centers': available_centers,
        'months': MONTHS_IT,
        'years': available_years,
        'selected_center': selected_center,
        'selected_month': selected_month,
        'selected_year': selected_year,
    })


def session_detail(request, pk):
    """Scheda pubblica della raccolta: slot prenotabili e stato del donatore (lista/standby)."""
    session = get_object_or_404(DonationSession.objects.select_related('center'), pk=pk)
    if session.status == 'DRAFT' and not is_operator(request.user):
        raise Http404('Raccolta non pubblicata.')
    user_donor = user_waitlist = user_standby = None
    if request.user.is_authenticated and not is_operator(request.user):
        try:
            user_donor = request.user.donor_profile
            user_waitlist = WaitlistEntry.objects.filter(donor=user_donor, session=session).first()
            user_standby = StandbyAvailability.objects.filter(donor=user_donor, session=session).first()
        except Donor.DoesNotExist:
            pass
    return render(request, 'core/session_detail.html', {
        'session': session,
        'slots': session.slots.select_related('donor').all(),
        'waitlist_count': session.waitlist_entries.count(),
        'user_donor': user_donor,
        'user_waitlist': user_waitlist,
        'user_standby': user_standby,
    })


# ---------------------------------------------------------------------------
# Account e area donatore
# ---------------------------------------------------------------------------

def register(request):
    """Registrazione donatore: crea User + profilo Donor e autentica subito."""
    if request.method == 'POST':
        form = DonorRegistrationForm(request.POST)
        if form.is_valid():
            login(request, form.save())
            messages.success(request, 'Registrazione completata. Puoi prenotare uno slot o entrare in lista d’attesa.')
            return redirect('dashboard')
    else:
        form = DonorRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def dashboard(request):
    """Dashboard donatore: prenotazioni, offerte urgenti, liste d'attesa e notifiche."""
    if is_operator(request.user):
        return redirect('operator_dashboard')
    donor = get_donor_or_raise(request.user)
    return render(request, 'core/dashboard.html', {
        'donor': donor,
        'next_appointment': Appointment.next_for_donor(donor),
        'appointments': Appointment.objects.filter(donor=donor)
            .select_related('slot__session__center').order_by('-slot__session__date', '-slot__time'),
        'waitlist_entries': WaitlistEntry.objects.filter(donor=donor)
            .select_related('session__center').order_by('-session__date'),
        'standby': StandbyAvailability.objects.filter(donor=donor)
            .select_related('session__center').order_by('-session__date'),
        'offers': WaitlistOffer.objects.filter(donor=donor, status__in=['SENT', 'ACCEPTED'])
            .select_related('slot__session__center').order_by('-created_at'),
        'notifications': Notification.objects.filter(donor=donor).order_by('-sent_at')[:10],
    })


@login_required
def profile(request):
    """Area personale: modifica dati anagrafici, storico prenotazioni ed email."""
    donor = get_donor_or_raise(request.user)
    next_appointment = Appointment.next_for_donor(donor)

    if request.method == 'POST':
        form = DonorProfileForm(request.POST, instance=donor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Area personale aggiornata correttamente.')
            return redirect('profile')
    else:
        form = DonorProfileForm(instance=donor)

    return render(request, 'core/profile.html', {
        'donor': donor,
        'form': form,
        'next_appointment': next_appointment,
        'past_appointments': Appointment.objects.filter(donor=donor)
            .select_related('slot__session__center')
            .exclude(pk=getattr(next_appointment, 'pk', None))
            .order_by('-slot__session__date', '-slot__time')[:10],
        'email_notifications': Notification.objects.filter(donor=donor, channel='EMAIL')
            .select_related('appointment').order_by('-sent_at')[:10],
        'all_notifications': Notification.objects.filter(donor=donor)
            .exclude(channel='EMAIL').order_by('-sent_at')[:10],
    })


@login_required
def book_slot_view(request, slot_id):
    """Prenotazione di uno slot libero da parte del donatore."""
    slot = get_object_or_404(Slot, pk=slot_id)
    if request.method != 'POST':
        return redirect('session_detail', pk=slot.session_id)
    if not hasattr(request.user, 'donor_profile'):
        # Staff/operatori non hanno un profilo donatore: messaggio chiaro, non un 403 grezzo.
        messages.error(request, 'Questo account non è un profilo donatore: le prenotazioni si gestiscono dall’area Gestione.')
        return redirect('session_detail', pk=slot.session_id)
    if run_service(request, book_slot, slot, request.user.donor_profile):
        messages.success(request, 'Prenotazione confermata.')
        return redirect('dashboard')
    return redirect('session_detail', pk=slot.session_id)


@login_required
def cancel_appointment_view(request, pk):
    donor = get_donor_or_raise(request.user)
    appointment = get_object_or_404(Appointment, pk=pk, donor=donor)
    if request.method == 'POST' and run_service(
            request, cancel_appointment, appointment, user=request.user, reason=request.POST.get('reason', '')):
        messages.success(request, 'Prenotazione annullata. Lo slot torna disponibile.')
    return redirect('dashboard')


@login_required
def join_waitlist(request, session_id):
    """Inserimento in lista d'attesa per una raccolta piena."""
    donor = get_donor_or_raise(request.user)
    session = get_object_or_404(DonationSession, pk=session_id)
    if request.method == 'POST':
        form = WaitlistForm(request.POST)
        if form.is_valid():
            if run_service(request, create_waitlist_entry, session, donor, **form.cleaned_data):
                messages.success(request, 'Sei stato inserito in lista d’attesa.')
            return redirect('dashboard')
    else:
        form = WaitlistForm()
    return render(request, 'core/waitlist_form.html', {'form': form, 'session': session})


@login_required
def confirm_standby_view(request, session_id):
    """Conferma di disponibilità standby (arrivo rapido in caso di slot liberato)."""
    donor = get_donor_or_raise(request.user)
    session = get_object_or_404(DonationSession, pk=session_id)
    if request.method == 'POST':
        form = StandbyAvailabilityForm(request.POST)
        if form.is_valid():
            if run_service(request, confirm_standby, session, donor, **form.cleaned_data):
                messages.success(request, 'Disponibilità standby confermata.')
            return redirect('dashboard')
    else:
        form = StandbyAvailabilityForm(initial={
            'available_from': session.start_time,
            'available_to': session.end_time,
        })
    return render(request, 'core/standby_form.html', {'form': form, 'session': session})


@login_required
def offer_response_view(request, offer_id, response):
    """Risposta del donatore a un'offerta urgente (accetta / più tardi / rifiuta)."""
    donor = get_donor_or_raise(request.user)
    offer = get_object_or_404(WaitlistOffer, pk=offer_id, donor=donor)
    if request.method == 'POST' and response in ['ACCEPT', 'LATE', 'DECLINE'] \
            and run_service(request, respond_to_offer, offer, response):
        messages.success(request, 'Risposta registrata.')
    return redirect('dashboard')


# ---------------------------------------------------------------------------
# Gestione admin: CMS (pagine e footer)
# ---------------------------------------------------------------------------

@user_passes_test(is_admin_user)
def management_pages(request):
    return render(request, 'management/pages.html', {
        'pages': CmsPage.objects.all().order_by('sort_order', 'title'),
    })


@user_passes_test(is_admin_user)
def management_page_create(request):
    response, _ = _handle_model_form(
        request, CmsPageForm, 'management/page_form.html', 'management_pages',
        success_message='Pagina "{obj.title}" creata correttamente.',
        extra_context={'mode': 'create'},
    )
    return response


@user_passes_test(is_admin_user)
def management_page_update(request, pk):
    page = get_object_or_404(CmsPage, pk=pk)
    response, _ = _handle_model_form(
        request, CmsPageForm, 'management/page_form.html', 'management_pages',
        instance=page,
        success_message='Pagina "{obj.title}" aggiornata correttamente.',
        extra_context={'page': page, 'mode': 'update'},
    )
    return response


@user_passes_test(is_admin_user)
def management_page_toggle(request, pk):
    """Pubblica/nasconde una pagina con un click."""
    page = get_object_or_404(CmsPage, pk=pk)
    if request.method == 'POST':
        page.is_published = not page.is_published
        page.save(update_fields=['is_published', 'updated_at'])
        messages.success(request, f'Pagina "{page.title}" {"pubblicata" if page.is_published else "nascosta"}.')
    return redirect('management_pages')


@user_passes_test(is_admin_user)
def management_page_delete(request, pk):
    page = get_object_or_404(CmsPage, pk=pk)
    if request.method == 'POST':
        title = page.title
        page.delete()
        messages.warning(request, f'Pagina "{title}" eliminata.')
    return redirect('management_pages')


@user_passes_test(is_admin_user)
def management_footer(request):
    return render(request, 'management/footer_sections.html', {
        'sections': FooterSection.objects.all().order_by('sort_order', 'id'),
    })


@user_passes_test(is_admin_user)
def management_footer_update(request, pk):
    section = get_object_or_404(FooterSection, pk=pk)
    response, _ = _handle_model_form(
        request, FooterSectionForm, 'management/footer_section_form.html', 'management_footer',
        instance=section,
        success_message='Sezione footer "{obj.title}" aggiornata correttamente.',
        extra_context={'section': section},
    )
    return response


# ---------------------------------------------------------------------------
# Gestione admin: sedi
# ---------------------------------------------------------------------------

@user_passes_test(is_admin_user)
def management_centers(request):
    return render(request, 'management/centers.html', {
        'centers': DonationCenter.objects.annotate(sessions_count=Count('sessions')).order_by('city', 'name'),
    })


@user_passes_test(is_admin_user)
def management_center_create(request):
    response, _ = _handle_model_form(
        request, DonationCenterForm, 'management/center_form.html', 'management_centers',
        success_message='Sede "{obj.name}" creata correttamente.',
        extra_context={'mode': 'create'},
    )
    return response


@user_passes_test(is_admin_user)
def management_center_update(request, pk):
    center = get_object_or_404(DonationCenter, pk=pk)
    response, _ = _handle_model_form(
        request, DonationCenterForm, 'management/center_form.html', 'management_centers',
        instance=center,
        success_message='Sede "{obj.name}" aggiornata correttamente.',
        extra_context={'center': center, 'mode': 'update'},
    )
    return response


@user_passes_test(is_admin_user)
def management_center_toggle(request, pk):
    center = get_object_or_404(DonationCenter, pk=pk)
    if request.method == 'POST':
        center.active = not center.active
        center.save(update_fields=['active', 'updated_at'])
        messages.success(request, f'Sede "{center.name}" {"attivata" if center.active else "disattivata"}.')
    return redirect('management_centers')


# ---------------------------------------------------------------------------
# Gestione admin: giornate di raccolta
# ---------------------------------------------------------------------------

@user_passes_test(is_admin_user)
def management_sessions(request):
    sessions = DonationSession.objects.select_related('center').annotate(
        total_slots=Count('slots'),
        booked_slots=Count('slots', filter=Q(slots__status__in=Slot.OCCUPIED_STATUSES)),
        free_slots=Count('slots', filter=Q(slots__status='FREE')),
    ).order_by('-date', '-start_time')
    return render(request, 'management/sessions.html', {'sessions': sessions})


def _save_session_form(request, form, success_prefix):
    """Salva la raccolta e, se richiesto, genera/riallinea gli slot in un colpo solo."""
    session = form.save()
    if 'generate_slots' in request.POST:
        result = generate_slots_for_session(session, reset_free=request.POST.get('reset_free') == '1')
        messages.success(request, f'{success_prefix}. Slot creati: {result["created"]}, riallineati: {result["updated"]}.')
    else:
        messages.success(request, f'{success_prefix}.')
    return redirect('management_appointments', pk=session.pk)


@user_passes_test(is_admin_user)
def management_session_create(request):
    if request.method == 'POST':
        form = SessionCreateForm(request.POST, request.FILES)
        if form.is_valid():
            return _save_session_form(request, form, 'Giornata di raccolta creata')
    else:
        form = SessionCreateForm()
    return render(request, 'management/session_form.html', {'form': form, 'mode': 'create'})


@user_passes_test(is_admin_user)
def management_session_update(request, pk):
    session = get_object_or_404(DonationSession, pk=pk)
    if request.method == 'POST':
        form = SessionCreateForm(request.POST, request.FILES, instance=session)
        if form.is_valid():
            return _save_session_form(request, form, 'Giornata di raccolta aggiornata')
    else:
        form = SessionCreateForm(instance=session)
    return render(request, 'management/session_form.html', {'form': form, 'session': session, 'mode': 'update'})


@user_passes_test(is_admin_user)
def management_generate_slots(request, pk):
    """Genera gli slot mancanti; con ``reset_free=1`` riallinea anche quelli senza prenotazioni."""
    session = get_object_or_404(DonationSession, pk=pk)
    if request.method == 'POST':
        result = generate_slots_for_session(session, reset_free=request.POST.get('reset_free') == '1')
        if result['created'] or result['updated']:
            messages.success(request, f'Slot aggiornati. Creati: {result["created"]}, riallineati: {result["updated"]}, previsti: {result["total_desired"]}.')
        else:
            messages.info(request, 'Nessun nuovo slot generato: gli slot risultano già coerenti con la configurazione.')
    return redirect('management_appointments', pk=session.pk)


@user_passes_test(is_admin_user)
def management_set_session_status(request, pk, status):
    session = get_object_or_404(DonationSession, pk=pk)
    allowed = {choice[0] for choice in DonationSession.STATUS_CHOICES}
    if request.method == 'POST' and status in allowed:
        session.status = status
        session.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Stato raccolta aggiornato: {session.get_status_display()}.')
    return redirect('management_sessions')


@user_passes_test(is_admin_user)
def management_appointments(request, pk):
    """Pannello prenotazioni di una raccolta: slot, prenotazioni e statistiche."""
    session = get_object_or_404(DonationSession.objects.select_related('center'), pk=pk)
    session_appointments = Appointment.objects.filter(slot__session=session)
    stats = {
        'total_slots': session.slots.count(),
        'free_slots': session.slots.filter(status='FREE').count(),
        'booked': session_appointments.filter(status__in=Appointment.ACTIVE_STATUSES).count(),
        'cancelled': session_appointments.filter(status__in=['CANCELLED_BY_DONOR', 'CANCELLED_BY_OPERATOR']).count(),
        'checked_in': session_appointments.filter(checkin__status='CHECKED_IN').count(),
        'completed': session_appointments.filter(status='COMPLETED').count(),
    }
    return render(request, 'management/appointments.html', {
        'session': session,
        'slots': session.slots.select_related('donor').prefetch_related('appointments').order_by('time'),
        'appointments': session_appointments.select_related('donor', 'slot').order_by('slot__time', 'donor__last_name'),
        'stats': stats,
    })


@user_passes_test(is_admin_user)
def management_print_appointments(request, pk):
    """Versione stampabile dell'elenco prenotazioni (firma, note, check-in su carta)."""
    session = get_object_or_404(DonationSession.objects.select_related('center'), pk=pk)
    slots = session.slots.select_related('donor').prefetch_related('appointments').order_by('time')
    return render(request, 'management/print_appointments.html', {'session': session, 'slots': slots})


@user_passes_test(is_admin_user)
def management_send_appointment_email(request, appointment_id):
    """Invio manuale dell'email di riepilogo stato prenotazione."""
    appointment = get_object_or_404(Appointment.objects.select_related('slot__session', 'donor'), pk=appointment_id)
    if request.method == 'POST':
        status = send_appointment_status_email(appointment, user=request.user)
        if status == 'SENT':
            messages.success(request, f'Email riepilogo inviata a {appointment.donor.email}.')
        elif status == 'SIMULATED':
            messages.warning(request, 'Email solo simulata: nessun server SMTP configurato, il messaggio è stato scritto nel terminale del server. Configura l’SMTP nel file .env (vedi README).')
        else:
            messages.error(request, 'Email non inviata: controlla l’indirizzo del donatore o la configurazione SMTP. L’errore è salvato nello storico email.')
    return redirect('management_appointments', pk=appointment.slot.session_id)


# ---------------------------------------------------------------------------
# Dashboard operatore
# ---------------------------------------------------------------------------

@user_passes_test(is_operator)
def operator_dashboard(request):
    """Vista operativa: raccolte con conteggi e alert dashboard più recenti."""
    sessions = DonationSession.objects.select_related('center').annotate(
        total_slots=Count('slots'),
        booked_slots=Count('slots', filter=Q(slots__status__in=Slot.OCCUPIED_STATUSES)),
        risk_slots=Count('slots', filter=Q(slots__status__in=['RISK', 'REPLACEABLE'])),
    ).order_by('date')
    notifications = Notification.objects.filter(channel='DASHBOARD').order_by('-sent_at')[:12]
    return render(request, 'operator/dashboard.html', {'sessions': sessions, 'notifications': notifications})


@user_passes_test(is_operator)
def operator_session(request, pk):
    """Console della giornata: slot con azioni rapide, lista d'attesa, standby e offerte."""
    session = get_object_or_404(DonationSession.objects.select_related('center'), pk=pk)
    standby = session.standby_availabilities.select_related('donor').all()
    offers = WaitlistOffer.objects.filter(slot__session=session).select_related('donor', 'slot').order_by('slot__time', '-score')
    session_appointments = Appointment.objects.filter(slot__session=session)
    stats = {
        'booked': session.slots.filter(status__in=Slot.OCCUPIED_STATUSES).count(),
        'checked_in': session_appointments.filter(checkin__status='CHECKED_IN').count(),
        'risk': session.slots.filter(status__in=['RISK', 'REPLACEABLE']).count(),
        'standby': standby.filter(status='CONFIRMED').count(),
        'offers': offers.count(),
        'accepted': offers.filter(status='ACCEPTED').count(),
        'no_show': session_appointments.filter(status='NO_SHOW').count(),
    }
    return render(request, 'operator/session.html', {
        'session': session,
        'slots': session.slots.select_related('donor').prefetch_related('appointments', 'offers').all(),
        'waitlist': session.waitlist_entries.select_related('donor').all(),
        'standby': standby,
        'offers': offers,
        'stats': stats,
    })


# ---------------------------------------------------------------------------
# Factory per le azioni operative (check-in, no-show, esiti, conferme, ...)
#
# Ogni azione segue lo stesso schema: carica la prenotazione, esegue la funzione
# di servizio su POST, mostra un messaggio e torna alla pagina della raccolta.
# Le factory qui sotto generano queste view a partire da 4 parametri, invece di
# ripetere ~15 funzioni quasi identiche.
# ---------------------------------------------------------------------------

def _appointment_action(service, message_tpl, *, permission, redirect_name,
                        level='success', post_fields=(), post_defaults=None):
    """Crea una view POST-only che applica ``service`` a una prenotazione.

    - ``message_tpl`` supporta il segnaposto ``{donor}``.
    - ``post_fields``: nomi di campi POST inoltrati al service (es. 'notes', 'reason').
    - ``post_defaults``: valori di default per i campi POST mancanti.
    """
    defaults = post_defaults or {}

    @user_passes_test(permission)
    def view(request, appointment_id):
        appointment = get_object_or_404(
            Appointment.objects.select_related('slot__session', 'donor'), pk=appointment_id)
        if request.method == 'POST':
            kwargs = {field: request.POST.get(field, defaults.get(field, '')) for field in post_fields}
            if run_service(request, service, appointment, user=request.user, **kwargs) is not None:
                getattr(messages, level)(request, message_tpl.format(donor=appointment.donor))
        return redirect(redirect_name, pk=appointment.slot.session_id)

    return view


def _slot_action(service, *, permission, redirect_name, on_result):
    """Come sopra, ma per azioni che operano su uno Slot (rischio, attiva standby)."""

    @user_passes_test(permission)
    def view(request, slot_id):
        slot = get_object_or_404(Slot, pk=slot_id)
        if request.method == 'POST':
            try:
                on_result(request, slot, service(slot, user=request.user))
            except DonoFlowError as exc:
                messages.error(request, str(exc))
        return redirect(redirect_name, pk=slot.session_id)

    return view


# --- Azioni prenotazione, area Gestione admin ------------------------------
management_confirm_appointment = _appointment_action(
    confirm_appointment_by_operator, 'Prenotazione confermata per {donor}.',
    permission=is_admin_user, redirect_name='management_appointments')
management_checkin_appointment = _appointment_action(
    mark_checkin, 'Check-in registrato per {donor}.',
    permission=is_admin_user, redirect_name='management_appointments')
management_cancel_appointment = _appointment_action(
    cancel_appointment_by_operator, 'Prenotazione annullata per {donor}.',
    permission=is_admin_user, redirect_name='management_appointments', level='warning',
    post_fields=('reason',), post_defaults={'reason': 'Annullamento da gestione admin'})
management_no_show_appointment = _appointment_action(
    mark_no_show, '{donor} segnato come no-show.',
    permission=is_admin_user, redirect_name='management_appointments', level='warning')
management_complete_appointment = _appointment_action(
    mark_donation_completed, 'Donazione effettuata registrata per {donor}.',
    permission=is_admin_user, redirect_name='management_appointments', post_fields=('notes',))
management_not_done_appointment = _appointment_action(
    mark_donation_not_done, 'Donazione non effettuata registrata per {donor}.',
    permission=is_admin_user, redirect_name='management_appointments', level='warning', post_fields=('notes',))

# --- Azioni prenotazione, console operatore --------------------------------
operator_checkin = _appointment_action(
    mark_checkin, 'Check-in registrato per {donor}.',
    permission=is_operator, redirect_name='operator_session')
operator_no_show = _appointment_action(
    mark_no_show, '{donor} segnato come no-show.',
    permission=is_operator, redirect_name='operator_session', level='warning')
operator_complete = _appointment_action(
    mark_donation_completed, 'Donazione effettuata registrata per {donor}.',
    permission=is_operator, redirect_name='operator_session')
operator_not_done = _appointment_action(
    mark_donation_not_done, 'Donazione non effettuata registrata per {donor}.',
    permission=is_operator, redirect_name='operator_session', level='warning')


# --- Azioni su slot ---------------------------------------------------------
def _after_mark_risk(request, slot, _result):
    messages.warning(request, f'Slot {slot.time:%H:%M} marcato come ritardo critico.')


def _after_activate_standby(request, slot, offers):
    if offers:
        messages.success(request, f'Offerta urgente inviata a {len(offers)} standby compatibili.')
    else:
        messages.error(request, 'Nessun candidato standby compatibile trovato.')


operator_mark_risk = _slot_action(
    mark_slot_risk, permission=is_operator, redirect_name='operator_session', on_result=_after_mark_risk)
operator_activate_standby = _slot_action(
    activate_standby_for_slot, permission=is_operator, redirect_name='operator_session', on_result=_after_activate_standby)


# --- Azioni su offerte standby ----------------------------------------------
@user_passes_test(is_operator)
def operator_simulate_offer_response(request, offer_id, response):
    """Nella demo l'operatore può simulare la risposta del donatore all'offerta."""
    offer = get_object_or_404(WaitlistOffer, pk=offer_id)
    if request.method == 'POST' and response in ['ACCEPT', 'LATE', 'DECLINE'] \
            and run_service(request, respond_to_offer, offer, response):
        messages.success(request, f'Risposta simulata per {offer.donor}: {offer.get_response_display()}')
    return redirect('operator_session', pk=offer.slot.session_id)


@user_passes_test(is_operator)
def operator_assign_offer(request, offer_id):
    """Conferma manuale del sostituto scelto tra le offerte accettate."""
    offer = get_object_or_404(WaitlistOffer, pk=offer_id)
    if request.method == 'POST' and run_service(request, assign_standby_offer, offer, user=request.user):
        messages.success(request, f'Slot assegnato a {offer.donor}.')
    return redirect('operator_session', pk=offer.slot.session_id)
