import http.server
import mimetypes
import os
import uuid
import json
import requests
import time
import threading
import numpy as np
from PIL import Image
from io import BytesIO
from http.server import ThreadingHTTPServer

# Directory to save processed images
STATIC_DIR = 'static'
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# Time in seconds after which files  be deleted (5 minutes)
DELETE_AFTER = 180

def crop_white_space(image_url: str, output_filename: str, white_tolerance: int = 10):
    # Download the image
    response = requests.get(image_url)
    img = Image.open(BytesIO(response.content)).convert("RGBA")

    # Convert image to numpy array
    img_array = np.array(img)
    r, g, b, a = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2], img_array[:, :, 3]
    white_mask = ((r >= 255 - white_tolerance) & (g >= 255 - white_tolerance) & (b >= 255 - white_tolerance))

    img_preserved = img_array.copy()

    img_preserved[white_mask] = [255, 255, 255, 255]  # Make white pixels white, not transparent

    img_no_white_bg = Image.fromarray(img_preserved, 'RGBA')

    # Find the bounding box of non-white areas
    bbox = img_no_white_bg.getbbox()
    if bbox:
        # Adding a small margin to ensure text is not cropped
        margin = 10
        left = max(0, bbox[0] - margin)
        top = max(0, bbox[1] - margin)
        right = min(img_no_white_bg.width, bbox[2] + margin)
        bottom = min(img_no_white_bg.height, bbox[3] + margin)
        img_cropped = img_no_white_bg.crop((left, top, right, bottom))
    else:
        img_cropped = img_no_white_bg

    # Save the processed image
    img_cropped.save(output_filename, format='PNG')


class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'error': 'Invalid JSON format'}
                self.wfile.write(json.dumps(response).encode())
                return

            image_url = data.get('url')
            if not image_url:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'error': 'URL is required'}
                self.wfile.write(json.dumps(response).encode())
                return

            # Generate a unique filename
            unique_filename = f'processed_image_{uuid.uuid4().hex}.png'
            output_filename = os.path.join(STATIC_DIR, unique_filename)

            # Process the image
            crop_white_space(image_url, output_filename)

            # Return the URL of the processed image
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'url': f'http://192.168.0.116:8000/static/{unique_filename}'}
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_error(404, 'Not Found')

    def do_GET(self):
        if self.path.startswith('/static/'):
            file_path = os.path.join(STATIC_DIR, self.path[len('/static/'):])
            if os.path.isfile(file_path):
                mime_type, _ = mimetypes.guess_type(file_path)
                mime_type = mime_type or 'application/octet-stream'
                with open(file_path, 'rb') as file:
                    self.send_response(200)
                    self.send_header('Content-type', mime_type)
                    self.end_headers()
                    self.wfile.write(file.read())
                return
            else:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = json.dumps({'error': 'File not found'})
                self.wfile.write(response.encode('utf-8'))
                return
        self.send_response(404)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = json.dumps({'error': 'Endpoint not found'})
        self.wfile.write(response.encode('utf-8'))


# Function to clean up old files
def cleanup_old_files():
    while True:
        now = time.time()
        for filename in os.listdir(STATIC_DIR):
            file_path = os.path.join(STATIC_DIR, filename)
            if os.path.isfile(file_path):
                file_age = now - os.path.getmtime(file_path)
                if file_age > DELETE_AFTER:
                    os.remove(file_path)
                    print(f"Deleted old file: {file_path}")
        time.sleep(60) 


# Start the HTTP server
def run(server_class=ThreadingHTTPServer, handler_class=RequestHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    
    # Start the cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    
    print(f'Starting httpd on port {port}...')
    httpd.serve_forever()


if __name__ == "__main__":
    run()
