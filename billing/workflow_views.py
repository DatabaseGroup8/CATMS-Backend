"""Consultation finalization, insurance claim and partial-payment workflow.

All financial values returned as decimal strings. The MySQL procedures own their
transactions; Django must not wrap CALL in transaction.atomic().
"""
import json
import logging
from datetime import date
from uuid import UUID
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from accounts.decorators import jwt_required
from .workflow_common import (
    bad, payload, positive_int, text_value, amount, parse_date,
    call_out, procedure_failed,
)

logger = logging.getLogger(__name__)


def _actor(request):
    """JWT decorator has already verified signature; SQL also checks current employee."""
    return positive_int(request.employee_id, 'employee_id'), positive_int(request.branch_id, 'branch_id')


@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def get_completed_appointments(request):
    try:
        employee_id, branch_id = _actor(request)
        date_filter = request.GET.get('date')
        selected = parse_date(date_filter) if date_filter else None
    except (ValueError, AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT a.appointment_id, a.patient_id, p.full_name, a.status,
                       ts.available_date, ts.start_time, u.full_name,
                       i.Invoice_id, cr.medical_record_id
                FROM Appointment a
                JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
                JOIN Doctor d ON d.doctor_id=ts.doctor_id
                JOIN Employee de ON de.employee_id=d.employee_id
                JOIN `User` u ON u.user_id=de.user_id
                JOIN Patient p ON p.patient_id=a.patient_id
                LEFT JOIN Invoice i ON i.appointment_id=a.appointment_id
                LEFT JOIN consultation_record cr ON cr.appointment_id=a.appointment_id
                WHERE a.status='Completed' AND ts.branch_id=%s
                  AND (%s IS NULL OR ts.available_date=%s)
                  AND EXISTS (
                      SELECT 1 FROM Employee e WHERE e.employee_id=%s
                      AND e.branch_id=ts.branch_id
                      AND e.role='Receptionist' AND e.status='Active'
                  )
                ORDER BY ts.available_date DESC,ts.start_time DESC
                LIMIT 100
            """, [branch_id, selected, selected, employee_id])
            rows=cursor.fetchall()
    except DatabaseError:
        logger.exception('Completed appointment lookup failed')
        return bad('Could not retrieve completed appointments', 500)
    return JsonResponse({'status':'success', 'appointments':[
        {'appointment_id':r[0], 'patient_id':r[1], 'patient_name':r[2],
         'status':r[3], 'date':str(r[4]), 'start_time':str(r[5]),
         'doctor_name':r[6], 'invoice_id':r[7], 'medical_record_id':r[8],
         'billing_status':'Finalized' if r[7] is not None else 'Not Started'}
        for r in rows]})


@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
@require_POST
def finalize_consultation_bill(request):
    try:
        employee_id, _ = _actor(request)
        data = payload(request)
        appointment_id=positive_int(data.get('appointment_id'),'appointment_id')
        report = data.get('medical_report')
        if not isinstance(report,dict):
            raise ValueError('medical_report must be an object')
        chief = text_value(report.get('chief_complaint'), 'chief_complaint', required=True)
        symptoms = text_value(report.get('symptoms'), 'symptoms')
        diagnosis = text_value(report.get('diagnosis'), 'diagnosis', required=True)
        medicines=data.get('medications',[])
        treatments=data.get('treatments',[])
        if not isinstance(medicines,list) or not isinstance(treatments,list):
            raise ValueError('medications and treatments must be arrays')
        if not (1 <= len(medicines)+len(treatments) <= 100):
            raise ValueError('Provide 1 to 100 billable items')
        for med in medicines:
            if not isinstance(med,dict):
                raise ValueError('Invalid medication entry')
            positive_int(med.get('medication_id'), 'medication_id')
            quantity=positive_int(med.get('quantity'),'quantity')
            days=positive_int(med.get('duration_days'),'duration_days')
            if quantity>10000 or days>99999:
                raise ValueError('Medication quantity/duration too large')
            text_value(med.get('dosage'),'dosage',50,True)
            text_value(med.get('frequency'),'frequency',50,True)
            text_value(med.get('instructions',''),'instructions')
        for t in treatments:
            if not isinstance(t,dict):
                raise ValueError('Invalid treatment entry')
            positive_int(t.get('treatment_service_code'),'treatment_service_code')
    except (ValueError, AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            rec_id, invoice_id, subtotal, success, message = call_out(
                cursor,
                'CALL FinalizeConsultationBill(%s,%s,%s,%s,%s,%s,%s,'
                '@final_record,@final_invoice,@final_total,@final_ok,@final_msg)',
                [appointment_id, employee_id, chief, symptoms, diagnosis,
                 json.dumps(medicines), json.dumps(treatments)],
                'SELECT @final_record,@final_invoice,@final_total,@final_ok,@final_msg'
            )
    except DatabaseError:
        logger.exception('Consultation finalization database error')
        return bad('Unable to finalize consultation', 500)
    if not success:
        return procedure_failed(logger, 'FinalizeConsultationBill', message)
    return JsonResponse({'status':'success','appointment_id':appointment_id,
                         'medical_record_id':rec_id,'invoice_id':invoice_id,
                         'sub_total':str(subtotal),'insurance_claimed_amount':'0.00'},status=201)


def _invoice_summary_sql():
    return """
        SELECT i.Invoice_id, i.appointment_id, a.patient_id, p.full_name,
               i.sub_total, COALESCE(i.insurance_claimed_amount,0),
               COALESCE((SELECT SUM(x.payment_amount) FROM Payment x
                         WHERE x.Invoice_id=i.Invoice_id AND x.status='Completed'),0),
               CalculateOutstandingBalance(i.Invoice_id),
               c.claim_amount, c.approved_amount, c.insurance_paid_amount, c.claim_status
        FROM Invoice i
        JOIN Appointment a ON a.appointment_id=i.appointment_id
        JOIN Patient p ON p.patient_id=a.patient_id
        JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
        LEFT JOIN Claims c ON c.invoice_id=i.Invoice_id
        WHERE i.Invoice_id=%s AND ts.branch_id=%s
          AND EXISTS (
              SELECT 1 FROM Employee e WHERE e.employee_id=%s
               AND e.branch_id=ts.branch_id AND e.role='Receptionist' AND e.status='Active'
          )
    """


@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def get_invoice_summary(request, invoice_id):
    try:
        employee_id, branch_id=_actor(request)
    except (ValueError,AttributeError) as exc:
        return bad(str(exc),403)
    try:
        with connection.cursor() as cursor:
            cursor.execute(_invoice_summary_sql(),[invoice_id,branch_id,employee_id])
            r=cursor.fetchone()
    except DatabaseError:
        logger.exception('Invoice summary lookup failed')
        return bad('Could not retrieve invoice summary',500)
    if r is None:
        return bad('Invoice not found',404)
    return JsonResponse({'status':'success','data':{
        'invoice_id':r[0],'appointment_id':r[1], 'patient_id':r[2], 'patient_name':r[3],
        'sub_total':str(r[4]), 'insurance_claimed_amount':str(r[5]),
        'total_patient_paid':str(r[6]), 'patient_outstanding':str(r[7]),
        'claim_amount':str(r[8]) if r[8] is not None else None,
        'approved_amount':str(r[9]) if r[9] is not None else None,
        'insurance_paid_amount':str(r[10]) if r[10] is not None else None,
        'claim_status':r[11],
        'insurance_cash_received':str(r[10]) if r[10] is not None else '0.00',
    }})


@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def get_patient_insurance_for_invoice(request, invoice_id):
    try:
        employee_id, branch_id=_actor(request)
    except (ValueError,AttributeError) as exc:
        return bad(str(exc),403)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT ins.Insurance_id, ip.package_name, ip.copayment_percentage,
                       ins.started_date,ins.end_date
                FROM Invoice i
                JOIN Appointment a ON a.appointment_id=i.appointment_id
                JOIN Time_Slot ts ON ts.time_slot_id=a.time_slot_id
                JOIN Insurance ins ON ins.patient_id=a.patient_id
                JOIN Insurance_Packages ip ON ip.insurance_package_id=ins.insurance_package_id
                WHERE i.Invoice_id=%s AND ts.branch_id=%s
                  AND ins.status='Active' AND ins.started_date<=ts.available_date
                  AND (ins.end_date IS NULL OR ins.end_date>=ts.available_date)
                  AND (ip.started_date IS NULL OR ip.started_date<=ts.available_date)
                  AND EXISTS (
                      SELECT 1 FROM Employee e WHERE e.employee_id=%s
                      AND e.branch_id=ts.branch_id AND e.status='Active' AND e.role='Receptionist'
                  )
                ORDER BY ins.Insurance_id
            """, [invoice_id,branch_id,employee_id])
            rows=cursor.fetchall()
    except DatabaseError:
        logger.exception('Invoice insurance lookup failed')
        return bad('Could not retrieve insurance',500)
    return JsonResponse({'status':'success','policies':[
        {'insurance_id':r[0], 'package_name':r[1],
         'copayment_percentage':str(r[2]),'start_date':str(r[3]),
         'end_date':str(r[4]) if r[4] else None}
        for r in rows]})


@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
@require_POST
def apply_invoice_insurance(request, invoice_id):
    try:
        employee_id,_ = _actor(request)
        insurance_id=positive_int(payload(request).get('insurance_id'),'insurance_id')
    except (ValueError,AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            claim,success,message=call_out(
                cursor,
                'CALL ApplyInvoiceInsurance(%s,%s,%s,@claim_value,@claim_ok,@claim_msg)',
                [invoice_id,insurance_id,employee_id],
                'SELECT @claim_value,@claim_ok,@claim_msg'
            )
    except DatabaseError:
        logger.exception('Insurance application failed')
        return bad('Could not apply insurance',500)
    if not success:
        return procedure_failed(logger,'ApplyInvoiceInsurance',message)
    return JsonResponse({'status':'success','invoice_id':invoice_id,
                         'insurance_claimed_amount':str(claim),
                         'claim_status':'Submitted'},status=201)


@csrf_exempt
@jwt_required(allowed_roles=['Receptionist'])
@require_POST
def process_full_checkout(request):
    """Records ONE patient payment; invoice must already exist. Kept legacy URL name."""
    try:
        employee_id,_=_actor(request)
        data=payload(request)
        invoice_id=positive_int(data.get('invoice_id'),'invoice_id')
        paid=amount(data.get('payment_amount'),'payment_amount')
        method=text_value(data.get('payment_method'),'payment_method',20,True)
        raw_key=text_value(data.get('request_key'),'request_key',36,True)
        if str(UUID(raw_key)) != raw_key.lower():
            raise ValueError('request_key must be a UUID')
    except (ValueError,AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            payment_id,success,message=call_out(
                cursor,
                'CALL RecordPayment(%s,%s,%s,%s,%s,@pay_id,@pay_ok,@pay_msg)',
                [invoice_id,employee_id,paid,method,raw_key],
                'SELECT @pay_id,@pay_ok,@pay_msg'
            )
            if not success:
                return procedure_failed(logger,'RecordPayment',message)
            # Procedure has already committed; balance is a separate read.
            try:
                cursor.execute('SELECT CalculateOutstandingBalance(%s)',[invoice_id])
                remaining=cursor.fetchone()[0]
            except DatabaseError:
                logger.exception('Payment succeeded but balance lookup failed')
                remaining=None
    except DatabaseError:
        logger.exception('Payment procedure failed')
        return bad('Unable to record payment',500)
    return JsonResponse({'status':'success','invoice_id':invoice_id,
                         'payment_id':payment_id,'payment_amount':str(paid),
                         'balance_remaining':str(remaining) if remaining is not None else None},status=201)


@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
@require_POST
def resolve_insurance_claim(request, invoice_id):
    try:
        employee_id,_=_actor(request)
        approved=amount(payload(request).get('approved_amount'), 'approved_amount',allow_zero=True)
    except (ValueError,AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            success,message=call_out(cursor,
                'CALL ResolveInsuranceClaim(%s,%s,%s,@resolve_ok,@resolve_msg)',
                [invoice_id,employee_id,approved],
                'SELECT @resolve_ok,@resolve_msg')
    except DatabaseError:
        logger.exception('Insurance claim resolution failed')
        return bad('Unable to resolve claim',500)
    if not success:
        return procedure_failed(logger,'ResolveInsuranceClaim',message)
    return JsonResponse({'status':'success','invoice_id':invoice_id,
                         'approved_amount':str(approved),'message':message})


@csrf_exempt
@jwt_required(allowed_roles=['Manager'])
@require_POST
def record_insurance_settlement(request, invoice_id):
    try:
        employee_id,_=_actor(request)
        received=amount(payload(request).get('amount'),'amount')
    except (ValueError,AttributeError) as exc:
        return bad(str(exc))
    try:
        with connection.cursor() as cursor:
            success,message=call_out(cursor,
                'CALL RecordInsuranceSettlement(%s,%s,%s,@settle_ok,@settle_msg)',
                [invoice_id,employee_id,received],
                'SELECT @settle_ok,@settle_msg')
    except DatabaseError:
        logger.exception('Insurance settlement failed')
        return bad('Unable to record insurer settlement',500)
    if not success:
        return procedure_failed(logger,'RecordInsuranceSettlement',message)
    return JsonResponse({'status':'success','invoice_id':invoice_id,
                         'amount_received':str(received),'message':message})


@jwt_required(allowed_roles=['Receptionist'])
@require_GET
def get_outstanding_balance_compat(request, invoice_id):
    """Legacy /api/billing/balance/<id>/ response, with branch-based authorization."""
    try:
        employee_id, branch_id = _actor(request)
    except (ValueError, AttributeError):
        return bad('Invalid employee context', 403)
    try:
        with connection.cursor() as cursor:
            cursor.execute(_invoice_summary_sql(), [invoice_id, branch_id, employee_id])
            record = cursor.fetchone()
    except DatabaseError:
        logger.exception('Balance lookup failed')
        return bad('Unable to retrieve outstanding balance', 500)
    if record is None:
        return bad('Invoice not found', 404)
    return JsonResponse({
        'success': True, 'invoice_id': record[0],
        'outstanding_balance': str(record[7]),
    })
