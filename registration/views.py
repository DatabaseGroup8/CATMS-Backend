from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
import json
import logging
from datetime import date, time
from django.db import DatabaseError
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.http import JsonResponse
from django.db import connection, DatabaseError
from django.views.decorators.http import require_GET
from accounts.decorators import jwt_required
from django.db import transaction
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@csrf_exempt
@jwt_required(allowed_roles=['Receptionist', 'Doctor'])
def search_patients(request):
    # Step 1: Enforce GET method since we are reading data
    if request.method == 'GET':
        # Grab the search term from the URL (e.g., /api/registration/search/?q=Kamal)
        # Defaults to an empty string if no search term is provided
        search_query = request.GET.get('q', '')
        
        try:
            with connection.cursor() as cursor:
                # Add SQL wildcards (%) to find partial matches anywhere in the string
                search_pattern = f"%{search_query}%"
                
                # Step 2: Execute raw SQL with the LIKE operator using your exact schema
                cursor.execute("""
                    SELECT 
                        patient_id, 
                        full_name, 
                        DOB, 
                        CalculateAge(DOB) AS age,
                        contact_no,
                        NIC
                    FROM Patient
                    WHERE full_name LIKE %s
                       OR contact_no LIKE %s
                       OR NIC LIKE %s
                    ORDER BY full_name ASC
                    LIMIT 50;
                """, [search_pattern, search_pattern, search_pattern])
                
                # Step 3: Fetch all matching rows
                rows = cursor.fetchall()
                
            # Step 4: Map the raw tuple data into a JSON-friendly list of dictionaries
            patients_list = []
            for row in rows:
                patients_list.append({
                    'patient_id': row[0],
                    'full_name': row[1],
                    # Convert date object to a standard string format securely
                    'DOB': row[2].strftime('%Y-%m-%d') if row[2] else None,
                    'age': row[3],
                    'contact_no': row[4],
                    'NIC': row[5]
                })

            # Step 5: Return the payload
            return JsonResponse({
                'status': 'success',
                'results_count': len(patients_list),
                'data': patients_list
            }, status=200)

        except Exception as e:
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method is allowed'}, status=405)



@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Receptionist'])
def quick_register_patient(request):

    branch_id = getattr(request, 'branch_id', None)

    if branch_id is None:
        return JsonResponse({
            'status': 'error',
            'message': 'Branch context missing.'
        }, status=403)

    try:
        data = json.loads(request.body)

        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object.')

        def get_text(field):
            value = data.get(field)

            if value is None:
                return None

            if not isinstance(value, str):
                raise ValueError(f'{field} must be a string.')

            return value.strip() or None

        full_name = get_text('full_name')
        contact_no = get_text('contact_no')
        nic = get_text('NIC')
        gender = get_text('gender')
        dob_string = data.get('DOB')

        if not full_name:
            raise ValueError('Full name is required.')

        if len(full_name) > 100:
            raise ValueError('Full name is too long.')

        for value, limit, field in [
            (contact_no, 20, 'contact_no'),
            (nic, 20, 'NIC'),
            (gender, 20, 'gender')
        ]:
            if value is not None and len(value) > limit:
                raise ValueError(f'{field} is too long.')

        if not isinstance(dob_string, str) or not dob_string:
            raise ValueError('Date of birth is required.')

        try:
            dob = date.fromisoformat(dob_string)
        except ValueError:
            raise ValueError('DOB must be YYYY-MM-DD.')

        if dob > date.today():
            raise ValueError(
                'Date of birth cannot be in the future.'
            )

    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

    try:
        with connection.cursor() as cursor:

            # Call RegisterPatient stored procedure
            cursor.execute("""
                CALL RegisterPatient(
                    %s, %s, %s, %s, %s, %s,
                    @patient_id,
                    @success,
                    @message
                )
            """, [
                branch_id,
                full_name,
                contact_no,
                dob,
                nic,
                gender
            ])

            while cursor.nextset():
                pass

            # Retrieve procedure outputs
            cursor.execute("""
                SELECT @patient_id, @success, @message
            """)

            patient_id, success, message = cursor.fetchone()

            if not success:
                return JsonResponse({
                    'status': 'error',
                    'message': message
                }, status=400)

            # Calculate current age using the SQL function
            cursor.execute("""
                SELECT CalculateAge(DOB)
                FROM Patient
                WHERE patient_id = %s
            """, [patient_id])

            result = cursor.fetchone()
            age = result[0] if result else None

        return JsonResponse({
            'status': 'success',
            'message': message,
            'data': {
                'patient_id': patient_id,
                'full_name': full_name,
                'contact_no': contact_no,
                'DOB': dob.isoformat(),
                'age': age,
                'NIC': nic,
                'gender': gender,
                'registered_branch_id': branch_id
            }
        }, status=201)

    except DatabaseError:
        logger.exception('Quick patient registration failed')

        return JsonResponse({
            'status': 'error',
            'message': 'Unable to register patient.'
        }, status=500)


@csrf_exempt
@jwt_required(allowed_roles=['Receptionist', 'Doctor'])
def get_patient_appointments(request):
    # Check that the request uses the GET Method
    if request.method == 'GET':
        try:
            # Get the patient ID and optional appointment status from the query parameters
            patient_id = request.GET.get('patient_id')
            status = request.GET.get('status')

            # Patient ID is required
            if not patient_id:
                return JsonResponse({
                    'status':'error',
                    'message':'patient_id is required'
                }, status = 400)

            # Open a database cursor to execute raw SQL
            with connection.cursor() as cursor:

                # Retrieve the patient's appointments
                # A status filter is applied only when a status is provided
                cursor.execute("""
                    SELECT
                        a.appointment_id,
                        a.patient_id,
                        a.time_slot_id,
                        a.type,
                        a.status,
                        a.notes,
                        a.updated_at,
                        a.created_at,
                        ts.doctor_id,
                        ts.branch_id,
                        ts.available_date,
                        ts.start_time,
                        ts.end_time
                    FROM Appointment a
                    JOIN Time_Slot ts
                        ON a.time_slot_id = ts.time_slot_id
                    WHERE a.patient_id = %s
                    AND (%s IS NULL OR a.status = %s)
                    ORDER BY ts.available_date DESC, ts.start_time DESC;\
                """,[
                    patient_id,
                    status,
                    status
                ])

                # Retrieve all matching appointment records
                rows = cursor.fetchall()

                # Get the column names returned by the query
                columns = [column[0] for column in cursor.description]

                # Convert each database row into a dictionary
                appointments = [
                    dict(zip(columns, row))
                    for row in rows
                ]

                # Use the required SQL function to calculate the total no of appointments for the patient
                cursor.execute("""
                    SELECT CountPatientAppointments(%s, %s);
                """, [
                    patient_id,
                    status
                ])

                # Get the total appointment count
                total_appointments = cursor.fetchone()[0]

            # Return the appointments and total count as JSON
            return JsonResponse({
                'status':'success',
                'patient_id':int(patient_id),
                'total_appointments':total_appointments,
                'appointments': appointments
            }, status = 200)

        # Handle the unexpected database or server errors
        except Exception as e:
            return JsonResponse({
                'status':'critical_error',
                'message':str(e)
            }, status = 500)


    # Reject requests that are not GET
    return JsonResponse({
        'status':'error',
        'message':'Only GET method is allowed'
    }, status = 405)

@require_POST
@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
def create_time_slot(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('JSON object required')
        doctor_id = data.get('doctor_id')
        available = data.get('available', True)
        if type(doctor_id) is not int or doctor_id <= 0:
            raise ValueError('doctor_id must be positive integer')
        if type(available) is not bool:
            raise ValueError('available must be boolean')
        slot_date = date.fromisoformat(data['available_date'])
        start = time.fromisoformat(data['start_time'])
        end = time.fromisoformat(data['end_time'])
        if start.tzinfo or end.tzinfo or end <= start:
            raise ValueError('Invalid time range')
        if slot_date < timezone.localdate():
            raise ValueError('Cannot create past slot')
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return JsonResponse({'success': False,
            'error': 'Invalid slot data'}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT 1 FROM Employee
                WHERE employee_id=%s AND branch_id=%s
                AND role='Receptionist' AND status='Active'
            ''', [employee_id, branch_id])
            if cursor.fetchone() is None:
                return JsonResponse({'success': False,
                    'error': 'Access denied'}, status=403)
            cursor.execute('''
                SET @slot_id=NULL, @slot_message=NULL,
                @slot_success=0
            ''')
            cursor.execute('''
                CALL AddTimeSlot(
                %s,%s,%s,%s,%s,%s,
                @slot_id,@slot_message,@slot_success
                )
            ''', [doctor_id, branch_id, slot_date,
                  start, end, available])
            while cursor.nextset():
                pass
            cursor.execute('SELECT @slot_id,@slot_message,@slot_success')
            slot_id, message, success = cursor.fetchone()
        if not success:
            return JsonResponse({'success': False,
                    'error': message or 'Slot rejected'}, status=409)
        return JsonResponse({'success': True,
                    'time_slot_id': slot_id,
                    'available': available}, status=201)
    except DatabaseError:
        logger.exception('Create slot failed')
        return JsonResponse({'success': False,
            'error': 'Database error'}, status=500)

@require_POST
@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
def book_appointment(request):
    """POST JSON: patient_id, time_slot_id, type (optional), and notes (optional).

    Requires BookAppointment in MySQL, which locks the daily slot during booking
    and dynamically generates an incrementing queue token.
    """
    # Reject malformed JSON and invalid fields before calling the database.
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("The request body must be a JSON object.")
            
        for field in ("patient_id", "time_slot_id"):
            if type(data.get(field)) is not int or data[field] <= 0:
                raise ValueError(f"{field} must be a positive integer.")
                
        notes = data.get("notes", "")
        if not isinstance(notes, str):
            raise ValueError("notes must be a string.")
            
        # Extract the appointment type, defaulting to 'General' if omitted
        appointment_type = data.get("type", "General")
        if not isinstance(appointment_type, str):
            raise ValueError("type must be a string.")
            
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            # Initialize MySQL session variables, including the new @appointment_number
            cursor.execute(
                "SET @appointment_id = NULL, @appointment_number = NULL, "
                "@booking_message = NULL, @booking_success = 0"
            )
            
            # Call the stored procedure with the newly required 'type' parameter
            cursor.execute(
                "CALL BookAppointment(%s, %s, %s, %s, %s, @appointment_id, @appointment_number, @booking_message, @booking_success)",
                [data["patient_id"], data["time_slot_id"], appointment_type, notes, request.employee_id],
            )
            
            # Consume CALL result sets to prevent "Commands out of sync" errors
            while cursor.nextset():
                pass
                
            # Fetch the generated IDs and status flags back into Python
            cursor.execute("SELECT @appointment_id, @appointment_number, @booking_message, @booking_success")
            appointment_id, appointment_number, message, success = cursor.fetchone()
            
    # Keep database diagnostics in server logs and return a generic error.
    except DatabaseError:
        logger.exception("Failed to book appointment")
        return JsonResponse({"success": False, "error": "Unable to book appointment."}, status=500)
        
    # Handle logical failures returned by the procedure (e.g., patient not found)
    if not success:
        logger.warning("BookAppointment failed: %s", message)
        # Use the specific message generated by the SQL procedure if available
        error_msg = message if message else "Appointment could not be booked. Check availability."
        return JsonResponse({"success": False, "error": error_msg}, status=400)
        
    # Return both the database ID and the critical queue token to the frontend
    return JsonResponse({
        "success": True, 
        "appointment_id": appointment_id,
        "token_number": appointment_number
    }, status=201)
    
    

@jwt_required(allowed_roles=['Receptionist', 'Doctor'])
@require_GET
def get_daily_schedule(request):
    """Show sessions by branch/date. Capacity is NOT modeled in current schema."""
    try:
        raw_date = request.GET.get('date')
        selected_date = date.fromisoformat(raw_date) if raw_date else date.today()
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)
        if branch_id <= 0 or employee_id <= 0:
            raise ValueError('Invalid JWT context')
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid date or employee context'}, status=400)
    # Doctors only see their own schedule; receptionists see all branch doctors.
    doctor_only = request.user_role == 'Doctor'
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT ts.time_slot_id, u.full_name,
                       COALESCE(spec.specializations, 'Not assigned'),
                       ts.available_date, ts.start_time, ts.end_time,
                       COALESCE(booked.current_patients, 0), ts.available
                FROM Time_Slot ts
                JOIN Doctor d ON d.doctor_id = ts.doctor_id
                JOIN Employee e ON e.employee_id = d.employee_id
                JOIN `User` u ON u.user_id = e.user_id
                LEFT JOIN (
                    SELECT ds.doctor_id,
                           GROUP_CONCAT(s.specialization_name ORDER BY s.specialization_name SEPARATOR ', ')
                           AS specializations
                    FROM Doctor_Specialization ds
                    JOIN Specialization s ON s.specialization_id = ds.specialization_id
                    GROUP BY ds.doctor_id
                ) spec ON spec.doctor_id = d.doctor_id
                LEFT JOIN (
                    SELECT time_slot_id, COUNT(*) AS current_patients
                    FROM Appointment WHERE status = 'Scheduled'
                    GROUP BY time_slot_id
                ) booked ON booked.time_slot_id = ts.time_slot_id
                WHERE ts.available_date = %s AND ts.branch_id = %s
                  AND e.branch_id = ts.branch_id AND e.status = 'Active'
                  AND EXISTS (
                      SELECT 1 FROM Employee actor
                      WHERE actor.employee_id = %s AND actor.branch_id = ts.branch_id
                        AND actor.status = 'Active' AND actor.role = %s
                  )
                  AND (%s = 0 OR e.employee_id = %s)
                ORDER BY ts.start_time, u.full_name
            """, [selected_date, branch_id, employee_id, request.user_role,
                    int(doctor_only), employee_id])
            rows = cursor.fetchall()
    except DatabaseError:
        logger.exception('Unable to fetch schedule')
        return JsonResponse({'status':'error','message':'Unable to retrieve schedule'}, status=500)
    data = []
    for r in rows:
        # No capacity field exists, so don't report Fully Booked based on an invented limit.
        data.append({
                        'time_slot_id': r[0],
                        'doctor_name': r[1],
                        'specialty': r[2],
                        'date': str(r[3]),
                        'start_time': str(r[4]),
                        'end_time': str(r[5]),
                        'booked_count': r[6],
                        'available': bool(r[7]),
                        'status': 'Open' if r[7] else 'Closed'
                    })
    return JsonResponse({'status':'success','date':str(selected_date),
                         'branch_id':branch_id, 'count':len(data), 'data': data})

@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
@require_http_methods(['PATCH'])
def update_time_slot_availability(request, slot_id):
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise ValueError('JSON object required')
        available = body.get('available')
        if type(available) is not bool:
            raise ValueError('available must be boolean')
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)

    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        return JsonResponse({'success': False,
                             'error': 'Invalid request'}, status=400)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('''
                    SELECT 1 FROM Employee
                    WHERE employee_id=%s AND branch_id=%s
                      AND role='Receptionist' AND status='Active'
                ''', [employee_id, branch_id])
                if cursor.fetchone() is None:
                    return JsonResponse({'success': False,
                                         'error': 'Access denied'}, status=403)
                cursor.execute('''
                    SELECT available,available_date FROM Time_Slot
                    WHERE time_slot_id=%s AND branch_id=%s FOR UPDATE
                ''', [slot_id, branch_id])
                slot = cursor.fetchone()
                if slot is None:
                    return JsonResponse({'success': False,
                                         'error': 'Slot not found'}, status=404)
                if slot[1] < timezone.localdate():
                    return JsonResponse({'success': False,
                                         'error': 'Cannot edit past slot'}, status=400)
                if bool(slot[0]) != available:
                    cursor.execute('''
                        UPDATE Time_Slot SET available=%s
                        WHERE time_slot_id=%s
                    ''', [available, slot_id])
                cursor.execute('''
                    SELECT COUNT(*) FROM Appointment
                    WHERE time_slot_id=%s AND status='Scheduled'
                ''', [slot_id])
                booked = cursor.fetchone()[0]
        return JsonResponse({'success': True,
                             'time_slot_id': slot_id,
                             'available': available,
                             'scheduled_appointments': booked})
    except DatabaseError:
        logger.exception('Update slot availability failed')
        return JsonResponse({'success': False,
                             'error': 'Database error'}, status=500)

# ---------------------------------------------------------------------------
# Receptionist appointment management: list, reschedule, cancel.
# Requires database/appointment_changes.sql to have been executed once.
# ---------------------------------------------------------------------------
@require_GET
@jwt_required(allowed_roles=['Receptionist'])
def manage_appointments(request):
    """Appointments for the signed-in receptionist's branch and selected date."""
    try:
        selected_date = date.fromisoformat(request.GET.get('date', ''))
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'error', 'message': 'date must be YYYY-MM-DD'}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT 1 FROM Employee
                WHERE employee_id=%s AND branch_id=%s
                  AND role='Receptionist' AND status='Active'
            ''', [employee_id, branch_id])
            if cursor.fetchone() is None:
                return JsonResponse({'status': 'error', 'message': 'Access denied'}, status=403)

            cursor.execute('''
                SELECT a.appointment_id, a.patient_id, p.full_name,
                       a.time_slot_id, a.appointment_number, a.type,
                       a.status, a.notes, ts.available_date, ts.start_time,
                       ts.end_time, u.full_name AS doctor_name
                FROM Appointment a
                JOIN Patient p ON p.patient_id = a.patient_id
                JOIN Time_Slot ts ON ts.time_slot_id = a.time_slot_id
                JOIN Doctor d ON d.doctor_id = ts.doctor_id
                JOIN Employee e ON e.employee_id = d.employee_id
                JOIN `User` u ON u.user_id = e.user_id
                WHERE ts.branch_id = %s AND ts.available_date = %s
                ORDER BY ts.start_time ASC, a.appointment_number ASC
            ''', [branch_id, selected_date])
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for row in rows:
            row['available_date'] = row['available_date'].isoformat()
            row['start_time'] = str(row['start_time'])
            row['end_time'] = str(row['end_time'])

        return JsonResponse({
            'status': 'success', 'date': selected_date.isoformat(),
            'data': rows, 'count': len(rows)
        })
    except DatabaseError:
        logger.exception('Cannot load appointments for management')
        return JsonResponse({'status': 'error', 'message': 'Could not retrieve appointments'}, status=500)


def _appointment_change_body(request, expect_slot=False):
    """Validate JSON before executing privileged stored procedures."""
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValueError('Valid JSON is required')
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    reason = data.get('reason', '')
    if not isinstance(reason, str) or len(reason) > 500:
        raise ValueError('reason must be text of at most 500 characters')
    if expect_slot:
        slot = data.get('new_time_slot_id')
        if type(slot) is not int or slot < 1:
            raise ValueError('new_time_slot_id must be a positive integer')
        return (slot, reason.strip())
    if len(reason.strip()) < 3:
        raise ValueError('Provide a cancellation reason of at least 3 characters')
    return reason.strip()


@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Receptionist'])
def reschedule_appointment(request, appointment_id):
    """Move only a Scheduled appointment into an open session of this branch."""
    try:
        new_slot_id, reason = _appointment_change_body(request, expect_slot=True)
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)
    except (ValueError, TypeError, AttributeError) as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SET @reschedule_number=NULL, @reschedule_message=NULL,
                    @reschedule_success=0
            ''')
            cursor.execute('''
                CALL RescheduleAppointment(
                    %s,%s,%s,%s,%s,
                    @reschedule_number,@reschedule_message,@reschedule_success
                )
            ''', [appointment_id, new_slot_id, employee_id, branch_id, reason])
            while cursor.nextset():
                pass
            cursor.execute('''
                SELECT @reschedule_number,@reschedule_message,@reschedule_success
            ''')
            queue_number, message, success = cursor.fetchone()
    except DatabaseError:
        logger.exception('Reschedule appointment failed')
        return JsonResponse({'status': 'error', 'message': 'Rescheduling failed in the database'}, status=500)

    if not success:
        return JsonResponse({'status': 'error', 'message': message or 'Rescheduling rejected'}, status=409)
    return JsonResponse({
        'status': 'success', 'appointment_id': appointment_id,
        'new_time_slot_id': new_slot_id, 'token_number': queue_number,
        'message': message
    })


@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Receptionist'])
def cancel_appointment(request, appointment_id):
    """Soft-cancel a Scheduled appointment without deleting its record."""
    try:
        reason = _appointment_change_body(request)
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)
    except (ValueError, TypeError, AttributeError) as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SET @cancel_message=NULL, @cancel_success=0
            ''')
            cursor.execute('''
                CALL CancelAppointment(
                    %s,%s,%s,%s,@cancel_message,@cancel_success
                )
            ''', [appointment_id, employee_id, branch_id, reason])
            while cursor.nextset():
                pass
            cursor.execute('SELECT @cancel_message,@cancel_success')
            message, success = cursor.fetchone()
    except DatabaseError:
        logger.exception('Cancel appointment failed')
        return JsonResponse({'status': 'error', 'message': 'Cancellation failed in the database'}, status=500)

    if not success:
        return JsonResponse({'status': 'error', 'message': message or 'Cancellation rejected'}, status=409)
    return JsonResponse({
        'status': 'success', 'appointment_id': appointment_id,
        'status_value': 'Cancelled', 'message': message
    })
