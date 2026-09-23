DELIMITER //
-- Procedure: AddMedication

CREATE PROCEDURE AddMedication(
    --IN parameters receive the raw data from backend
    --MySQL automatically takes values from the backend and drop into IN parameters
    IN p_generic_name VARCHAR(100),
    IN p_manufacturer VARCHAR(100),
    IN p_form VARCHAR(50),
    IN p_contraindications VARCHAR(255),
    IN p_side_effects VARCHAR(255),
    
    --OUT parameters send the final result back to the backend
    OUT p_medication_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_duplicate_count INT DEFAULT 0; --to keep track of how many identical rows already exist in the database
    
    -- 1. The Error Handler: If anything crashes, undo the changes and report back(SQL version of try....catch)
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_medication_id = NULL;
    
    -- 3. Start Transaction
    START TRANSACTION;
    
    -- 4. Validation: Prevent empty names
    IF p_generic_name IS NULL OR TRIM(p_generic_name) = '' THEN
        SET p_error_message = 'Generic name is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 5. Validation: Check for exact duplicates in the Medication table
    SELECT COUNT(*) INTO v_duplicate_count
    FROM Medication
    WHERE generic_name = p_generic_name 
    AND manufacturer = p_manufacturer
    AND form = p_form;
    
    IF v_duplicate_count > 0 THEN
        SET p_error_message = 'This medication already exists in the system';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- 6. Insert the Data
    INSERT INTO Medication (
        generic_name, 
        manufacturer, 
        form, 
        contraindications, 
        side_effects
    ) VALUES (
        p_generic_name,
        p_manufacturer,
        p_form,
        p_contraindications,
        p_side_effects
    );
    
    -- 7. Success! Grab the auto-generated INT ID
    SET p_medication_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Medication added successfully';
    
    COMMIT;
END //
--........................................................................................................................

-- Procedure: CreateConsultationWithDetails

CREATE PROCEDURE CreateConsultationWithDetails(
    IN p_appointment_id INT,
    IN p_chief_complaint VARCHAR(255),
    IN p_symptoms TEXT,
    IN p_diagnoses TEXT,
    
    -- JSON Arrays sent from the frontend
    IN p_treatments JSON,       
    IN p_prescriptions JSON,    
    
    OUT p_consultation_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_medical_record_id INT;
    DECLARE v_appointment_exists INT DEFAULT 0;
    
    -- JSON loop variables
    DECLARE v_idx INT DEFAULT 0;
    DECLARE v_array_length INT DEFAULT 0;
    
    -- Treatment extraction variables
    DECLARE v_treatment_code INT;
    
    -- Prescription extraction variables
    DECLARE v_med_id INT;
    DECLARE v_dosage VARCHAR(255);
    DECLARE v_freq VARCHAR(255);
    DECLARE v_days INT;
    DECLARE v_instr VARCHAR(255);

    -- 1. The Error Handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_consultation_id = NULL;

    -- 3. Start Transaction
    START TRANSACTION;

    -- 4. Validate Appointment
    SELECT COUNT(*) INTO v_appointment_exists 
    FROM Appointment 
    WHERE appointment_id = p_appointment_id AND status = 'Scheduled';
    
    IF v_appointment_exists = 0 THEN
        SET p_error_message = 'Valid Scheduled Appointment not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 5. Insert Medical Record
    INSERT INTO Medical_record (chief_complaint, symptoms, diagnoses)
    VALUES (p_chief_complaint, p_symptoms, p_diagnoses);
    
    SET v_medical_record_id = LAST_INSERT_ID();

    -- 6. Insert Consultation Record
    INSERT INTO Consultation_record (appointment_id, medical_record_id) 
    VALUES (p_appointment_id, v_medical_record_id);
    
    SET p_consultation_id = LAST_INSERT_ID();

    -- 7. Update Appointment Status
    UPDATE Appointment SET status = 'Completed' WHERE appointment_id = p_appointment_id;

    INSERT INTO Invoice (appointment_id, sub_total, insurance_claimed_amount)
    VALUES (p_appointment_id, 0.00, 0.00);

    -- 8. Parse and Insert Treatments
    IF p_treatments IS NOT NULL AND JSON_LENGTH(p_treatments) > 0 THEN
        SET v_array_length = JSON_LENGTH(p_treatments);
        SET v_idx = 0;
        
        WHILE v_idx < v_array_length DO
            -- Dynamically extract the treatment code based on the loop index
            SET v_treatment_code = JSON_UNQUOTE(JSON_EXTRACT(p_treatments, CONCAT('$[', v_idx, '].treatment_service_code')));
            
            INSERT INTO Treatment (medical_record_id, treatment_service_code)
            VALUES (v_medical_record_id, v_treatment_code);
            
            SET v_idx = v_idx + 1;
        END WHILE;
    END IF;

    -- 9. Parse and Insert Prescriptions
    IF p_prescriptions IS NOT NULL AND JSON_LENGTH(p_prescriptions) > 0 THEN
        SET v_array_length = JSON_LENGTH(p_prescriptions);
        SET v_idx = 0;
        
        WHILE v_idx < v_array_length DO
            -- Extract all prescription fields for the current array object
            SET v_med_id = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].medication_id')));
            SET v_dosage = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].dosage')));
            SET v_freq = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].frequency')));
            SET v_days = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].duration_days')));
            SET v_instr = JSON_UNQUOTE(JSON_EXTRACT(p_prescriptions, CONCAT('$[', v_idx, '].instructions')));
            
            INSERT INTO Prescription (medical_record_id, medication_id, dosage, frequency, duration_days, instructions)
            VALUES (v_medical_record_id, v_med_id, v_dosage, v_freq, v_days, v_instr);
            
            SET v_idx = v_idx + 1;
        END WHILE;
    END IF;

    -- 10. Commit the Transaction
    SET p_success = TRUE;
    SET p_error_message = 'Consultation and details saved successfully';

    COMMIT;
END //
--...............................................................................................................................

-- Procedure: AddPrescriptionWithItems

CREATE PROCEDURE AddPrescriptionWithItems(
    IN p_medical_record_id INT,
    IN p_prescription_items JSON,
    
    OUT p_items_added INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_record_exists INT DEFAULT 0;
    DECLARE v_idx INT DEFAULT 0;
    DECLARE v_array_length INT DEFAULT 0;
    
    -- Extraction variables
    DECLARE v_med_id INT;
    DECLARE v_dosage VARCHAR(50);
    DECLARE v_freq VARCHAR(50);
    DECLARE v_days VARCHAR(50);
    DECLARE v_instr VARCHAR(255);

    -- 1. Error Handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_items_added = 0;

    -- 3. Start Transaction
    START TRANSACTION;

    -- 4. Validate Medical Record
    SELECT COUNT(*) INTO v_record_exists 
    FROM Medical_record 
    WHERE medical_record_id = p_medical_record_id;
    
    IF v_record_exists = 0 THEN
        SET p_error_message = 'Medical record not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 5. Validate JSON Array
    IF p_prescription_items IS NULL OR JSON_LENGTH(p_prescription_items) = 0 THEN
        SET p_error_message = 'Prescription items array cannot be empty';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 6. Parse and Insert Loop
    SET v_array_length = JSON_LENGTH(p_prescription_items);
    
    WHILE v_idx < v_array_length DO
        SET v_med_id = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].medication_id')));
        SET v_dosage = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].dosage')));
        SET v_freq = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].frequency')));
        SET v_days = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].duration_days')));
        SET v_instr = JSON_UNQUOTE(JSON_EXTRACT(p_prescription_items, CONCAT('$[', v_idx, '].instructions')));
        
        INSERT INTO Prescription (
            medical_record_id, medication_id, dosage, frequency, duration_days, instructions
        ) VALUES (
            p_medical_record_id, v_med_id, v_dosage, v_freq, v_days, v_instr
        );
        
        SET p_items_added = p_items_added + 1;
        SET v_idx = v_idx + 1;
    END WHILE;

    -- 7. Success Output
    SET p_success = TRUE;
    SET p_error_message = 'Prescriptions added successfully';

    COMMIT;
END;

--......................................................................................................................................
--Procedure: AddPatientCondition
CREATE PROCEDURE AddPatientCondition(
    IN p_patient_id INT,
    IN p_condition_id INT,
    IN p_diagnosed_date DATE,
    IN p_is_chronic BOOLEAN,
    IN p_current_status VARCHAR(30),
    
    OUT p_patient_condition_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_patient_exists INT DEFAULT 0;
    DECLARE v_condition_exists INT DEFAULT 0;
    DECLARE v_duplicate_count INT DEFAULT 0;

    -- 1. The Error Handler
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    -- 2. Initialize Outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_patient_condition_id = NULL;

    -- 3. Start Transaction
    START TRANSACTION;

    -- 4. Foreign Key Validation: Patient
    SELECT COUNT(*) INTO v_patient_exists 
    FROM Patient 
    WHERE patient_id = p_patient_id;
    
    IF v_patient_exists = 0 THEN
        SET p_error_message = 'Patient not found in the system';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 5. Foreign Key Validation: Condition
    SELECT COUNT(*) INTO v_condition_exists 
    FROM Conditions 
    WHERE condition_id = p_condition_id;
    
    IF v_condition_exists = 0 THEN
        SET p_error_message = 'Condition not found in the medical dictionary';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    -- 6. Logical Validation: Prevent Duplicates
    SELECT COUNT(*) INTO v_duplicate_count FROM Patient_Condition 
    WHERE patient_id = p_patient_id 
    AND condition_id = p_condition_id
    AND diagnosed_date = p_diagnosed_date;
    
    IF v_duplicate_count > 0 THEN
        SET p_error_message = 'This patient already has this condition recorded for today';
        ROLLBACK; LEAVE proc_label;
    END IF;

    -- 7. Insert the Record
    INSERT INTO Patient_Condition (
        patient_id, 
        condition_id, 
        diagnosed_date, 
        is_chronic, 
        current_status
    ) VALUES (
        p_patient_id, 
        p_condition_id, 
        p_diagnosed_date, 
        p_is_chronic, 
        p_current_status
    );

    -- 8. Success Output
    SET p_patient_condition_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Patient condition recorded successfully';

    COMMIT;
END;

--..............................................................................................................
--Procedure: AddTreatment
CREATE PROCEDURE AddTreatment(
    IN p_medical_record_id INT,
    IN p_treatment_service_code INT,
    
    OUT p_treatment_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_record_exists INT DEFAULT 0;
    DECLARE v_service_exists INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;

    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_treatment_id = NULL;

    START TRANSACTION;

    SELECT COUNT(*) INTO v_record_exists 
    FROM Medical_record 
    WHERE medical_record_id = p_medical_record_id;
    
    IF v_record_exists = 0 THEN
        SET p_error_message = 'Medical record not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    SELECT COUNT(*) INTO v_service_exists 
    FROM Treatment_catalogue 
    WHERE treatment_service_code = p_treatment_service_code;
    
    IF v_service_exists = 0 THEN
        SET p_error_message = 'Invalid treatment service code';
        ROLLBACK;
        LEAVE proc_label;
    END IF;

    INSERT INTO Treatment (medical_record_id, treatment_service_code)
    VALUES (p_medical_record_id, p_treatment_service_code);

    SET p_treatment_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Treatment added successfully';

    COMMIT;
END;

--.................................................................................................................
-- Procedure: Record Payment
DROP PROCEDURE IF EXISTS `RecordPayment`$$
CREATE PROCEDURE `RecordPayment`(
    IN p_invoice_id INT,
    IN p_user_id INT,
    IN p_appointment_id INT,
    IN p_payment_amount DECIMAL(10,2),
    IN p_payment_method VARCHAR(100),
    OUT p_payment_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_outstanding DECIMAL(10,2);
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    
    START TRANSACTION;
    
    -- Check balance using the custom function
    SET v_outstanding = CalculateOutstandingBalance(p_invoice_id);
    
    IF p_payment_amount <= 0 THEN
        SET p_error_message = 'Payment amount must be greater than zero';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    IF p_payment_amount > v_outstanding THEN
        SET p_error_message = 'Payment exceeds outstanding balance';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- Insert the payment record[cite: 1, 2]
    INSERT INTO Payment (Invoice_id, patient_id, payment_method, status, payment_date, payment_amount)
    VALUES (p_invoice_id, p_user_id, p_payment_method, 'Completed', CURDATE(), p_payment_amount);
    
    SET p_payment_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Payment recorded successfully';
    
    COMMIT;
END proc_label$$

--...................................................................................................................................
-- Procedure: Process Insurance Claim
DROP PROCEDURE IF EXISTS `ProcessInsuranceClaim`$$
CREATE PROCEDURE `ProcessInsuranceClaim`(
    IN p_invoice_id INT,
    IN p_insurance_id INT,
    IN p_claim_amount DECIMAL(10,2),
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_invoice_exists INT DEFAULT 0;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    START TRANSACTION;
    
    SELECT COUNT(*) INTO v_invoice_exists FROM Invoice WHERE Invoice_id = p_invoice_id;
    
    IF v_invoice_exists = 0 THEN
        SET p_error_message = 'Invoice not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    INSERT INTO Claims (insurance_id, invoice_id, issued_date)
    VALUES (p_insurance_id, p_invoice_id, CURDATE());
    
    UPDATE Invoice 
    SET insurance_claimed_amount = insurance_claimed_amount + p_claim_amount
    WHERE Invoice_id = p_invoice_id;
    
    SET p_success = TRUE;
    SET p_error_message = 'Claim processed successfully';
    
    COMMIT;
END proc_label$$

DELIMITER ;
--...................................................................................................................................
-- Procedure: Add timeslots to timslot table
DROP PROCEDURE IF EXISTS `AddTimeSlot`$$

CREATE DEFINER=`root`@`localhost` PROCEDURE `AddTimeSlot`(
    IN p_doctor_id CHAR(36),
    IN p_branch_id CHAR(36),
    IN p_available_date DATE,
    IN p_start_time TIME,
    IN p_end_time TIME,
   
    OUT p_time_slot_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    -- ALL DECLARE STATEMENTS MUST COME FIRST
    DECLARE v_doctor_exists INT DEFAULT 0;
    DECLARE v_branch_exists INT DEFAULT 0;
   
    -- Error handler (must be declared AFTER variables but BEFORE any SET/SELECT)
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
   
    -- NOW executable statements can start
    -- Initialize outputs
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_time_slot_id = NULL;
   
    -- Start transaction
    START TRANSACTION;
   
    -- Validation: Check if doctor exists
    SELECT COUNT(*) INTO v_doctor_exists
    FROM doctor
    WHERE doctor_id = p_doctor_id;
   
    IF v_doctor_exists = 0 THEN
        SET p_error_message = 'Doctor not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Validation: Check if branch exists and is active
    SELECT COUNT(*) INTO v_branch_exists
    FROM branch
    WHERE branch_id = p_branch_id AND is_active = TRUE;
   
    IF v_branch_exists = 0 THEN
        SET p_error_message = 'Branch not found or inactive';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Validation: Check required fields
    IF p_available_date IS NULL THEN
        SET p_error_message = 'Available date is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    IF p_start_time IS NULL THEN
        SET p_error_message = 'Start time is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    IF p_end_time IS NULL THEN
        SET p_error_message = 'End time is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Validation: Check end_time > start_time
    IF p_end_time <= p_start_time THEN
        SET p_error_message = 'End time must be after start time';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
   
    -- Insert time slot
    INSERT INTO time_slot (
        doctor_id, branch_id, available_date, 
        is_booked, start_time, end_time
    ) VALUES (
        v_time_slot_id, p_doctor_id, p_branch_id, p_available_date, 
        FALSE, p_start_time, p_end_time
    );
   
    -- Success
    SET p_time_slot_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Time slot added successfully';
   
    COMMIT;
END proc_label$$

--...................................................................................................................................
-- Procedure: CreateTimeSlot
CREATE DEFINER=`root`@`localhost` PROCEDURE `CreateTimeSlot`(
    IN p_doctor_id INT,
    IN p_branch_id INT,
    IN p_available_date DATE,
    IN p_start_time TIME,
    IN p_end_time TIME,
    OUT p_time_slot_id CHAR(36),
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    -- ...existing code from AddTimeSlot...
    DECLARE v_time_slot_id INT;
    DECLARE v_doctor_exists INT DEFAULT 0;
    DECLARE v_branch_exists INT DEFAULT 0;
    --If an SQL error happens while executing this block, run the error-handling code and then exit the block
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_time_slot_id = NULL;
    START TRANSACTION;
    SELECT COUNT(*) INTO v_doctor_exists FROM doctor WHERE doctor_id = p_doctor_id;
    IF v_doctor_exists = 0 THEN
        SET p_error_message = 'Doctor not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    SELECT COUNT(*) INTO v_branch_exists FROM branch WHERE branch_id = p_branch_id AND is_active = TRUE;
    IF v_branch_exists = 0 THEN
        SET p_error_message = 'Branch not found or inactive';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    IF p_available_date IS NULL THEN
        SET p_error_message = 'Available date is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    IF p_start_time IS NULL THEN
        SET p_error_message = 'Start time is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    IF p_end_time IS NULL THEN
        SET p_error_message = 'End time is required';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    IF p_end_time <= p_start_time THEN
        SET p_error_message = 'End time must be after start time';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    SET v_time_slot_id = UUID();
    INSERT INTO time_slot (
        time_slot_id, doctor_id, branch_id, available_date, 
        is_booked, start_time, end_time
    ) VALUES (
        v_time_slot_id, p_doctor_id, p_branch_id, p_available_date, 
        FALSE, p_start_time, p_end_time
    );
    SET p_time_slot_id = v_time_slot_id;
    SET p_success = TRUE;
    SET p_error_message = 'Time slot added successfully';
    COMMIT;
END proc_label$$


--...................................................................................................................................
-- Procedure: BookAppointment

CREATE DEFINER=`root`@`localhost` PROCEDURE `BookAppointment`(
    IN p_patient_id INT,
    IN p_time_slot_id INT,
    IN p_notes TEXT,
    
    OUT p_appointment_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_appointment_id CHAR(36);
    DECLARE v_slot_exists INT DEFAULT 0;
    DECLARE v_slot_booked TINYINT DEFAULT 0;
    DECLARE v_patient_exists INT DEFAULT 0;
    DECLARE v_slot_date DATE;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    SET p_error_message = NULL;
    SET p_appointment_id = NULL;
    
    START TRANSACTION;
    
    SELECT COUNT(*) INTO v_patient_exists 
    FROM patient 
    WHERE patient_id = p_patient_id;
    
    IF v_patient_exists = 0 THEN
        SET p_error_message = 'Patient not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    SELECT COUNT(*) INTO v_slot_exists
    FROM time_slot 
    WHERE time_slot_id = p_time_slot_id;
    
    IF v_slot_exists = 0 THEN
        SET p_error_message = 'Time slot not found';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    SELECT 
        is_booked,
        available_date
    INTO v_slot_booked, v_slot_date
    FROM time_slot 
    WHERE time_slot_id = p_time_slot_id
    FOR UPDATE;
    
    IF v_slot_booked = 1 THEN
        SET p_error_message = 'Time slot already booked';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    IF v_slot_date < CURDATE() THEN
        SET p_error_message = 'Cannot book time slot in the past';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    
    UPDATE time_slot 
    SET is_booked = 1
    WHERE time_slot_id = p_time_slot_id;
    
    IF ROW_COUNT() != 1 THEN
        SET p_error_message = 'Failed to mark time slot as booked';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    INSERT INTO appointment (appointment_id, time_slot_id, patient_id, status, notes)
    VALUES (p_time_slot_id, p_patient_id, 'Scheduled', p_notes);
    
    IF ROW_COUNT() != 1 THEN
        SET p_error_message = 'Failed to create appointment record';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    SET p_appointment_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Appointment booked successfully';
    
    COMMIT;
END proc_label$$

DELIMITER //

    --Procedure Generate Invoice--
DROP PROCEDURE IF EXISTS GenerateInvoice //

CREATE PROCEDURE GenerateInvoice(
    IN p_appointment_id INT,
    OUT p_invoice_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_appointment_exists INT DEFAULT 0;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 p_error_message = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = FALSE;
    END;
    
    SET p_success = FALSE;
    SET p_error_message = NULL;
    
    START TRANSACTION;
    
    -- Verify the appointment exists and is marked as Completed
    SELECT COUNT(*) INTO v_appointment_exists 
    FROM Appointment 
    WHERE appointment_id = p_appointment_id AND status = 'Completed';
    
    IF v_appointment_exists = 0 THEN
        SET p_error_message = 'Cannot generate invoice: Appointment not completed';
        ROLLBACK;
        LEAVE proc_label;
    END IF;
    
    -- Insert the blank invoice so billing triggers can populate the sub_total later
    INSERT INTO Invoice (appointment_id, sub_total, insurance_claimed_amount)
    VALUES (p_appointment_id, 0.00, 0.00);
    
    SET p_invoice_id = LAST_INSERT_ID();
    SET p_success = TRUE;
    SET p_error_message = 'Invoice generated successfully';
    
    COMMIT;
END //

DELIMITER ;
