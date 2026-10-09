from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
import logging
from datetime import date

from django.db import DatabaseError
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
def get_doctor_performance_report(request):
    # Step 1: Enforce GET method since we are only reading data
    if request.method == 'GET':
        try:
            # Step 2: Open a secure database cursor
            with connection.cursor() as cursor:
                
                # Step 3: Execute the analytical SQL query
                cursor.execute("""
                    SELECT 
                        d.doctor_id,
                        d.first_name,
                        d.last_name,
                        d.specialization,
                        COUNT(a.appointment_id) AS total_appointments,
                        SUM(CASE WHEN a.status = 'Completed' THEN 1 ELSE 0 END) AS completed_appointments,
                        SUM(CASE WHEN a.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_appointments
                    FROM Doctor d
                    LEFT JOIN Time_Slot ts ON d.doctor_id = ts.doctor_id
                    LEFT JOIN Appointment a ON ts.time_slot_id = a.time_slot_id
                    GROUP BY 
                        d.doctor_id, 
                        d.first_name, 
                        d.last_name, 
                        d.specialization
                    ORDER BY completed_appointments DESC;
                """)
                
                # Step 4: Fetch all aggregated rows
                rows = cursor.fetchall()

            # Step 5: Format the raw tuple data into a JSON-friendly list of dictionaries
            performance_data = []
            for row in rows:
                performance_data.append({
                    'doctor_id': row[0],
                    'doctor_name': f"Dr. {row[1]} {row[2]}",
                    'specialization': row[3],
                    'total_appointments': row[4],
                    # Convert Decimal/None types safely to integers
                    'completed_appointments': int(row[5]) if row[5] else 0,
                    'cancelled_appointments': int(row[6]) if row[6] else 0
                })

            # Step 6: Return the payload
            return JsonResponse({
                'status': 'success',
                'doctor_count': len(performance_data),
                'data': performance_data
            }, status=200)

        except Exception as e:
            return JsonResponse({'status': 'critical_error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Only GET method is allowed'}, status=405)

@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
def get_common_conditons_report(request):
    # Check that the request uses the GET Method
    if request == 'GET':
        try:
            # Open a database cursor to execute raw SQL
            with connection.cursor() as cursor:

                # Find the no of times each medical condition has been recorded
                cursor.execute("""
                    SELECT
                        c.condition_id,
                        c.condition_name,
                        COUNT(pc.patient_condition_id) AS occurence_count
                    FROM Patient_condtion pc
                    JOIN Conditions c
                        ON pc.condition_id = c.condition_id
                    GROUP BY
                        c.condition_id,
                        c.condition_name
                    ORDER BY
                        occurence_count DESC,
                """)

                # Retrieve all condition records
                rows = cursor.fetchall()

                # Get the column names returned by the query
                columns = [column[0] for column in cursor.description]

                # Convert each database row into a dictionary
                report = [
                    dict(zip(columns, row))
                    for row in rows
                ]

            # Return the common condtion report as JSON
            return JsonResponse({
                'status':'success',
                'report': report
            }, status = 200)

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


@require_GET
@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
def get_medication_usage_report(request):
    """Count prescriptions and distinct patients per medication.

    Optional inclusive start_date/end_date filters use the appointment date.
    Only completed consultations count. Usage means prescription records,
    since the schema does not store dispensed quantities.
    """
    # Either date boundary may be omitted for an open-ended reporting period.
    try:
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        start_date = date.fromisoformat(start_date) if start_date is not None else None
        end_date = date.fromisoformat(end_date) if end_date is not None else None
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date must not be after end_date.")
    except ValueError:
        return JsonResponse({"success": False, "error": "Use valid YYYY-MM-DD dates with start_date <= end_date."}, status=400)

    # Only fixed SQL fragments are joined; user-supplied dates remain parameters.
    conditions = ["a.status = %s"]
    params = ["Completed"]
    if start_date is not None:
        conditions.append("ts.available_date >= %s")
        params.append(start_date)
    if end_date is not None:
        conditions.append("ts.available_date <= %s")
        params.append(end_date)
    # Follow prescriptions through consultations to their appointment dates.
    # DISTINCT prevents joins from counting the same prescription or patient twice.
    sql = """
        SELECT m.medication_id, m.generic_name, m.form, m.manufacturer,
               COUNT(DISTINCT p.prescription_id) AS prescription_count,
               COUNT(DISTINCT a.patient_id) AS patient_count
        FROM Medication m
        JOIN Prescription p ON p.medication_id = m.medication_id
        JOIN consultation_record cr ON cr.medical_record_id = p.medical_record_id
        JOIN Appointment a ON a.appointment_id = cr.appointment_id
        JOIN Time_Slot ts ON ts.time_slot_id = a.time_slot_id
        WHERE """ + " AND ".join(conditions) + """
        GROUP BY m.medication_id, m.generic_name, m.form, m.manufacturer
        ORDER BY prescription_count DESC, m.medication_id
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            # Convert database tuples into JSON objects using the column names.
            columns = [column[0] for column in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError:
        logger.exception("Failed to retrieve medication usage report")
        return JsonResponse({"success": False, "error": "Unable to retrieve medication usage report."}, status=500)
    # Include the applied date filters; an empty report returns an empty results list.
    return JsonResponse({"success": True, "start_date": start_date,
                         "end_date": end_date, "results": results})


@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
def get_revenue_report(request):
    if request.method == 'GET':
        try:
            with connection.cursor() as cursor:
                # Generates the Doctor-wise revenue report required by the clinic management[cite: 5]
                cursor.execute("""
                    SELECT d.doctor_id, d.first_name, d.last_name, SUM(i.total_amount) as total_revenue
                    FROM Doctor d
                    JOIN Appointment a ON d.doctor_id = a.doctor_id
                    JOIN Invoice i ON a.appointment_id = i.appointment_id
                    GROUP BY d.doctor_id, d.first_name, d.last_name
                """)
                rows = cursor.fetchall()
                report_data = []
                for row in rows:
                    report_data.append({
                        'doctor_id': row[0],
                        'first_name': row[1],
                        'last_name': row[2],
                        'total_revenue': float(row[3]) if row[3] else 0.0
                    })
            return JsonResponse({'status': 'success', 'data': report_data}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)