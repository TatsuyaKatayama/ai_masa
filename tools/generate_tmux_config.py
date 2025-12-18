import yaml
import sys
import os
import shlex

def load_yaml_config(config_path):
    """Loads a YAML config file, falling back to a .default version if it exists."""
    if not os.path.exists(config_path):
        default_path = f"{config_path}.default"
        if os.path.exists(default_path):
            print(f"Info: Using default config '{default_path}'", file=sys.stderr)
            config_path = default_path
        else:
            print(f"Error: Config file not found at '{config_path}' or '{default_path}'", file=sys.stderr)
            sys.exit(1)
            
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def build_panes(team_name, ai_masa_project_root, venv_activate_path):
    agent_library_path = os.path.join(ai_masa_project_root, 'config', 'agent_library.yml')
    team_library_path = os.path.join(ai_masa_project_root, 'config', 'team_library.yml')

    agent_library = load_yaml_config(agent_library_path)
    team_library = load_yaml_config(team_library_path)

    try:
        selected_team_members = team_library[team_name]
    except KeyError:
        print(f"Error: Team '{team_name}' not found in the loaded team library", file=sys.stderr)
        sys.exit(1)
    
    user_input_logging_panes = []
    other_agent_panes = []
    has_gemini_cli_agent = False # Flag to track gemini cli agents

    # Build panes for each agent
    for member_key in selected_team_members:
        try:
            agent_config = agent_library[member_key]
        except KeyError:
            print(f"Error: Agent '{member_key}' not found in the loaded agent library", file=sys.stderr)
            sys.exit(1)

        agent_type_full = agent_config['type']
        
        # Check for gemini_cli_agent
        if 'gemini_cli_agent' in agent_type_full:
            has_gemini_cli_agent = True

        agent_module_path = '.'.join(agent_type_full.split('.')[:-1])
        agent_name_in_config = agent_config.get('name', member_key)
        user_lang = agent_config.get('user_lang', 'English')
        role_prompt = agent_config.get('role_prompt')
        llm_command = agent_config.get('llm_command')
        working_dir = agent_config.get('working_dir')

        command_parts = [
            f"python -m ai_masa.agents.{agent_module_path}",
            shlex.quote(agent_name_in_config),
        ]
        if 'user_input_agent' not in agent_module_path:
            command_parts.append(shlex.quote(user_lang))

        if 'user_input_agent' in agent_module_path:
            try:
                current_index = selected_team_members.index(member_key)
                if current_index + 1 < len(selected_team_members):
                    next_member_key = selected_team_members[current_index + 1]
                    next_agent_name = agent_library[next_member_key].get('name', next_member_key)
                    command_parts.append(f"--default_target_agent {shlex.quote(next_agent_name)}")
            except ValueError:
                pass

        if 'role_based' in agent_module_path.lower() and role_prompt:
            command_parts.append(f"--role_prompt {shlex.quote(role_prompt)}")
        
        if llm_command:
            command_parts.append(f'--llm_command {shlex.quote(llm_command)}')

        if working_dir:
            command_parts.append(f'--working_dir {shlex.quote(working_dir)}')
        
        command = " ".join(command_parts)
        
        pane_str = (
            f"        - {member_key.lower().replace(' ', '_')}:\n"
            f"            - source {venv_activate_path}\n"
            f"            - {command}"
        )

        if 'user_input_agent' in agent_module_path or 'logging_agent' in agent_module_path:
            user_input_logging_panes.append(pane_str)
        else:
            other_agent_panes.append(pane_str)

    # Build the shell pane separately
    shell_pane = f"            - source {venv_activate_path}\n            - # Generic shell pane"

    return "\n".join(user_input_logging_panes), shell_pane, "\n".join(other_agent_panes), has_gemini_cli_agent

def generate_config(team_name, ai_masa_project_root, tmuxinator_session_root, venv_activate_path, template_path, output_path, project_name):
    """Generates the final tmuxinator config file."""
    user_input_logging_panes_str, shell_pane_str, other_agent_panes_str, has_gemini_cli = build_panes(team_name, ai_masa_project_root, venv_activate_path)

    with open(template_path, 'r') as f:
        template_content = f.read()
    
    # Replace placeholders
    config_content = template_content.replace('__PROJECT_ROOT__', tmuxinator_session_root)
    config_content = config_content.replace('__PROJECT_NAME__', project_name)
    config_content = config_content.replace('__USER_INPUT_LOGGING_PANES__', user_input_logging_panes_str)
    config_content = config_content.replace('__SHELL_PANE__', shell_pane_str)
    config_content = config_content.replace('__OTHER_AGENT_PANES__', other_agent_panes_str)

    with open(output_path, 'w') as f:
        f.write(config_content)

    # Return the flag indicating presence of gemini cli agent
    return has_gemini_cli

if __name__ == '__main__':
    if len(sys.argv) != 8:
        print(f"Usage: python {sys.argv[0]} <team_name> <ai_masa_project_root> <tmuxinator_session_root> <venv_activate_path> <template_path> <output_path> <project_name>", file=sys.stderr)
        sys.exit(1)
    
    team_name, ai_masa_project_root, tmuxinator_session_root, venv_activate_path, template_path, output_path, project_name = sys.argv[1:8]
    
    has_gemini_cli = generate_config(team_name, ai_masa_project_root, tmuxinator_session_root, venv_activate_path, template_path, output_path, project_name)
    # Print the boolean flag as the last line of output
    print(has_gemini_cli)
