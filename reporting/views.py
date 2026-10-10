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


@jwt_required(allowed_roles=['Manager'])
@require_GET
def doctor_revenue(request):
    """Report 2: Invoice-cohort billed and collected amounts, doctor-wise."""
    try:
        start, end = _period(request)
    except ValueError as exc:
        return _error(str(exc))
    try:
        branch_id = _manager_branch(request)
        if branch_id is None:
            return _error('Manager branch access denied', 403)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT d.doctor_id, u.full_name,
                       COALESCE(fin.invoice_count, 0),
                       COALESCE(fin.invoiced, 0),
                       COALESCE(fin.patient_paid, 0),
                       COALESCE(fin.insurance_allocated, 0),
                       COALESCE(fin.insurer_received, 0),
                       COALESCE(fin.patient_outstanding, 0)
                FROM Doctor d
                JOIN Employee e ON e.employee_id=d.employee_id
                JOIN `User` u ON u.user_id=e.user_id
                LEFT JOIN (
                    SELECT ts.doctor_id,
                           COUNT(i.Invoice_id) AS invoice_count,
                           SUM(COALESCE(i.sub_total,0)) AS invoiced,
                           SUM(COALESCE(pay.paid,0)) AS patient_paid,
                           SUM(COALESCE(i.insurance_claimed_amount,0)) AS insurance_allocated,
                           SUM(COALESCE(cl.insurer_paid,0)) AS insurer_received,
                           SUM(GREATEST(
                               COALESCE(i.sub_total,0)
                               -COALESCE(i.insurance_claimed_amount,0)
                               -COALESCE(pay.paid,0),0
                           )) AS patient_outstanding
                    FROM Invoice i
                    JOIN Appointment a ON a.appointment_id=i.appointment_id
                    JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
                    LEFT JOIN (
                        SELECT Invoice_id,
                               SUM(CASE WHEN status='Completed'
                                   THEN COALESCE(payment_amount,0) ELSE 0 END) AS paid
                        FROM Payment GROUP BY Invoice_id
                    ) pay ON pay.Invoice_id=i.Invoice_id
                    LEFT JOIN (
                        SELECT invoice_id,
                               SUM(COALESCE(insurance_paid_amount,0)) AS insurer_paid
                        FROM Claims GROUP BY invoice_id
                    ) cl ON cl.invoice_id=i.Invoice_id
                    WHERE ts.branch_id=%s
                      AND a.status='Completed'
                      AND i.created_at BETWEEN %s AND %s
                    GROUP BY ts.doctor_id
                ) fin ON fin.doctor_id=d.doctor_id
                WHERE e.branch_id=%s
                ORDER BY COALESCE(fin.invoiced,0) DESC, u.full_name, d.doctor_id
            """, [branch_id, start, end, branch_id])
            rows = cursor.fetchall()
        items = [{
            'doctor_id': r[0], 'doctor_name': r[1],
            'invoice_count': int(r[2] or 0),
            'invoiced_revenue': _money(r[3]),
            'patient_payments_received': _money(r[4]),
            'insurance_allocated': _money(r[5]),
            'insurance_payments_received': _money(r[6]),
            'total_cash_collected': _money(Decimal(r[4] or 0) + Decimal(r[6] or 0)),
            'patient_outstanding': _money(r[7]),
        } for r in rows]
        return JsonResponse({
            'status': 'success', 'branch_id': branch_id,
            'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'period_basis': 'invoice_created_at',
            'payment_basis': 'all_completed_patient_payments_to_date_for_selected_invoices',
            'data': items,
        })
    except DatabaseError:
        logger.exception('Doctor revenue report failed')
        return _error('Unable to retrieve doctor revenue', 500)
