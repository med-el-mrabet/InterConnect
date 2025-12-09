"""
Database models for Planning Service.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date
import json

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://planning_user:planning_pass@localhost:5432/planning_db')


def get_db_connection():
    """Create a database connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def get_all_technicians():
    """Get all technicians."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM technicians ORDER BY name")
            return cur.fetchall()
    finally:
        conn.close()


def get_technician_by_id(technician_id):
    """Get technician by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM technicians WHERE id = %s", (technician_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_available_slots(start_date, end_date, specialty=None):
    """Get available slots within a date range."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT 
                    a.id, a.slot_date, a.start_time, a.end_time, a.is_booked,
                    t.id as technician_id, t.name as technician_name, t.specialty
                FROM availability_slots a
                JOIN technicians t ON a.technician_id = t.id
                WHERE a.is_booked = false 
                  AND t.is_available = true
                  AND a.slot_date >= %s 
                  AND a.slot_date <= %s
            """
            params = [start_date, end_date]
            
            if specialty:
                query += " AND t.specialty ILIKE %s"
                params.append(f"%{specialty}%")
            
            query += " ORDER BY a.slot_date, a.start_time"
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_slot_by_id(slot_id):
    """Get availability slot by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.*, t.name as technician_name, t.specialty
                FROM availability_slots a
                JOIN technicians t ON a.technician_id = t.id
                WHERE a.id = %s
            """, (slot_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_earliest_available_dates(days_ahead=14):
    """Get the earliest available dates for inspection."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT a.slot_date, 
                       array_agg(DISTINCT t.specialty) as specialties,
                       COUNT(*) as available_slots
                FROM availability_slots a
                JOIN technicians t ON a.technician_id = t.id
                WHERE a.is_booked = false 
                  AND t.is_available = true
                  AND a.slot_date >= CURRENT_DATE
                  AND a.slot_date <= CURRENT_DATE + INTERVAL '%s days'
                GROUP BY a.slot_date
                ORDER BY a.slot_date
                LIMIT 10
            """ % days_ahead)
            return cur.fetchall()
    finally:
        conn.close()


def create_inspection(data):
    """Create a new inspection request."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO inspections 
                    (wagon_id, client_company, issue_description, urgency, requested_date, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                RETURNING *
            """, (
                data['wagon_id'],
                data['client_company'],
                data.get('issue_description', ''),
                data.get('urgency', 'normal'),
                data.get('requested_date')
            ))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_inspection_by_id(inspection_id):
    """Get inspection by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT i.*, t.name as technician_name, t.specialty as technician_specialty
                FROM inspections i
                LEFT JOIN technicians t ON i.technician_id = t.id
                WHERE i.id = %s
            """, (inspection_id,))
            return cur.fetchone()
    finally:
        conn.close()


def schedule_inspection(inspection_id, scheduled_date, location, technician_id):
    """Schedule an inspection with a specific date and technician."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Update the inspection
            cur.execute("""
                UPDATE inspections 
                SET scheduled_date = %s, 
                    location = %s, 
                    technician_id = %s, 
                    status = 'scheduled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (scheduled_date, location, technician_id, inspection_id))
            inspection = cur.fetchone()
            
            # Book the availability slot
            scheduled_dt = datetime.fromisoformat(str(scheduled_date).replace('Z', '+00:00'))
            cur.execute("""
                UPDATE availability_slots 
                SET is_booked = true, inspection_id = %s
                WHERE technician_id = %s 
                  AND slot_date = %s
                  AND is_booked = false
                LIMIT 1
            """, (inspection_id, technician_id, scheduled_dt.date()))
            
            conn.commit()
            return inspection
    finally:
        conn.close()


def schedule_inspection_by_slot(inspection_id, slot_id, location):
    """Schedule an inspection using a slot ID."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get slot info
            cur.execute("SELECT * FROM availability_slots WHERE id = %s", (slot_id,))
            slot = cur.fetchone()
            
            if not slot:
                raise ValueError("Slot not found")
            
            if slot['is_booked']:
                raise ValueError("Slot is already booked")
            
            # Update inspection with slot info
            cur.execute("""
                UPDATE inspections 
                SET scheduled_date = %s, 
                    location = %s, 
                    technician_id = %s, 
                    status = 'scheduled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (
                slot['slot_date'],
                location,
                slot['technician_id'],
                inspection_id
            ))
            inspection = cur.fetchone()
            
            # Book the slot
            cur.execute("""
                UPDATE availability_slots 
                SET is_booked = true, inspection_id = %s
                WHERE id = %s
            """, (inspection_id, slot_id))
            
            conn.commit()
            return inspection
    finally:
        conn.close()


def complete_inspection(inspection_id, findings, parts_needed, estimated_repair_hours):
    """Complete an inspection with findings."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE inspections 
                SET findings = %s, 
                    parts_needed = %s, 
                    estimated_repair_hours = %s,
                    status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (
                findings,
                json.dumps(parts_needed),
                estimated_repair_hours,
                inspection_id
            ))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_inspections_by_status(status=None, client_company=None):
    """Get inspections filtered by status and/or client."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT i.*, t.name as technician_name
                FROM inspections i
                LEFT JOIN technicians t ON i.technician_id = t.id
                WHERE 1=1
            """
            params = []
            
            if status:
                query += " AND i.status = %s"
                params.append(status)
            
            if client_company:
                query += " AND i.client_company = %s"
                params.append(client_company)
            
            query += " ORDER BY i.created_at DESC"
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()
