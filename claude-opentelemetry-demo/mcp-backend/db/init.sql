-- The firm database both services read, laid out per tenant the way the
-- reference backend does: one props table per org in meta_db, tenant data
-- in org_<n>_* tables, conversation state in conv_db. MariaDB runs this
-- file once, on first start, so seeding adds no spans to the traces.

CREATE DATABASE IF NOT EXISTS fed_db;
CREATE DATABASE IF NOT EXISTS meta_db;
CREATE DATABASE IF NOT EXISTS conv_db;
GRANT ALL PRIVILEGES ON fed_db.* TO 'lxuser'@'%';
GRANT ALL PRIVILEGES ON meta_db.* TO 'lxuser'@'%';
GRANT ALL PRIVILEGES ON conv_db.* TO 'lxuser'@'%';

CREATE TABLE fed_db.orgs_list (org_id INT PRIMARY KEY, name VARCHAR(255));
CREATE TABLE fed_db.actors_list (actor_id INT PRIMARY KEY, email VARCHAR(255), org_id INT);
INSERT INTO fed_db.orgs_list VALUES
  (1, 'Firm 1'),
  (2, 'Firm 2'),
  (3, 'Firm 3'),
  (4, 'Firm 4'),
  (5, 'Firm 5'),
  (6, 'Firm 6'),
  (7, 'Firm 7'),
  (8, 'Firm 8'),
  (9, 'Firm 9'),
  (10, 'Firm 10'),
  (11, 'Firm 11'),
  (12, 'Firm 12'),
  (13, 'Firm 13'),
  (14, 'Firm 14'),
  (15, 'Firm 15'),
  (16, 'Firm 16'),
  (17, 'Firm 17'),
  (18, 'Firm 18'),
  (19, 'Firm 19'),
  (20, 'Firm 20'),
  (21, 'Firm 21'),
  (22, 'Firm 22'),
  (23, 'Firm 23'),
  (24, 'Firm 24'),
  (25, 'Firm 25'),
  (26, 'Firm 26'),
  (27, 'Firm 27'),
  (28, 'Firm 28'),
  (29, 'Firm 29'),
  (30, 'Firm 30'),
  (31, 'Firm 31'),
  (32, 'Firm 32'),
  (33, 'Firm 33'),
  (34, 'Firm 34'),
  (35, 'Firm 35'),
  (36, 'Firm 36'),
  (37, 'Firm 37'),
  (38, 'Firm 38'),
  (39, 'Firm 39'),
  (40, 'Firm 40'),
  (41, 'Firm 41'),
  (42, 'Firm 42'),
  (43, 'Firm 43'),
  (44, 'Firm 44'),
  (45, 'Firm 45'),
  (46, 'Firm 46'),
  (47, 'Firm 47'),
  (48, 'Firm 48'),
  (49, 'Firm 49'),
  (50, 'Firm 50'),
  (51, 'Firm 51'),
  (52, 'Firm 52'),
  (53, 'Firm 53'),
  (54, 'Acme Engineering'),
  (55, 'Firm 55'),
  (56, 'Firm 56'),
  (57, 'Firm 57'),
  (58, 'Firm 58'),
  (59, 'Firm 59'),
  (60, 'Firm 60');
INSERT INTO fed_db.actors_list VALUES (1, 'estimator@example.com', 54);

CREATE TABLE meta_db.org_1_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_1_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_2_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_2_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_3_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_3_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_4_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_4_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_5_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_5_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_6_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_6_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_7_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_7_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_8_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_8_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_9_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_9_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_10_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_10_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_11_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_11_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_12_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_12_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_13_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_13_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_14_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_14_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_15_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_15_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_16_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_16_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_17_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_17_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_18_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_18_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_19_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_19_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_20_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_20_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_21_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_21_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_22_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_22_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_23_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_23_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_24_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_24_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_25_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_25_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_26_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_26_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_27_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_27_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_28_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_28_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_29_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_29_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_30_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_30_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_31_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_31_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_32_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_32_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_33_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_33_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_34_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_34_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_35_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_35_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_36_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_36_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_37_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_37_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_38_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_38_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_39_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_39_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_40_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_40_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_41_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_41_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_42_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_42_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_43_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_43_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_44_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_44_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_45_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_45_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_46_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_46_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_47_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_47_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_48_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_48_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_49_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_49_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_50_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_50_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_51_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_51_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_52_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_52_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_53_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_53_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_54_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_54_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_55_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_55_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_56_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_56_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_57_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_57_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_58_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_58_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_59_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_59_props VALUES ('region', 'us-west');
CREATE TABLE meta_db.org_60_props (k VARCHAR(64) PRIMARY KEY, v VARCHAR(255));
INSERT INTO meta_db.org_60_props VALUES ('region', 'us-west');

CREATE TABLE meta_db.org_54_corp (org_id INT PRIMARY KEY, name VARCHAR(255), hq VARCHAR(255), sectors VARCHAR(255));
INSERT INTO meta_db.org_54_corp VALUES (54, 'Acme Engineering', 'San Diego, CA', 'water, transit, education, healthcare');
CREATE TABLE meta_db.org_54_bids (bid_id VARCHAR(32) PRIMARY KEY, title VARCHAR(255), client VARCHAR(255), due_date VARCHAR(32), team VARCHAR(255));
INSERT INTO meta_db.org_54_bids VALUES ('wrw50evpgs8z9l', 'Sample RFP', 'Unknown client', '', '["Marcus Lee", "Grace Kim"]');
CREATE TABLE meta_db.org_54_employees (name VARCHAR(255) PRIMARY KEY, role VARCHAR(255), years INT);
INSERT INTO meta_db.org_54_employees VALUES
  ('Dana Whitfield', 'Principal in Charge', 24),
  ('Marcus Lee', 'Senior Project Manager', 17),
  ('Priya Raman', 'Water Resources Lead', 12),
  ('Tomás Ortega', 'Structural Engineer', 9),
  ('Grace Kim', 'Proposal Manager', 7);
CREATE TABLE meta_db.org_54_projects (project_id VARCHAR(32) PRIMARY KEY, name VARCHAR(255), client VARCHAR(255), year INT, value_usd BIGINT, summary TEXT);
INSERT INTO meta_db.org_54_projects VALUES
  ('414945489583W', 'Riverside Wastewater Treatment Upgrade', 'City of Riverside', 2023, 48000000, 'Expansion of a 12 MGD plant with new clarifiers and a biosolids building.'),
  ('913385709268W', 'North County Transit Center', 'North County Transit District', 2022, 31500000, 'Bus transfer hub with a parking structure and solar canopies.'),
  ('578692717522W', 'Harbor Bridge Seismic Retrofit', 'Port Authority', 2021, 22000000, 'Seismic retrofit of a 1960s steel truss bridge under live traffic.'),
  ('043904274067W', 'Mesa Unified K-8 Campus', 'Mesa Unified School District', 2024, 64000000, 'New K-8 campus for 1,100 students, design-build, LEED Gold.'),
  ('394718595955W', 'Valley Medical Center Central Plant', 'Valley Health', 2023, 18750000, 'Chiller and boiler replacement in an operating hospital.');
CREATE TABLE conv_db.c_54_chunk (snippet_id VARCHAR(32) PRIMARY KEY, project_id VARCHAR(32), title VARCHAR(255), text TEXT);
INSERT INTO conv_db.c_54_chunk VALUES
  ('1790941918186566039', '414945489583W', 'Riverside final report', 'Delivered the clarifier expansion three weeks early with no permit violations during construction.'),
  ('-7873854199872705048', '913385709268W', 'Transit center lessons learned', 'Phasing around live bus operations kept the hub open throughout construction.'),
  ('63969276736009642', '578692717522W', 'Bridge retrofit closeout', 'Night-only closures and a temporary bypass let traffic run during the retrofit.'),
  ('-8857541797583122584', '043904274067W', 'K-8 campus award letter', 'The district cited our community engagement plan and the LEED Gold commitment.'),
  ('2233263107820336767', '394718595955W', 'Central plant risk memo', 'Shutdown windows of four hours limited the chiller swaps to two per weekend.');
-- Progress of each managed-agent session, written by the app's poller.
CREATE TABLE conv_db.c_54_facet (id VARCHAR(64) PRIMARY KEY, type VARCHAR(32), data TEXT, update_time_ms BIGINT);
