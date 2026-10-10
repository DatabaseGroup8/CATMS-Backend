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
                        contact_no
                    FROM Patient
                    WHERE full_name LIKE %s 
                       OR contact_no LIKE %s
                    ORDER BY full_name ASC
                    LIMIT 50;
                """, [search_pattern, search_pattern])
                
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
                    'contact_no': row[4]
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
    """POST JSON: doctor_id, branch_id, available_date, start_time, end_time.

    Dates use YYYY-MM-DD and times use HH:MM[:SS]. Requires the MySQL
    CreateTimeSlot procedure; it must enforce schedule overlap constraints.
    """
    # Reject malformed JSON and invalid fields before calling the database.
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("The request body must be a JSON object.")
        for field in ("doctor_id", "branch_id"):
            if type(data.get(field)) is not int or data[field] <= 0:
                raise ValueError(f"{field} must be a positive integer.")
        for field in ("available_date", "start_time", "end_time"):
            if not isinstance(data.get(field), str):
                raise ValueError(f"{field} is required and must be a string.")
            
        # Parse dates and times so comparisons use actual date/time values.
        available_date = date.fromisoformat(data["available_date"])
        start_time = time.fromisoformat(data["start_time"])
        end_time = time.fromisoformat(data["end_time"])
        # MySQL TIME fields here represent local times without UTC offsets.
        if start_time.tzinfo is not None or end_time.tzinfo is not None:
            raise ValueError("Times must be local times without a UTC offset.")
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time.")
        if available_date < timezone.localdate():
            raise ValueError("available_date must not be in the past.")
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            # Reset connection-scoped variables that receive the procedure outputs.
            cursor.execute("SET @slot_id = NULL, @slot_message = NULL, @slot_success = 0")
            # Bind request values as parameters; the procedure manages its transaction.
            cursor.execute(
                "CALL AddTimeSlot(%s, %s, %s, %s, %s, @slot_id, @slot_message, @slot_success)",
                [data["doctor_id"], data["branch_id"], available_date, start_time, end_time],
            )
            # Consume CALL result sets before selecting its OUT parameters.
            while cursor.nextset():
                pass
            cursor.execute("SELECT @slot_id, @slot_message, @slot_success")
            slot_id, message, success = cursor.fetchone()
    # Keep database diagnostics in server logs and return a generic error.
    except DatabaseError:
        logger.exception("Failed to create time slot")
        return JsonResponse({"success": False, "error": "Unable to create time slot."}, status=500)
    # Handle failures returned by the procedure, even when CALL itself succeeds.
    if not success:
        logger.warning("CreateTimeSlot failed: %s", message)
        return JsonResponse({"success": False, "error": "Time slot could not be created. Check the doctor, branch and schedule."}, status=400)
    # Return the new record ID with HTTP 201 (Created).
    return JsonResponse({"success": True, "time_slot_id": slot_id}, status=201)


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
                "CALL BookAppointment(%s, %s, %s, %s, @appointment_id, @appointment_number, @booking_message, @booking_success)",
                [data["patient_id"], data["time_slot_id"], appointment_type, notes],
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
                       COALESCE(booked.current_patients, 0), ts.is_booked
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
            'time_slot_id': r[0], 'doctor_name': r[1], 'specialty': r[2],
            'date': str(r[3]), 'start_time': str(r[4]), 'end_time': str(r[5]),
            'current_patients': r[6], 'max_patients': None,
            'status': 'Closed' if r[7] else 'Open',
        })
    return JsonResponse({'status':'success','date':str(selected_date),
                         'branch_id':branch_id, 'count':len(data), 'data': data})
