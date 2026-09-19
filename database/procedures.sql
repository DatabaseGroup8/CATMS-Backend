DELIMITER //

CREATE PROCEDURE AddMedication(
    IN p_generic_name VARCHAR(100),
    IN p_manufacturer VARCHAR(100),
    IN p_form VARCHAR(50),
    IN p_contraindications VARCHAR(255),
    IN p_side_effects VARCHAR(255),
    
    OUT p_medication_id INT,
    OUT p_error_message VARCHAR(255),
    OUT p_success BOOLEAN
)
proc_label: BEGIN
    DECLARE v_duplicate_count INT DEFAULT 0;
    
    -- 1. The Error Handler: If anything crashes, undo the changes and report back
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

DELIMITER ;
