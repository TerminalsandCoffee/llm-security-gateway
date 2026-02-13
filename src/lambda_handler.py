"""AWS Lambda entry point.

Mangum translates API Gateway HTTP API (v2) events into ASGI,
letting the existing FastAPI app run unchanged on Lambda.
"""

from mangum import Mangum

from src.main import app

handler = Mangum(app, lifespan="off")
