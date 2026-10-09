from django.shortcuts import render
import json
from datetime import date
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.db import DatabaseError
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

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
                        ts.start_time,
                        mr.chief_complaint,
                        mr.symptoms,
                        mr.diagnosis
                    FROM Appointment a
                    JOIN Time_Slot ts ON a.time_slot_id = ts.time_slot_id
                    JOIN Consultation_record cr ON a.appointment_id = cr.appointment_id
                    JOIN Medical_record mr ON cr.medical_record_id = mr.medical_record_id
                    WHERE a.patient_id = %s
                    ORDER BY ts.start_time DESC;
                """, [patient_id])
                
                # Step 4: Fetch ALL matching rows
                # python list of tuples
                rows = cursor.fetchall()

            # Step 5: Format the raw tuple data into a list of dictionaries
            history_data = []
            for row in rows:
                history_data.append({
                    'appointment_id': row[0],
                    # Convert datetime object to string so it can be serialized to JSON safely
                    'date': row[1].strftime('%Y-%m-%d %H:%M') if row[1] else None,
                    'chief_complaint': row[2],
                    'symptoms': row[3],
                    'diagnoses': row[4]
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


@csrf_exempt
def get_consultation_summary(request):
    # Check that the request uses the GET method
    if request.method == 'GET':
        try:
            # Get the consultation record ID from the URL query parameters
            consultation_rec_id = request.GET.get('consultation_red_id')

            # Make sure the consultation ID was provided
            if not consultation_rec_id:
                return JsonResponse({
                    'status': 'error',
                    'message':'consultation_rec_id is required'
                }, status = 400)

            # Open a database cursor to execute raw SQL
            with connection.cursor() as cursor:

                # Retrieve the consultation details
                # and calculate the consultation duration
                # using the GetConsultationDuration() SQL function

                cursor.execute("""
                    SELECT
                        cr.consultation_rec_id,
                        cr.appointment_id,
                        cr-medical_record_id,
                        cr.invoice_id,
                        a.patient_id,
                        a.time_slot_id,
                        a.type,
                        a.status,
                        a.notes,
                        mr.chief_complaint,
                        mr.symptoms,
                        mr.diagnosis,
                        GetConsulatationDuration(
                            cr.consultation_rec_id
                            ) AS duration_minutes
                    FROM Consultation_record cr
                    JOIN Appointment a
                           ON cr.medical_record_id = mr.medical_record_id
                    WHERE cr.consultation_rec_id = %s;                
                """, [consultation_rec_id])

                # Get the first matching consultation
                row = cursor.fetchone()

                # If no consultation was found, return 404
                if row is None:
                    return JsonResponse({
                        'status':'error',
                        'message':'Consultation not found'
                    }, status = 404)

                # Get the column names returned by the SQL query
                columns = [column[0] for column in cursor.description]

                # Convert the database row into a dictionary
                consultation = dict(zip(column, row))

            # Return the consultation details as JSON
            return JsonResponse({
                'status':'success',
                'consultation': consultation
            }, status = 200)

        # Handle unexpected database or server errors
        except Exception as e:
            return JsonResponse({
                'status':'critical error',
                'message': str(e)
            }, status = 500)

    # Reject requests that are not GET
    return JsonResponse({
        'status':'error',
        'message':'Only GET method is allowed'
    }, status = 405)

@require_POST
def create_consultation(request):
    """Accept JSON consultation details, treatments and prescriptions.

    Requires CreateConsultationWithDetails to be installed in MySQL.
    Each treatment contains treatment_service_code; each prescription contains
    medication_id, dosage, frequency, duration_days and optional instructions.
    """
    # Validate the JSON body before sending any data to MySQL.
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("The request body must be a JSON object.")
        appointment_id = data.get("appointment_id")
        if type(appointment_id) is not int or appointment_id <= 0:
            raise ValueError("appointment_id must be a positive integer.")
        for field in ("chief_complaint", "symptoms", "diagnosis"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                raise ValueError(f"{field} must be a non-empty string.")
        if len(data["chief_complaint"]) > 255:
            raise ValueError("chief_complaint must not exceed 255 characters.")
        
        # Optional arrays are passed to the procedure as JSON strings.
        treatments = data.get("treatments", [])
        prescriptions = data.get("prescriptions", [])
        for items, id_field in ((treatments, "treatment_service_code"),
                                (prescriptions, "medication_id")):
            if not isinstance(items, list):
                raise ValueError("treatments and prescriptions must be arrays.")
            for item in items:
                if (not isinstance(item, dict) or type(item.get(id_field)) is not int
                        or item[id_field] <= 0):
                    raise ValueError(f"Each item needs a positive integer {id_field}.")

        # Match prescription fields to the database and procedure limits.
        for item in prescriptions:
            for field in ("dosage", "frequency"):
                if (not isinstance(item.get(field), str)
                        or not item[field].strip() or len(item[field]) > 50):
                    raise ValueError(f"{field} must contain 1 to 50 characters.")
            if type(item.get("duration_days")) is not int or item["duration_days"] <= 0:
                raise ValueError("duration_days must be a positive integer.")
            if (not isinstance(item.get("instructions", ""), str)
                    or len(item.get("instructions", "")) > 255):
                raise ValueError("instructions must be a string of at most 255 characters.")
            item.setdefault("instructions", "")
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    try:
        with connection.cursor() as cursor:
            # Reset connection-scoped variables used for the procedure OUT parameters.
            cursor.execute("SET @consultation_id = NULL, @consultation_message = NULL, @consultation_success = 0")
            # Bind values separately from SQL; the procedure manages its transaction.
            cursor.execute(
                "CALL CreateConsultationWithDetails(%s, %s, %s, %s, %s, %s, "
                "@consultation_id, @consultation_message, @consultation_success)",
                [appointment_id, data["chief_complaint"], data["symptoms"],
                 data["diagnosis"], json.dumps(treatments), json.dumps(prescriptions)],
            )
            # Drain CALL result sets before reading the OUT parameter values.
            while cursor.nextset():
                pass
            cursor.execute("SELECT @consultation_id, @consultation_message, @consultation_success")
            consultation_id, message, success = cursor.fetchone()
    # Log database details on the server without exposing them in the response.
    except DatabaseError:
        logger.exception("Failed to create consultation")
        return JsonResponse({"success": False, "error": "Unable to create consultation."}, status=500)
    # A procedure may report failure without raising a Python database exception.
    if not success:
        logger.warning("CreateConsultationWithDetails failed: %s", message)
        return JsonResponse({"success": False, "error": "Consultation could not be created. Check the appointment and consultation details."}, status=400)
    # HTTP 201 indicates that the consultation was created.
    return JsonResponse({"success": True, "consultation_id": consultation_id}, status=201)   



@csrf_exempt
@require_POST
def add_medication(request):
    """Adds a new medication to the clinical dictionary."""
    try:
        data = json.loads(request.body)
        
        # Extract fields matching the Medication table[cite: 4]
        generic_name = data.get('generic_name')
        manufacturer = data.get('manufacturer')
        form = data.get('form')
        contraindications = data.get('contraindications')
        side_effects = data.get('side_effects')

        if not generic_name:
            return JsonResponse({'status': 'error', 'message': 'Generic name is required.'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Medication (generic_name, manufacturer, form, contraindications, side_effects)
                VALUES (%s, %s, %s, %s, %s);
            """, [generic_name, manufacturer, form, contraindications, side_effects])
            new_id = cursor.lastrowid

        return JsonResponse({'status': 'success', 'message': 'Medication added successfully', 'medication_id': new_id}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON payload.'}, status=400)
    except DatabaseError as e:
        logger.exception("Database error in add_medication")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
@require_POST
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

@csrf_exempt
@require_POST
def add_treatment_catalogue(request):
    """Adds a specific treatment service to the catalogue."""
    try:
        data = json.loads(request.body)
        
        # Extract fields matching Treatment_Catalogue table[cite: 4]
        treatment_category_id = data.get('treatment_category_id')
        treatment_name = data.get('treatment_name')
        base_price = data.get('base_price')
        duration = data.get('duration')
        
        # Automatically set updated_date to today[cite: 4]
        updated_date = date.today().strftime('%Y-%m-%d')

        if not treatment_category_id or not treatment_name or base_price is None:
            return JsonResponse({'status': 'error', 'message': 'Category ID, treatment name, and base price are required.'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Treatment_Catalogue (treatment_category_id, treatment_name, base_price, duration, updated_date)
                VALUES (%s, %s, %s, %s, %s);
            """, [treatment_category_id, treatment_name, base_price, duration, updated_date])
            new_code = cursor.lastrowid

        return JsonResponse({'status': 'success', 'message': 'Treatment added to catalogue successfully', 'treatment_service_code': new_code}, status=201)

    except Exception as e:
        logger.exception("Error in add_treatment_catalogue")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)            