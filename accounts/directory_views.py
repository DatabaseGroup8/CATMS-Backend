import logging
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from accounts.decorators import jwt_required

logger = logging.getLogger(__name__)

@require_GET
def list_branches(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT branch_id, branch_name, district
                FROM Branch
                ORDER BY branch_name
            """)
            rows = cursor.fetchall()

        return JsonResponse({
            'status': 'success',
            'data': [
                {
                    'branch_id': row[0],
                    'branch_name': row[1],
                    'district': row[2]
                }
                for row in rows
            ]
        })

    except DatabaseError:
        logger.exception('Branch directory failed')
        return JsonResponse({
            'status': 'error',
            'message': 'Unable to load branches'
        }, status=500)


@jwt_required(allowed_roles=['Manager'])
@require_GET
def list_staff(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT e.employee_id, u.full_name, u.email,
                       u.contact_no, e.role, e.status,
                       e.joined_date, e.salary
                FROM Employee e
                JOIN `User` u ON u.user_id = e.user_id
                WHERE e.branch_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM Employee m
                      WHERE m.employee_id = %s
                        AND m.branch_id = e.branch_id
                        AND m.role = 'Manager'
                        AND m.status = 'Active'
                  )
                ORDER BY u.full_name
                LIMIT 100
            """, [request.branch_id, request.employee_id])
            rows = cursor.fetchall()

        return JsonResponse({
            'status': 'success',
            'data': [
                {
                    'employee_id': r[0],
                    'full_name': r[1],
                    'email': r[2],
                    'contact_no': r[3],
                    'role': r[4],
                    'status': r[5],
                    'joined_date': str(r[6]) if r[6] else None,
                    'salary': str(r[7]) if r[7] is not None else None
                }
                for r in rows
            ]
        })
    except DatabaseError:
        logger.exception('Staff list failed')
        return JsonResponse({
            'status': 'error',
            'message': 'Unable to load staff'
        }, status=500)