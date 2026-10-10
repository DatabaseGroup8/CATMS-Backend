from django.shortcuts import render
import json
from datetime import date
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.db import DatabaseError
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from accounts.decorators import jwt_required

logger = logging.getLogger(__name__)

@csrf_exempt
@jwt_required(allowed_roles=['Doctor'])
def add_patient_condition(request):
    # Step 1: Enforce POST method since we are writing data
    if request.method == 'POST':
        try:
            # Step 2: Parse the incoming JSON payload from the frontend
            data = json.loads(request.body)
            
            patient_id = data.get('patient_id')
            condition_id = data.get('condition_id')
            diagnosed_date = data.get('diagnosed_date')
            is_chronic = data.get('is_chronic')
            current_status = data.get('current_status')

            # Step 3: Open a secure database cursor
            with connection.cursor() as cursor:
                
                # Step 4: Call the Stored Procedure
                # Pass the input variables using %s to prevent SQL injection
                # Map the OUT parameters to MySQL session variables (@)
                cursor.execute("""
                    CALL AddPatientCondition(
                        %s, %s, %s, %s, %s, 
                        @p_patient_condition_id, @p_error_message, @p_success
                    );
                """, [
                    patient_id, condition_id, diagnosed_date, 
                    is_chronic, current_status
                ])
                
                # Step 5: Fetch the generated OUT parameters back into Python tuple
                cursor.execute("SELECT @p_patient_condition_id, @p_error_message, @p_success;")
                result = cursor.fetchone()
                
                # Unpack the MySQL tuple
                patient_condition_id, error_message, success = result

            # Step 6: Evaluate the transaction and return the appropriate HTTP Response
            if success:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Condition successfully recorded.',
                    'patient_condition_id': patient_condition_id
                }, status=201)
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': error_message
                }, status=400)

        except Exception as e:
            # Catch Python or severe Database crashes
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    # Fallback for incorrect HTTP methods (like GET)
    return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)


@csrf_exempt
@jwt_required(allowed_roles=['Doctor'])
def get_patient_history(request, patient_id):
    # Step 1: Enforce GET method since we are only reading data
    if request.method == 'GET':
        try:
            # Step 2: Open a secure database cursor
            with connection.cursor() as cursor:
                
                # Step 3: Execute the raw SQL JOIN query
                # We join Appointment -> Time_Slot (for the date) -> Consultation -> Medical Record
                cursor.execute("""
                    SELECT
                        a.appointment_id,
                        DATE_FORMAT(ts.available_date, '%%Y-%%m-%%d')
                            AS appointment_date,
                        TIME_FORMAT(ts.start_time, '%%H:%%i')
                            AS start_time,
                        mr.chief_complaint,
                        mr.symptoms,
                        mr.diagnosis

                    FROM Appointment a

                    JOIN Time_Slot ts
                        ON a.time_slot_id = ts.time_slot_id

                    JOIN consultation_record cr
                        ON a.appointment_id = cr.appointment_id

                    JOIN Medical_record mr
                        ON cr.medical_record_id = mr.medical_record_id

                    WHERE a.patient_id = %s
                      AND EXISTS (
                          SELECT 1 FROM Appointment aa
                          JOIN Time_Slot t2 ON t2.time_slot_id = aa.time_slot_id
                          JOIN Doctor d2 ON d2.doctor_id = t2.doctor_id
                          JOIN Employee e2 ON e2.employee_id = d2.employee_id
                          WHERE aa.patient_id = a.patient_id
                            AND e2.employee_id = %s
                            AND e2.status = 'Active'
                            AND e2.role = 'Doctor'
                            AND e2.branch_id = %s
                            AND t2.branch_id = e2.branch_id
                      )

                    ORDER BY
                        ts.available_date DESC,
                        ts.start_time DESC

                """, [patient_id, request.employee_id, request.branch_id])

                rows = cursor.fetchall()


            # Step 5: Format the raw tuple data into a list of dictionaries

            history_data = []

            for row in rows:
                history_data.append({
                    'appointment_id': row[0],
                    'date': row[1],
                    'start_time': row[2],
                    'chief_complaint': row[3],
                    'symptoms': row[4],
                    'diagnoses': row[5]
                })


            # Step 6: Return the formatted JSON response
            return JsonResponse({
                'status': 'success', 
                'patient_id': patient_id,
                'record_count': len(history_data),
                'data': history_data
            }, status=200)

        except Exception as e:
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method is allowed'}, status=405)


@jwt_required(allowed_roles=['Doctor'])
@require_GET
def get_consultation_summary(request):
    """Return consultation to the doctor assigned to this patient's appointment."""
    try:
        consultation_id = int(request.GET.get('consultation_rec_id', ''))
        if consultation_id <= 0 or consultation_id > 2147483647:
            raise ValueError()
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Valid consultation_rec_id required'}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT cr.consultation_rec_id, cr.appointment_id,
                       cr.medical_record_id, cr.invoice_id, a.patient_id,
                       a.type, a.status, a.notes,
                       mr.chief_complaint, mr.symptoms, mr.diagnosis,
                       GetConsultationDuration(cr.consultation_rec_id) AS scheduled_duration_minutes
                FROM consultation_record cr
                JOIN Appointment a ON a.appointment_id = cr.appointment_id
                JOIN Medical_record mr ON mr.medical_record_id = cr.medical_record_id
                JOIN Time_Slot ts ON ts.time_slot_id = a.time_slot_id
                JOIN Doctor d ON d.doctor_id = ts.doctor_id
                JOIN Employee e ON e.employee_id = d.employee_id
                WHERE cr.consultation_rec_id = %s
                  AND e.employee_id = %s
                  AND e.branch_id = %s
                  AND ts.branch_id = e.branch_id
                  AND e.role = 'Doctor' AND e.status = 'Active'
            """, [consultation_id, request.employee_id, request.branch_id])
            row = cursor.fetchone()
            columns = [column[0] for column in cursor.description]
        if row is None:
            return JsonResponse({'status': 'error', 'message': 'Consultation not found'}, status=404)
        return JsonResponse({'status': 'success', 'consultation': dict(zip(columns, row))})
    except DatabaseError:
        logger.exception('Consultation summary failed')
        return JsonResponse({'status': 'error', 'message': 'Unable to retrieve consultation'}, status=500)






@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Receptionist'])
def add_condition_category(request):
    """Adds a new condition category."""
    try:
        data = json.loads(request.body)
        category_name = data.get('category_name') # Maps to Condition_category table[cite: 4]

        if not category_name:
            return JsonResponse({'status': 'error', 'message': 'Category name is required.'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Condition_category (category_name)
                VALUES (%s);
            """, [category_name])
            new_id = cursor.lastrowid

        return JsonResponse({'status': 'success', 'message': 'Condition category added successfully', 'condition_category_id': new_id}, status=201)

    except Exception as e:
        logger.exception("Error in add_condition_category")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Receptionist'])
def add_condition(request):
    """Adds a specific medical condition under a category."""
    try:
        data = json.loads(request.body)
        
        # Extract fields matching the Conditions table[cite: 4]
        condition_category_id = data.get('condition_category_id')
        condition_name = data.get('condition_name')
        description = data.get('description')

        if not condition_category_id or not condition_name:
            return JsonResponse({'status': 'error', 'message': 'Condition category ID and condition name are required.'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Conditions (condition_category_id, condition_name, description)
                VALUES (%s, %s, %s);
            """, [condition_category_id, condition_name, description])
            new_id = cursor.lastrowid

        return JsonResponse({'status': 'success', 'message': 'Condition added successfully', 'condition_id': new_id}, status=201)

    except Exception as e:
        logger.exception("Error in add_condition")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
@require_POST
@jwt_required(allowed_roles=['Receptionist'])
def add_treatment_category(request):
    """Adds a new category for treatments."""
    try:
        data = json.loads(request.body)
        
        # Extract fields matching Treatment_Category table[cite: 4]
        category_name = data.get('category_name')
        description = data.get('description')

        if not category_name:
            return JsonResponse({'status': 'error', 'message': 'Category name is required.'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Treatment_Category (category_name, description)
                VALUES (%s, %s);
            """, [category_name, description])
            new_id = cursor.lastrowid

        return JsonResponse({'status': 'success', 'message': 'Treatment category added successfully', 'treatment_category_id': new_id}, status=201)

    except Exception as e:
        logger.exception("Error in add_treatment_category")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



