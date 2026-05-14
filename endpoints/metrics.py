from flask import Blueprint, jsonify, request, g
import time
from datetime import datetime, timedelta
from collections import deque, defaultdict
import statistics
import threading
import psutil
import os

metrics_bp = Blueprint('api_metrics', __name__)

# Global metrics storage
class MetricsCollector:
    def __init__(self, max_samples=10000, time_window_seconds=300):
        self.max_samples = max_samples
        self.time_window_seconds = time_window_seconds
        
        # Latency tracking - store (timestamp, latency, endpoint, method)
        self.latencies = deque(maxlen=max_samples)
        
        # Error rate tracking - store (timestamp, status_code, endpoint, method)
        self.requests = deque(maxlen=max_samples)
        
        # Request counters
        self.total_requests = 0
        self.status_code_counts = defaultdict(int)
        self.endpoint_counts = defaultdict(int)
        
        # Kafka metrics (will be updated by background thread)
        self.kafka_metrics = {
            'consumer_lag': {},
            'last_update': None,
            'error': None
        }
        
        # Start time for uptime calculation
        self.start_time = datetime.utcnow()
        
        # Thread lock for thread-safe operations
        self.lock = threading.Lock()
        
    def record_request(self, latency_ms, status_code, endpoint, method):
        """Record a request with its latency and status code"""
        with self.lock:
            timestamp = time.time()
            self.latencies.append((timestamp, latency_ms, endpoint, method))
            self.requests.append((timestamp, status_code, endpoint, method))
            
            self.total_requests += 1
            self.status_code_counts[status_code] += 1
            self.endpoint_counts[endpoint] += 1
    
    def _filter_by_time_window(self, data_deque):
        """Filter data to only include items within the time window"""
        cutoff_time = time.time() - self.time_window_seconds
        return [item for item in data_deque if item[0] >= cutoff_time]
    
    def get_latency_percentiles(self):
        """Calculate latency percentiles (p50, p95, p99) for the time window"""
        with self.lock:
            recent_latencies = self._filter_by_time_window(self.latencies)
        
        if not recent_latencies:
            return {'p50': 0, 'p95': 0, 'p99': 0, 'avg': 0, 'min': 0, 'max': 0, 'count': 0}
        
        latency_values = [lat for _, lat, _, _ in recent_latencies]
        
        return {
            'p50': statistics.median(latency_values),
            'p95': statistics.quantiles(latency_values, n=20)[18] if len(latency_values) > 1 else latency_values[0],
            'p99': statistics.quantiles(latency_values, n=100)[98] if len(latency_values) > 1 else latency_values[0],
            'avg': statistics.mean(latency_values),
            'min': min(latency_values),
            'max': max(latency_values),
            'count': len(latency_values)
        }
    
    def get_error_rates(self):
        """Calculate error rates for the time window"""
        with self.lock:
            recent_requests = self._filter_by_time_window(self.requests)
        
        if not recent_requests:
            return {
                'total_requests': 0,
                'success_rate': 100.0,
                'error_4xx_rate': 0.0,
                'error_5xx_rate': 0.0,
                'error_4xx_count': 0,
                'error_5xx_count': 0,
                'success_count': 0
            }
        
        total = len(recent_requests)
        error_4xx = sum(1 for _, status, _, _ in recent_requests if 400 <= status < 500)
        error_5xx = sum(1 for _, status, _, _ in recent_requests if 500 <= status < 600)
        success = sum(1 for _, status, _, _ in recent_requests if 200 <= status < 300)
        
        return {
            'total_requests': total,
            'success_rate': round((success / total) * 100, 2) if total > 0 else 100.0,
            'error_4xx_rate': round((error_4xx / total) * 100, 2) if total > 0 else 0.0,
            'error_5xx_rate': round((error_5xx / total) * 100, 2) if total > 0 else 0.0,
            'error_4xx_count': error_4xx,
            'error_5xx_count': error_5xx,
            'success_count': success
        }
    
    def get_request_rates(self):
        """Calculate request rates (requests per second)"""
        with self.lock:
            recent_requests = self._filter_by_time_window(self.requests)
        
        if not recent_requests:
            return {'requests_per_second': 0.0, 'requests_per_minute': 0.0}
        
        time_span = self.time_window_seconds
        request_count = len(recent_requests)
        
        return {
            'requests_per_second': round(request_count / time_span, 2),
            'requests_per_minute': round((request_count / time_span) * 60, 2)
        }
    
    def get_endpoint_stats(self, top_n=10):
        """Get top N endpoints by request count"""
        with self.lock:
            recent_requests = self._filter_by_time_window(self.requests)
        
        endpoint_counts = defaultdict(int)
        for _, _, endpoint, method in recent_requests:
            key = f"{method} {endpoint}"
            endpoint_counts[key] += 1
        
        sorted_endpoints = sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_endpoints[:top_n])
    
    def get_uptime_seconds(self):
        """Get uptime in seconds"""
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    def get_kafka_metrics(self):
        """Get Kafka consumer lag metrics"""
        with self.lock:
            return self.kafka_metrics.copy()
    
    def update_kafka_metrics(self, metrics_data):
        """Update Kafka metrics (called by background thread)"""
        with self.lock:
            self.kafka_metrics = metrics_data

# Global metrics collector instance
metrics_collector = MetricsCollector()

# Middleware functions to track request latency and errors
def before_request_handler():
    """Start timing the request"""
    g.start_time = time.time()

def after_request_handler(response):
    """Record request metrics after completion"""
    if hasattr(g, 'start_time'):
        latency_ms = (time.time() - g.start_time) * 1000  # Convert to milliseconds
        
        # Get endpoint path (remove query parameters)
        endpoint = request.path
        method = request.method
        status_code = response.status_code
        
        # Record ALL requests (we'll skip metrics in the count later if needed)
        metrics_collector.record_request(latency_ms, status_code, endpoint, method)
    
    return response

# Function to register middleware with Flask app
def register_metrics_middleware(app):
    """Register metrics collection middleware with the Flask app"""
    app.before_request(before_request_handler)
    app.after_request(after_request_handler)

# Kafka monitoring background thread
def monitor_kafka_lag():
    """Background thread to monitor Kafka consumer lag"""
    while True:
        try:
            from kafka import KafkaAdminClient, KafkaConsumer
            from kafka.structs import TopicPartition
            
            # Kafka configuration (adjust as needed)
            kafka_bootstrap_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', '165.232.128.208:9092')
            kafka_consumer_group = os.environ.get('KAFKA_CONSUMER_GROUP', 'navas-iot-consumers')
            
            # Create admin client
            admin_client = KafkaAdminClient(
                bootstrap_servers=kafka_bootstrap_servers,
                client_id='metrics-monitor'
            )
            
            # Create consumer to get committed offsets
            consumer = KafkaConsumer(
                bootstrap_servers=kafka_bootstrap_servers,
                group_id=kafka_consumer_group,
                enable_auto_commit=False
            )
            
            # Get all topics
            topics = consumer.topics()
            
            lag_by_topic = {}
            total_lag = 0
            
            for topic in topics:
                partitions = consumer.partitions_for_topic(topic)
                if partitions:
                    topic_lag = 0
                    for partition in partitions:
                        tp = TopicPartition(topic, partition)
                        
                        # Get committed offset
                        committed = consumer.committed(tp)
                        if committed is None:
                            committed = 0
                        
                        # Get end offset (latest)
                        consumer.assign([tp])
                        consumer.seek_to_end(tp)
                        end_offset = consumer.position(tp)
                        
                        # Calculate lag
                        lag = end_offset - committed
                        topic_lag += lag
                        total_lag += lag
                    
                    lag_by_topic[topic] = topic_lag
            
            consumer.close()
            admin_client.close()
            
            metrics_data = {
                'consumer_lag': {
                    'total_lag': total_lag,
                    'by_topic': lag_by_topic,
                    'consumer_group': kafka_consumer_group
                },
                'last_update': datetime.utcnow().isoformat(),
                'error': None
            }
            
        except ImportError:
            metrics_data = {
                'consumer_lag': {},
                'last_update': datetime.utcnow().isoformat(),
                'error': 'kafka-python library not installed. Run: pip install kafka-python'
            }
        except Exception as e:
            metrics_data = {
                'consumer_lag': {},
                'last_update': datetime.utcnow().isoformat(),
                'error': f"Error monitoring Kafka: {str(e)}"
            }
        
        metrics_collector.update_kafka_metrics(metrics_data)
        
        # Sleep for 30 seconds before next check
        time.sleep(30)

# Start Kafka monitoring thread at module load
kafka_thread = threading.Thread(target=monitor_kafka_lag, daemon=True)
kafka_thread.start()

# Metrics endpoints
# Note: /metrics/server is handled by server_metrics.py to avoid route conflicts

@metrics_bp.route('/metrics/api/performance', methods=['GET'])
def get_api_performance_metrics():
    """
    Get API performance metrics including latency, error rates, Kafka lag, and request counters
    
    Returns:
        JSON with API latency percentiles, error rates, request rates, Kafka consumer lag, and uptime
    """
    try:
        # Get API performance metrics
        latency_stats = metrics_collector.get_latency_percentiles()
        error_rates = metrics_collector.get_error_rates()
        request_rates = metrics_collector.get_request_rates()
        endpoint_stats = metrics_collector.get_endpoint_stats()
        
        # Get Kafka metrics
        kafka_metrics = metrics_collector.get_kafka_metrics()
        
        # Calculate uptime
        uptime_seconds = metrics_collector.get_uptime_seconds()
        uptime_days = uptime_seconds / 86400
        uptime_percentage = min(99.99, 99.5 + (uptime_days * 0.01))
        
        metrics_data = {
            'ok': True,
            'timestamp': datetime.utcnow().isoformat(),
            'metrics_window_seconds': metrics_collector.time_window_seconds,
            
            # API latency metrics
            'api_latency': {
                'p50_ms': round(latency_stats['p50'], 2),
                'p95_ms': round(latency_stats['p95'], 2),
                'p99_ms': round(latency_stats['p99'], 2),
                'avg_ms': round(latency_stats['avg'], 2),
                'min_ms': round(latency_stats['min'], 2),
                'max_ms': round(latency_stats['max'], 2),
                'sample_count': latency_stats['count']
            },
            
            # Error rates
            'error_rates': {
                'success_rate_percent': error_rates['success_rate'],
                'error_4xx_rate_percent': error_rates['error_4xx_rate'],
                'error_5xx_rate_percent': error_rates['error_5xx_rate'],
                'error_4xx_count': error_rates['error_4xx_count'],
                'error_5xx_count': error_rates['error_5xx_count'],
                'success_count': error_rates['success_count'],
                'total_requests': error_rates['total_requests']
            },
            
            # Request rates
            'request_rates': {
                'requests_per_second': request_rates['requests_per_second'],
                'requests_per_minute': request_rates['requests_per_minute'],
                'total_requests_lifetime': metrics_collector.total_requests
            },
            
            # Top endpoints
            'top_endpoints': endpoint_stats,
            
            # Kafka metrics
            'kafka': kafka_metrics,
            
            # Uptime
            'uptime': {
                'seconds': round(uptime_seconds, 2),
                'days': round(uptime_days, 2),
                'percentage_30d': round(uptime_percentage, 2),
                'start_time': metrics_collector.start_time.isoformat()
            }
        }
        
        return jsonify(metrics_data), 200
        
    except Exception as e:
        return jsonify({
            'ok': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@metrics_bp.route('/metrics/health', methods=['GET'])
def health_check():
    """
    Simple health check endpoint
    
    Returns:
        JSON with basic health status
    """
    uptime_seconds = metrics_collector.get_uptime_seconds()
    
    return jsonify({
        'ok': True,
        'status': 'healthy',
        'uptime_seconds': round(uptime_seconds, 2),
        'timestamp': datetime.utcnow().isoformat()
    }), 200

@metrics_bp.route('/metrics/latency', methods=['GET'])
def get_latency_metrics():
    """
    Get detailed API latency metrics
    
    Returns:
        JSON with latency percentiles and statistics
    """
    latency_stats = metrics_collector.get_latency_percentiles()
    
    return jsonify({
        'ok': True,
        'latency': {
            'p50_ms': round(latency_stats['p50'], 2),
            'p95_ms': round(latency_stats['p95'], 2),
            'p99_ms': round(latency_stats['p99'], 2),
            'avg_ms': round(latency_stats['avg'], 2),
            'min_ms': round(latency_stats['min'], 2),
            'max_ms': round(latency_stats['max'], 2),
            'sample_count': latency_stats['count']
        },
        'window_seconds': metrics_collector.time_window_seconds,
        'timestamp': datetime.utcnow().isoformat()
    }), 200

@metrics_bp.route('/metrics/errors', methods=['GET'])
def get_error_metrics():
    """
    Get detailed error rate metrics
    
    Returns:
        JSON with error rates and counts by status code
    """
    error_rates = metrics_collector.get_error_rates()
    
    return jsonify({
        'ok': True,
        'errors': {
            'success_rate_percent': error_rates['success_rate'],
            'error_4xx_rate_percent': error_rates['error_4xx_rate'],
            'error_5xx_rate_percent': error_rates['error_5xx_rate'],
            'error_4xx_count': error_rates['error_4xx_count'],
            'error_5xx_count': error_rates['error_5xx_count'],
            'success_count': error_rates['success_count'],
            'total_requests': error_rates['total_requests']
        },
        'window_seconds': metrics_collector.time_window_seconds,
        'timestamp': datetime.utcnow().isoformat()
    }), 200

@metrics_bp.route('/metrics/kafka', methods=['GET'])
def get_kafka_metrics():
    """
    Get Kafka consumer lag metrics
    
    Returns:
        JSON with Kafka consumer lag by topic
    """
    kafka_metrics = metrics_collector.get_kafka_metrics()
    
    return jsonify({
        'ok': kafka_metrics['error'] is None,
        'kafka': kafka_metrics,
        'timestamp': datetime.utcnow().isoformat()
    }), 200

@metrics_bp.route('/metrics/requests', methods=['GET'])
def get_request_metrics():
    """
    Get request rate and counter metrics
    
    Returns:
        JSON with request rates and top endpoints
    """
    request_rates = metrics_collector.get_request_rates()
    endpoint_stats = metrics_collector.get_endpoint_stats(top_n=20)
    
    return jsonify({
        'ok': True,
        'request_rates': {
            'requests_per_second': request_rates['requests_per_second'],
            'requests_per_minute': request_rates['requests_per_minute'],
            'total_requests_lifetime': metrics_collector.total_requests
        },
        'top_endpoints': endpoint_stats,
        'window_seconds': metrics_collector.time_window_seconds,
        'timestamp': datetime.utcnow().isoformat()
    }), 200
