from django.shortcuts import render
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

@csrf_exempt
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
                
                # Step 5: Fetch the generated OUT parameters back into Python
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

def add_treatment(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Only POST method is allowed."},
            status = 405
        )

    try:
        data = json.loads(request.body)

        medical_record_id = data.get("medical_record_id")
        treatment_service_code = data.get("treatment_service_code")

        if medical_record_id is None or treatment_service_code is None:
            return JsonResponse(
                {
                    "error": "medical_record_id and treatment_service_code are required."
                },
                status = 400
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                CALL AddTreatment(%s, %s, @p_treatment_id, @p_error_message, @p_success)
                """,
                [
                    medical_record_id,
                    treatment_service_code
                ]
            )

            cursor.execute(
                """
                SELECT
                    @p_treatment_id,
                    @p_error_message,
                    @p_success
                """
            )

            result = cursor.fetchone()

        treatment_id, error_message, success = result

        if success:
            return JsonResponse(
                {
                    "success" : True,
                    "treatment_id" : treatment_id,
                    "message" : "Treatment added successfully."
                },
                status = 201
            )

        return JsonResponse(
            {
                "success": False,
                "error": error_message 
            },
            status = 400
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON request body."},
            status = 400
        )

    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status = 500
        )