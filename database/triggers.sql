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
    
    -- Fetch the base price from the Treatment Catalogue
    SELECT base_price INTO v_treatment_price
    FROM Treatment_Catalogue
    WHERE treatment_service_code = NEW.treatment_service_code;
    
    -- Find the appointment ID tied to this treatment's medical record
    SELECT cr.appointment_id INTO v_appointment_id
    FROM Consultation_record cr
    WHERE cr.medical_record_id = NEW.medical_record_id
    LIMIT 1;
    
    -- Find the invoice for this appointment
    SELECT invoice_id INTO v_invoice_id
    FROM Invoice
    WHERE appointment_id = v_appointment_id
    LIMIT 1;
    
    -- Add the treatment cost to the invoice sub_total
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
    
    -- Block the payment if it exceeds the remaining bill
    IF NEW.payment_amount > v_outstanding THEN
        SIGNAL SQLSTATE '45000' 
        SET MESSAGE_TEXT = 'Payment rejected: Amount exceeds the outstanding invoice balance';
    END IF;
END$$

DELIMITER ;

--Trigger 3: Validate a patient's age
DELIMITER $$

DROP TRIGGER IF EXISTS validate_patient_age$$

CREATE TRIGGER validate_patient_age
BEFORE INSERT ON Patient
FOR EACH ROW
BEGIN
    IF NEW.DOB IS NOT NULL
       AND CalculateAge(NEW.DOB) < 0 THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Patient date of birth cannot be in the future.';

    END IF;
END$$

DELIMITER ;