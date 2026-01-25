import os

def load_env_file(env_path='.env'):
    """
    Loads environment variables from a specified .env file.
    It supports dynamic path resolution for values containing shell variables
    like ${PWD} and other standard environment variables (e.g., $HOME).
    """
    if not os.path.exists(env_path):
        print(f"Warning: .env file not found at {env_path}")
        return

    print(f"Loading environment variables from {env_path}...")
    
    # Get the current working directory for ${PWD} replacement
    pwd = os.getcwd()
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('\'"')

                # Replace ${PWD} with the current working directory
                value = value.replace('${PWD}', pwd)
                
                # Expand other standard environment variables like $HOME, etc.
                value = os.path.expandvars(value)
                
                os.environ[key] = value
                print(f"Set environment variable: {key}={value}")
    print("Environment variables loaded.")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(current_dir, '..', '..') # Assumes ai_masa is project root
    env_file_path = os.path.join(project_root, '.env')
    load_env_file(env_file_path)
