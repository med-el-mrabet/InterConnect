"""
Notification Service - Kafka consumer that pushes notifications to ERPs.
"""
from flask import Flask, request, jsonify
from datetime import datetime
import threading
import requests
import os
import sys
import json
import logging
import time

# Add shared folder to path
sys.path.insert(0, '/app/shared')

from models import (
    get_notification_template,
    create_notification,
    update_notification_status,
    get_notification_by_id,
    get_notifications,
    get_pending_notifications,
    get_notification_stats
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ERP URLs
ERP_WAGONLITS_URL = os.getenv('ERP_WAGONLITS_URL', 'http://localhost:5010')
ERP_DEVMATERIELS_URL = os.getenv('ERP_DEVMATERIELS_URL', 'http://localhost:5011')
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')

# Kafka Topics to consume
KAFKA_TOPICS = [
    'inspection.requested',
    'inspection.scheduled',
    'inspection.completed',
    'devis.generated',
    'devis.validated',
    'devis.rejected'
]

# Kafka consumer thread
kafka_consumer_thread = None
consumer_running = False


def send_notification_to_erp(notification_id, target_erp, payload):
    """Send notification to target ERP via HTTP POST."""
    try:
        if target_erp == 'ERP_WAGL':
            url = f"{ERP_WAGONLITS_URL}/api/notifications"
        elif target_erp == 'ERP_DEMAT':
            url = f"{ERP_DEVMATERIELS_URL}/api/notifications"
        else:
            raise ValueError(f"Unknown target ERP: {target_erp}")
        
        logger.info(f"Sending notification to {url}")
        
        response = requests.post(
            url,
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code in [200, 201, 202]:
            update_notification_status(
                notification_id, 
                'sent', 
                response.status_code, 
                response.text[:500]
            )
            logger.info(f"Notification {notification_id} sent successfully to {target_erp}")
            return True
        else:
            update_notification_status(
                notification_id, 
                'failed', 
                response.status_code, 
                error_message=f"HTTP {response.status_code}: {response.text[:200]}"
            )
            logger.warning(f"Notification {notification_id} failed: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        update_notification_status(
            notification_id, 
            'failed', 
            error_message=f"Connection error: {str(e)[:200]}"
        )
        logger.error(f"Connection error sending notification {notification_id}: {e}")
        return False
    except Exception as e:
        update_notification_status(
            notification_id, 
            'failed', 
            error_message=str(e)[:200]
        )
        logger.error(f"Error sending notification {notification_id}: {e}")
        return False


def process_kafka_message(event_type, event_data):
    """Process a Kafka message and create notifications for both ERPs."""
    logger.info(f"Processing Kafka message: {event_type}")
    
    try:
        # Get notification template
        template = get_notification_template(event_type)
        
        # Create notification for WagonLits
        wagonlits_payload = {
            'event_type': event_type,
            'event_data': event_data,
            'template': template['template_wagonlits'] if template else {},
            'timestamp': datetime.now().isoformat()
        }
        
        wagonlits_notification = create_notification(
            event_type=event_type,
            event_id=str(event_data.get('inspection_id') or event_data.get('devis_id')),
            source_service='kafka',
            target_erp='ERP_WAGL',
            payload=wagonlits_payload
        )
        
        # Create notification for DevMateriels
        devmateriels_payload = {
            'event_type': event_type,
            'event_data': event_data,
            'template': template['template_devmateriels'] if template else {},
            'timestamp': datetime.now().isoformat()
        }
        
        devmateriels_notification = create_notification(
            event_type=event_type,
            event_id=str(event_data.get('inspection_id') or event_data.get('devis_id')),
            source_service='kafka',
            target_erp='ERP_DEMAT',
            payload=devmateriels_payload
        )
        
        # Send notifications
        send_notification_to_erp(
            wagonlits_notification['id'], 
            'ERP_WAGL', 
            wagonlits_payload
        )
        
        send_notification_to_erp(
            devmateriels_notification['id'], 
            'ERP_DEMAT', 
            devmateriels_payload
        )
        
        logger.info(f"Notifications created and sent for event: {event_type}")
        
    except Exception as e:
        logger.error(f"Error processing Kafka message: {e}")


def kafka_consumer_loop():
    """Kafka consumer loop running in a separate thread."""
    global consumer_running
    
    logger.info("Starting Kafka consumer loop...")
    
    # Wait for Kafka to be ready
    time.sleep(10)
    
    try:
        from kafka_utils import create_kafka_consumer
        
        consumer = create_kafka_consumer(
            topics=KAFKA_TOPICS,
            group_id='notification-service'
        )
        
        logger.info(f"Kafka consumer connected, listening to topics: {KAFKA_TOPICS}")
        consumer_running = True
        
        for message in consumer:
            if not consumer_running:
                break
                
            try:
                event_type = message.topic
                event_data = message.value
                
                logger.info(f"Received Kafka message: {event_type}")
                process_kafka_message(event_type, event_data)
                
            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}")
                
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")
        consumer_running = False


def start_kafka_consumer():
    """Start the Kafka consumer in a background thread."""
    global kafka_consumer_thread
    
    if kafka_consumer_thread is None or not kafka_consumer_thread.is_alive():
        kafka_consumer_thread = threading.Thread(target=kafka_consumer_loop, daemon=True)
        kafka_consumer_thread.start()
        logger.info("Kafka consumer thread started")


def serialize_notification(notification):
    """Serialize notification for JSON response."""
    if notification is None:
        return None
    
    result = dict(notification)
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    return result


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'notification-service',
        'kafka_consumer_running': consumer_running
    })


# ==================== NOTIFICATIONS ENDPOINTS ====================

@app.route('/notifications', methods=['GET'])
def list_notifications():
    """Get all notifications with optional filters."""
    try:
        status = request.args.get('status')
        target_erp = request.args.get('target_erp')
        event_type = request.args.get('event_type')
        limit = request.args.get('limit', 100, type=int)
        
        notifications = get_notifications(status, target_erp, event_type, limit)
        
        return jsonify({
            'notifications': [serialize_notification(n) for n in notifications],
            'total': len(notifications)
        })
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/<int:notification_id>', methods=['GET'])
def get_notification(notification_id):
    """Get notification by ID."""
    try:
        notification = get_notification_by_id(notification_id)
        if notification:
            return jsonify(serialize_notification(notification))
        return jsonify({'error': 'Notification not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching notification: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/<int:notification_id>/retry', methods=['POST'])
def retry_notification(notification_id):
    """Retry sending a failed notification."""
    try:
        notification = get_notification_by_id(notification_id)
        if not notification:
            return jsonify({'error': 'Notification not found'}), 404
        
        if notification['status'] == 'sent':
            return jsonify({'error': 'Notification already sent'}), 400
        
        success = send_notification_to_erp(
            notification_id,
            notification['target_erp'],
            notification['payload']
        )
        
        updated = get_notification_by_id(notification_id)
        return jsonify({
            'success': success,
            'notification': serialize_notification(updated)
        })
    except Exception as e:
        logger.error(f"Error retrying notification: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/stats', methods=['GET'])
def get_stats():
    """Get notification statistics."""
    try:
        stats = get_notification_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/retry-pending', methods=['POST'])
def retry_pending():
    """Retry all pending/failed notifications."""
    try:
        pending = get_pending_notifications(50)
        results = {'success': 0, 'failed': 0}
        
        for notification in pending:
            success = send_notification_to_erp(
                notification['id'],
                notification['target_erp'],
                notification['payload']
            )
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
        
        return jsonify({
            'processed': len(pending),
            'results': results
        })
    except Exception as e:
        logger.error(f"Error retrying pending: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/notifications/send-test', methods=['POST'])
def send_test_notification():
    """Send a test notification manually (for testing)."""
    try:
        data = request.get_json()
        
        event_type = data.get('event_type', 'test.notification')
        target_erp = data.get('target_erp', 'ERP_WAGL')
        
        notification = create_notification(
            event_type=event_type,
            event_id='test-001',
            source_service='manual',
            target_erp=target_erp,
            payload=data.get('payload', {'test': True})
        )
        
        success = send_notification_to_erp(
            notification['id'],
            target_erp,
            notification['payload']
        )
        
        updated = get_notification_by_id(notification['id'])
        return jsonify({
            'success': success,
            'notification': serialize_notification(updated)
        }), 201
        
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        return jsonify({'error': str(e)}), 500


# Start Kafka consumer when app starts
@app.before_request
def ensure_kafka_consumer():
    """Ensure Kafka consumer is running."""
    start_kafka_consumer()


if __name__ == '__main__':
    logger.info("Starting Notification Service on port 5003")
    # Start Kafka consumer
    start_kafka_consumer()
    app.run(host='0.0.0.0', port=5003, debug=True, threaded=True)
