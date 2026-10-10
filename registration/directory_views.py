
import logging

from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from accounts.decorators import jwt_required

logger = logging.getLogger(__name__)


@jwt_required(allowed_roles=['Receptionist', 'Manager'])
@require_GET
def list_doctors(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT d.doctor_id, u.full_name, d.room_no,
                       d.medical_licence_number,
                       COALESCE(
                           GROUP_CONCAT(
                               DISTINCT s.specialization_name
                               ORDER BY s.specialization_name
                               SEPARATOR ', '
                           ),
                           'Not assigned'
                       ) AS specializations
                FROM Doctor d
                JOIN Employee e ON e.employee_id = d.employee_id
                JOIN `User` u ON u.user_id = e.user_id
                LEFT JOIN Doctor_Specialization ds
                    ON ds.doctor_id = d.doctor_id
                LEFT JOIN Specialization s
                    ON s.specialization_id = ds.specialization_id
                WHERE e.branch_id = %s
                  AND e.role = 'Doctor'
                  AND e.status = 'Active'
                  AND EXISTS (
                      SELECT 1
                      FROM Employee actor
                      WHERE actor.employee_id = %s
                        AND actor.branch_id = %s
                        AND actor.role = %s
                        AND actor.status = 'Active'
                  )
                GROUP BY d.doctor_id, u.full_name,
                         d.room_no, d.medical_licence_number
                ORDER BY u.full_name
            """, [
                request.branch_id,
                request.employee_id,
                request.branch_id,
                request.user_role
            ])
            rows = cursor.fetchall()

        return JsonResponse({
            'status': 'success',
            'data': [
                {
                    'doctor_id': r[0],
                    'full_name': r[1],
                    'room_no': r[2],
                    'medical_licence_number': r[3],
                    'specializations': r[4]
                }
                for r in rows
            ]
        })

    except DatabaseError:
        logger.exception('Doctor directory failed')
        return JsonResponse({
            'status': 'error',
            'message': 'Unable to load doctors'
        }, status=500)


@jwt_required(allowed_roles=['Receptionist', 'Doctor'])
@require_GET
def get_patient_details(request, patient_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT p.patient_id, p.full_name, p.contact_no,
                       p.NIC, p.gender, p.DOB,
                       CalculateAge(p.DOB), p.registered_branch_id
                FROM Patient p
                WHERE p.patient_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM Employee actor
                      WHERE actor.employee_id = %s
                        AND actor.branch_id = %s
                        AND actor.role = %s
                        AND actor.status = 'Active'
                  )
                  AND (
                      %s = 'Receptionist'
                      OR EXISTS (
                          SELECT 1
                          FROM Appointment a
                          JOIN Time_Slot ts
                              ON ts.time_slot_id = a.time_slot_id
                          JOIN Doctor d
                              ON d.doctor_id = ts.doctor_id
                          WHERE a.patient_id = p.patient_id
                            AND d.employee_id = %s
                      )
                  )
            """, [
                patient_id,
                request.employee_id,
                request.branch_id,
                request.user_role,
                request.user_role,
                request.employee_id
            ])
            row = cursor.fetchone()

        if row is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Patient not found or access denied'
            }, status=404)

        return JsonResponse({
            'status': 'success',
            'data': {
                'patient_id': row[0],
                'full_name': row[1],
                'contact_no': row[2],
                'NIC': row[3],
                'gender': row[4],
                'DOB': str(row[5]) if row[5] else None,
                'age': row[6],
                'registered_branch_id': row[7]
            }
        })

    except DatabaseError:
        logger.exception('Patient lookup failed')
        return JsonResponse({
            'status': 'error',
            'message': 'Unable to load patient'
        }, status=500)
