from flask import Flask, request

class FlaskAppWrapper:
    def __init__(self, shared_queue):
        self.app = Flask(__name__)
        self.shared_queue = shared_queue

        # Define a route to handle incoming POST requests
        @self.app.route('/post_listener', methods=['POST'])
        def post_handler():
            data = request.get_json()  # Assuming JSON data in the POST request
            self.shared_queue.put(data)
            return 'Data received successfully!', 200

    def run_app(self, host='0.0.0.0', port=8889):
        # Start the Flask app
        self.app.run(host=host, port=port, debug=True, use_reloader=False)
