import subprocess
import os
import signal
import sys
import time
from dotenv import load_dotenv

load_dotenv()

processes = []


def cleanup(signum, frame):
    print("\nShutting down all services...")
    for p in processes:
        p.terminate()
    for p in processes:
        p.wait()
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

if __name__ == "__main__":
    print("Starting all microservices...")
    
    python_cmd = sys.executable
    
    services = [
        ("Discogs Service", [python_cmd, "-m", "uvicorn", "services.discogs.main:app", "--host", "0.0.0.0", "--port", "3001"]),
        ("Recommender Service", [python_cmd, "-m", "uvicorn", "services.recommender.main:app", "--host", "0.0.0.0", "--port", "3002"]),
        ("Pricing Service", [python_cmd, "-m", "uvicorn", "services.pricing.main:app", "--host", "0.0.0.0", "--port", "3003"]),
        ("Last.fm Service", [python_cmd, "-m", "uvicorn", "services.lastfm.main:app", "--host", "0.0.0.0", "--port", "3004"]),
        ("API Gateway", [python_cmd, "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "5000"]),
    ]
    
    for name, cmd in services:
        print(f"Starting {name}...")
        p = subprocess.Popen(cmd)
        processes.append(p)
        time.sleep(2)
    
    print("\nAll services started!")
    print("- Discogs Service: http://localhost:3001")
    print("- Recommender Service: http://localhost:3002")
    print("- Pricing Service: http://localhost:3003")
    print("- Last.fm Service: http://localhost:3004")
    print("- API Gateway: http://localhost:5000")
    print("\nPress Ctrl+C to stop all services")
    
    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        cleanup(None, None)
