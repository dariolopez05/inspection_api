from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "http_requests_total", "Peticiones HTTP totales", ["method", "path", "status"]
)
LATENCY = Histogram(
    "http_request_duration_seconds", "Latencia de las peticiones HTTP", ["method", "path"]
)
INFERENCE = Histogram("inference_duration_seconds", "Latencia de la inferencia del modelo")
PREDICTIONS = Counter("predictions_total", "Predicciones por resultado", ["outcome"])


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
