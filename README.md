# 🤖 ai-masa - 分散マルチエージェント LLM システム

## 🌟 プロジェクト概要

`ai-masa` は、複数のLLMエージェントが協調してタスクを遂行する、分散型のマルチエージェントシステムです。通信基盤に **Redis Pub/Sub** を採用し、各エージェントは独立したプロセスとして動作します。エージェント間の対話履歴や個々のエージェントの状態は **Redis (RedisJSON)** 上の **MemoryManager** によって一元管理され、永続化されます。

ユーザーからの指示は `UserInputAgent` を通じて入力され、目的に応じて設定された多様な思考エージェント（`GeminiCliAgent`, `OpencodeAgent`, `RoleBasedAgent`など）が応答を担います。`LoggingAgent` が全ての通信を記録し、後から対話内容を確認・分析することが可能です。

## ⚙️ システムアーキテクチャ

`ai-masa`は、Pub/Subモデルに基づいた柔軟なマルチエージェントアーキテクチャを採用しています。中心的なメッセージブローカー（Redis）を介して、各エージェントが他のエージェントと非同期に通信します。

```mermaid
graph TD
    subgraph User Interaction
        UserInput[UserInputAgent]
    end

    subgraph Core Infrastructure
        Broker[(Redis Pub/Sub)]
        Memory[MemoryManager <br> (RedisJSON)]
    end

    subgraph Agent Layer
        Agent1[Thinking Agent A <br> e.g., GeminiCliAgent]
        Agent2[Thinking Agent B <br> e.g., RoleBasedOpencodeAgent]
        AgentN[... and so on]
    end
    
    subgraph System Agents
        Logger[LoggingAgent]
        Manager[AgentManager]
    end

    UserInput -- "Publish" --> Broker
    Broker -- "Subscribe" --> Agent1
    Broker -- "Subscribe" --> Agent2
    Broker -- "Subscribe" --> AgentN
    Broker -- "Subscribe" --> Logger
    Broker -- "Subscribe" --> Manager
    
    Agent1 -- "Publish" --> Broker
    Agent2 -- "Publish" --> Broker

    Agent1 -- "Read/Write" --> Memory
    Agent2 -- "Read/Write" --> Memory
    UserInput -- "Read/Write" --> Memory
```

- **UserInputAgent**: ユーザーからのテキスト入力を受け取り、指定されたターゲットエージェントにメッセージを送信します。
- **Thinking Agents**: それぞれが特定の役割や能力を持つエージェント群です。LLM（Gemini, OpenAIなど）と対話し、思考や応答生成を行います。
- **LoggingAgent**: システム内を流れる全てのメッセージを購読し、ファイルに記録します。
- **AgentManager**: 各エージェントの稼働状況を監視します。
- **Redis Pub/Sub**: エージェント間のメッセージングを担うブローカーです。
- **MemoryManager**: RedisJSONを利用して、各対話の履歴（メモリ）やエージェントの状態を永続化・管理します。

## 📦 セットアップ

### 1. 前提条件

- [Python 3.10+](https://www.python.org/)
- [Docker](https://www.docker.com/) と [Docker Compose](https://docs.docker.com/compose/)
- [Ruby](https://www.ruby-lang.org/en/)
- [tmux](https://github.com/tmux/tmux/wiki)
- [tmuxinator](https://github.com/tmuxinator/tmuxinator) (`gem install tmuxinator`)
- [opencode-cli](https://github.com/opencode-ai/opencode-cli) (OpencodeAgentを利用する場合)

### 2. 環境構築

1.  **リポジトリをクローン**
    ```bash
    git clone https://github.com/your-username/ai-masa.git
    cd ai-masa
    ```

2.  **Redisサーバーの起動**
    プロジェクトルートで以下のコマンドを実行し、RedisをDockerコンテナとして起動します。
    ```bash
    docker-compose up -d
    ```

3.  **Python依存関係のインストール**
    仮想環境を作成し、必要なライブラリをインストールします。
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```
    

### 3. ユーザー設定の作成

本プロジェクトでは、Gitで管理されるデフォルト設定 (`.default` ファイル) と、ユーザーが自由に編集できるローカル設定 (`.yml` ファイル) を分離しています。

初回起動前に、以下のコマンドを実行して、デフォルト設定をコピーして自分用の設定ファイルを作成してください。

```bash
cp config/agent_library.yml.default config/agent_library.yml
cp config/team_library.yml.default config/team_library.yml
cp config/orchestration.yml.default config/orchestration.yml
```

- `agent_library.yml`: 使用するエージェントの定義リストです。
- `team_library.yml`: エージェントを組み合わせてチームを定義します。
- `orchestration.yml`: どのチームを、どのtmuxinatorテンプレートで起動するかを定義します。

これらの `.yml` ファイルは `.gitignore` によりGitの追跡対象外となっているため、自由に変更・追加して自分だけのチームや起動構成を作成できます。

## 🚀 実行方法

1.  **エイリアスの設定**
    `orchestrate.sh` スクリプトを簡単に実行できるよう、エイリアスを設定することを推奨します。`~/.bashrc` や `~/.zshrc` などに以下の行を追加してください。
    ```bash
    alias masa='bash {PATH_TO_ai_masa}/orchestrate.sh'
    ```
    設定を適用するには、`source ~/.bashrc` または `source ~/.zshrc` を実行するか、新しいターミナルセッションを開始してください。

2.  **エージェントチームの起動**
    `orchestrate.sh` スクリプトは、`tmuxinator` を使って設定に基づいた `tmux` セッション内で全てのエージェントを自動的に開始します。プロジェクトのルートディレクトリで、エイリアスを定義した後、以下のコマンドでチームを起動できます。

    ```bash
    # config/orchestration.yml の 'default' 設定で起動
    masa

    # '3pane' という名前の設定で起動
    masa 3pane
    ```

    実行後、新しい `tmux` セッションがアタッチされます。各ペインでエージェントのログを確認でき、`UserInputAgent` のペインからメッセージを送信できます。

## 🧪 テスト

ユニットテストおよび統合テストを実行するには、以下のコマンドを使用します。

```bash
python -m unittest discover tests
```

## 📂 主要なファイルと役割

| ファイル/ディレクトリ | 役割 |
| :--- | :--- |
| `ai_masa/agents/` | 各エージェント（`UserInputAgent`, `GeminiCliAgent`, `OpencodeAgent`, `RoleBasedAgent`等）の実装。 |
| `ai_masa/comms/memory_manager.py` | RedisJSONを利用してエージェントの対話履歴（メモリ）と状態を管理する。 |
| `config/` | エージェント、チーム、オーケストレーションの設定ファイル群。 |
| `*.yml.default` | Gitで管理されるデフォルトの設定ファイル。 |
| `*.yml` | ユーザーがカスタマイズするためのローカル設定ファイル (Git追跡対象外)。 |
| `orchestrate.sh` | `tmuxinator` を使ってエージェント群を起動するメインスクリプト。 |
| `tools/generate_tmux_config.py`| `orchestrate.sh`から呼び出され、tmuxinator設定を動的に生成する。 |
| `tools/log_visualizer.py` | ログファイルをLINE風のHTMLとして可視化するツール。 |
| `docker-compose.yml` | Redisサーバーを起動するためのDocker Compose設定。 |
| `tests/` | プロジェクトのユニットテストおよび統合Test。 |

### 📄 ログ可視化ツール

`ai-masa` は、エージェント間の会話ログをLINEのような対話形式でHTMLファイルとして可視化するツールを提供します。これにより、エージェントの挙動や会話の流れを直感的に把握できます。

#### 1. ツールの場所

`ai_masa/tools/log_visualizer.py`

#### 2. 機能概要

指定された `.jsonl` 形式のログファイル（`LoggingAgent`が出力したもの）を読み込み、登場するエージェントを自動で特定します。各エージェントには、視覚的に区別しやすい背景色と、頭文字から生成されたSVGアイコンが割り当てられます。これらの情報に基づいて、HTML、CSS、SVGファイルを生成します。

#### 3. 使い方

以下のコマンドを実行して、会話ログをHTMLファイルとして可視化できます。

```bash
python -m ai_masa.tools.log_visualizer \
    --log_file /path/to/your/log/file.jsonl \
    --output_dir /path/to/output/directory \
    --title "Your Conversation Title"
```

**引数:**

*   `--log_file` (必須): 可視化したい `.jsonl` 形式のログファイルへのパスを指定します。`LoggingAgent` が出力したログファイル（例: `works/LoggingAgent/your_project_name/logs/<job_id>.jsonl`）を指定してください。
*   `--output_dir` (必須): 生成された `conversation.html` ファイル、`style.css`、および各エージェントの `*.svg` アイコンファイルが出力されるディレクトリを指定します。指定されたディレクトリが存在しない場合は自動的に作成されます。
*   `--title` (任意): 生成されるHTMLページのタイトルとして表示される文字列を指定します。デフォルトは `"Conversation Log"` です。

**実行例:**

```bash
# 例: 特定のjob_idのログを可視化する場合
python -m ai_masa.tools.log_visualizer \
    --log_file works/LoggingAgent/ai_masa_openfoam/logs/5b8d8501-72af-4c35-9f1f-03063ba677bb.jsonl \
    --output_dir html_logs/openfoam_conversation \
    --title "OpenFOAM Simulation with Foamer and FoamManager"

# 出力されたHTMLファイルを開く
# ブラウザで html_logs/openfoam_conversation/conversation.html を開いてください。
```

**出力ファイル:**

指定された `--output_dir` には以下のファイルが生成されます。

*   `conversation.html`: 会話ログを表示するメインのHTMLファイル。
*   `style.css`: 会話のスタイルを定義するCSSファイル。
*   `*_icon.svg`: 各エージェントの頭文字から生成されたSVGアイコンファイル。


