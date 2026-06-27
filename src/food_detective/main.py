"""
Food Detective — main entry point.
Starts the FastAPI backend in a background thread, then launches the Tkinter UI.
"""
import threading
import time
import uvicorn
import os
from food_detective.app import create_app
from food_detective.ui import FoodDetectiveApp
import tkinter as tk


import requests

def run_server():
    app = create_app()
    host = os.getenv("FOOD_DETECTIVE_HOST", "127.0.0.1")
    port = int(os.getenv("FOOD_DETECTIVE_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="error")


def wait_for_server(url: str, timeout: float = 5.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            r = requests.get(url, timeout=0.2)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.1)
    return False


def run_app():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for the backend server to respond to health checks
    host = os.getenv("FOOD_DETECTIVE_HOST", "127.0.0.1")
    port = os.getenv("FOOD_DETECTIVE_PORT", "8765")
    wait_for_server(f"http://{host}:{port}/health")

    root = tk.Tk()
    FoodDetectiveApp(root)
    root.mainloop()


if __name__ == "__main__":
    run_app()
