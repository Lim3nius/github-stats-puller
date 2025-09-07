import threading
import time
import uvicorn
from dotenv import load_dotenv
from loguru import logger

from .client import GitHubEventsClient
from .server import app
from .main import setup_logging


def run_client_polling():
    """Run the GitHub events client polling in a separate thread"""
    logger.info("Starting GitHub events polling client thread")
    client = GitHubEventsClient()
    
    while True:
        try:
            events = client.poll_events()
            if events:
                logger.info(f"Client downloaded {len(events)} events")
            time.sleep(client.state.poll_interval_sec)
        except Exception as e:
            logger.error(f"Error in client polling: {e}")
            time.sleep(60)  # Wait 1 minute before retrying


def run_server():
    """Run the FastAPI server"""
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)


def main():
    """Main entry point that runs both client and server"""
    load_dotenv("gh.env")
    setup_logging()
    
    logger.info("Starting GitHub Events API with polling client")
    
    # Start client polling in a daemon thread
    client_thread = threading.Thread(target=run_client_polling, daemon=True)
    client_thread.start()
    
    # Run the server in the main thread
    run_server()


if __name__ == "__main__":
    main()