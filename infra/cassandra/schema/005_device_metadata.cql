-- Display metadata for the environmental/planner role's map view (R1). Small, static
-- lookup table - one row per known device, read once and cached by the backend
-- (CassandraReader.device_metadata_sync). Placement is not arbitrary: derived from
-- analyzing each device's actual 8-day co/lpg/smoke statistics in the source Kaggle
-- dataset (see REQUIREMENTS.md D28's neighboring context / project plan history) -
-- persistently-elevated-low-variance -> roadside, tight-low-variance -> quiet area,
-- low-mean-high-variance -> intermittently exposed near the river.
CREATE TABLE IF NOT EXISTS iot.device_metadata (
    device_id  text PRIMARY KEY,
    name       text,
    area       text,
    lat        double,
    lon        double
);

INSERT INTO iot.device_metadata (device_id, name, area, lat, lon) VALUES
    ('b8:27:eb:bf:9d:51', 'Kaiserstrasse', 'Hauptverkehrsachse (B70)', 52.5220, 7.3255);
INSERT INTO iot.device_metadata (device_id, name, area, lat, lon) VALUES
    ('1c:bf:ce:15:ec:4d', 'Baccum', 'Wohngebiet / Gruenzone', 52.5340, 7.3130);
INSERT INTO iot.device_metadata (device_id, name, area, lat, lon) VALUES
    ('00:0f:00:70:91:0a', 'Emsbruecke', 'Emsufer (Konrad-Adenauer-Ring)', 52.5265, 7.3160);
