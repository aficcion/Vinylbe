import subprocess
import os
import signal
import sys
import time

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
    
    services = [
        ("Spotify Service", ["uvicorn", "services.spotify.main:app", "--host", "0.0.0.0", "--port", "3000"]),
        ("Discogs Service", ["uvicorn", "services.discogs.main:app", "--host", "0.0.0.0", "--port", "3001"]),
        ("Recommender Service", ["uvicorn", "services.recommender.main:app", "--host", "0.0.0.0", "--port", "3002"]),
        ("Pricing Service", ["uvicorn", "services.pricing.main:app", "--host", "0.0.0.0", "--port", "3003"]),
        ("API Gateway", ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "5000"]),
    ]
    
    for name, cmd in services:
        print(f"Starting {name}...")
        p = subprocess.Popen(cmd)
        processes.append(p)
        time.sleep(2)
    
    print("\nAll services started!")
    print("- Spotify Service: http://localhost:3000")
    print("- Discogs Service: http://localhost:3001")
    print("- Recommender Service: http://localhost:3002")
    print("- Pricing Service: http://localhost:3003")
    print("- API Gateway: http://localhost:5000")
    print("\nPress Ctrl+C to stop all services")
    
    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        cleanup(None, None)
