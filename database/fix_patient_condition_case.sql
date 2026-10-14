-- CATMS Aiven hotfix: correct Linux case-sensitive table reference in AddPatientCondition.
-- Target database: catms_final_db. Run SELECT DATABASE() first and confirm.
-- This changes only ONE stored procedure. It does not drop/create tables or delete patient rows.

DROP PROCEDURE IF EXISTS AddPatientCondition;

DELIMITER $$

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
    SELECT COUNT(*) INTO v_duplicate_count FROM Patient_condition 
    WHERE patient_id = p_patient_id 
    AND condition_id = p_condition_id
    AND diagnosed_date = p_diagnosed_date;
    
    IF v_duplicate_count > 0 THEN
        SET p_error_message = 'This patient already has this condition recorded for today';
        ROLLBACK; LEAVE proc_label;
    END IF;

    -- 7. Insert the Record
    INSERT INTO Patient_condition (
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
END$$

DELIMITER ;
