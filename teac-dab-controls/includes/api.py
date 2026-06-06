from fastapi import FastAPI
import logging
import threading
from queue import Queue
from typing import Any, Optional
from uvicorn import Config, Server

logger = logging.getLogger("ApiWrapper")

class ApiWrapper:
    """Run a FastAPI instance in a background thread and push POSTed JSON to a shared queue."""

    def __init__(self, shared_queue: Queue[Any]) -> None:
        self.app = FastAPI()
        self.shared_queue = shared_queue

        # Define a route to handle incoming POST requests in FastAPI
        @self.app.post('/post_listener')
        async def post_handler(data: dict[str, Any]) -> dict[str, str]:
            logger.debug("Received POST data: %s", data)
            self.shared_queue.put(data)
            return {'message': 'Data received successfully!'}

    def run_app(self, host: str = '0.0.0.0', port: int = 8889, stop_event: Optional[threading.Event] = None) -> None:
        # Use programmatic Server so we can stop it cleanly
        config = Config(app=self.app, host=host, port=port, log_level='info')
        server = Server(config=config)

        def _run():
            server.run()

        server_thread = threading.Thread(target=_run)
        server_thread.start()

        if stop_event is not None:
            stop_event.wait()
            server.should_exit = True
            server_thread.join()
        else:
            # Block until server stops if no stop_event provided
            server_thread.join()