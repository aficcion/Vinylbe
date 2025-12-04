#!/usr/bin/env python3
"""
Script de inicio para producción que maneja mejor los puertos y el ciclo de vida
de los servicios en entornos cloud.
"""
import subprocess
import os
import signal
import sys
import time
from dotenv import load_dotenv

load_dotenv()

processes = []


def cleanup(signum, frame):
    print("\n🛑 Shutting down all services...")
    for p in processes:
        try:
            p.terminate()
        except:
            pass
    
    # Esperar a que terminen gracefully
    time.sleep(2)
    
    # Forzar si no terminaron
    for p in processes:
        try:
            if p.poll() is None:
                p.kill()
        except:
            pass
    
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

if __name__ == "__main__":
    print("🚀 Starting Vinylbe microservices...")
    
    python_cmd = sys.executable
    
    # Obtener puerto del gateway desde variable de entorno (para Railway, Render, etc.)
    gateway_port = os.getenv("PORT", "5000")
    
    services = [
        ("Discogs Service", [python_cmd, "-m", "uvicorn", "services.discogs.main:app", "--host", "0.0.0.0", "--port", "3001"]),
        ("Recommender Service", [python_cmd, "-m", "uvicorn", "services.recommender.main:app", "--host", "0.0.0.0", "--port", "3002"]),
        ("Pricing Service", [python_cmd, "-m", "uvicorn", "services.pricing.main:app", "--host", "0.0.0.0", "--port", "3003"]),
        ("Last.fm Service", [python_cmd, "-m", "uvicorn", "services.lastfm.main:app", "--host", "0.0.0.0", "--port", "3004"]),
        ("Spotify Service", [python_cmd, "-m", "uvicorn", "services.spotify.main:app", "--host", "0.0.0.0", "--port", "3005"]),
        ("API Gateway", [python_cmd, "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", gateway_port]),
    ]
    
    for name, cmd in services:
        print(f"▶️  Starting {name}...")
        try:
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env=os.environ.copy()  # Pass environment variables to subprocess
            )
            processes.append(p)
            time.sleep(2)  # Dar tiempo a que arranque
            
            # Verificar que no haya fallado inmediatamente
            if p.poll() is not None:
                print(f"❌ {name} failed to start!")
                _, stderr = p.communicate()
                print(f"Error: {stderr}")
            else:
                print(f"✅ {name} started successfully")
        except Exception as e:
            print(f"❌ Failed to start {name}: {str(e)}")
    
    print("\n" + "="*60)
    print("🎉 All services started!")
    print("="*60)
    print(f"📍 Discogs Service:     http://localhost:3001")
    print(f"📍 Recommender Service: http://localhost:3002")
    print(f"📍 Pricing Service:     http://localhost:3003")
    print(f"📍 Last.fm Service:     http://localhost:3004")
    print(f"📍 Spotify Service:     http://localhost:3005")
    print(f"📍 API Gateway:         http://localhost:{gateway_port}")
    print("="*60)
    print("\n💡 Press Ctrl+C to stop all services\n")
    
    # Monitorear procesos
    try:
        while True:
            time.sleep(5)
            # Verificar si algún proceso murió
            for i, (name, _) in enumerate(services):
                if processes[i].poll() is not None:
                    print(f"⚠️  Warning: {name} stopped unexpectedly!")
                    _, stderr = processes[i].communicate()
                    if stderr:
                        print(f"Error output: {stderr}")
    except KeyboardInterrupt:
        cleanup(None, None)
