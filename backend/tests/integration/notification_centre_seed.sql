-- Fictional identities only; source tables are loaded from actual migrations.
INSERT INTO auth.users VALUES
 ('00000000-0000-0000-0000-000000000001'),('00000000-0000-0000-0000-000000000002'),
 ('00000000-0000-0000-0000-000000000003'),('00000000-0000-0000-0000-000000000004');
INSERT INTO patients(id,email,first_name,last_name,date_of_birth,timezone) VALUES
 ('00000000-0000-0000-0000-000000000001','patient@synthetic.invalid','Synthetic','Patient','1960-01-01','America/Los_Angeles'),
 ('00000000-0000-0000-0000-000000000004','foreign@synthetic.invalid','Foreign','Patient','1960-01-01','America/Los_Angeles');
INSERT INTO clinics(id,display_name,canonical_name) VALUES
 ('00000000-0000-0000-0000-000000000007','Synthetic clinic','synthetic clinic');
INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id) VALUES
 ('00000000-0000-0000-0000-000000000002','one@synthetic.invalid','First','Clinician','Synthetic','Synthetic clinic','00000000-0000-0000-0000-000000000007'),
 ('00000000-0000-0000-0000-000000000003','two@synthetic.invalid','Second','Clinician','Synthetic','Synthetic clinic','00000000-0000-0000-0000-000000000007');
INSERT INTO care_teams(id,patient_id,clinician_id,role,status) VALUES
 ('00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','primary_care','active');
