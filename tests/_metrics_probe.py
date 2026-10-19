"""Print the payment service /metrics right after startup, in a FRESH interpreter.

Run as a subprocess by tests/test_api.py: the prometheus_client registry is process-global, so inside the
pytest process other tests have already incremented the series and the check would pass for the wrong reason.
Leading underscore: not collected by pytest."""
import sys
from fastapi.testclient import TestClient
import services.payment.main as payment
with TestClient(payment.app) as client:
    sys.stdout.write(client.get('/metrics').text)
