import os
import time
from datetime import datetime

from cbpro import WebsocketClient
from config import Config


class StreamClient(WebsocketClient):
    def __init__(self, graph, trade_pairs) -> None:
        self.config = Config()
        self.graph = graph
        self._starter = True
        self._too_fast = 0

        self._pairs = trade_pairs
        # print(self._pairs)
        # time.sleep(5)

        super(StreamClient, self).__init__(
            self.config.COINBASE_AUTH_KEY,
            self.config.COINBASE_AUTH_SECRET,
            self.config.COINBASE_PASSWORD,
        )

    def on_open(self):
        self.products = self._pairs
        self.channels = ["ticker"]
        self.url = "wss://ws-feed.pro.coinbase.com"
        if self._starter:
            os.system("clear")
            print("------ Let's go! ------", end="\r")
            self._starter = False
            self._current_second = datetime.utcnow().replace(microsecond=0)
        else:
            print("-- Back in the game! --", end="\r")

    def on_message(self, msg):
        if "price" in msg:
            # print(msg)
            base, quote = msg["product_id"].split("-")
            # print(base, quote)
            self.graph[base][quote] = float(msg["price"])
            self.graph[quote][base] = 1.0 / float(msg["price"])
            time.sleep(1)

        # msg_time = datetime.strptime(msg["time"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        #     microsecond=0
        # )
        # if msg_time == self._current_second:
        #     self._prices.append(float(msg["price"]))
        # else:
        #     result = np.mean(self._prices) if self._prices else float(msg["price"])
        #     while self.price_buffer.qsize() >= 2:
        #         self.price_buffer.get()
        #     self.price_buffer.put(result)
        #     self._prices = list()
        #     self._current_second = msg_time

    def on_close(self):
        print("-- Take a breather! --", end="\r")
