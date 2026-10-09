"""Five management reports for CATMS (MySQL 8, plain Django).

Financial report periods use Invoice.created_at (invoice cohort), while
appointment and treatment reports use Time_Slot.available_date.
Patient and insurer payments are counted to date for the selected invoice cohort;
this is NOT a cash-flow-by-payment-date report.

Copy into CATMS/reporting/required_reports.py.
"""
import logging
import re
from datetime import date
from decimal import Decimal

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.decorators import jwt_required

logger = logging.getLogger(__name__)


def _error(message, status=400):
    return JsonResponse({'status': 'error', 'message': message}, status=status)


def _manager_branch(request):
    """Re-check JWT role/branch against the *current* Employee record."""
    try:
        branch_id = int(request.branch_id)
        employee_id = int(request.employee_id)
    except (TypeError, ValueError, AttributeError):
        return None

    if branch_id <= 0 or employee_id <= 0:
        return None

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT e.branch_id
            FROM Employee e
            WHERE e.employee_id = %s
              AND e.branch_id = %s
              AND e.role = 'Manager'
              AND e.status = 'Active'
            LIMIT 1
        """, [employee_id, branch_id])
        row = cursor.fetchone()
    return row[0] if row else None


def _date_param(request, key):
    """Require one ISO YYYY-MM-DD query parameter."""
    raw = request.GET.get(key)
    if not raw or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
        raise ValueError(f'{key} is required (YYYY-MM-DD)')
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f'{key} is invalid') from exc


def _period(request):
    start = _date_param(request, 'start_date')
    end = _date_param(request, 'end_date')
    if start > end:
        raise ValueError('start_date must be on or before end_date')
    return start, end


def _money(value):
    return f'{Decimal(value or 0):.2f}'


@jwt_required(allowed_roles=['Manager'])
@require_GET
def branch_daily_appointments(request):
    """Report 1: Scheduled/completed/cancelled on a specific appointment date."""
    try:
        day = _date_param(request, 'date')
    except ValueError as exc:
        return _error(str(exc))
    try:
        branch_id = _manager_branch(request)
        if branch_id is None:
            return _error('Manager branch access denied', 403)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT b.branch_id, b.branch_name,
                       COUNT(a.appointment_id) AS total,
                       SUM(CASE WHEN a.status='Scheduled' THEN 1 ELSE 0 END) AS scheduled,
                       SUM(CASE WHEN a.status='Completed' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN a.status='Cancelled' THEN 1 ELSE 0 END) AS cancelled
                FROM Branch b
                LEFT JOIN Time_Slot ts
                    ON ts.branch_id=b.branch_id AND ts.available_date=%s
                LEFT JOIN Appointment a ON a.time_slot_id=ts.time_slot_id
                WHERE b.branch_id=%s
                GROUP BY b.branch_id,b.branch_name
            """, [day, branch_id])
            row = cursor.fetchone()
        if row is None:
            return _error('Branch not found', 404)
        return JsonResponse({'status': 'success', 'date': day.isoformat(), 'data': {
            'branch_id': row[0], 'branch_name': row[1],
            'total_appointments': int(row[2] or 0),
            'scheduled': int(row[3] or 0),
            'completed': int(row[4] or 0),
            'cancelled': int(row[5] or 0),
        }})
    except DatabaseError:
        logger.exception('Branch-wise appointments report failed')
        return _error('Unable to retrieve appointment report', 500)