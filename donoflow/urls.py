from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('come-funziona/', views.public_page, {'slug': 'come-funziona'}, name='how_it_works'),
    path('privacy/', views.public_page, {'slug': 'privacy'}, name='privacy_page'),
    path('info/', views.public_page, {'slug': 'info'}, name='info_page'),
    path('p/<slug:slug>/', views.public_page, name='public_page'),
    path('accounts/register/', views.register, name='register'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('area-personale/', views.profile, name='profile'),
    path('sessions/', views.sessions_list, name='sessions_list'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('slots/<int:slot_id>/book/', views.book_slot_view, name='book_slot'),
    path('appointments/<int:pk>/cancel/', views.cancel_appointment_view, name='cancel_appointment'),
    path('sessions/<int:session_id>/waitlist/', views.join_waitlist, name='join_waitlist'),
    path('sessions/<int:session_id>/standby/', views.confirm_standby_view, name='confirm_standby'),
    path('offers/<int:offer_id>/<str:response>/', views.offer_response_view, name='offer_response'),

    path('gestione/pagine/', views.management_pages, name='management_pages'),
    path('gestione/footer/', views.management_footer, name='management_footer'),
    path('gestione/footer/<int:pk>/modifica/', views.management_footer_update, name='management_footer_update'),
    path('gestione/pagine/nuova/', views.management_page_create, name='management_page_create'),
    path('gestione/pagine/<int:pk>/modifica/', views.management_page_update, name='management_page_update'),
    path('gestione/pagine/<int:pk>/toggle/', views.management_page_toggle, name='management_page_toggle'),
    path('gestione/pagine/<int:pk>/elimina/', views.management_page_delete, name='management_page_delete'),
    path('gestione/raccolte/', views.management_sessions, name='management_sessions'),
    path('gestione/sedi/', views.management_centers, name='management_centers'),
    path('gestione/sedi/nuova/', views.management_center_create, name='management_center_create'),
    path('gestione/sedi/<int:pk>/modifica/', views.management_center_update, name='management_center_update'),
    path('gestione/sedi/<int:pk>/toggle/', views.management_center_toggle, name='management_center_toggle'),
    path('gestione/raccolte/nuova/', views.management_session_create, name='management_session_create'),
    path('gestione/raccolte/<int:pk>/modifica/', views.management_session_update, name='management_session_update'),
    path('gestione/raccolte/<int:pk>/genera-slot/', views.management_generate_slots, name='management_generate_slots'),
    path('gestione/raccolte/<int:pk>/stato/<str:status>/', views.management_set_session_status, name='management_set_session_status'),
    path('gestione/raccolte/<int:pk>/prenotazioni/', views.management_appointments, name='management_appointments'),
    path('gestione/raccolte/<int:pk>/stampa/', views.management_print_appointments, name='management_print_appointments'),
    path('gestione/prenotazioni/<int:appointment_id>/conferma/', views.management_confirm_appointment, name='management_confirm_appointment'),
    path('gestione/prenotazioni/<int:appointment_id>/checkin/', views.management_checkin_appointment, name='management_checkin_appointment'),
    path('gestione/prenotazioni/<int:appointment_id>/annulla/', views.management_cancel_appointment, name='management_cancel_appointment'),
    path('gestione/prenotazioni/<int:appointment_id>/no-show/', views.management_no_show_appointment, name='management_no_show_appointment'),
    path('gestione/prenotazioni/<int:appointment_id>/effettuata/', views.management_complete_appointment, name='management_complete_appointment'),
    path('gestione/prenotazioni/<int:appointment_id>/non-effettuata/', views.management_not_done_appointment, name='management_not_done_appointment'),
    path('gestione/prenotazioni/<int:appointment_id>/email/', views.management_send_appointment_email, name='management_send_appointment_email'),
    path('operator/', views.operator_dashboard, name='operator_dashboard'),
    path('operator/sessions/<int:pk>/', views.operator_session, name='operator_session'),
    path('operator/slots/<int:slot_id>/risk/', views.operator_mark_risk, name='operator_mark_risk'),
    path('operator/slots/<int:slot_id>/activate-standby/', views.operator_activate_standby, name='operator_activate_standby'),
    path('operator/offers/<int:offer_id>/<str:response>/simulate/', views.operator_simulate_offer_response, name='operator_simulate_offer_response'),
    path('operator/offers/<int:offer_id>/assign/', views.operator_assign_offer, name='operator_assign_offer'),
    path('operator/appointments/<int:appointment_id>/checkin/', views.operator_checkin, name='operator_checkin'),
    path('operator/appointments/<int:appointment_id>/no-show/', views.operator_no_show, name='operator_no_show'),
    path('operator/appointments/<int:appointment_id>/effettuata/', views.operator_complete, name='operator_complete'),
    path('operator/appointments/<int:appointment_id>/non-effettuata/', views.operator_not_done, name='operator_not_done'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
