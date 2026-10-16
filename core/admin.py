from django.contrib import admin

from .models import (
    Appointment,
    CmsPage,
    AuditLog,
    CheckIn,
    DonationCenter,
    DonationOutcome,
    DonationSession,
    Donor,
    FooterSection,
    Notification,
    Slot,
    StandbyAvailability,
    WaitlistEntry,
    WaitlistOffer,
)


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'phone', 'email', 'blood_group', 'donor_status', 'reliability_score')
    search_fields = ('first_name', 'last_name', 'phone', 'email', 'fiscal_code')
    list_filter = ('donor_status', 'blood_group', 'preferred_channel')


@admin.register(DonationCenter)
class DonationCenterAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'active')
    list_filter = ('city', 'active')
    search_fields = ('name', 'city', 'address')


class SlotInline(admin.TabularInline):
    model = Slot
    extra = 0
    fields = ('time', 'expected_arrival_time', 'status', 'donor')


@admin.register(DonationSession)
class DonationSessionAdmin(admin.ModelAdmin):
    list_display = ('date', 'title', 'center', 'start_time', 'end_time', 'slot_duration_minutes', 'capacity', 'public_slots', 'reserved_slots', 'status')
    list_filter = ('status', 'center', 'date')
    search_fields = ('title', 'center__name', 'center__city', 'public_description')
    fieldsets = (
        ('Dati principali', {'fields': ('center', 'title', 'date', 'start_time', 'end_time', 'slot_duration_minutes', 'expected_arrival_minutes', 'donation_type', 'status')}),
        ('Capienza e slot', {'fields': ('capacity', 'public_slots', 'reserved_slots', 'standby_slots')}),
        ('Informazioni pubbliche', {'fields': ('featured_image', 'public_description', 'public_instructions')}),
        ('Note interne', {'fields': ('notes',)}),
    )
    inlines = [SlotInline]


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ('session', 'time', 'expected_arrival_time', 'status', 'donor')
    list_filter = ('status', 'session__date', 'session__center')
    search_fields = ('donor__first_name', 'donor__last_name')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('slot', 'donor', 'status', 'source', 'created_at')
    list_filter = ('status', 'source', 'slot__session__date')
    search_fields = ('donor__first_name', 'donor__last_name')


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ('session', 'position', 'donor', 'status', 'minimum_notice_minutes', 'max_arrival_minutes')
    list_filter = ('status', 'session__date')


@admin.register(StandbyAvailability)
class StandbyAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('session', 'donor', 'available_from', 'available_to', 'max_arrival_minutes', 'status')
    list_filter = ('status', 'session__date')


@admin.register(WaitlistOffer)
class WaitlistOfferAdmin(admin.ModelAdmin):
    list_display = ('slot', 'donor', 'estimated_arrival_minutes', 'score', 'response', 'status')
    list_filter = ('response', 'status')


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ('appointment', 'expected_arrival_time', 'actual_checkin_time', 'status')
    list_filter = ('status',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('sent_at', 'donor', 'channel', 'template', 'status')
    list_filter = ('channel', 'template', 'status')
    search_fields = ('message', 'donor__first_name', 'donor__last_name')


@admin.register(DonationOutcome)
class DonationOutcomeAdmin(admin.ModelAdmin):
    list_display = ('appointment', 'outcome', 'completed_at')
    list_filter = ('outcome',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'object_type', 'object_id')
    list_filter = ('action', 'object_type')
    search_fields = ('action', 'notes')


@admin.register(CmsPage)
class CmsPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'show_in_navigation', 'show_in_footer', 'sort_order', 'updated_at')
    list_filter = ('is_published', 'show_in_navigation', 'show_in_footer')
    search_fields = ('title', 'slug', 'summary', 'content')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('sort_order', 'title')


@admin.register(FooterSection)
class FooterSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'key', 'is_active', 'sort_order', 'updated_at')
    list_filter = ('is_active', 'key')
    ordering = ('sort_order', 'id')
