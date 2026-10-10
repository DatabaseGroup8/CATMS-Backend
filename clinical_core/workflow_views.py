"""Doctor schedule/completion and receptionist catalogue search/add API views."""
import json
import logging
from datetime import date
from decimal import Decimal
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from accounts.decorators import jwt_required
from billing.workflow_common import (
    bad, payload, positive_int, text_value, amount, parse_date,
    call_out, procedure_failed,
)

logger = logging.getLogger(__name__)


@jwt_required(allowed_roles=['Doctor'])
@require_GET
def get_doctor_appointments(request):
    try:
        selected = parse_date(request.GET.get('date', date.today().isoformat()))
        employee_id = positive_int(request.employee_id, 'employee_id')
        branch_id = positive_int(request.branch_id, 'branch_id')
    except (ValueError, AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT a.appointment_id, a.patient_id, p.full_name,
                       a.appointment_number, a.status, a.type,
                       ts.time_slot_id, ts.available_date, ts.start_time, ts.end_time
                FROM Appointment a
                JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
                JOIN Doctor d ON d.doctor_id=ts.doctor_id
                JOIN Employee e ON e.employee_id=d.employee_id
                JOIN Patient p ON p.patient_id=a.patient_id
                WHERE e.employee_id=%s AND e.branch_id=%s AND e.status='Active'
                  AND e.role='Doctor' AND ts.branch_id=e.branch_id
                  AND ts.available_date=%s
                ORDER BY ts.start_time, a.appointment_number
            """, [employee_id, branch_id, selected])
            rows = cursor.fetchall()
    except DatabaseError:
        logger.exception('Doctor appointment lookup failed')
        return bad('Could not retrieve appointments', 500)
    return JsonResponse({'status': 'success', 'appointments': [
        {'appointment_id': r[0], 'patient_id': r[1], 'patient_name': r[2],
         'appointment_number': r[3], 'status': r[4], 'type': r[5],
         'time_slot_id': r[6], 'date': str(r[7]),
         'start_time': str(r[8]), 'end_time': str(r[9])} for r in rows]})


@csrf_exempt
@jwt_required(allowed_roles=['Doctor'])
@require_POST
def mark_appointment_completed(request, appointment_id):
    try:
        employee_id = positive_int(request.employee_id, 'employee_id')
    except (ValueError, AttributeError) as exc:
        return bad(str(exc), 403)
    try:
        with connection.cursor() as cursor:
            success, message = call_out(
                cursor,
                'CALL MarkAppointmentCompleted(%s, %s, @complete_ok, @complete_msg)',
                [appointment_id, employee_id],
                'SELECT @complete_ok, @complete_msg',
            )
    except DatabaseError:
        logger.exception('Doctor completion failed')
        return bad('Could not complete appointment', 500)
    if not success:
        return procedure_failed(logger, 'MarkAppointmentCompleted', message)
    return JsonResponse({'status': 'success', 'appointment_id': appointment_id,
                         'message': message})


@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def search_medications(request):
    q = request.GET.get('q', '').strip()
    if len(q) > 100:
        return bad('Search text too long')
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT medication_id,generic_name,manufacturer,form,price
                FROM Medication WHERE generic_name LIKE %s
                ORDER BY generic_name LIMIT 50
            """, ['%' + q + '%'])
            rows = cursor.fetchall()
    except DatabaseError:
        logger.exception('Medication search failed')
        return bad('Search unavailable', 500)
    return JsonResponse({'status': 'success', 'data': [
        {'medication_id': r[0], 'generic_name': r[1], 'manufacturer': r[2],
         'form': r[3], 'price': str(r[4]) if r[4] is not None else None}
        for r in rows]})


@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def search_treatments(request):
    q = request.GET.get('q', '').strip()
    if len(q) > 100:
        return bad('Search text too long')
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT tc.treatment_service_code,tc.treatment_name,
                    tc.base_price,tc.insurance_eligible,c.category_name
                FROM Treatment_Catalogue tc
                LEFT JOIN Treatment_Category c ON c.treatment_category_id=tc.treatment_category_id
                WHERE tc.treatment_name LIKE %s
                ORDER BY tc.treatment_name LIMIT 50
            """, ['%' + q + '%'])
            rows = cursor.fetchall()
    except DatabaseError:
        logger.exception('Treatment search failed')
        return bad('Search unavailable', 500)
    return JsonResponse({'status': 'success', 'data': [
        {'treatment_service_code': r[0], 'treatment_name': r[1],
         'base_price': str(r[2]) if r[2] is not None else None,
         'insurance_eligible': bool(r[3]), 'category_name': r[4]}
        for r in rows]})


@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
@require_POST
def add_medication(request):
    try:
        data = payload(request)
        name = text_value(data.get('generic_name'), 'generic_name', 100, True)
        manufacturer = text_value(data.get('manufacturer'), 'manufacturer', 100)
        form = text_value(data.get('form'), 'form', 50)
        contra = text_value(data.get('contraindications'), 'contraindications', 255)
        effects = text_value(data.get('side_effects'), 'side_effects', 255)
        price = amount(data.get('price'), 'price', allow_zero=True)
    except ValueError as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            med_id, message, success = call_out(
                cursor,
                'CALL AddMedication(%s,%s,%s,%s,%s,%s,@med_id,@med_msg,@med_ok)',
                [name, manufacturer, form, contra, effects, price],
                'SELECT @med_id,@med_msg,@med_ok'
            )
    except DatabaseError:
        logger.exception('Medication creation failed')
        return bad('Unable to add medication', 500)
    if not success:
        return procedure_failed(logger, 'AddMedication', message)
    return JsonResponse({'status': 'success', 'medication_id': med_id}, status=201)



@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
@require_POST
def add_treatment_catalogue(request):
    try:
        data = payload(request)
        category = positive_int(data.get('treatment_category_id'), 'treatment_category_id')
        name = text_value(data.get('treatment_name'), 'treatment_name', 100, True)
        price = amount(data.get('base_price'), 'base_price', allow_zero=True)
        duration = text_value(data.get('duration'), 'duration', 50)
        eligible = data.get('insurance_eligible', False)
        if type(eligible) is not bool:
            raise ValueError('insurance_eligible must be boolean')
    except ValueError as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Treatment_Catalogue
                  (treatment_category_id,treatment_name,base_price,duration,updated_date,insurance_eligible)
                VALUES (%s,%s,%s,%s,CURDATE(),%s)
            """, [category, name, price, duration, eligible])
            code = cursor.lastrowid
    except DatabaseError:
        logger.exception('Treatment catalogue creation failed')
        return bad('Unable to add treatment', 500)
    return JsonResponse({'status': 'success', 'treatment_service_code': code}, status=201)
