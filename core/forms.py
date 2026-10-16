from datetime import datetime

from django.utils import timezone

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import CmsPage, Donor, DonationCenter, FooterSection, WaitlistEntry, StandbyAvailability, DonationSession


def html5_date_widget():
    """<input type=date> accetta SOLO il formato ISO (AAAA-MM-GG).

    Senza `format` Django rende la data localizzata ("09/10/2026"): il browser la
    scarta e il campo appare vuoto, bloccando il salvataggio o cancellando il dato.
    """
    return forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


def html5_time_widget():
    return forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')


class DonorRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label='Nome', max_length=80)
    last_name = forms.CharField(label='Cognome', max_length=80)
    email = forms.EmailField(label='Email')
    phone = forms.CharField(label='Telefono', max_length=30)
    fiscal_code = forms.CharField(label='Codice fiscale', max_length=16, required=False)
    birth_date = forms.DateField(label='Data di nascita', required=False, widget=html5_date_widget())
    blood_group = forms.ChoiceField(label='Gruppo sanguigno', choices=Donor.BLOOD_GROUP_CHOICES, required=False)
    preferred_channel = forms.ChoiceField(label='Canale preferito', choices=Donor.CHANNEL_CHOICES)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'fiscal_code', 'birth_date', 'blood_group', 'preferred_channel', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Donor.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Esiste già un account con questa email. Prova ad accedere.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            Donor.objects.create(
                user=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                email=self.cleaned_data['email'],
                phone=self.cleaned_data['phone'],
                fiscal_code=self.cleaned_data.get('fiscal_code', ''),
                birth_date=self.cleaned_data.get('birth_date'),
                blood_group=self.cleaned_data.get('blood_group', ''),
                preferred_channel=self.cleaned_data['preferred_channel'],
            )
        return user


class DonorProfileForm(forms.ModelForm):
    email = forms.EmailField(label='Email', required=True)
    first_name = forms.CharField(label='Nome', max_length=80)
    last_name = forms.CharField(label='Cognome', max_length=80)
    birth_date = forms.DateField(label='Data di nascita', required=False, widget=html5_date_widget())

    class Meta:
        model = Donor
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'fiscal_code',
            'birth_date', 'blood_group', 'preferred_channel',
        ]
        labels = {
            'phone': 'Telefono',
            'fiscal_code': 'Codice fiscale',
            'blood_group': 'Gruppo sanguigno',
            'preferred_channel': 'Canale preferito',
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Donor.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Questa email è già associata a un altro donatore.')
        return email

    def save(self, commit=True):
        donor = super().save(commit=False)
        if commit:
            donor.save()
            if donor.user:
                donor.user.first_name = donor.first_name
                donor.user.last_name = donor.last_name
                donor.user.email = donor.email
                donor.user.save(update_fields=['first_name', 'last_name', 'email'])
        return donor


class DonationCenterForm(forms.ModelForm):
    class Meta:
        model = DonationCenter
        fields = ['name', 'address', 'city', 'latitude', 'longitude', 'active', 'notes']
        labels = {
            'name': 'Nome sede',
            'address': 'Indirizzo',
            'city': 'Comune',
            'latitude': 'Latitudine',
            'longitude': 'Longitudine',
            'active': 'Sede attiva',
            'notes': 'Note interne',
        }
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }


class WaitlistForm(forms.ModelForm):
    class Meta:
        model = WaitlistEntry
        fields = ['preferred_time_range', 'minimum_notice_minutes', 'max_arrival_minutes']
        labels = {
            'preferred_time_range': 'Fascia preferita',
            'minimum_notice_minutes': 'Preavviso minimo',
            'max_arrival_minutes': 'Tempo massimo di arrivo stimato',
        }


class StandbyAvailabilityForm(forms.ModelForm):
    available_from = forms.TimeField(label='Disponibile dalle', widget=html5_time_widget())
    available_to = forms.TimeField(label='Disponibile fino alle', widget=html5_time_widget())

    class Meta:
        model = StandbyAvailability
        fields = ['available_from', 'available_to', 'minimum_notice_minutes', 'max_arrival_minutes', 'preferred_channel']
        labels = {
            'minimum_notice_minutes': 'Preavviso minimo',
            'max_arrival_minutes': 'Tempo stimato di arrivo',
            'preferred_channel': 'Canale preferito',
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('available_from'), cleaned.get('available_to')
        if start and end and start >= end:
            self.add_error('available_to', 'L’orario finale deve essere successivo a quello iniziale.')
        return cleaned


class SessionCreateForm(forms.ModelForm):
    date = forms.DateField(label='Data raccolta', widget=html5_date_widget())
    start_time = forms.TimeField(label='Ora inizio', widget=html5_time_widget())
    end_time = forms.TimeField(label='Ora fine', widget=html5_time_widget())
    featured_image = forms.ImageField(label='Immagine in evidenza', required=False)

    class Meta:
        model = DonationSession
        fields = [
            'center', 'title', 'date', 'start_time', 'end_time', 'slot_duration_minutes',
            'expected_arrival_minutes', 'donation_type', 'capacity', 'public_slots',
            'reserved_slots', 'standby_slots', 'status', 'featured_image',
            'public_description', 'public_instructions', 'notes',
        ]
        labels = {
            'center': 'Sede',
            'title': 'Titolo pubblico',
            'slot_duration_minutes': 'Durata singolo slot, in minuti',
            'expected_arrival_minutes': 'Anticipo richiesto per arrivo/check-in, in minuti',
            'donation_type': 'Tipo donazione',
            'capacity': 'Capacità reale della raccolta',
            'public_slots': 'Slot prenotabili online',
            'reserved_slots': 'Slot riservati/bloccati da operatore',
            'standby_slots': 'Numero indicativo standby da mantenere',
            'status': 'Stato',
            'public_description': 'Dati informativi pubblici',
            'public_instructions': 'Indicazioni per i donatori',
            'notes': 'Note interne',
        }
        widgets = {
            'public_description': forms.Textarea(attrs={'rows': 4}),
            'public_instructions': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get('date')
        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')
        duration = cleaned.get('slot_duration_minutes')
        capacity = cleaned.get('capacity') or 0
        public_slots = cleaned.get('public_slots') or 0
        reserved_slots = cleaned.get('reserved_slots') or 0

        if start_time and end_time and start_time >= end_time:
            self.add_error('end_time', 'L’orario di fine deve essere successivo all’orario di inizio.')
            return cleaned

        if duration is None or duration < 5:
            self.add_error('slot_duration_minutes', 'La durata dello slot deve essere di almeno 5 minuti.')
            return cleaned

        # Le nuove raccolte non possono essere nel passato (le esistenti restano modificabili).
        if date and not self.instance.pk and date < timezone.localdate():
            self.add_error('date', 'La data della raccolta non può essere nel passato.')

        if date and start_time and end_time:
            minutes = int((datetime.combine(date, end_time) - datetime.combine(date, start_time)).total_seconds() // 60)
            max_slots = minutes // duration
            if capacity > max_slots:
                self.add_error(
                    'capacity',
                    f'Con questo orario e slot da {duration} minuti puoi generare al massimo {max_slots} slot.',
                )

        if public_slots + reserved_slots > capacity:
            self.add_error('public_slots', 'Slot pubblici + slot riservati non possono superare la capacità reale.')
            self.add_error('reserved_slots', 'Slot pubblici + slot riservati non possono superare la capacità reale.')

        return cleaned


class CmsPageForm(forms.ModelForm):
    class Meta:
        model = CmsPage
        fields = [
            'title', 'slug', 'menu_label', 'summary', 'content',
            'is_published', 'show_in_navigation', 'show_in_footer', 'sort_order',
        ]
        labels = {
            'content': 'Contenuto della pagina',
        }
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 2}),
            'content': forms.Textarea(attrs={'rows': 22, 'class': 'code-editor'}),
        }
        help_texts = {
            'slug': 'Parte finale dell’indirizzo, ad esempio: chi-siamo. Usa lettere minuscole e trattini.',
            'menu_label': 'Testo breve usato nel menu. Se vuoto, viene usato il titolo.',
            'content': 'HTML consentito perché le pagine possono essere modificate solo dagli amministratori.',
            'sort_order': 'Numero più basso = posizione precedente nei menu.',
        }


class FooterSectionForm(forms.ModelForm):
    class Meta:
        model = FooterSection
        fields = ['title', 'content', 'is_active', 'sort_order']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 12, 'class': 'code-editor'}),
        }
        help_texts = {
            'content': 'HTML semplice consentito. Puoi inserire paragrafi, elenchi e collegamenti.',
            'sort_order': 'Numero più basso = sezione mostrata prima.',
        }
