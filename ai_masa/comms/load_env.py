import os

def load_env_file(env_path='.env'):
    """
    Loads environment variables from a specified .env file.
    If the .env file is not found, it attempts to load from .env.example.
    It supports dynamic path resolution for values containing shell variables
    like ${PWD} and other standard environment variables (e.g., $HOME).
    """
    file_to_load = env_path
    if not os.path.exists(env_path):
        example_env_path = os.path.join(os.path.dirname(env_path), '.env.example')
        if os.path.exists(example_env_path):
            print(f"Warning: .env file not found at {env_path}. Loading from {example_env_path} instead.")
            file_to_load = example_env_path
        else:
            print(f"Warning: .env file not found at {env_path} and .env.example not found at {example_env_path}. No environment variables loaded.")
            return

    print(f"Loading environment variables from {file_to_load}...")
    
    # Get the current working directory for ${PWD} replacement
    pwd = os.getcwd()
    
    with open(file_to_load, 'r') as f:
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
