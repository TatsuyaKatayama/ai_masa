import unittest
import threading
import time
import json
import sys
import os

# パスを通す
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ai_masa.agents.base_agent import BaseAgent
from ai_masa.models.message import Message

class TestRedisCommunication(unittest.TestCase):
    """
    Redisを介したエージェント間通信の統合テスト
    ※ Redisサーバーが localhost:6379 で動いている必要があります
    """

    def setUp(self):
        # テスト用エージェントの作成
        self.agent_chief = BaseAgent("Chief", "Manager")
        self.agent_calc = BaseAgent("Calculator", "Worker")
        
        # 受信確認用バッファ
        self.chief_received = []
        self.calc_received = []

        # スレッドオブジェクトを保持
        self.t1 = None
        self.t2 = None

        # コールバックをテスト用に上書きして、受信内容をリストに保存
        def mock_handler_chief(msg_json):
            msg = Message.from_json(msg_json)
            if msg.to_agent == "Chief": 
                self.chief_received.append(msg)

        def mock_handler_calc(msg_json):
            msg = Message.from_json(msg_json)
            if msg.to_agent == "Calculator":
                self.calc_received.append(msg)
                # Calculatorは受信したらChiefへ返信するシミュレーション
                if "計算して" in msg.content:
                    self.agent_calc.broadcast(
                        target="Chief",
                        content="計算完了: 100mm2",
                        job_id="job-123"
                    )

        # プライベートメソッドをモックに差し替え (subscribe内部で呼ばれる)
        self.agent_chief._on_message_received = mock_handler_chief
        self.agent_calc._on_message_received = mock_handler_calc
    
    def tearDown(self):
        print("\n--- Tearing down test ---")
        # エージェントのシャットダウンをトリガー
        self.agent_chief.shutdown()
        self.agent_calc.shutdown()

        # スレッドが終了するのを待つ
        if self.t1 and self.t1.is_alive():
            self.t1.join()
        if self.t2 and self.t2.is_alive():
            self.t2.join()
        
        # スレッドが停止した後に接続を閉じる
        self.agent_chief.broker.disconnect()
        self.agent_calc.broker.disconnect()
        print("--- Teardown complete ---")

    def test_pubsub_communication(self):
        print("\n--- Testing Redis Pub/Sub ---")

        # 1. 各エージェントの監視ループを別スレッドで開始
        self.t1 = threading.Thread(target=self.agent_chief.observe_loop)
        self.t2 = threading.Thread(target=self.agent_calc.observe_loop)
        self.t1.start()
        self.t2.start()

        # Redisの接続とサブスクライブ待ち
        time.sleep(1)

        # 2. Chief -> Calculator へメッセージ送信
        print("[Test] Chief sends request...")
        self.agent_chief.broadcast(
            target="Calculator",
            content="断面積を計算して",
            job_id="job-123"
        )

        # 通信の伝播待ち
        time.sleep(1)

        # 3. 検証: Calculatorが受信したか？
        self.assertTrue(len(self.calc_received) > 0, "Calculator should receive the message")
        self.assertEqual(self.calc_received[0].content, "断面積を計算して")
        self.assertEqual(self.calc_received[0].from_agent, "Chief")

        # 4. 検証: Calculatorの返信をChiefが受信したか？
        time.sleep(1) # 返信待ち
        self.assertTrue(len(self.chief_received) > 0, "Chief should receive the reply")
        self.assertEqual(self.chief_received[0].content, "計算完了: 100mm2")
        self.assertEqual(self.chief_received[0].from_agent, "Calculator")
        
        print("--- Test Passed ✅ ---")

if __name__ == '__main__':
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
