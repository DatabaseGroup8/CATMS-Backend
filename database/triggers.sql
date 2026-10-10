-- CATMS FINAL triggers, fresh install, MySQL 8.0.16+
-- Run AFTER functions.sql and procedures.sql.
-- NO trg_update_invoice_subtotal: FinalizeConsultationBill sets subtotal atomically.
DELIMITER $$
CREATE TRIGGER trg_prevent_overpayment
BEFORE INSERT ON Payment
FOR EACH ROW
BEGIN
    DECLARE v_remaining DECIMAL(12,2);
    IF NEW.payment_amount IS NULL OR NEW.payment_amount<=0
       OR NEW.status IS NULL OR NEW.status<>'Completed'
       OR NEW.request_key IS NULL OR TRIM(NEW.request_key)='' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid completed payment or request key';
    END IF;
    SET v_remaining=CalculateOutstandingBalance(NEW.Invoice_id);
    IF v_remaining IS NULL OR NEW.payment_amount>v_remaining THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Payment exceeds patient outstanding';
    END IF;
END$$

CREATE TRIGGER validate_patient_age
BEFORE INSERT ON Patient
FOR EACH ROW
BEGIN
    IF NEW.DOB IS NOT NULL AND NEW.DOB>CURDATE() THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Patient DOB cannot be in future';
    END IF;
    SET NEW.age=CalculateAge(NEW.DOB);
END$$

CREATE TRIGGER update_patient_age_on_dob_change
BEFORE UPDATE ON Patient
FOR EACH ROW
BEGIN
    IF NEW.DOB IS NOT NULL AND NEW.DOB>CURDATE() THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Patient DOB cannot be in future';
    END IF;
    IF NOT (NEW.DOB <=> OLD.DOB) THEN
        SET NEW.age=CalculateAge(NEW.DOB);
    END IF;
END$$
DELIMITER ;
