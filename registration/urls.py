# registration/urls.py
from django.urls import path
from . import views
from . import directory_views

urlpatterns = [
    path('search/', views.search_patients, name='search_patients'),

    # GET: /api/registration/patient-appointments/?patient_id=5
    # Retrieves all appointments for a specific patient and returns the total appointment count
    path('patient-appointments/', views.get_patient_appointments, name= 'get_patient_appointments'),
    
    
    path(
        'patients/quick-register/',
        views.quick_register_patient,
        name='quick_register_patient'
    ),

    path(
        'time-slots/create/',
        views.create_time_slot,
        name='create_time_slot'
    ),

    path(
        'appointments/book/',
        views.book_appointment,
        name='book_appointment'
    ),

    # Receptionist appointment rescheduling and cancellation.
    path('appointments/manage/', views.manage_appointments, name='manage_appointments'),
    path('appointments/<int:appointment_id>/reschedule/',
         views.reschedule_appointment, name='reschedule_appointment'),
    path('appointments/<int:appointment_id>/cancel/',
         views.cancel_appointment, name='cancel_appointment'),

    path(
        'schedules/daily/',
        views.get_daily_schedule,
        name='get_daily_schedule'
    ),

    path(
        'time-slots/<int:slot_id>/availability/',
        views.update_time_slot_availability,
        name='update_time_slot_availability'
        ),

    path(
    'doctors/',
    directory_views.list_doctors,
    name='list_doctors'
        ),

    path(
    'patients/<int:patient_id>/',
    directory_views.get_patient_details,
    name='get_patient_details'
        ),
]