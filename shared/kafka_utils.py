"""
Kafka utilities for microservices communication.
"""
import json
import os
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import NoBrokersAvailable
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')

# Kafka Topics
TOPICS = {
    'INSPECTION_REQUESTED': 'inspection.requested',
    'INSPECTION_SCHEDULED': 'inspection.scheduled',
    'INSPECTION_COMPLETED': 'inspection.completed',
    'DEVIS_GENERATED': 'devis.generated',
    'DEVIS_VALIDATED': 'devis.validated',
    'DEVIS_REJECTED': 'devis.rejected',
}


def create_kafka_producer(retries=5, retry_delay=5):
    """
    Create a Kafka producer with retry logic.
    """
    for attempt in range(retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3
            )
            logger.info(f"Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
            return producer
        except NoBrokersAvailable:
            logger.warning(f"Kafka not available, attempt {attempt + 1}/{retries}")
            if attempt < retries - 1:
                time.sleep(retry_delay)
    raise Exception("Failed to connect to Kafka after multiple attempts")


def create_kafka_consumer(topics, group_id, retries=5, retry_delay=5):
    """
    Create a Kafka consumer with retry logic.
    """
    for attempt in range(retries):
        try:
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(','),
                group_id=group_id,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='earliest',
                enable_auto_commit=True
            )
            logger.info(f"Kafka consumer connected to {KAFKA_BOOTSTRAP_SERVERS}")
            return consumer
        except NoBrokersAvailable:
            logger.warning(f"Kafka not available, attempt {attempt + 1}/{retries}")
            if attempt < retries - 1:
                time.sleep(retry_delay)
    raise Exception("Failed to connect to Kafka after multiple attempts")


def publish_event(producer, topic, key, data):
    """
    Publish an event to a Kafka topic.
    """
    try:
        future = producer.send(topic, key=key, value=data)
        result = future.get(timeout=10)
        logger.info(f"Event published to {topic}: {key}")
        return result
    except Exception as e:
        logger.error(f"Failed to publish event to {topic}: {e}")
        raise
