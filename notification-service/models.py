"""
Database models for Notification Service.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime
import json

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://notification_user:notification_pass@localhost:5434/notification_db')


def get_db_connection():
    """Create a database connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def get_notification_template(event_type):
    """Get notification template for an event type."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM notification_templates WHERE event_type = %s AND active = true",
                (event_type,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def create_notification(event_type, event_id, source_service, target_erp, payload):
    """Create a new notification entry."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO notifications 
                    (event_type, event_id, source_service, target_erp, payload, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                RETURNING *
            """, (event_type, event_id, source_service, target_erp, Json(payload)))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def update_notification_status(notification_id, status, http_status_code=None, response_body=None, error_message=None):
    """Update notification status after sending attempt."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status == 'sent':
                cur.execute("""
                    UPDATE notifications 
                    SET status = %s, 
                        http_status_code = %s, 
                        response_body = %s,
                        sent_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                """, (status, http_status_code, response_body, notification_id))
            else:
                cur.execute("""
                    UPDATE notifications 
                    SET status = %s, 
                        http_status_code = %s, 
                        error_message = %s,
                        retry_count = retry_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                """, (status, http_status_code, error_message, notification_id))
            conn.commit()
            return cur.fetchone()
    finally:
        conn.close()


def get_notification_by_id(notification_id):
    """Get notification by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM notifications WHERE id = %s", (notification_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_notifications(status=None, target_erp=None, event_type=None, limit=100):
    """Get notifications with optional filters."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM notifications WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            if target_erp:
                query += " AND target_erp = %s"
                params.append(target_erp)
            
            if event_type:
                query += " AND event_type = %s"
                params.append(event_type)
            
            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_pending_notifications(limit=50):
    """Get pending notifications for retry."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM notifications 
                WHERE status IN ('pending', 'failed') 
                  AND retry_count < max_retries
                ORDER BY created_at ASC 
                LIMIT %s
            """, (limit,))
            return cur.fetchall()
    finally:
        conn.close()


def get_notification_stats():
    """Get notification statistics."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    status,
                    target_erp,
                    COUNT(*) as count
                FROM notifications
                GROUP BY status, target_erp
                ORDER BY status, target_erp
            """)
            stats = cur.fetchall()
            
            cur.execute("""
                SELECT COUNT(*) as total FROM notifications
            """)
            total = cur.fetchone()['total']
            
            cur.execute("""
                SELECT COUNT(*) as sent_today 
                FROM notifications 
                WHERE status = 'sent' 
                  AND sent_at >= CURRENT_DATE
            """)
            sent_today = cur.fetchone()['sent_today']
            
            return {
                'by_status_and_target': stats,
                'total': total,
                'sent_today': sent_today
            }
    finally:
        conn.close()
