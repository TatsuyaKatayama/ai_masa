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
    local template_path="${project_root}/config/templates/orchestration.yml.template"
    local config_path="${project_working_dir}/${project_name}.yml"

    # 2. テンプレートファイルの存在チェック
    if [ ! -f "$template_path" ]; then
        echo "Error: Template file not found at $template_path"
        exit 1
    fi

    # 3. works ディレクトリと設定ファイルをテンプレートから生成
    mkdir -p "${project_working_dir}/logs"
    
    # sedでプレースホルダーを置換
    sed -e "s|__PROJECT_ROOT__|${project_root}|g" \
        -e "s|__PROJECT_NAME__|${project_name}|g" \
        "$template_path" > "$config_path"
    
    echo "✅ Generated tmuxinator config at $config_path"
    echo "✅ Ensured works directory exists at ${project_working_dir}"

    # 4. tmuxinatorセッションを開始 (-pオプションで設定ファイルを直接指定)
    echo "🚀 Starting tmuxinator session using config: $config_path"
    tmuxinator start -p "$config_path"
}

orchestrate_agents
