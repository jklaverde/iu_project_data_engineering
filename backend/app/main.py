import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from .alert_store import AlertStore
from .auth import make_require_role, make_require_session
from .cassandra_client import CassandraReader
from .config import load_config
from .kafka_client import KafkaReader
from .logging_setup import configure_logging
from .routers import admin, anomalies, auth, sensors, steps, ws
from .state_poller import StatePoller
from .ws_manager import ConnectionManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = app.state.config
    logger.info(json.dumps({"event": "backend_starting", "kafka_bootstrap_servers": config.kafka_bootstrap_servers}))

    app.state.kafka_reader.start()
    app.state.cassandra_reader.start()
    await app.state.poller.start()

    yield

    await app.state.poller.stop()
    app.state.kafka_reader.stop()
    app.state.cassandra_reader.stop()


def create_app() -> FastAPI:
    config = load_config()
    configure_logging(config.log_level)

    app = FastAPI(lifespan=lifespan)
    app.state.config = config
    app.state.kafka_reader = KafkaReader(config.kafka_bootstrap_servers, config.kafka_topic_name)
    app.state.cassandra_reader = CassandraReader(
        config.cassandra_host, config.cassandra_port, config.cassandra_keyspace, config.known_device_ids
    )
    app.state.ws_manager = ConnectionManager()
    app.state.poller = StatePoller(config, app.state.kafka_reader, app.state.cassandra_reader, app.state.ws_manager)
    app.state.alert_store = AlertStore()

    require_session = make_require_session(config)
    require_admin = make_require_role(config, "admin")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(steps.router, dependencies=[Depends(require_session)])
    app.include_router(anomalies.router, dependencies=[Depends(require_session)])
    app.include_router(sensors.router, dependencies=[Depends(require_session)])
    app.include_router(admin.webhook_router)
    app.include_router(admin.alerts_router, dependencies=[Depends(require_admin)])
    app.include_router(ws.router)

    # Serves the React build (mounted last so it only catches paths no API
    # route above already matched).
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()
