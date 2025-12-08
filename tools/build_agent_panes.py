import yaml
import sys
import os
import shlex

def build_agent_panes(team_name, project_root, venv_activate_path):
    agent_library_path = os.path.join(project_root, 'config', 'agent_library.yml')
    team_library_path = os.path.join(project_root, 'config', 'team_library.yml')

    with open(agent_library_path, 'r') as f:
        agent_library = yaml.safe_load(f)

    with open(team_library_path, 'r') as f:
        team_library = yaml.safe_load(f)

    selected_team_members = [] # Initialize to avoid UnboundLocalError
    try:
        selected_team_members = team_library[team_name]
    except KeyError:
        print(f"Error: Team '{team_name}' not found in {team_library_path}", file=sys.stderr)
        sys.exit(1)
    
    panes = []

    # Add a generic shell pane at the start for debugging/overall control
    panes.append("        - shell:\n            - source " + venv_activate_path)
    panes.append("            - # Generic shell pane")

    for member_key in selected_team_members:
        try:
            agent_config = agent_library[member_key]
        except KeyError:
            print(f"Error: Agent '{member_key}' not found in {agent_library_path}", file=sys.stderr)
            sys.exit(1)

        agent_type_full = agent_config['type'] # e.g., user_input_agent.UserInputAgent
        agent_module_path = '.'.join(agent_type_full.split('.')[:-1]) # e.g., user_input_agent
        agent_class_name = agent_type_full.split('.')[-1] # e.g., UserInputAgent
        agent_name_in_config = agent_config.get('name', member_key)
        user_lang = agent_config.get('user_lang', 'English')
        role_prompt = agent_config.get('role_prompt')

        # Base command for all agents
        command_parts = [
            f"python -m ai_masa.agents.{agent_module_path}",
            shlex.quote(agent_name_in_config),
        ]
        if agent_module_path != 'user_input_agent':
            command_parts.append(shlex.quote(user_lang))

        if agent_module_path == 'user_input_agent':
            # Find the next agent in the team to be the default target
            try:
                current_index = selected_team_members.index(member_key)
                if current_index + 1 < len(selected_team_members):
                    next_member_key = selected_team_members[current_index + 1]
                    next_agent_name = agent_library[next_member_key].get('name', next_member_key)
                    command_parts.append(f"--default_target_agent {shlex.quote(next_agent_name)}")
            except ValueError: # user_input_agent not found in list (shouldn't happen if it's being iterated)
                pass

        if 'role_based' in agent_module_path.lower() and role_prompt:
            command_parts.append(f"--role_prompt {shlex.quote(role_prompt)}")
        
        command = " ".join(command_parts)
        
        # Add log redirection for non-user_input agents
        log_dir = os.path.join(project_root, 'logs')
        log_path = os.path.join(log_dir, f"{agent_name_in_config}.log")
        if agent_module_path != 'user_input_agent': # Use module path for comparison
             command = f"mkdir -p {log_dir} && {command} > {shlex.quote(log_path)} 2>&1"


        panes.append(f"        - {member_key.lower().replace(' ', '_')}:\n            - source {venv_activate_path}") # Use member_key for pane name
        panes.append(f"            - {command}")

    return "\n".join(panes)

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python build_agent_panes.py <team_name> <project_root> <venv_activate_path>", file=sys.stderr)
        sys.exit(1)
    
    team_name = sys.argv[1]
    project_root = sys.argv[2]
    venv_activate_path = sys.argv[3]
    
    print(build_agent_panes(team_name, project_root, venv_activate_path))
