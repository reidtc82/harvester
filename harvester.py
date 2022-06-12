import itertools
import os
import pprint
import sys
import time
from itertools import repeat
from multiprocessing import Manager, Process
from app.reaper import Reaper

import cbpro

from app.streaming import StreamClient
from app.utility.graph import Graph
from config import Config


def stream_manager(graph, trade_pairs):
    stream = StreamClient(graph, trade_pairs)

    try:
        stream.start()
        while True:
            time.sleep(300)
            stream.close()
            stream.start()
    except KeyboardInterrupt:
        stream.close()

    if stream.error:
        sys.exit(1)
    else:
        sys.exit(0)


def graph_printer(graph):
    while True:
        for base in graph.keys():
            for quote in graph[base].keys():
                if graph[base][quote] > 0:
                    print((base + "<-{0:.8f}-" + quote).format(graph[base][quote]))
        time.sleep(1)


def reaper_manager(graph, trade_pairs):
    reaper = Reaper(graph, trade_pairs)
    reaper.run()


if __name__ == "__main__":
    cfg = Config()
    public_client = cbpro.PublicClient()
    try:
        products = public_client.get_products()
    except Exception as e:
        print("error getting products", str(e))

    exclusions = ["ETH", "EUR", "GBP", "BTCAUCTION"]
    invalid_products = [
        "BTCAUCTION-USD",
        "UST-USD",
        "GNT-USDC",
        "WLUNA-USD",
        "XRP-USD",
        "UST-USDT",
        "WLUNA-USDT",
        "XRP-BTC",
    ]
    manager = Manager()
    graph = manager.dict()
    for product in products:
        if (
            product["base_currency"] not in exclusions
            and product["quote_currency"] not in exclusions
            and product["id"] not in invalid_products
        ):
            if product["base_currency"] in graph.keys():
                graph[product["base_currency"]][product["quote_currency"]] = 0.00
            else:
                graph[product["base_currency"]] = manager.dict()
                graph[product["base_currency"]][product["quote_currency"]] = 0.0

            if product["quote_currency"] in graph.keys():
                graph[product["quote_currency"]][product["base_currency"]] = 0.0
            else:
                graph[product["quote_currency"]] = manager.dict()
                graph[product["quote_currency"]][product["base_currency"]] = 0.0

    trade_pairs = list()
    for pair in products:
        if (
            pair["base_currency"] not in exclusions
            and pair["quote_currency"] not in exclusions
            and pair["id"] not in invalid_products
        ):
            trade_pairs.append(pair["id"])

    for key in graph.keys():
        if len(graph[key]) < 3:
            if key in trade_pairs:
                trade_pairs.remove(key)

    p1 = Process(target=stream_manager, args=(graph, trade_pairs))
    p2 = Process(target=reaper_manager, args=(graph, trade_pairs))

    p1.start()
    p2.start()

    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        p1.terminate()
