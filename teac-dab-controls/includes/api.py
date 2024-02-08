from fastapi import FastAPI
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

    def run_app(self, host='0.0.0.0', port=8889):
        # Start FastAPI
        uvicorn.run(self.app, host=host, port=port)