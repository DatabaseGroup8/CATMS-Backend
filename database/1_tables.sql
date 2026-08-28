CREATE DATABASE IF NOT EXISTS catms_db;
USE catms_db;

-- 1. Address Table
CREATE TABLE Address (
    address_id INT PRIMARY KEY AUTO_INCREMENT,
    address_line_1 VARCHAR(150),
    address_line_2 VARCHAR(150),
    city VARCHAR(50),
    province VARCHAR(50),
    postal_code VARCHAR(10)
);

-- 2. User Table
CREATE TABLE User (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    address_id INT,
    full_name VARCHAR(100),
    NIC VARCHAR(20),
    gender VARCHAR(10),
    DOB DATE,
    email VARCHAR(150),
    contact_no VARCHAR(15),
    Password_hash VARCHAR(255),
    FOREIGN KEY (address_id) REFERENCES Address(address_id)
);

-- 3. Branch Table
CREATE TABLE Branch (
    branch_id INT PRIMARY KEY AUTO_INCREMENT,
    branch_name VARCHAR(100),
    district VARCHAR(50),
    contact_id INT,
    address_id INT,
    FOREIGN KEY (address_id) REFERENCES Address(address_id)
);

-- 4. Employee Table
CREATE TABLE Employee (
    employee_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    branch_id INT,
    role VARCHAR(50),
    salary DECIMAL(10,2),
    joined_date DATE,
    FOREIGN KEY (user_id) REFERENCES User(user_id),
    FOREIGN KEY (branch_id) REFERENCES Branch(branch_id)
);

-- 5. Doctor Table
CREATE TABLE Doctor (
    doctor_id INT PRIMARY KEY AUTO_INCREMENT,
    employee_id INT,
    room_no VARCHAR(10),
    medical_licence_number VARCHAR(50),
    FOREIGN KEY (employee_id) REFERENCES Employee(employee_id)
);

-- 6. Patient Table
CREATE TABLE Patient (
    patient_id INT AUTO_INCREMENT PRIMARY KEY,
    address_id INT,
    registered_branch_id INT,
    contact_no VARCHAR(20),
    emergency_contact_no VARCHAR(20),
    blood_group VARCHAR(5),
    full_name VARCHAR(100),
    allergies TEXT,
    chronic_conditions TEXT,
    NIC VARCHAR(20),
    gender VARCHAR(20),
    DOB DATE,
    email VARCHAR(254),
    FOREIGN KEY (address_id) REFERENCES Address(address_id),
    FOREIGN KEY (registered_branch_id) REFERENCES Branch(branch_id)
);

-- 7. Condition category Table
CREATE TABLE Condition_category( 
    condition_category_id INT AUTO_INCREMENT PRIMARY KEY, 
    category_name VARCHAR(100)
);

-- 8. Conditions
CREATE TABLE Conditions( 
    condition_id INT AUTO_INCREMENT PRIMARY KEY, 
    condition_category_id INT, 
    condition_name VARCHAR(100), 
    description TEXT, 
    FOREIGN KEY (condition_category_id) REFERENCES Condition_category(condition_category_id)
); 

-- 9. Patient_condition 
CREATE TABLE Patient_condition( 
    patient_condition_id INT AUTO_INCREMENT PRIMARY KEY, 
    patient_id INT,
    condition_id INT,
    diagnosed_date DATE , 
    is_chronic BOOLEAN, 
    current_status VARCHAR(30), 
    FOREIGN KEY (patient_id) REFERENCES Patient(patient_id), 
    FOREIGN KEY (condition_id) REFERENCES Conditions(condition_id)
);

-- 10. Specialization Table
CREATE TABLE Specialization (
    specialization_id INT AUTO_INCREMENT PRIMARY KEY,
    specialization_name VARCHAR(100),
    description TEXT
);

-- 11. Doctor_Specialization Table
CREATE TABLE Doctor_Specialization (
    specialization_id INT,
    doctor_id INT,
    PRIMARY KEY (specialization_id, doctor_id),
    FOREIGN KEY (specialization_id) REFERENCES Specialization(specialization_id),
    FOREIGN KEY (doctor_id) REFERENCES Doctor(doctor_id)
);

-- 12. Time_Slot Table
CREATE TABLE Time_Slot (
    time_slot_id INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id INT,
    branch_id INT,
    available_date DATE,
    start_time TIME,
    end_time TIME,
    FOREIGN KEY (doctor_id) REFERENCES Doctor(doctor_id),
    FOREIGN KEY (branch_id) REFERENCES Branch(branch_id)
);

-- 13. Appointment Table
CREATE TABLE Appointment (
    appointment_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    time_slot_id INT,
    type VARCHAR(50),
    status VARCHAR(50),
    notes TEXT,
    updated_at DATE,
    created_at DATE,
    FOREIGN KEY (user_id) REFERENCES User(user_id),
    FOREIGN KEY (time_slot_id) REFERENCES Time_Slot(time_slot_id)
);

