from flask import Flask, render_template, request, send_from_directory, jsonify, redirect, url_for, session
import os
from comfyapi import generate_image
from threading import Lock
import json
import hashlib
from functools import wraps
import sys
import shutil
import getpass

def initialize_config():
    """Copy default config if it doesn't exist."""
    if not os.path.exists('config.yaml'):
        print("No config.yaml found. Creating from default...")
        if not os.path.exists('defaults/config-default.yaml'):
            print("Error: defaults/config-default.yaml not found!")
            sys.exit(1)
        shutil.copy('defaults/config-default.yaml', 'config.yaml')
        print("Created config.yaml\nPlease configure it before running the application again.")
        sys.exit(0)

def initialize_users():
    """Create users.json with admin account if it doesn't exist."""
    if not os.path.exists('users.json'):
        print("No users.json found. Creating new admin account...")
        while True:
            password = getpass.getpass("Enter admin password: ")
            confirm = getpass.getpass("Confirm admin password: ")
            if password == confirm:
                break
            print("Passwords don't match. Try again.")
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        users = {'admin': hashed_password}
        
        with open('users.json', 'w') as f:
            json.dump(users, f, indent=4)
        print("Created users.json with admin account")
        return True
    return False

# Add initialization before app creation
initialize_config()
initialize_users()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key for sessions
UPLOAD_FOLDER = 'output'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Load users from JSON file
def load_users():
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        password = request.form['password']
        
        # Hash the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        if username in users and users[username] == hashed_password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    # Only allow admin user to access this page
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        password = request.form['password']
        
        # Hash the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        if username in users:
            # Update existing user's password
            users[username] = hashed_password
            save_users(users)
            return render_template('admin.html', success=f"Updated password for {username}")
        else:
            # Create new user
            users[username] = hashed_password
            save_users(users)
            return render_template('admin.html', success=f"Created user {username}")
    
    return render_template('admin.html')

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    if request.method == 'POST':
        prompt_text = request.form['prompt']
        
        if not generate_lock.acquire(blocking=False):
            return jsonify({
                'error': 'Another request is being processed. Please try again in a few seconds.'
            }), 429
        
        try:
            output_path = generate_image(prompt_text, config_path="config.yaml")
            generated_image_path = output_path[0]
            image_name = os.path.basename(generated_image_path)
            retain_last_n_images(app.config['UPLOAD_FOLDER'], n=20)
            
            return jsonify({
                'success': True,
                'prompt': prompt_text,
                'image_path': image_name
            })
        except Exception as e:
            return jsonify({
                'error': f"An error occurred: {str(e)}"
            }), 500
        finally:
            generate_lock.release()

@app.route('/uploads/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

if __name__ == '__main__':
    app.run(debug=False, port=1111, host="0.0.0.0")
