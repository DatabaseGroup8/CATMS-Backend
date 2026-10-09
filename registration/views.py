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

logger = logging.getLogger(__name__)


@csrf_exempt
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
def quick_register_patient(request):
    try:
        data = json.loads(request.body)
        
        # Extract the active branch from the frontend header
        branch_id = request.headers.get('X-Branch-ID')
        if not branch_id:
            return JsonResponse({'status': 'error', 'message': 'Branch context missing.'}, status=401)
        
        # Extract matching your exact schema
        full_name = data.get('full_name', '').strip()
        contact_no = data.get('contact_no', '').strip()
        dob = data.get('DOB')  # Expected format: 'YYYY-MM-DD'
        nic = data.get('NIC', '').strip()
        gender = data.get('gender', '').strip()
        
        if not full_name:
            return JsonResponse({'status': 'error', 'message': 'Full name is required.'}, status=400)
            
        with connection.cursor() as cursor:
            # Insert using your exact column names
            cursor.execute("""
                INSERT INTO Patient (full_name, contact_no, DOB, NIC, gender, registered_branch_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, [full_name, contact_no, dob, nic, gender, branch_id])
            
            cursor.execute("SELECT LAST_INSERT_ID();")
            new_patient_id = cursor.fetchone()[0]
            
        return JsonResponse({
            'status': 'success',
            'data': {
                'patient_id': new_patient_id,
                'full_name': full_name,
                'contact_no': contact_no,
                'DOB': dob
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)

@csrf_exempt
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
    
    

@require_GET
def get_daily_schedule(request):
    """
    Retrieves the doctor schedule (time slots) for a specific date and branch.
    Expects an optional query parameter: ?date=YYYY-MM-DD (defaults to today).
    """
    try:
        target_date_str = request.GET.get('date')
        target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()

        branch_id = request.headers.get('X-Branch-ID')
        if not branch_id:
            return JsonResponse({'status': 'error', 'message': 'X-Branch-ID header is required.'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    ts.time_slot_id,
                    u.full_name AS doctor_name,
                    e.role AS specialty, 
                    ts.available_date,
                    ts.start_time,
                    ts.end_time,
                    ts.current_patients,
                    ts.max_patients
                FROM Time_Slot ts
                JOIN Doctor d ON ts.doctor_id = d.doctor_id
                JOIN Employee e ON d.employee_id = e.employee_id
                JOIN User u ON e.user_id = u.user_id
                WHERE ts.available_date = %s 
                  AND e.branch_id = %s
                ORDER BY ts.start_time ASC;
            """, [target_date, branch_id])
            
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

        schedule_list = []
        for row in rows:
            slot_data = dict(zip(columns, row))
            
            current_count = slot_data['current_patients'] or 0
            max_count = slot_data['max_patients'] or 0
            
            # Dynamic capacity logic
            status = "Available" if current_count < max_count else "Fully Booked"

            schedule_list.append({
                'time_slot_id': slot_data['time_slot_id'],
                'doctor_name': slot_data['doctor_name'],
                'specialty': slot_data['specialty'],
                'date': slot_data['available_date'].strftime('%Y-%m-%d') if slot_data['available_date'] else None,
                'start_time': str(slot_data['start_time']), 
                'end_time': str(slot_data['end_time']),
                'current_patients': current_count,
                'max_patients': max_count,
                'status': status
            })

        return JsonResponse({
            'status': 'success',
            'date': target_date.strftime('%Y-%m-%d'),
            'branch_id': int(branch_id),
            'count': len(schedule_list),
            'data': schedule_list
        }, status=200)

    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
    except DatabaseError:
        logger.exception("Database error in get_daily_schedule")
        return JsonResponse({'status': 'critical_error', 'message': 'Unable to retrieve schedule.'}, status=500)
    except Exception as e:
        logger.exception("Unexpected error in get_daily_schedule")
        return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
