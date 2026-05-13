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
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.2)

    root = tk.Tk()
    FoodDetectiveApp(root)
    root.mainloop()
