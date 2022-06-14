from pprint import pprint
from app.analytics_client import SimulationClient
from app.errors.not_really_error import FoundPath
from config import Config
import time
import os
import bisect


class PathNode:
    def __init__(self, next, price, volume, base, quote) -> None:
        self.next = next
        self.price = price
        self.volume = volume
        self.base = base
        self.quote = quote


class KeyWrapper:
    def __init__(self, iterable, key):
        self.it = iterable
        self.key = key

    def __getitem__(self, i):
        return self.key(self.it[i])

    def __len__(self):
        return len(self.it)


class Reaper:
    priority = dict()
    pos_dict = dict()
    ordered_keys = list()
    _valid_path = None
    highest_total = 0.0

    def __init__(self, graph, trade_pairs) -> None:
        self._graph = graph
        self.current_node = PathNode(None, None, None, None, quote="USD")
        self.trade_pairs = trade_pairs
        self.config = Config()
        self.analytics = SimulationClient()
        self._build_priority(graph)

    def _build_priority(self, graph) -> None:
        for key in graph.keys():
            if key in self.priority:
                self.priority[key]["valid_count"] = 0.0
                self.priority[key]["appear_count"] = 0.0
                self.priority[key]["weight"] = 0.0
            else:
                self.priority[key] = dict()
                self.priority[key]["valid_count"] = 0.0
                self.priority[key]["appear_count"] = 0.0
                self.priority[key]["weight"] = 0.0

    def _update_priority(self) -> None:
        self.ordered_keys = list()
        for key in self.priority.keys():
            self.priority[key]["weight"] = (
                self.priority[key]["valid_count"] / self.priority[key]["appear_count"]
                if self.priority[key]["appear_count"] > 0.0
                else 0.0
            )
            tup = (key, self.priority[key]["weight"])
            if tup not in self.ordered_keys:
                self.ordered_keys.append(tup)

        self.ordered_keys.sort(key=lambda x: x[1], reverse=True)
        for i, key in enumerate(self.ordered_keys):
            self.pos_dict[key[0]] = i

    # def reap(self, node: PathNode) -> None:
    #     order_item = self.place_limit_order(
    #         product_id=node.base + "-" + node.quote,
    #         side="buy",
    #         price=node.price,
    #         size=node.volume,
    #         time_in_force="GTT",
    #         cancel_after="min",
    #     )

    #     if "message" in order_item:
    #         raise Exception()

    # def nav_path(self):
    #     while self.current_node.next:
    #         try:
    #             self.reap(self.current_node)
    #         except Exception as e:
    #             break
    #         else:
    #             self.current_node = self.current_node.next

    def make_path(self, v, explored=None, path=None):
        # profitbale USD path
        if explored is None:
            explored = []
        if path is None:
            path = [v]

        explored.append(v)

        paths = []
        the_keys = list()
        for key in self._graph[v].keys():
            the_keys.insert(self.pos_dict[key], key)
        # print(self._graph[v].keys(), the_keys)

        for t in self._graph[v].keys():
            if t not in explored and self._graph[v][t] > 0.0:
                t_path = path + [t]
                self.priority[t]["appear_count"] += 1
                paths.append(tuple(t_path))
                paths.extend(self.make_path(t, explored[:], t_path))

                if (
                    t_path[-1] in self._graph["USD"].keys()
                    and self._graph["USD"][t_path[-1]] > 0.0
                ):
                    if len(t_path) > 2:
                        # print("Testing", str_out)
                        if self.check_path(t_path):
                            self._valid_path = t_path
                            raise FoundPath()
        return paths

    def run(self):
        while True:
            try:
                self.make_path("USD")
            except FoundPath as e:
                pass
            except Exception as e:
                print(str(e))
            finally:
                print("*********** Made a path **********")

    def check_path(self, path) -> bool:
        # graph[buy this][with this] I think
        total = self.config.MIN_TRAN

        if path[-1] + "-USD" in self.trade_pairs:
            path.append("USD")
            for i, use_this in enumerate(path[0 : len(path) - 1]):
                try:
                    time.sleep(0.1)
                    buy_this = path[i + 1]
                    total *= 1 - self.config.FEE
                    total /= self._graph[buy_this][use_this]
                except ZeroDivisionError:
                    return False

            if total > self.highest_total:
                self.highest_total = total
                str_out = ""
                for i, use_this in enumerate(path):
                    if i < len(path) - 1:
                        str_out += use_this + ("-{0:.8f}->").format(
                            self._graph[path[i + 1]][use_this]
                        )
                    else:
                        str_out += path[i]
                os.system("clear")
                print("Highest path -", str_out)
                print("Highest revenue", self.highest_total)
                print("USD balance:", self.analytics.get_balance(), "\n")

            if total > self.config.MIN_TRAN:
                if self.analytics.get_balance() >= self.config.MIN_TRAN:
                    self.analytics.set_balance(
                        self.analytics.get_balance() + (total - self.config.MIN_TRAN)
                    )
                for key in path:
                    self.priority[key]["valid_count"] += 1

                self._update_priority()
                # print(self.ordered_keys)

                return True

        return False
