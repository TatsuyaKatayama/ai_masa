import argparse
import json
import os
import hashlib
import html
from datetime import datetime
import base64
import markdown_it
import shutil

import colorsys

def generate_separated_colors(agents: list) -> dict:
    """
    エージェントのリストに対して、視覚的に区別しやすい色の辞書を生成します。
    'User' エージェントは特定の青色に固定されます。
    他のエージェントには、色相環上で均等に分散したパステルカラーが割り当てられます。
    """
    colors = {}
    
    # 'User' エージェントを特別扱い
    user_color = "#3498DB"  # 指定された青系
    if "User" in agents:
        colors["User"] = user_color

    # 'User' を除いた他のエージェントをアルファベット順にソートし、決定性を確保
    other_agents = sorted([agent for agent in agents if agent != "User"])
    
    num_agents = len(other_agents)
    if num_agents == 0:
        return colors

    # 見やすいパステルカラーにするための彩度と明度の設定
    saturation = 0.75  # 鮮やかすぎない 75%
    lightness = 0.80   # 明るめの 80%

    for i, agent_name in enumerate(other_agents):
        # 色相をエージェントの数に応じて均等に分散
        hue = i / num_agents
        # HSLからRGBへ変換 (colorsysではHLSの順)
        rgb_float = colorsys.hls_to_rgb(hue, lightness, saturation)
        # 0-255の整数に変換
        rgb_int = tuple(round(c * 255) for c in rgb_float)
        # HEX形式にフォーマット
        hex_color = f"#{rgb_int[0]:02x}{rgb_int[1]:02x}{rgb_int[2]:02x}"
        colors[agent_name] = hex_color
        
    return colors

def get_text_color(bg_color_hex: str) -> str:
    """背景色に基づいて、見やすいテキスト色（白または黒）を返す。"""
    r = int(bg_color_hex[1:3], 16)
    g = int(bg_color_hex[3:5], 16)
    b = int(bg_color_hex[5:7], 16)
    # ルミナンス計算 (ITU-R BT.709)
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return "#000000" if luminance > 0.5 else "#FFFFFF" # 明るい背景には黒、暗い背景には白

def generate_agent_icon_svg(agent_name: str, bg_color: str, text_color: str) -> str:
    """エージェント名（頭文字）と色から円形SVGアイコンの文字列を生成する。"""
    initial = agent_name[0].upper()
    svg_template = f"""<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
        <circle cx="20" cy="20" r="20" fill="{bg_color}"/>
        <text x="20" y="26" font-family="Arial, sans-serif" font-size="20" fill="{text_color}" text-anchor="middle" dominant-baseline="middle">{initial}</text>
    </svg>"""
    return svg_template

def generate_dynamic_css(agent_data: dict) -> str:
    """エージェントデータに基づいて動的なCSSを生成する。"""
    css_rules = []
    for agent_name, colors in agent_data.items():
        bg_color = colors["bg_color"]
        text_color = colors["text_color"]
        # replace space with hyphen for css class names
        agent_class_name = agent_name.replace(' ', '-')
        
        alignment = "flex-end" if agent_name == "User" else "flex-start"
        
        css_rules.append(f".message-row.from-{agent_class_name}-agent {{ justify-content: {alignment}; }}")
        css_rules.append(f".message-row.from-{agent_class_name}-agent .message-bubble {{ background-color: {bg_color}; color: {get_text_color(bg_color)}; }}")
        css_rules.append(f".message-row.from-{agent_class_name}-agent .agent-name {{ color: {text_color}; }}")

    base_css = """
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f0f0f0; }
    .container { max-width: 800px; margin: 20px auto; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    .message-row { display: flex; margin-bottom: 15px; align-items: flex-start; }
    .message-row.from-User-agent { justify-content: flex-end; } /* ユーザーのメッセージは右寄せ */
    .message-row:not(.from-User-agent) { justify-content: flex-start; } /* その他のメッセージは左寄せ */
    .agent-icon { width: 40px; height: 40px; border-radius: 50%; overflow: hidden; margin-right: 10px; flex-shrink: 0; }
    .message-row.from-User-agent .agent-icon { margin-right: 0; margin-left: 10px; }
    .message-content { display: flex; flex-direction: column; max-width: 70%; }
    .agent-name { font-weight: bold; font-size: 0.9em; margin-bottom: 3px; }
    .message-bubble { padding: 10px 15px; border-radius: 18px; line-height: 1.4; word-wrap: break-word; }
    .message-info { font-size: 0.75em; color: #888; margin-top: 3px; text-align: right; }
    .message-row:not(.from-User-agent) .message-info { text-align: left; }
    .timestamp { font-size: 0.7em; color: #aaa; margin-left: 10px; }
    """
    return base_css + "\n" + "\n".join(css_rules)

def load_logs(log_file_path: str) -> list:
    """JSONL形式のログファイルを読み込む。"""
    logs = []
    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON from log file: {e} in line: {line.strip()}")
    return logs

def main():
    parser = argparse.ArgumentParser(description="Generate an HTML conversation log from a JSONL file.")
    parser.add_argument("--log_file", required=True, help="Path to the JSONL log file.")
    parser.add_argument("--output_dir", required=True, help="Directory to output the conversation.html file.")
    parser.add_argument("--title", default="Conversation Log", help="Title for the HTML page.")
    parser.add_argument("--no-markdown", action="store_true", help="Disable Markdown rendering.")
    parser.add_argument("--no-math", action="store_true", help="Disable KaTeX math rendering.")
    
    args = parser.parse_args()

    # 出力ディレクトリの作成
    os.makedirs(args.output_dir, exist_ok=True)

    # ログファイルの出力ディレクトリへのコピー
    log_filename = os.path.basename(args.log_file)
    destination_log_path = os.path.join(args.output_dir, log_filename)
    shutil.copyfile(args.log_file, destination_log_path)
    print(f"Log file copied to: {destination_log_path}")

    # ログの読み込み
    logs = load_logs(args.log_file)

    # ユニークなエージェント名を抽出
    agents = set()
    for log in logs:
        agents.add(log.get("from_agent"))
        if log.get("to_agent") and log.get("to_agent") != "_broadcast_":
            agents.add(log.get("to_agent"))
        if log.get("cc_agents"):
            for cc_agent in log["cc_agents"]:
                if cc_agent != "_broadcast_":
                    agents.add(cc_agent)
    agents.discard(None) # Noneがあれば除外
    agents.discard("") # 空文字列があれば除外
    
    # エージェントごとの色を一括生成
    agent_colors = generate_separated_colors(list(agents))

    # エージェントごとのアイコンファイル名を生成
    agent_data = {}
    for agent in sorted(list(agents)):
        bg_color = agent_colors[agent]
        text_color = get_text_color(bg_color)
        
        # SVGアイコンをファイルに保存
        icon_svg_content = generate_agent_icon_svg(agent, bg_color, text_color)
        icon_filename = f"{agent.replace(' ', '_')}_icon.svg"
        icon_filepath = os.path.join(args.output_dir, icon_filename)
        with open(icon_filepath, 'w', encoding='utf-8') as f:
            f.write(icon_svg_content)
            
        agent_data[agent] = {
            "bg_color": bg_color,
            "text_color": text_color,
            "icon_filename": icon_filename
        }

    print(f"Detected agents and their styles (icons saved to files):")
    for agent, data in agent_data.items():
        print(f"  {agent}: BG={data['bg_color']}, Text={data['text_color']}, Icon='{data['icon_filename']}'")

    # 動的CSSの生成とファイルへの保存
    dynamic_css = generate_dynamic_css(agent_data)
    css_filepath = os.path.join(args.output_dir, "style.css")
    with open(css_filepath, 'w', encoding='utf-8') as f:
        f.write(dynamic_css)

    # メッセージHTMLの生成
    md = markdown_it.MarkdownIt()
    messages_html = []
    for log in logs:
        from_agent = log.get("from_agent", "Unknown")
        to_agent = log.get("to_agent")
        
        content = log.get("content", "")
        if not args.no_markdown:
            # ```latex ... ``` を $$...$$ に変換
            content = content.replace("```latex", "$$").replace("```", "$$")
            content_html = md.render(content)
        else:
            # HTMLエスケープを追加して、安全に表示
            import html
            content_html = f"<pre style='white-space: pre-wrap; word-wrap: break-word;'>{html.escape(content)}</pre>"
        
        timestamp_str = datetime.fromisoformat(log.get("timestamp")).strftime('%Y-%m-%d %H:%M:%S') if log.get("timestamp") else ""

        agent_class_name = from_agent.replace(' ', '-')
        icon_filename = agent_data.get(from_agent, {}).get("icon_filename", "")
        
        # エージェントフロー表示
        agent_display_name = from_agent
        if to_agent and to_agent != "_broadcast_":
            agent_display_name += f" (→ {to_agent})"

        message_html = f"""
        <div class='message-row from-{agent_class_name}-agent'>
            <div class='agent-icon'>
                <img src='{icon_filename}' alt='{from_agent[0].upper()}' />
            </div>
            <div class='message-content'>
                <div class='agent-name'>{agent_display_name}</div>
                <div class='message-bubble'>{content_html}</div>
                <div class='message-info'><span class='timestamp'>{timestamp_str}</span></div>
            </div>
        </div>
        """
        messages_html.append(message_html)

    # KaTeX関連のヘッダーを条件付きで生成
    katex_header = ""
    if not args.no_math:
        katex_header = """
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
        <script src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"></script>
        <script>
            document.addEventListener("DOMContentLoaded", function() {
                renderMathInElement(document.body, {
                    delimiters: [
                        {left: "$$", right: "$$", display: true},
                        {left: "$", right: "$", display: false},
                        {left: "\\\\(", right: "\\\\)", display: false},
                        {left: "\\\\[", right: "\\\\]", display: true}}
                    ]
                });
            });
        </script>
        """

    # 最終HTMLの組み立て
    messages_html_content = "\n".join(messages_html)
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{args.title}</title>
        <link rel="stylesheet" href="style.css">
        {katex_header}
    </head>
    <body>
        <div class="container">
            {messages_html_content}
        </div>
    </body>
    </html>
    """

    # HTMLファイルを保存
    output_filename = f"{args.title.replace(' ', '_')}.html"
    output_file_path = os.path.join(args.output_dir, output_filename)
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(full_html)


    print(f"HTML conversation log generated successfully at: {output_file_path}")

if __name__ == "__main__":
    main()
