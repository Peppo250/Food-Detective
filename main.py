"""
Food Detective — main entry point.
Starts the FastAPI backend in a background thread, then launches the Tkinter UI.
"""
import threading
import time
import uvicorn
from app import create_app
from ui import FoodDetectiveApp
import tkinter as tk


def run_server():
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="error")


if __name__ == "__main__":
    # Start backend in daemon thread so it dies when UI closes
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Give the server a moment to bind
    time.sleep(1.2)

    root = tk.Tk()
    app_ui = FoodDetectiveApp(root)
    root.mainloop()
