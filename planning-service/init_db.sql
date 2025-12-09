-- Planning Service Database Schema

-- Technicians table
CREATE TABLE IF NOT EXISTS technicians (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150),
    phone VARCHAR(20),
    specialty VARCHAR(100),
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inspections table
CREATE TABLE IF NOT EXISTS inspections (
    id SERIAL PRIMARY KEY,
    wagon_id VARCHAR(50) NOT NULL,
    client_company VARCHAR(100) NOT NULL,
    issue_description TEXT,
    urgency VARCHAR(20) DEFAULT 'normal',
    requested_date DATE,
    scheduled_date TIMESTAMP,
    location VARCHAR(200),
    status VARCHAR(50) DEFAULT 'pending',
    technician_id INTEGER REFERENCES technicians(id),
    findings TEXT,
    parts_needed JSONB,
    estimated_repair_hours DECIMAL(5,2),
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Availability slots table
CREATE TABLE IF NOT EXISTS availability_slots (
    id SERIAL PRIMARY KEY,
    technician_id INTEGER REFERENCES technicians(id),
    slot_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_booked BOOLEAN DEFAULT false,
    inspection_id INTEGER REFERENCES inspections(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(status);
CREATE INDEX IF NOT EXISTS idx_inspections_wagon_id ON inspections(wagon_id);
CREATE INDEX IF NOT EXISTS idx_availability_date ON availability_slots(slot_date);
CREATE INDEX IF NOT EXISTS idx_availability_technician ON availability_slots(technician_id);

-- Insert sample technicians
INSERT INTO technicians (name, email, phone, specialty, is_available) VALUES
    ('Jean Dupont', 'jean.dupont@devmateriels.fr', '+33 1 23 45 67 89', 'Système de freinage', true),
    ('Marie Martin', 'marie.martin@devmateriels.fr', '+33 1 23 45 67 90', 'Électricité', true),
    ('Pierre Bernard', 'pierre.bernard@devmateriels.fr', '+33 1 23 45 67 91', 'Hydraulique', true),
    ('Sophie Petit', 'sophie.petit@devmateriels.fr', '+33 1 23 45 67 92', 'Mécanique générale', true),
    ('Luc Moreau', 'luc.moreau@devmateriels.fr', '+33 1 23 45 67 93', 'Système de freinage', true)
ON CONFLICT DO NOTHING;

-- Generate availability slots for the next 30 days
DO $$
DECLARE
    tech_id INTEGER;
    slot_date DATE;
    slot_start TIME;
BEGIN
    FOR tech_id IN SELECT id FROM technicians LOOP
        FOR slot_date IN SELECT generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '30 days', '1 day')::DATE LOOP
            -- Morning slot: 08:00 - 12:00
            INSERT INTO availability_slots (technician_id, slot_date, start_time, end_time, is_booked)
            VALUES (tech_id, slot_date, '08:00:00', '12:00:00', false)
            ON CONFLICT DO NOTHING;
            
            -- Afternoon slot: 14:00 - 18:00
            INSERT INTO availability_slots (technician_id, slot_date, start_time, end_time, is_booked)
            VALUES (tech_id, slot_date, '14:00:00', '18:00:00', false)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END LOOP;
END $$;
