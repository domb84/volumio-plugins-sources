from fastapi import FastAPI
import threading
import uvicorn

class ApiWrapper:
    def __init__(self, shared_queue):
        self.app = FastAPI()
        self.shared_queue = shared_queue

        # Define a route to handle incoming POST requests in FastAPI
        @self.app.post('/post_listener')
        async def post_handler(data: dict):
            self.shared_queue.put(data)
            return {'message': 'Data received successfully!'}

    def _wait_for_stop(self, stop_event):
        stop_event.wait()
        if hasattr(self, '_server'):
            self._server.should_exit = True

    def run_app(self, host='0.0.0.0', port=8889, stop_event=None):
        config = uvicorn.Config(self.app, host=host, port=port, log_level='warning')
        self._server = uvicorn.Server(config)
        if stop_event is not None:
            threading.Thread(target=self._wait_for_stop, args=(stop_event,), daemon=True).start()
        self._server.run()
