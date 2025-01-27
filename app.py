from flask import Flask, render_template, request, send_from_directory
import os
from comfyapi import generate_image
from threading import Lock

app = Flask(__name__)
UPLOAD_FOLDER = 'output'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Lock to ensure only one thread can generate an image at a time
generate_lock = Lock()

# Ensure the generated images folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def retain_last_n_images(folder, n=20):
    """Ensure that only the last `n` images are kept in the folder."""
    files = [
        os.path.join(folder, f) 
        for f in os.listdir(folder) 
        if os.path.isfile(os.path.join(folder, f))
    ]
    # Sort files by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)

    # Remove files beyond the `n` most recent
    for file in files[n:]:
        try:
            os.remove(file)
        except Exception as e:
            print(f"Error deleting file {file}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if request.method == 'POST':
        prompt_text = request.form['prompt']
        
        # Attempt to acquire the lock
        if not generate_lock.acquire(blocking=False):
            return render_template('index.html', error="Another request is already being processed.<br>Please try again in a few seconds.") # Another request is already being processed. Please wait.
        
        try:
            # Generate the image
            output_path = generate_image(prompt_text, config_path="config.yaml")
            generated_image_path = output_path[0]  # Assuming output_path is a list and we need the first item
            image_name = os.path.basename(generated_image_path)

            # Retain only the last 20 images
            retain_last_n_images(app.config['UPLOAD_FOLDER'], n=20)

            return render_template('index.html', prompt=prompt_text, image_path=image_name)
        except Exception as e:
            return render_template('index.html', error=f"An error occurred: {str(e)}")
        finally:
            # Release the lock
            generate_lock.release()

@app.route('/uploads/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=1111, host="0.0.0.0")
