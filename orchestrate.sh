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
    
    # sedでプレースホルダーを置換
    local selected_team="${AI_MASA_TEAM:-default_team}" # Get team name from AI_MASA_TEAM env var, default to default_team
    echo "Debug: Selected team is ${selected_team}"

    # Generate agent panes content into a temporary file
    local tmp_panes_file=$(mktemp)
    if ! python "${project_root}/tools/build_agent_panes.py" "${selected_team}" "${project_root}" "${venv_path}" > "$tmp_panes_file"; then
        echo "Error: Failed to generate agent panes."
        rm "$tmp_panes_file"
        exit 1
    fi

    # Use awk to perform replacements, including injecting content from the temp file for agent panes
    awk -v project_root="${project_root}" \
        -v venv_activate_path="${venv_path}" \
        -v project_name="${project_name}" \
        -v agent_panes_file="${tmp_panes_file}" \
        '{ \
            gsub(/__PROJECT_ROOT__/, project_root); \
            gsub(/__VENV_ACTIVATE_PATH__/, venv_activate_path); \
            gsub(/__PROJECT_NAME__/, project_name); \
            if ($0 ~ /__AGENT_PANES__/) { \
                while ((getline line < agent_panes_file) > 0) { \
                    print line \
                }; \
                close(agent_panes_file); \
            } else { \
                print \
            } \
        }' "$template_path" > "$config_path"
    
    # Clean up the temporary file
    rm "$tmp_panes_file"
    
    echo "✅ Generated tmuxinator config at $config_path"
    echo "✅ Ensured works directory exists at ${project_working_dir}"

    # 4. tmuxinatorセッションを開始 (-pオプションで設定ファイルを直接指定)
    echo "🚀 Starting tmuxinator session using config: $config_path"
    tmuxinator start -p "$config_path"
}

orchestrate_agents
