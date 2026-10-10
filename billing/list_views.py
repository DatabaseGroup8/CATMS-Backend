import logging
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from accounts.decorators import jwt_required
logger = logging.getLogger(__name__)

@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def list_invoices(request):
    only_outstanding = request.GET.get(
        'outstanding_only', 'false').lower()
    q = request.GET.get('q', '').strip()
    if only_outstanding not in ('true', 'false') or len(q) > 100:
        return JsonResponse({'status': 'error',
            'message': 'Invalid filters'}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT i.Invoice_id, i.appointment_id,
                       p.patient_id, p.full_name, p.contact_no,
                       i.created_at, i.sub_total,
                       i.insurance_claimed_amount,
                       COALESCE(pay.paid, 0),
                       CalculateOutstandingBalance(i.Invoice_id)
                FROM Invoice i
                JOIN Appointment a ON a.appointment_id=i.appointment_id
                JOIN Patient p ON p.patient_id=a.patient_id
                JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
                LEFT JOIN (
                    SELECT Invoice_id, SUM(payment_amount) AS paid
                    FROM Payment WHERE status='Completed'
                    GROUP BY Invoice_id
                ) pay ON pay.Invoice_id=i.Invoice_id
                WHERE ts.branch_id=%s
                  AND EXISTS (
                      SELECT 1 FROM Employee e
                      WHERE e.employee_id=%s
                        AND e.branch_id=ts.branch_id
                        AND e.role='Receptionist' AND e.status='Active'
                  )
                  AND (p.full_name LIKE %s OR p.contact_no LIKE %s)
                  AND (%s='false' OR
                       CalculateOutstandingBalance(i.Invoice_id)>0)
                ORDER BY i.created_at DESC, i.Invoice_id DESC
                LIMIT 100
            ''', [request.branch_id, request.employee_id,
                  f'%{q}%', f'%{q}%', only_outstanding])
            rows = cursor.fetchall()
            return JsonResponse({'status': 'success', 'data': [
                {'invoice_id': r[0], 'appointment_id': r[1],
                 'patient_id': r[2], 'patient_name': r[3],
                 'contact_no': r[4], 'created_at': str(r[5]),
                 'sub_total': str(r[6]),
                 'insurance_claimed_amount': str(r[7]),
                 'total_paid': str(r[8]),
                 'outstanding_balance': str(r[9])}
                for r in rows
            ]})
    except DatabaseError:
        logger.exception('Invoice list failed')
        return JsonResponse({'status': 'error',
            'message': 'Unable to load invoices'}, status=500)
        
        
@jwt_required(allowed_roles=['Manager'])
@require_GET
def list_insurance_packages(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT ip.insurance_package_id, ip.package_name,
                       ip.annual_name, ip.copayment_percentage,
                       ip.started_date
                FROM Insurance_Packages ip
                WHERE EXISTS (
                    SELECT 1 FROM Employee m
                    WHERE m.employee_id=%s AND m.branch_id=%s
                      AND m.role='Manager' AND m.status='Active'
                )
                ORDER BY ip.package_name
            ''', [request.employee_id, request.branch_id])
            rows = cursor.fetchall()
            return JsonResponse({'status': 'success', 'data': [
                {'insurance_package_id': r[0], 'package_name': r[1],
                 'annual_name': r[2],
                 'copayment_percentage': (
                     str(r[3]) if r[3] is not None else None),
                 'started_date': str(r[4]) if r[4] else None}
                for r in rows
            ]})
    except DatabaseError:
        logger.exception('Package list failed')
        return JsonResponse({'status': 'error',
            'message': 'Unable to load packages'}, status=500)
        
        
@jwt_required(allowed_roles=['Manager'])
@require_GET
def list_insurance_claims(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT c.invoice_id, c.insurance_id,
                       p.full_name, ip.package_name,
                       c.claim_amount, c.approved_amount,
                       c.insurance_paid_amount, c.claim_status,
                       c.issued_date
                FROM Claims c
                JOIN Invoice i ON i.Invoice_id=c.invoice_id
                JOIN Appointment a ON a.appointment_id=i.appointment_id
                JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
                JOIN Patient p ON p.patient_id=a.patient_id
                JOIN Insurance ins ON ins.Insurance_id=c.insurance_id
                JOIN Insurance_Packages ip
                    ON ip.insurance_package_id=ins.insurance_package_id
                WHERE ts.branch_id=%s
                  AND EXISTS (
                      SELECT 1 FROM Employee m
                      WHERE m.employee_id=%s
                        AND m.branch_id=ts.branch_id
                        AND m.role='Manager' AND m.status='Active'
                  )
                ORDER BY c.issued_date DESC, c.invoice_id DESC
                LIMIT 100
            ''', [request.branch_id, request.employee_id])
            rows = cursor.fetchall()
            return JsonResponse({'status': 'success', 'data': [
                {'invoice_id': r[0], 'insurance_id': r[1],
                 'patient_name': r[2], 'package_name': r[3],
                 'claim_amount': str(r[4]),
                 'approved_amount': (
                     str(r[5]) if r[5] is not None else None),
                 'insurance_paid_amount': str(r[6]),
                 'claim_status': r[7],
                 'issued_date': str(r[8]) if r[8] else None}
                for r in rows
            ]})
    except DatabaseError:
        logger.exception('Claims list failed')
        return JsonResponse({'status': 'error',
            'message': 'Unable to load claims'}, status=500)