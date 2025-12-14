#!/bin/bash

# --- Helper Functions ---
# Checks for the presence of a command.
command_exists() {
    command -v "$1" &> /dev/null
}

# Exits with an error message.
fail() {
    echo "Error: $1" >&2
    exit 1
}

# --- Main Orchestration Logic ---
orchestrate_agents() {
    # 1. Project Root and Prerequisite Checks
    # Ensure the script is run from the project root by checking for a sentinel file.
    if [ ! -f "pyproject.toml" ]; then
        fail "This script must be run from the root of the ai_masa project."
    fi

    if ! command_exists tmuxinator;
     then
        fail "tmuxinator is not installed. Please run 'gem install tmuxinator'."
    fi

    local venv_path="../.venv/bin/activate"
    if [ ! -f "$venv_path" ]; then
        fail "Virtual environment not found at '$venv_path'. Please run setup scripts."
    fi

    # 2. Load Orchestration Config
    local orchestration_config_path="./config/orchestration.yml"
    local default_orchestration_config_path="${orchestration_config_path}.default"

    if [ -f "$orchestration_config_path" ]; then
        # Use user's config
        : # Pass
    elif [ -f "$default_orchestration_config_path" ]; then
        echo "Info: User 'orchestration.yml' not found. Using default."
        orchestration_config_path=$default_orchestration_config_path
    else
        fail "Orchestration config not found at '$orchestration_config_path' or '$default_orchestration_config_path'."
    fi

    # 3. Determine Selected Orchestration Setting
    local setting_name="${1:-default}" # Use first argument or 'default'
    echo "Using orchestration setting: '${setting_name}'"

    # Use a Python script to parse YAML, as it's safer than bash parsing.
    local config_values
    config_values=$(python -c "
import yaml, sys
try:
    with open('$orchestration_config_path', 'r') as f:
        data = yaml.safe_load(f)
    setting = data.get('$setting_name', {})
    values = [
        str(setting.get('project_name', '')),
        str(setting.get('team_name', '')),
        str(setting.get('template', '')),
        str(setting.get('session_root', 'works'))
    ]
    print(' '.join(values))
except (yaml.YAMLError, FileNotFoundError, KeyError):
    sys.exit(1)
")
    
    if [ -z "$config_values" ]; then
        fail "Could not find setting '${setting_name}' in '$orchestration_config_path'."
    fi

    # Read parsed values into variables
    local project_name team_name template session_root
    read -r project_name team_name template session_root <<< "$config_values"

    if [ -z "$project_name" ] || [ -z "$team_name" ] || [ -z "$template" ]; then
        fail "Setting '${setting_name}' is missing one or more required keys (project_name, team_name, template)."
    fi

    # 4. Set up Paths
    local ai_masa_project_root="."
    local tmuxinator_session_root="${session_root}"
    local project_working_dir="${tmuxinator_session_root}/${project_name}"
    local tmux_config_path="${project_working_dir}/${project_name}.yml"
    local template_path="./config/templates/${template}"

    if [ ! -f "$template_path" ]; then
        fail "Template file not found at '$template_path'."
    fi

    # 5. Generate Tmuxinator Config
    mkdir -p "${project_working_dir}/logs"
    
    echo "Generating tmuxinator config for team '${team_name}'..."
    
    if ! python "./tools/generate_tmux_config.py" \
            "${team_name}" \
            "${ai_masa_project_root}" \
            "${tmuxinator_session_root}" \
            "$(realpath "$venv_path")" \
            "${template_path}" \
            "${tmux_config_path}" \
            "${project_name}"; then
        fail "Failed to generate tmuxinator config."
    fi
    
    echo "✅ Generated tmuxinator config at '$tmux_config_path'"
    echo "✅ Project working directory is '$project_working_dir'"

    # 6. Start Tmuxinator Session
    echo "🚀 Starting tmuxinator session..."
    tmuxinator start -p "$tmux_config_path"
}

orchestrate_agents "$@"
