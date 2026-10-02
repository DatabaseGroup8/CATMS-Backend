from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

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
