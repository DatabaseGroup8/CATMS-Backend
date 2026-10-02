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
                
                # Step 2: Execute raw SQL with the LIKE operator
                cursor.execute("""
                    SELECT 
                        patient_id, 
                        first_name, 
                        last_name, 
                        date_of_birth, 
                        CalculateAge(date_of_birth) AS age,
                        contact_number
                    FROM Patient
                    WHERE first_name LIKE %s 
                       OR last_name LIKE %s 
                       OR contact_number LIKE %s
                    ORDER BY first_name ASC
                    LIMIT 50;
                """, [search_pattern, search_pattern, search_pattern])
                
                # Step 3: Fetch all matching rows
                rows = cursor.fetchall()
                
            # Step 4: Map the raw tuple data into a JSON-friendly list of dictionaries
            patients_list = []
            for row in rows:
                patients_list.append({
                    'patient_id': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    # Convert date object to a standard string format
                    'date_of_birth': row[3].strftime('%Y-%m-%d') if row[3] else None,
                    'age': row[4],
                    'contact_number': row[4]
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


def get_patient_appointments(request):
    # Check that the request uses the GET Method
    if request == 'GET':
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
def create_time_slot(request):
    """POST JSON: doctor_id, branch_id, available_date, start_time, end_time.

    Dates use YYYY-MM-DD and times use HH:MM[:SS]. Requires the MySQL
    CreateTimeSlot procedure; it must enforce schedule overlap constraints.
    """
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

        available_date = date.fromisoformat(data["available_date"])
        start_time = time.fromisoformat(data["start_time"])
        end_time = time.fromisoformat(data["end_time"])
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
            cursor.execute("SET @slot_id = NULL, @slot_message = NULL, @slot_success = 0")
            cursor.execute(
                "CALL CreateTimeSlot(%s, %s, %s, %s, %s, @slot_id, @slot_message, @slot_success)",
                [data["doctor_id"], data["branch_id"], available_date, start_time, end_time],
            )
            while cursor.nextset():
                pass
            cursor.execute("SELECT @slot_id, @slot_message, @slot_success")
            slot_id, message, success = cursor.fetchone()
    except DatabaseError:
        logger.exception("Failed to create time slot")
        return JsonResponse({"success": False, "error": "Unable to create time slot."}, status=500)
    if not success:
        logger.warning("CreateTimeSlot failed: %s", message)
        return JsonResponse({"success": False, "error": "Time slot could not be created. Check the doctor, branch and schedule."}, status=400)
    return JsonResponse({"success": True, "time_slot_id": slot_id}, status=201)


@require_POST
def book_appointment(request):
    """POST JSON: patient_id, time_slot_id and optional notes.

    Requires BookAppointment in MySQL, which locks the slot during booking.
    """
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
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SET @appointment_id = NULL, @booking_message = NULL, @booking_success = 0")
            cursor.execute(
                "CALL BookAppointment(%s, %s, %s, @appointment_id, @booking_message, @booking_success)",
                [data["patient_id"], data["time_slot_id"], notes],
            )
            while cursor.nextset():
                pass
            cursor.execute("SELECT @appointment_id, @booking_message, @booking_success")
            appointment_id, message, success = cursor.fetchone()
    except DatabaseError:
        logger.exception("Failed to book appointment")
        return JsonResponse({"success": False, "error": "Unable to book appointment."}, status=500)
    if not success:
        logger.warning("BookAppointment failed: %s", message)
        return JsonResponse({"success": False, "error": "Appointment could not be booked. Check the patient and slot availability."}, status=400)
    return JsonResponse({"success": True, "appointment_id": appointment_id}, status=201)
