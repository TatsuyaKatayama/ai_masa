#!/bin/bash

orchestrate_agents() {
    echo "Orchestrating agents with tmuxinator..."

    # 1. tmuxinatorの存在チェック
    if ! command -v tmuxinator &> /dev/null; then
        echo "Error: tmuxinator is not installed."
        echo "Please install it first. (e.g., 'gem install tmuxinator')"
        exit 1
    fi

    local project_name="ai_masa_orchestration"
    local project_root="$(dirname "$(realpath "$0")")"
    local project_working_dir="${project_root}/works/${project_name}"
    local config_path="${project_working_dir}/${project_name}.yml"
    local template_path="${project_root}/config/templates/orchestration.yml.template"
    local venv_path="$(realpath "${project_root}/../.venv/bin/activate")"

    # 2. venvとテンプレートファイルの存在チェック
    if [ ! -f "$venv_path" ]; then
        echo "Error: Virtual environment activation script not found at $venv_path"
        exit 1
    fi
    if [ ! -f "$template_path" ]; then
        echo "Error: Template file not found at $template_path"
        exit 1
    fi

    # 3. works ディレクトリと設定ファイルをテンプレートから生成
    mkdir -p "${project_working_dir}/logs"
    
    # Generate tmuxinator config from template
    local selected_team="${AI_MASA_TEAM:-default_team}" # Get team name from AI_MASA_TEAM env var, default to default_team
    echo "Debug: Selected team is ${selected_team}"

    if ! python "${project_root}/tools/generate_tmux_config.py" \
            "${selected_team}" \
            "${project_root}" \
            "${venv_path}" \
            "${template_path}" \
            "${config_path}"; then
        echo "Error: Failed to generate tmuxinator config."
        exit 1
    fi
    
    echo "✅ Generated tmuxinator config at $config_path"
    echo "✅ Ensured works directory exists at ${project_working_dir}"

    # 4. tmuxinatorセッションを開始 (-pオプションで設定ファイルを直接指定)
    echo "🚀 Starting tmuxinator session using config: $config_path"
    tmuxinator start -p "$config_path"
}

orchestrate_agents
