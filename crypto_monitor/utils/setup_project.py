"""
Initialize project structure and create necessary files.
"""
import os
from pathlib import Path

def setup_project():
    # Get the project root directory
    project_root = Path(__file__).resolve().parent
    
    # Create directories
    dirs = ['logs', 'data', 'data/backups', 'models']
    for d in dirs:
        dir_path = project_root / d
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {dir_path}")

    # Create .env template
    env_path = project_root / '.env'
    if not env_path.exists():
        env_content = """# Twitter API Credentials
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret

# Binance API Credentials
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

# Optional: Proxy Configuration (if needed)
# HTTP_PROXY=http://proxy.example.com:8080
# HTTPS_PROXY=http://proxy.example.com:8080
"""
        env_path.write_text(env_content)
        print(f"Created .env template: {env_path}")

    # Create empty __init__.py files
    init_locations = [
        project_root,
    ]
    
    for loc in init_locations:
        init_file = loc / '__init__.py'
        if not init_file.exists():
            init_file.touch()
            print(f"Created __init__.py: {init_file}")

    print("\nProject structure setup complete!")
    print("\nNext steps:")
    print("1. Fill in your API credentials in the .env file")
    print("2. Install required packages from requirements.txt")
    print("3. Run main.py to start the monitoring system")

if __name__ == "__main__":
    setup_project()
