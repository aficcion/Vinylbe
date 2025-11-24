#!/usr/bin/env python3
"""
Script to load a PostgreSQL backup from a SQL file.
Reads database credentials from .env file.
"""
import os
import sys
import subprocess

def get_env_var(name):
    """Read environment variable from .env file"""
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith(name + '='):
                    return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return os.environ.get(name)

def parse_database_url(db_url):
    """Parse PostgreSQL connection URL"""
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        sys.exit(1)
    
    # Remove prefix
    if db_url.startswith("postgresql://"):
        url = db_url[13:]
    elif db_url.startswith("postgres://"):
        url = db_url[11:]
    else:
        print("Error: Invalid DATABASE_URL format")
        sys.exit(1)
    
    # Split user:pass@host...
    if '@' in url:
        creds, location = url.split('@', 1)
        user_pass = creds.split(':')
        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ''
    else:
        print("Error: Could not parse credentials from DATABASE_URL")
        sys.exit(1)
    
    # Split host:port/dbname
    if '/' in location:
        host_port, dbname = location.split('/', 1)
    else:
        host_port = location
        dbname = 'vinylbe'
    
    if ':' in host_port:
        host, port = host_port.split(':')
    else:
        host = host_port
        port = '5432'
    
    return {
        'host': host,
        'port': port,
        'user': user,
        'password': password,
        'dbname': dbname
    }

def load_backup(backup_file):
    """Load SQL backup into PostgreSQL database"""
    if not os.path.exists(backup_file):
        print(f"Error: Backup file not found: {backup_file}")
        sys.exit(1)
    
    print(f"Loading backup from: {backup_file}")
    
    # Get database credentials
    db_url = get_env_var('DATABASE_URL')
    db_config = parse_database_url(db_url)
    
    print(f"Connecting to database '{db_config['dbname']}' at {db_config['host']}:{db_config['port']}")
    
    # Set PGPASSWORD environment variable for psql
    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['password']
    
    # Build psql command
    cmd = [
        'psql',
        '-h', db_config['host'],
        '-p', db_config['port'],
        '-U', db_config['user'],
        '-d', db_config['dbname'],
        '-f', backup_file
    ]
    
    print(f"\nExecuting: psql -h {db_config['host']} -p {db_config['port']} -U {db_config['user']} -d {db_config['dbname']} -f {backup_file}")
    print("This may take a few moments...\n")
    
    try:
        # Run psql command
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Backup loaded successfully!")
            if result.stdout:
                print("\nOutput:")
                print(result.stdout)
        else:
            print("❌ Error loading backup:")
            print(result.stderr)
            sys.exit(1)
            
    except FileNotFoundError:
        print("❌ Error: 'psql' command not found.")
        print("Please install PostgreSQL client tools:")
        print("  brew install postgresql")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_backup.py <backup_file.sql>")
        print("\nExample:")
        print("  python scripts/load_backup.py attached_assets/backup_vinilogy_20251122_214115.sql")
        sys.exit(1)
    
    backup_file = sys.argv[1]
    load_backup(backup_file)
