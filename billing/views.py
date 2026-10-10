"""Compatibility imports. Billing workflow handlers are in workflow_views.py.

Do not restore the old direct-insert process_full_checkout: invoices are finalized
by FinalizeConsultationBill and payments by RecordPayment.
"""
from .workflow_views import (
    process_full_checkout,
    get_outstanding_balance_compat as outstanding_balance,
)
