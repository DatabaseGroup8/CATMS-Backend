DELIMITER $$

-- Trigger 1: Auto-Update Invoice Subtotal when Treatments are added
DROP TRIGGER IF EXISTS `trg_update_invoice_subtotal`$$
CREATE TRIGGER `trg_update_invoice_subtotal`
AFTER INSERT ON `Treatment`
FOR EACH ROW
BEGIN
    DECLARE v_treatment_price DECIMAL(10,2);
    DECLARE v_appointment_id INT;
    DECLARE v_invoice_id INT;
    
    -- Fetch the base price from the Treatment Catalogue[cite: 1, 2]
    SELECT base_price INTO v_treatment_price
    FROM Treatment_Catalogue
    WHERE treatment_service_code = NEW.treatment_service_code;
    
    -- Find the appointment ID tied to this treatment's medical record[cite: 1]
    SELECT cr.appointment_id INTO v_appointment_id
    FROM Consultation_record cr
    WHERE cr.medical_record_id = NEW.medical_record_id
    LIMIT 1;
    
    -- Find the invoice for this appointment[cite: 1]
    SELECT invoice_id INTO v_invoice_id
    FROM Invoice
    WHERE appointment_id = v_appointment_id
    LIMIT 1;
    
    -- Add the treatment cost to the invoice sub_total[cite: 1, 2]
    IF v_invoice_id IS NOT NULL THEN
        UPDATE Invoice
        SET sub_total = sub_total + COALESCE(v_treatment_price, 0)
        WHERE invoice_id = v_invoice_id;
    END IF;
END$$

-- Trigger 2: Prevent Overpayment
DROP TRIGGER IF EXISTS `trg_prevent_overpayment`$$
CREATE TRIGGER `trg_prevent_overpayment`
BEFORE INSERT ON `Payment`
FOR EACH ROW
BEGIN
    DECLARE v_outstanding DECIMAL(10,2);
    
    -- Calculate what is actually owed
    SET v_outstanding = CalculateOutstandingBalance(NEW.invoice_id);
    
    -- Block the payment if it exceeds the remaining bill[cite: 2]
    IF NEW.payment_amount > v_outstanding THEN
        SIGNAL SQLSTATE '45000' 
        SET MESSAGE_TEXT = 'Payment rejected: Amount exceeds the outstanding invoice balance';
    END IF;
END$$

DELIMITER ;
