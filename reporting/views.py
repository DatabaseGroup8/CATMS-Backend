from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
import logging
from datetime import date
from accounts.decorators import jwt_required
from django.db import DatabaseError
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

@require_GET
@jwt_required(allowed_roles=['Manager'])
def get_doctor_performance_report(request):

    try:
        # Get manager's branch from the verified JWT
        branch_id = getattr(request, 'branch_id', None)

        if branch_id is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Manager branch not found'
            }, status=403)

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    d.doctor_id,
                    u.full_name,
                    COALESCE(
                        sp.specializations,
                        'Not assigned'
                    ) AS specialization,

                    COALESCE(
                        stats.total_appointments, 0
                    ) AS total_appointments,

                    COALESCE(
                        stats.completed_appointments, 0
                    ) AS completed_appointments,

                    COALESCE(
                        stats.cancelled_appointments, 0
                    ) AS cancelled_appointments

                FROM Doctor d

                INNER JOIN Employee e
                    ON d.employee_id = e.employee_id

                INNER JOIN `User` u
                    ON e.user_id = u.user_id

                -- Aggregate specializations separately
                LEFT JOIN (
                    SELECT
                        ds.doctor_id,
                        GROUP_CONCAT(
                            DISTINCT s.specialization_name
                            ORDER BY s.specialization_name
                            SEPARATOR ', '
                        ) AS specializations

                    FROM Doctor_Specialization ds

                    INNER JOIN Specialization s
                        ON ds.specialization_id =
                           s.specialization_id

                    GROUP BY ds.doctor_id
                ) sp
                    ON d.doctor_id = sp.doctor_id

                -- Aggregate appointment counts separately
                LEFT JOIN (
                    SELECT
                        ts.doctor_id,
                        ts.branch_id,

                        COUNT(a.appointment_id)
                            AS total_appointments,

                        SUM(
                            CASE
                                WHEN a.status = 'Completed'
                                THEN 1
                                ELSE 0
                            END
                        ) AS completed_appointments,

                        SUM(
                            CASE
                                WHEN a.status = 'Cancelled'
                                THEN 1
                                ELSE 0
                            END
                        ) AS cancelled_appointments

                    FROM Time_Slot ts

                    LEFT JOIN Appointment a
                        ON ts.time_slot_id = a.time_slot_id

                    GROUP BY
                        ts.doctor_id,
                        ts.branch_id
                ) stats
                    ON d.doctor_id = stats.doctor_id
                    AND stats.branch_id = e.branch_id

                WHERE e.branch_id = %s

                ORDER BY
                    completed_appointments DESC,
                    u.full_name ASC

            """, [branch_id])

            rows = cursor.fetchall()

        performance_data = []

        for row in rows:
            performance_data.append({
                'doctor_id': row[0],
                'doctor_name': row[1],
                'specialization': row[2],
                'total_appointments': int(row[3]),
                'completed_appointments': int(row[4]),
                'cancelled_appointments': int(row[5])
            })

        return JsonResponse({
            'status': 'success',
            'doctor_count': len(performance_data),
            'data': performance_data
        }, status=200)

    except Exception:
        logger.exception(
            'Failed to generate doctor performance report'
        )

        return JsonResponse({
            'status': 'error',
            'message': 'Unable to generate report'
        }, status=500)

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



@require_GET
@jwt_required(allowed_roles=['Manager'])
def get_revenue_report(request):

    try:
        # Get the manager's branch from JWT
        branch_id = getattr(request, 'branch_id', None)

        if branch_id is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Manager branch not found'
            }, status=403)

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    d.doctor_id,
                    u.full_name,

                    COALESCE(
                        SUM(i.sub_total), 0
                    ) AS total_revenue

                FROM Doctor d

                INNER JOIN Employee e
                    ON d.employee_id = e.employee_id

                INNER JOIN `User` u
                    ON e.user_id = u.user_id

                LEFT JOIN Time_Slot ts
                    ON d.doctor_id = ts.doctor_id
                    AND ts.branch_id = e.branch_id

                LEFT JOIN Appointment a
                    ON ts.time_slot_id = a.time_slot_id
                    AND a.status = 'Completed'

                LEFT JOIN Invoice i
                    ON a.appointment_id = i.appointment_id

                WHERE e.branch_id = %s

                GROUP BY
                    d.doctor_id,
                    u.full_name

                ORDER BY total_revenue DESC

            """, [branch_id])

            rows = cursor.fetchall()

        report_data = []

        for row in rows:
            report_data.append({
                'doctor_id': row[0],
                'doctor_name': row[1],
                'total_revenue': format(row[2], '.2f')
            })

        return JsonResponse({
            'status': 'success',
            'doctor_count': len(report_data),
            'data': report_data
        }, status=200)

    except Exception:
        logger.exception('Failed to generate revenue report')

        return JsonResponse({
            'status': 'error',
            'message': 'Unable to generate revenue report'
        }, status=500)
