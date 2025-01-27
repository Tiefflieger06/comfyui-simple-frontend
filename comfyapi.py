import websocket  # websocket-client library
import uuid
import json
import yaml
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict
import random

# Load configuration from config.yaml
def load_config(config_path: str = "config.yaml") -> Dict:
    with open(config_path, "r") as config_file:
        return yaml.safe_load(config_file)

# Load the workflow from a JSON file specified in the config
def load_workflow(workflow_path: str) -> Dict:
    with open(workflow_path, "r") as workflow_file:
        return json.load(workflow_file)

# Queue the prompt on the server
def queue_prompt(prompt: Dict, server_address: str, client_id: str) -> Dict:
    payload = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://{server_address}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())

def randomize_noise_seed(workflow: Dict, seed_node_id: str):
    """
    Randomizes the noise seed in the workflow.

    Args:
        workflow (Dict): The workflow dictionary.
        seed_node_id (str): The node ID for the noise seed.
    """
    workflow[seed_node_id]["inputs"]["noise_seed"] = random.randint(0, 2**32 - 1)

# Function to generate the image and save it to the local directory
def generate_image(prompt_text: str, config_path: str = "config.yaml", output_dir: str = "output") -> str:
    """
    Generate an image based on the given prompt.

    Args:
        prompt_text (str): The text for the text prompt node.
        config_path (str): Path to the YAML configuration file.
        output_dir (str): Directory to save the generated image.

    Returns:
        str: Path to the saved image.
    """
    # Load configuration and workflow
    config = load_config(config_path)
    server_address = config.get("server_address", "127.0.0.1:8188")
    workflow_path = config.get("workflow_path", "workflow.json")
    prompt_node_id = config.get("text_prompt_node_id", "6")
    image_prefix = config.get("image_prefix", "generated_image")
    seed_node_id = config.get("noise_seed_node_id", "13")
    output_node_id = config.get("output_node_id", "28")


    workflow = load_workflow(workflow_path)

    # Modify the workflow with the prompt text and noise seed
    workflow[prompt_node_id]["inputs"]["text"] = prompt_text
    randomize_noise_seed(workflow, seed_node_id)

    # Set up WebSocket connection
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(f"ws://{server_address}/ws?clientId={client_id}")
    
    # Queue the prompt
    prompt_id = queue_prompt(workflow, server_address, client_id)["prompt_id"]
    output_image_data = None
    current_node = ""

    output_images = []  # Collect all image data
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message["type"] == "executing":
                data = message["data"]
                if data["prompt_id"] == prompt_id:
                    if data["node"] is None:
                        break  # Execution is done
                    else:
                        current_node = data["node"]
        else:
            # Handle binary data for the SaveImageWebsocket node
            if current_node == output_node_id:
                output_images.append(out[8:])  # Collect the binary image data

    # Ensure at least one image was received
    if not output_images:
        print(output_images)
        raise RuntimeError("No image data received from the server.")

    images = []
    for output_image_data in output_images:
        # Save the image locally
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        images.append(Path(output_dir) / f"{image_prefix}_{prompt_id}.png")
        with open(images[-1], "wb") as image_file:
            image_file.write(output_image_data)
    
    ws.close()

    return [str(image.resolve()) for image in images]
