"""
Database models for ERP WagonLits simulation.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime
import json
import uuid

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://erp_wagonlits_user:erp_wagonlits_pass@localhost:5435/erp_wagonlits_db')


def get_db_connection():
    """Create a database connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


# ==================== WAGONS ====================

def get_all_wagons():
    """Get all wagons."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM wagons ORDER BY wagon_code")
            return cur.fetchall()
    finally:
        conn.close()


def get_wagon_by_code(wagon_code):
    """Get wagon by code."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM wagons WHERE wagon_code = %s", (wagon_code,))
            return cur.fetchone()
    finally:
        conn.close()


# ==================== INSPECTION REQUESTS ====================

def create_inspection_request(data):
    """Create a new inspection request."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get wagon id if wagon_code provided
            wagon_id = None
            if data.get('wagon_code'):
                cur.execute("SELECT id FROM wagons WHERE wagon_code = %s", (data['wagon_code'],))
                wagon = cur.fetchone()
                if wagon:
                    wagon_id = wagon['id']
            
            cur.execute("""
                INSERT INTO inspection_requests 
                    (wagon_id, wagon_code, issue_description, urgency, requested_date, status)
                VALUES (%s, %s, %s, %s, %s, 'requested')
                RETURNING *
            """, (
                wagon_id,
                data.get('wagon_code'),
                data.get('issue_description'),
                data.get('urgency', 'normal'),
                data.get('requested_date')
            ))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def update_inspection_from_notification(event_data):
    """Update inspection request from notification."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            external_id = event_data.get('inspection_id')
            
            # Check if we have a matching local request
            cur.execute("""
                SELECT * FROM inspection_requests 
                WHERE wagon_code = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (event_data.get('wagon_id'),))
            existing = cur.fetchone()
            
            if existing:
                # Update existing request
                cur.execute("""
                    UPDATE inspection_requests 
                    SET external_id = %s,
                        scheduled_date = %s,
                        location = %s,
                        technician_name = %s,
                        status = %s,
                        findings = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                """, (
                    external_id,
                    event_data.get('scheduled_date'),
                    event_data.get('location'),
                    event_data.get('technician_name'),
                    event_data.get('status', existing['status']),
                    event_data.get('findings'),
                    existing['id']
                ))
            else:
                # Create new entry
                cur.execute("""
                    INSERT INTO inspection_requests 
                        (external_id, wagon_code, status, scheduled_date, location, technician_name)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    external_id,
                    event_data.get('wagon_id'),
                    event_data.get('status', 'scheduled'),
                    event_data.get('scheduled_date'),
                    event_data.get('location'),
                    event_data.get('technician_name')
                ))
            
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_inspection_requests(status=None):
    """Get inspection requests."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status:
                cur.execute(
                    "SELECT * FROM inspection_requests WHERE status = %s ORDER BY created_at DESC",
                    (status,)
                )
            else:
                cur.execute("SELECT * FROM inspection_requests ORDER BY created_at DESC")
            return cur.fetchall()
    finally:
        conn.close()


# ==================== DEVIS ====================

def create_or_update_devis(event_data):
    """Create or update devis from notification."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            external_id = event_data.get('devis_id')
            
            # Check if exists
            cur.execute("SELECT * FROM devis_received WHERE external_devis_id = %s", (external_id,))
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE devis_received 
                    SET final_amount = %s,
                        proposed_intervention_date = %s,
                        status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                """, (
                    event_data.get('final_amount'),
                    event_data.get('proposed_intervention_date') or event_data.get('intervention_date'),
                    event_data.get('status', 'received'),
                    existing['id']
                ))
            else:
                cur.execute("""
                    INSERT INTO devis_received 
                        (external_devis_id, wagon_code, final_amount, proposed_intervention_date, status)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    external_id,
                    event_data.get('wagon_id'),
                    event_data.get('final_amount'),
                    event_data.get('proposed_intervention_date') or event_data.get('intervention_date'),
                    event_data.get('status', 'received')
                ))
            
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_devis_list(status=None):
    """Get devis list."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status:
                cur.execute(
                    "SELECT * FROM devis_received WHERE status = %s ORDER BY created_at DESC",
                    (status,)
                )
            else:
                cur.execute("SELECT * FROM devis_received ORDER BY created_at DESC")
            return cur.fetchall()
    finally:
        conn.close()


# ==================== ORDERS ====================

def create_order(devis_id, created_by):
    """Create order from validated devis."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get devis
            cur.execute("SELECT * FROM devis_received WHERE id = %s", (devis_id,))
            devis = cur.fetchone()
            
            if not devis:
                return None
            
            # Generate order number
            order_number = f"ORD-WAGL-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            
            cur.execute("""
                INSERT INTO orders 
                    (order_number, devis_id, wagon_code, total_amount, intervention_date, status, created_by)
                VALUES (%s, %s, %s, %s, %s, 'confirmed', %s)
                RETURNING *
            """, (
                order_number,
                devis_id,
                devis['wagon_code'],
                devis['final_amount'],
                devis['proposed_intervention_date'],
                created_by
            ))
            
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_orders(status=None):
    """Get orders."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status:
                cur.execute(
                    "SELECT * FROM orders WHERE status = %s ORDER BY created_at DESC",
                    (status,)
                )
            else:
                cur.execute("SELECT * FROM orders ORDER BY created_at DESC")
            return cur.fetchall()
    finally:
        conn.close()


# ==================== NOTIFICATIONS ====================

def log_notification(event_type, source, payload):
    """Log received notification."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO notifications_log (event_type, source, payload)
                VALUES (%s, %s, %s)
                RETURNING *
            """, (event_type, source, Json(payload)))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def mark_notification_processed(notification_id):
    """Mark notification as processed."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE notifications_log 
                SET processed = true, processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
            """, (notification_id,))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_notifications_log(processed=None, limit=100):
    """Get notifications log."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if processed is not None:
                cur.execute(
                    "SELECT * FROM notifications_log WHERE processed = %s ORDER BY created_at DESC LIMIT %s",
                    (processed, limit)
                )
            else:
                cur.execute("SELECT * FROM notifications_log ORDER BY created_at DESC LIMIT %s", (limit,))
            return cur.fetchall()
    finally:
        conn.close()
