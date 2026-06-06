from fastapi import FastAPI
import ctypes
import logging
import platform
import threading
from queue import Queue
from typing import Any, Dict, Optional
from uvicorn import Config, Server

logger = logging.getLogger("ApiWrapper")

def get_native_thread_id() -> Optional[int]:
    if hasattr(threading, 'get_native_id'):
        return threading.get_native_id()
    try:
        libc = ctypes.CDLL('libc.so.6', use_errno=True)
        if hasattr(libc, 'gettid'):
            tid = libc.gettid()
            tid = int(tid)
            return tid if tid > 0 else None
        arch = platform.machine()
        syscall_map = {
            'x86_64': 186,
            'i386': 224,
            'i686': 224,
            'armv7l': 224,
            'armv6l': 224,
            'aarch64': 178,
        }
        nr = syscall_map.get(arch)
        if nr is None:
            return None
        tid = libc.syscall(nr)
        tid = int(tid)
        return tid if tid > 0 else None
    except Exception:
        return None

class ApiWrapper:
    """Run a FastAPI instance in a background thread and push POSTed JSON to a shared queue."""

    def __init__(self, shared_queue: Queue) -> None:
        self.app = FastAPI()
        self.shared_queue = shared_queue

        # Define a route to handle incoming POST requests in FastAPI
        @self.app.post('/post_listener')
        async def post_handler(data: Dict[str, Any]) -> Dict[str, str]:
            logger.debug("Received POST data: %s", data)
            self.shared_queue.put(data)
            return {'message': 'Data received successfully!'}

    def run_app(self, host: str = '0.0.0.0', port: int = 8889, stop_event: Optional[threading.Event] = None) -> None:
        current = threading.current_thread()
        native_id = getattr(current, 'native_id', None) or get_native_thread_id()
        logger.info("API server starting in thread %s native_id=%s ident=%s", current.name, native_id, current.ident)
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