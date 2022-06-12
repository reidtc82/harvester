from pprint import pprint
from config import Config
import time


class PathNode:
    def __init__(self, next, price, volume, base, quote) -> None:
        self.next = next
        self.price = price
        self.volume = volume
        self.base = base
        self.quote = quote


class Reaper:
    def __init__(self, graph, trade_pairs) -> None:
        self._graph = graph
        self.current_node = PathNode(None, None, None, None, quote="USD")
        self.trade_pairs = trade_pairs
        self.config = Config()
        self._valid_path = None

    def reap(self, node: PathNode) -> None:
        # TODO: calculate profitable path back to USD and attempt to execute
        order_item = self.place_limit_order(
            product_id=node.base + "-" + node.quote,
            side="buy",
            price=node.price,
            size=node.volume,
            time_in_force="GTT",
            cancel_after="min",
        )

        if "message" in order_item:
            raise Exception()

    def nav_path(self):
        while self.current_node.next:
            try:
                self.reap(self.current_node)
            except Exception as e:
                break
            else:
                self.current_node = self.current_node.next

    def make_path(self, v, explored=None, path=None):
        # profitbale USD path
        if explored is None:
            explored = []
        if path is None:
            path = [v]

        explored.append(v)

        paths = []
        for t in self._graph[v].keys():
            if t not in explored and self._graph[v][t] > 0.0:
                t_path = path + [t]
                paths.append(tuple(t_path))
                paths.extend(self.make_path(t, explored[:], t_path))
                str_out = ""
                for i, item in enumerate(t_path[0 : len(t_path) - 1]):
                    str_out += item + ("-{0:.8f}->").format(
                        self._graph[item][t_path[i + 1]]
                    )
                if "USD" in self._graph[t_path[-1]].keys():
                    str_out += (
                        t_path[-1]
                        + ("-{0:.8f}->").format(self._graph[t_path[-1]]["USD"])
                        + "USD"
                    )
                    # print(str_out)
                    if self.check_path(t_path):
                        self._valid_path = t_path
                        break
        return paths

    def run(self):
        while True:
            self.make_path("USD")
            # print("A valid path", self._valid_path)
            # time.sleep(30)
            # self.nav_path()

    def check_path(self, path) -> bool:
        total = self.config.MIN_TRAN
        goal_total = self.config.MIN_TRAN
        if path[-1] + "-USD" in self.trade_pairs and len(path) > 2:
            path.append("USD")
            for i, sym in enumerate(path[0 : len(path) - 1]):
                try:
                    total /= self._graph[sym][path[i + 1]]
                except ZeroDivisionError:
                    # print("something broke and rate was 0")
                    return False
                goal_total *= self.config.GAIN

            time.sleep(1)
            if total >= goal_total:
                print("A valid path -", path)
                print(total, "<?>", goal_total)
                return True
        return False
