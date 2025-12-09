"""
Planning Service - Manages technician availability and inspection scheduling.
"""
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import sys
import json
import logging

# Add shared folder to path
sys.path.insert(0, '/app/shared')

from models import (
    get_all_technicians,
    get_technician_by_id,
    get_available_slots,
    get_earliest_available_dates,
    create_inspection,
    get_inspection_by_id,
    schedule_inspection,
    schedule_inspection_by_slot,
    complete_inspection,
    get_inspections_by_status,
    get_slot_by_id
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Kafka producer (lazy initialization)
kafka_producer = None

def get_kafka_producer():
    """Get or create Kafka producer."""
    global kafka_producer
    if kafka_producer is None:
        try:
            from kafka_utils import create_kafka_producer
            kafka_producer = create_kafka_producer()
        except Exception as e:
            logger.error(f"Failed to create Kafka producer: {e}")
    return kafka_producer


def publish_event(topic, key, data):
    """Publish event to Kafka."""
    try:
        producer = get_kafka_producer()
        if producer:
            from kafka_utils import publish_event as kafka_publish
            kafka_publish(producer, topic, key, data)
            logger.info(f"Event published to {topic}")
        else:
            logger.warning("Kafka producer not available, event not published")
    except Exception as e:
        logger.error(f"Failed to publish event: {e}")


def serialize_inspection(inspection):
    """Serialize inspection for JSON response."""
    if inspection is None:
        return None
    
    result = dict(inspection)
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, (bytes,)):
            result[key] = value.decode('utf-8')
    return result


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'planning-service'
    })


# ==================== TECHNICIANS ====================

@app.route('/technicians', methods=['GET'])
def list_technicians():
    """Get all technicians."""
    try:
        technicians = get_all_technicians()
        return jsonify([dict(t) for t in technicians])
    except Exception as e:
        logger.error(f"Error fetching technicians: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/technicians/<int:technician_id>', methods=['GET'])
def get_technician(technician_id):
    """Get technician by ID."""
    try:
        technician = get_technician_by_id(technician_id)
        if technician:
            return jsonify(dict(technician))
        return jsonify({'error': 'Technician not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching technician: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== AVAILABILITY ====================

@app.route('/inspection/availability', methods=['GET'])
def get_availability():
    """Get available slots for inspection."""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        specialty = request.args.get('specialty')
        
        if not start_date:
            start_date = datetime.now().date()
        else:
            start_date = datetime.fromisoformat(start_date).date()
        
        if not end_date:
            end_date = start_date + timedelta(days=14)
        else:
            end_date = datetime.fromisoformat(end_date).date()
        
        slots = get_available_slots(start_date, end_date, specialty)
        
        # Format for JSON response
        result = []
        for slot in slots:
            result.append({
                'slot_id': slot['id'],
                'date': str(slot['slot_date']),
                'start_time': str(slot['start_time']),
                'end_time': str(slot['end_time']),
                'technician_id': slot['technician_id'],
                'technician_name': slot['technician_name'],
                'specialty': slot['specialty']
            })
        
        return jsonify({
            'available_slots': result,
            'total': len(result),
            'message': 'Sélectionnez un slot_id pour planifier votre inspection'
        })
    except Exception as e:
        logger.error(f"Error fetching availability: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== INSPECTIONS ====================

@app.route('/inspection/request', methods=['POST'])
def request_inspection():
    """
    Request a new technical inspection.
    Returns available slots with IDs for scheduling.
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('wagon_id'):
            return jsonify({'error': 'wagon_id is required'}), 400
        if not data.get('client_company'):
            return jsonify({'error': 'client_company is required'}), 400
        
        # Create inspection
        inspection = create_inspection(data)
        
        # Get available slots for the next 14 days
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=14)
        slots = get_available_slots(start_date, end_date)
        
        # Format available slots with IDs
        available_slots = []
        for slot in slots[:20]:  # Limit to 20 slots
            available_slots.append({
                'slot_id': slot['id'],
                'date': str(slot['slot_date']),
                'start_time': str(slot['start_time']),
                'end_time': str(slot['end_time']),
                'technician_id': slot['technician_id'],
                'technician_name': slot['technician_name'],
                'specialty': slot['specialty']
            })
        
        response = {
            'inspection': serialize_inspection(inspection),
            'available_slots': available_slots,
            'total_slots': len(available_slots),
            'message': 'Inspection créée. Sélectionnez un slot_id ci-dessous pour planifier.',
            'next_step': f'POST /inspection/schedule/{{slot_id}} avec body: {{"inspection_id": {inspection["id"]}, "location": "votre_lieu"}}'
        }
        
        logger.info(f"Inspection requested: {inspection['id']} for wagon {inspection['wagon_id']}")
        return jsonify(response), 201
        
    except Exception as e:
        logger.error(f"Error creating inspection: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/inspection/<int:inspection_id>', methods=['GET'])
def get_inspection(inspection_id):
    """Get inspection by ID."""
    try:
        inspection = get_inspection_by_id(inspection_id)
        if inspection:
            return jsonify(serialize_inspection(inspection))
        return jsonify({'error': 'Inspection not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching inspection: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/inspection/schedule/<int:slot_id>', methods=['POST'])
def schedule_by_slot(slot_id):
    """
    Schedule an inspection using a slot ID.
    Much simpler - just provide the slot_id and location.
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('inspection_id'):
            return jsonify({'error': 'inspection_id is required'}), 400
        if not data.get('location'):
            return jsonify({'error': 'location is required'}), 400
        
        inspection_id = data['inspection_id']
        
        # Verify inspection exists
        existing = get_inspection_by_id(inspection_id)
        if not existing:
            return jsonify({'error': 'Inspection not found'}), 404
        
        if existing['status'] != 'pending':
            return jsonify({'error': 'Inspection is already scheduled or completed'}), 400
        
        # Verify slot exists and is available
        slot = get_slot_by_id(slot_id)
        if not slot:
            return jsonify({'error': 'Slot not found'}), 404
        
        if slot['is_booked']:
            return jsonify({'error': 'Ce créneau est déjà réservé. Veuillez en choisir un autre.'}), 400
        
        # Get technician info
        technician = get_technician_by_id(slot['technician_id'])
        
        # Schedule the inspection
        inspection = schedule_inspection_by_slot(
            inspection_id,
            slot_id,
            data['location']
        )
        
        # Build confirmation response
        confirmation = {
            'status': 'confirmed',
            'message': 'Inspection planifiée avec succès!',
            'inspection': serialize_inspection(inspection),
            'schedule_details': {
                'date': str(slot['slot_date']),
                'start_time': str(slot['start_time']),
                'end_time': str(slot['end_time']),
                'location': data['location'],
                'technician': {
                    'id': technician['id'],
                    'name': technician['name'],
                    'specialty': technician['specialty'],
                    'phone': technician.get('phone', 'N/A'),
                    'email': technician.get('email', 'N/A')
                }
            },
            'next_steps': [
                'Le technicien sera sur place à la date prévue',
                'Après l\'inspection, un devis sera généré',
                'Les deux ERP ont été notifiés de cette planification'
            ]
        }
        
        # Publish event to Kafka
        event_data = {
            'inspection_id': inspection['id'],
            'wagon_id': inspection['wagon_id'],
            'client_company': inspection['client_company'],
            'scheduled_date': str(slot['slot_date']),
            'start_time': str(slot['start_time']),
            'end_time': str(slot['end_time']),
            'location': inspection['location'],
            'technician_id': technician['id'],
            'technician_name': technician['name'],
            'technician_specialty': technician['specialty'],
            'status': 'scheduled',
            'scheduled_at': datetime.now().isoformat()
        }
        publish_event('inspection.scheduled', str(inspection['id']), event_data)
        
        logger.info(f"Inspection {inspection_id} scheduled via slot {slot_id}")
        return jsonify(confirmation), 200
        
    except Exception as e:
        logger.error(f"Error scheduling inspection: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/inspection/<int:inspection_id>/schedule', methods=['POST'])
def schedule_inspection_endpoint(inspection_id):
    """Schedule an inspection with a specific date and technician (legacy method)."""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('scheduled_date'):
            return jsonify({'error': 'scheduled_date is required'}), 400
        if not data.get('location'):
            return jsonify({'error': 'location is required'}), 400
        if not data.get('technician_id'):
            return jsonify({'error': 'technician_id is required'}), 400
        
        # Verify inspection exists
        existing = get_inspection_by_id(inspection_id)
        if not existing:
            return jsonify({'error': 'Inspection not found'}), 404
        
        # Verify technician exists
        technician = get_technician_by_id(data['technician_id'])
        if not technician:
            return jsonify({'error': 'Technician not found'}), 404
        
        # Schedule the inspection
        inspection = schedule_inspection(
            inspection_id,
            data['scheduled_date'],
            data['location'],
            data['technician_id']
        )
        
        # Publish event to Kafka
        event_data = {
            'inspection_id': inspection['id'],
            'wagon_id': inspection['wagon_id'],
            'client_company': inspection['client_company'],
            'scheduled_date': str(inspection['scheduled_date']),
            'location': inspection['location'],
            'technician_id': inspection['technician_id'],
            'technician_name': technician['name'],
            'status': 'scheduled'
        }
        publish_event('inspection.scheduled', str(inspection['id']), event_data)
        
        logger.info(f"Inspection {inspection_id} scheduled for {data['scheduled_date']}")
        return jsonify(serialize_inspection(inspection))
        
    except Exception as e:
        logger.error(f"Error scheduling inspection: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/inspection/<int:inspection_id>/complete', methods=['POST'])
def complete_inspection_endpoint(inspection_id):
    """Complete an inspection with findings and parts needed."""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('findings'):
            return jsonify({'error': 'findings is required'}), 400
        
        # Verify inspection exists
        existing = get_inspection_by_id(inspection_id)
        if not existing:
            return jsonify({'error': 'Inspection not found'}), 404
        
        if existing['status'] != 'scheduled':
            return jsonify({'error': 'Inspection must be scheduled before completion'}), 400
        
        # Complete the inspection
        inspection = complete_inspection(
            inspection_id,
            data['findings'],
            data.get('parts_needed', []),
            data.get('estimated_repair_hours', 0)
        )
        
        # Publish event to Kafka
        event_data = {
            'inspection_id': inspection['id'],
            'wagon_id': inspection['wagon_id'],
            'client_company': inspection['client_company'],
            'findings': inspection['findings'],
            'parts_needed': data.get('parts_needed', []),
            'estimated_repair_hours': inspection['estimated_repair_hours'],
            'status': 'completed',
            'completed_at': datetime.now().isoformat()
        }
        publish_event('inspection.completed', str(inspection['id']), event_data)
        
        logger.info(f"Inspection {inspection_id} completed")
        return jsonify(serialize_inspection(inspection))
        
    except Exception as e:
        logger.error(f"Error completing inspection: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/inspections', methods=['GET'])
def list_inspections():
    """List inspections with optional filters."""
    try:
        status = request.args.get('status')
        client = request.args.get('client_company')
        
        inspections = get_inspections_by_status(status, client)
        return jsonify([serialize_inspection(i) for i in inspections])
    except Exception as e:
        logger.error(f"Error listing inspections: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting Planning Service on port 5001")
    app.run(host='0.0.0.0', port=5001, debug=True)
