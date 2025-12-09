"""
Devis Service - Manages parts stock, quote generation, and price negotiations.
"""
from flask import Flask, request, jsonify
from datetime import datetime, date, timedelta
from decimal import Decimal
import os
import sys
import json
import logging

# Add shared folder to path
sys.path.insert(0, '/app/shared')

from models import (
    get_all_parts,
    get_part_by_reference,
    get_part_by_id,
    check_stock_availability,
    update_stock,
    create_devis,
    get_devis_by_id,
    update_devis_negotiation,
    validate_devis,
    reject_devis,
    get_devis_by_status
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


def serialize_devis(devis_data):
    """Serialize devis for JSON response."""
    if devis_data is None:
        return None
    
    def convert_value(value):
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return str(value)
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, bytes):
            return value.decode('utf-8')
        return value
    
    if isinstance(devis_data, dict):
        result = {}
        for key, value in devis_data.items():
            if isinstance(value, dict):
                result[key] = {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                result[key] = [{k: convert_value(v) for k, v in item.items()} if isinstance(item, dict) else convert_value(item) for item in value]
            else:
                result[key] = convert_value(value)
        return result
    return devis_data


# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'devis-service'
    })


# ==================== STOCK/PARTS ENDPOINTS ====================

@app.route('/stock/parts', methods=['GET'])
def list_parts():
    """Get all available parts."""
    try:
        category = request.args.get('category')
        parts = get_all_parts(category)
        
        result = []
        for part in parts:
            result.append({
                'id': part['id'],
                'reference': part['reference'],
                'name': part['name'],
                'description': part['description'],
                'category': part['category'],
                'catalog_price': float(part['catalog_price']),
                'stock_quantity': part['stock_quantity'],
                'available': part['stock_quantity'] > 0
            })
        
        return jsonify({
            'parts': result,
            'total': len(result)
        })
    except Exception as e:
        logger.error(f"Error fetching parts: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stock/parts/<reference>', methods=['GET'])
def get_part(reference):
    """Get part details by reference."""
    try:
        part = get_part_by_reference(reference)
        if part:
            return jsonify({
                'id': part['id'],
                'reference': part['reference'],
                'name': part['name'],
                'description': part['description'],
                'category': part['category'],
                'catalog_price': float(part['catalog_price']),
                'stock_quantity': part['stock_quantity'],
                'reorder_threshold': part['reorder_threshold'],
                'lead_time_days': part['lead_time_days'],
                'low_stock_warning': part['stock_quantity'] <= part['reorder_threshold']
            })
        return jsonify({'error': 'Part not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching part: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stock/check', methods=['POST'])
def check_stock():
    """
    Check stock availability for multiple parts.
    Returns detailed status and suggestions for each part.
    """
    try:
        data = request.get_json()
        parts_list = data.get('parts', [])
        
        if not parts_list:
            return jsonify({'error': 'parts list is required'}), 400
        
        availability = check_stock_availability(parts_list)
        
        # Build detailed response
        parts_status = []
        modifications_required = []
        
        for item in availability:
            part_info = {
                'reference': item['reference'],
                'name': item.get('name', 'Unknown'),
                'quantity_requested': item.get('quantity_needed', 0),
                'quantity_available': item.get('stock_quantity', 0),
                'unit_price': item.get('catalog_price', 0),
                'found_in_catalog': item.get('found', False),
                'in_stock': item.get('available', False)
            }
            
            if not item.get('found'):
                part_info['status'] = 'NOT_IN_CATALOG'
                part_info['message'] = f"La référence {item['reference']} n'existe pas dans notre catalogue"
                modifications_required.append({
                    'action': 'REMOVE',
                    'reference': item['reference'],
                    'reason': 'Référence non trouvée dans le catalogue'
                })
            elif not item.get('available'):
                part_info['status'] = 'INSUFFICIENT_STOCK'
                part_info['shortage'] = item.get('shortage', 0)
                part_info['message'] = f"Stock insuffisant: {item.get('stock_quantity', 0)} disponibles sur {item.get('quantity_needed', 0)} demandées"
                part_info['estimated_restock_date'] = item.get('estimated_restock_date')
                modifications_required.append({
                    'action': 'REDUCE_QUANTITY',
                    'reference': item['reference'],
                    'current_quantity': item.get('quantity_needed', 0),
                    'suggested_quantity': item.get('stock_quantity', 0),
                    'reason': f"Seulement {item.get('stock_quantity', 0)} pièces disponibles. Réduisez à {item.get('stock_quantity', 0)} ou attendez le {item.get('estimated_restock_date', 'N/A')}"
                })
            else:
                part_info['status'] = 'AVAILABLE'
                part_info['message'] = f"Disponible: {item.get('stock_quantity', 0)} en stock"
            
            parts_status.append(part_info)
        
        all_available = all(item.get('available', False) for item in availability if item.get('found'))
        total_value = sum(
            item.get('catalog_price', 0) * item.get('quantity_needed', 0) 
            for item in availability if item.get('found') and item.get('available')
        )
        
        response = {
            'parts_status': parts_status,
            'summary': {
                'total_parts_requested': len(parts_list),
                'parts_available': len([p for p in parts_status if p['status'] == 'AVAILABLE']),
                'parts_insufficient': len([p for p in parts_status if p['status'] == 'INSUFFICIENT_STOCK']),
                'parts_not_found': len([p for p in parts_status if p['status'] == 'NOT_IN_CATALOG'])
            },
            'can_proceed': all_available and len([p for p in parts_status if p['status'] == 'NOT_IN_CATALOG']) == 0,
            'total_available_value': total_value
        }
        
        if modifications_required:
            response['modifications_required'] = modifications_required
            response['message'] = "Des modifications sont nécessaires avant de pouvoir valider le devis. Voir 'modifications_required' pour les détails."
        else:
            response['message'] = "Toutes les pièces sont disponibles. Vous pouvez valider le devis."
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error checking stock: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stock/categories', methods=['GET'])
def get_categories():
    """Get all part categories."""
    try:
        parts = get_all_parts()
        categories = list(set(p['category'] for p in parts if p['category']))
        return jsonify({'categories': sorted(categories)})
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== DEVIS ENDPOINTS ====================

@app.route('/devis/generate', methods=['POST'])
def generate_devis():
    """
    Generate a quote (devis) based on inspection findings.
    Returns stock status and required modifications before validation.
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('wagon_id'):
            return jsonify({'error': 'wagon_id is required'}), 400
        if not data.get('client_company'):
            return jsonify({'error': 'client_company is required'}), 400
        
        parts_list = data.get('parts', [])
        
        # Check stock availability
        stock_check = check_stock_availability(parts_list)
        
        # Analyze stock issues and build suggestions
        parts_analysis = []
        modifications_required = []
        has_issues = False
        
        for item in stock_check:
            part_info = {
                'reference': item['reference'],
                'name': item.get('name', 'Unknown'),
                'quantity_requested': item.get('quantity_needed', 0),
                'quantity_in_stock': item.get('stock_quantity', 0),
                'unit_price': item.get('catalog_price', 0),
                'line_total': item.get('catalog_price', 0) * item.get('quantity_needed', 0) if item.get('found') and item.get('available') else 0
            }
            
            if not item.get('found'):
                part_info['status'] = 'NOT_IN_CATALOG'
                part_info['available'] = False
                has_issues = True
                modifications_required.append({
                    'action': 'RETIRER',
                    'reference': item['reference'],
                    'message': f"❌ Référence '{item['reference']}' introuvable. Retirez-la du devis."
                })
            elif not item.get('available'):
                part_info['status'] = 'STOCK_INSUFFISANT'
                part_info['available'] = False
                part_info['shortage'] = item.get('shortage', 0)
                part_info['restock_date'] = item.get('estimated_restock_date')
                has_issues = True
                modifications_required.append({
                    'action': 'MODIFIER_QUANTITE',
                    'reference': item['reference'],
                    'quantite_demandee': item.get('quantity_needed', 0),
                    'quantite_disponible': item.get('stock_quantity', 0),
                    'message': f"⚠️ '{item.get('name')}': Demandez {item.get('stock_quantity', 0)} au lieu de {item.get('quantity_needed', 0)}. Réappro prévu le {item.get('estimated_restock_date', 'N/A')}"
                })
            else:
                part_info['status'] = 'DISPONIBLE'
                part_info['available'] = True
            
            parts_analysis.append(part_info)
        
        # Create the devis (even with issues, so user can modify)
        devis = create_devis(data, stock_check)
        
        # Calculate totals
        total_parts = sum(p['line_total'] for p in parts_analysis if p['available'])
        intervention_hours = data.get('intervention_hours', 0)
        hourly_rate = 85.00
        labor_cost = intervention_hours * hourly_rate
        inspection_forfait = 1360.00
        subtotal = total_parts + labor_cost + inspection_forfait
        
        # Build response
        response = {
            'devis': serialize_devis({'devis': dict(devis)})['devis'],
            'parts_analysis': parts_analysis,
            'pricing': {
                'total_parts': total_parts,
                'labor_hours': intervention_hours,
                'hourly_rate': hourly_rate,
                'labor_cost': labor_cost,
                'inspection_forfait': inspection_forfait,
                'subtotal': subtotal,
                'final_amount': float(devis['final_amount'])
            },
            'stock_status': {
                'all_available': not has_issues,
                'parts_available': len([p for p in parts_analysis if p['status'] == 'DISPONIBLE']),
                'parts_with_issues': len([p for p in parts_analysis if p['status'] != 'DISPONIBLE'])
            }
        }
        
        if has_issues:
            response['can_validate'] = False
            response['modifications_required'] = modifications_required
            response['message'] = "⚠️ Le devis a été créé mais nécessite des modifications avant validation. Consultez 'modifications_required' pour les actions à effectuer."
            response['next_step'] = "Modifiez les quantités dans votre demande et régénérez le devis, ou attendez le réapprovisionnement."
        else:
            response['can_validate'] = True
            response['message'] = "✅ Toutes les pièces sont disponibles. Le devis peut être validé."
            response['next_step'] = f"POST /devis/{devis['id']}/validate avec {{'confirmed_by': 'votre_nom'}}"
        
        # Publish event to Kafka
        event_data = {
            'devis_id': devis['id'],
            'inspection_id': devis['inspection_id'],
            'wagon_id': devis['wagon_id'],
            'client_company': devis['client_company'],
            'final_amount': float(devis['final_amount']),
            'proposed_intervention_date': str(devis['proposed_intervention_date']),
            'has_stock_issues': has_issues,
            'status': 'draft',
            'created_at': datetime.now().isoformat()
        }
        publish_event('devis.generated', str(devis['id']), event_data)
        
        logger.info(f"Devis generated: {devis['id']} for wagon {devis['wagon_id']} (issues: {has_issues})")
        return jsonify(response), 201
        
    except Exception as e:
        logger.error(f"Error generating devis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devis/<int:devis_id>', methods=['GET'])
def get_devis(devis_id):
    """Get devis details by ID."""
    try:
        result = get_devis_by_id(devis_id)
        if result:
            return jsonify(serialize_devis(result))
        return jsonify({'error': 'Devis not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching devis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devis/<int:devis_id>/negotiate', methods=['PUT'])
def negotiate_devis_endpoint(devis_id):
    """Negotiate devis prices."""
    try:
        data = request.get_json()
        
        # Verify devis exists
        existing = get_devis_by_id(devis_id)
        if not existing:
            return jsonify({'error': 'Devis not found'}), 404
        
        if existing['devis']['status'] in ['validated', 'rejected']:
            return jsonify({'error': f"Cannot negotiate a {existing['devis']['status']} devis"}), 400
        
        # Update negotiation
        devis = update_devis_negotiation(
            devis_id,
            data.get('discount_percentage'),
            data.get('negotiated_parts'),
            data.get('new_intervention_date')
        )
        
        # Get updated devis with items
        result = get_devis_by_id(devis_id)
        
        logger.info(f"Devis {devis_id} negotiated")
        return jsonify(serialize_devis(result))
        
    except Exception as e:
        logger.error(f"Error negotiating devis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devis/<int:devis_id>/validate', methods=['POST'])
def validate_devis_endpoint(devis_id):
    """
    Validate and confirm devis as an order.
    Sends notification to both ERPs via Kafka.
    """
    try:
        data = request.get_json()
        
        if not data.get('confirmed_by'):
            return jsonify({'error': 'confirmed_by is required'}), 400
        
        # Verify devis exists
        existing = get_devis_by_id(devis_id)
        if not existing:
            return jsonify({'error': 'Devis not found'}), 404
        
        if existing['devis']['status'] == 'validated':
            return jsonify({'error': 'Devis already validated'}), 400
        
        if existing['devis']['status'] == 'rejected':
            return jsonify({'error': 'Cannot validate a rejected devis'}), 400
        
        # Validate the devis
        devis = validate_devis(devis_id, data['confirmed_by'], data.get('notes'))
        
        # Get items for the event
        items = existing.get('items', [])
        parts_list = [
            {
                'reference': item['part_reference'],
                'name': item['part_name'],
                'quantity': item['quantity'],
                'unit_price': float(item['negotiated_price']),
                'total': float(item['line_total'])
            }
            for item in items
        ]
        
        # Publish event to Kafka - will be consumed by Notification Service
        event_data = {
            'devis_id': devis['id'],
            'inspection_id': devis['inspection_id'],
            'wagon_id': devis['wagon_id'],
            'client_company': devis['client_company'],
            'final_amount': float(devis['final_amount']),
            'intervention_date': str(devis['proposed_intervention_date']),
            'confirmed_by': devis['confirmed_by'],
            'parts': parts_list,
            'status': 'validated',
            'validated_at': datetime.now().isoformat()
        }
        publish_event('devis.validated', str(devis['id']), event_data)
        
        # Get full result with items
        result = get_devis_by_id(devis_id)
        
        response = serialize_devis(result)
        response['confirmation'] = {
            'status': 'validated',
            'message': '✅ Devis validé avec succès! Les deux ERP ont été notifiés.',
            'notifications_sent_to': ['ERP WagonLits', 'ERP DevMateriels'],
            'next_steps': [
                f"Intervention prévue le {devis['proposed_intervention_date']}",
                f"Montant confirmé: {float(devis['final_amount'])}€",
                "Le stock a été réservé pour cette commande"
            ]
        }
        
        logger.info(f"Devis {devis_id} validated by {data['confirmed_by']}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error validating devis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devis/<int:devis_id>/reject', methods=['POST'])
def reject_devis_endpoint(devis_id):
    """Reject a devis."""
    try:
        data = request.get_json()
        
        # Verify devis exists
        existing = get_devis_by_id(devis_id)
        if not existing:
            return jsonify({'error': 'Devis not found'}), 404
        
        if existing['devis']['status'] in ['validated', 'rejected']:
            return jsonify({'error': f"Cannot reject a {existing['devis']['status']} devis"}), 400
        
        # Reject the devis
        devis = reject_devis(devis_id, data.get('reason'))
        
        # Publish event to Kafka
        event_data = {
            'devis_id': devis['id'],
            'wagon_id': devis['wagon_id'],
            'client_company': devis['client_company'],
            'reason': data.get('reason'),
            'status': 'rejected',
            'rejected_at': datetime.now().isoformat()
        }
        publish_event('devis.rejected', str(devis['id']), event_data)
        
        logger.info(f"Devis {devis_id} rejected")
        return jsonify(serialize_devis({'devis': dict(devis)}))
        
    except Exception as e:
        logger.error(f"Error rejecting devis: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devis', methods=['GET'])
def list_devis():
    """List all devis with optional filters."""
    try:
        status = request.args.get('status')
        client = request.args.get('client_company')
        
        devis_list = get_devis_by_status(status, client)
        
        result = []
        for d in devis_list:
            result.append({
                'id': d['id'],
                'wagon_id': d['wagon_id'],
                'client_company': d['client_company'],
                'final_amount': float(d['final_amount']),
                'status': d['status'],
                'proposed_intervention_date': str(d['proposed_intervention_date']) if d['proposed_intervention_date'] else None,
                'created_at': d['created_at'].isoformat() if d['created_at'] else None
            })
        
        return jsonify({
            'devis': result,
            'total': len(result)
        })
    except Exception as e:
        logger.error(f"Error listing devis: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting Devis Service on port 5002")
    app.run(host='0.0.0.0', port=5002, debug=True)
