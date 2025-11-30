# 🤖 ai-masa - Mechanism Analysis and Structuring Assistant

## 🌟 プロジェクト概要

本プロジェクトは、**Redis Pub/Sub** を通信基盤とし、**異なる物理マシン**で稼働する LLM エージェント（Gemini CLIを想定）が協調して複雑なタスクを遂行する分散型マルチエージェントシステムです。

ローカルの **Tmuxinator** をオーケストレーションに利用し、SSH 経由でリモートのエージェントを管理します。

## ⚙️ システムアーキテクチャ 

| 項目 | 詳細 |
| :--- | :--- |
| **通信プロトコル** | **JSON** 形式のメッセージ |
| **通信基盤** | **Redis Pub/Sub** (リアルタイム非同期通信) |
| **オーケストレーション** | **Tmuxinator** (ローカルからの SSH/プロセス管理) |
| **エージェント基盤** | **BaseAgent** (抽象化された  を利用) |
| **タスク管理** | SQLite () を使用した Job Pool |

## 📦 セットアップと依存関係

### 1. サーバー要件

* **Redis Server**: メッセージブローカーとして必須。ローカルまたはネットワーク上の単一インスタンスが必要です。

    ```bash
    # Dockerでの起動例
    docker run --name ai-masa-redis -p 6379:6379 -d redis
    ```

### 2. 環境構築

```bash
# 依存関係のインストール (poetryを使用する場合)
pip install poetry
poetry install

# または pip で個別インストール
pip install redis filelock
```

## 🚀 起動方法 (Tmuxinator Workflow)

エージェントをローカル/リモートで起動するための設定ファイルが必要です。

1.  **設定ファイルの準備**:
    ルートディレクトリに  を作成し、各エージェントの起動コマンドを定義します。

2.  **リモート起動**:
    リモートマシンでエージェントを起動する場合、 のペインコマンドを以下のように設定します。

    ```yaml
    # tmuxinator.yml の設定例
    windows:
      - collaboration:
          panes:
            # Chief Agentをリモートサーバーで起動
            - ssh user@remote-chief 'cd /path/to/repo && python3 -m ai-masa.base_agent Chief "Director"'
            # Calculator Agentをローカルで起動
            - python3 -m ai-masa.base_agent Calculator "Worker"
    ```

3.  **セッション開始**:

    ```bash
    tmuxinator start
    ```

## 🧪 テストの実行

通信統合テストを実行し、Redis Pub/Sub 経由でエージェント間のメッセージが正しく流れるか確認します。

```bash
# Redisが起動していることを確認してから実行
python3 -m unittest tests.test_integration_redis
```

## 📂 主要ファイルと役割

| ファイル/ディレクトリ | 役割 |
| :--- | :--- |
| `/comms/broker_base.py` | **MessageBroker** の抽象基底クラス (インターフェース) |
| `/comms/redis_broker.py` | Redis の Pub/Sub 機能を使用した具象実装 |
| `/base_agent.py` | エージェントの基底ロジック（, ） |
| `/models/message.py` | JSON 通信のデータモデル |
| `tests/test_integration_redis.py` | Redis を使用したエージェント間通信の統合テスト |
