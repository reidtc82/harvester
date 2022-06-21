import random
from app.analytics_client import SimulationClient
from app.errors.client_errors import ClientMessage
from app.errors.not_really_error import FoundPath
from config import Config
import time
import os
from datetime import datetime
from cbpro import AuthenticatedClient, PublicClient
import decimal


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
    _valid_path_count = 0
    base_precision = dict()
    quote_precision = dict()
    balances = dict()

    def __init__(self, graph, trade_pairs) -> None:
        self._graph = graph
        self.current_node = PathNode(None, None, None, None, quote="USD")
        self.trade_pairs = trade_pairs
        self.config = Config()
        self.analytics = SimulationClient()
        self.trade_client = AuthenticatedClient(
            self.config.COINBASE_AUTH_KEY,
            self.config.COINBASE_AUTH_SECRET,
            self.config.COINBASE_PASSWORD,
        )
        self._build_priority(graph)
        self._update_priority()
        self._start_time = datetime.now()
        # self.balances = self._graph.keys()
        pub_client = PublicClient()
        product_list = pub_client.get_products()
        self.base_precision["USD"] = 2
        for prod in product_list:
            self.base_precision[prod["base_currency"]] = int(
                prod["base_min_size"][::-1].find(".")
            )
            self.quote_precision[prod["quote_currency"]] = int(
                prod["quote_increment"][::-1].find(".")
            )
        self.base_precision["BTC"] = 8

        try:
            accounts = self.trade_client.get_accounts()
        except Exception as e:
            print(e)
        else:
            print("Updating balances...")
            for account in accounts:
                # print(account)
                self.balances[account["currency"]] = float(account["available"])

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

        if random.randint(1, 10) > 2:
            random.shuffle(the_keys)

        for t in the_keys:
            if t not in explored and self._graph[v][t] > 0.0:
                t_path = path + [t]
                self.priority[t]["appear_count"] += 1
                paths.append(tuple(t_path))
                paths.extend(self.make_path(t, explored[:], t_path))

                if (
                    "USD" in self._graph[t_path[-1]].keys()
                    and self._graph[t_path[-1]]["USD"] > 0.0
                ):
                    if len(t_path) > 2:
                        # print("t-path", t_path)
                        if self.check_path(t_path):
                            self._valid_path = t_path
                            # print("pre-valid", self._valid_path)
                            raise FoundPath()

        return paths

    def run(self):
        while True:
            try:
                self.make_path("USD")
            except FoundPath as e:
                # gnarly way to do this...
                self._valid_path_count += 1
                try:
                    # print("post valid path", self._valid_path)
                    self.execute_path()
                except Exception as e:
                    raise e
                except ClientMessage as cm:
                    print(cm.message)

                # pass
            except Exception as e:
                # print(e)
                pass

    def execute_path(self) -> None:
        # TODO: resolve balances in self._valid_path
        # TODO: execute self._valid_path - tack USD at the end
        #               1. each i, i+1 needs to be resolved to a valid pair
        #               2. each pair needs a valid price and volume and side
        #               3. construct order as limit with FOK
        #               4. if order fails, then abort continue
        path = self._valid_path
        print("New path...", path)
        if "USD" in self.balances:
            for i, coin in enumerate(path[: len(path) - 1]):
                pair = (
                    coin + "-" + path[i + 1]
                    if coin + "-" + path[i + 1] in self.trade_pairs
                    else path[i + 1] + "-" + coin
                    if path[i + 1] + "-" + coin in self.trade_pairs
                    else ""
                )
                base = pair.split("-")[0]
                quote = pair.split("-")[1]
                side = "sell" if pair.split("-")[0] == coin else "buy"

                price = self._graph[base][quote]
                if side == "buy" and quote == "USD":
                    size = float(
                        self.round_down(
                            self.config.MIN_TRAN / price, self.base_precision[base]
                        )
                    )
                else:
                    size = float(
                        self.round_down(
                            self.balances[quote] / price, self.base_precision[base]
                        )
                        if side == "buy"
                        else self.round_down(
                            self.balances[base], self.base_precision[base]
                        )
                    )

                if base in self.balances and quote in self.balances:
                    print(
                        "Trying...",
                        path,
                        pair,
                        side + " price-{0:.8f} size-{1:.8f}".format(price, size),
                        "base_balance {0:.8f} quote_balance {1:.8f}".format(
                            self.balances[base], self.balances[quote]
                        ),
                    )

                try:
                    if (
                        (
                            side == "buy"
                            and "USD" in pair
                            and self.balances["USD"] >= self.config.MIN_TRAN
                        )
                        or ("USD" not in pair and side == "buy")
                        or (side == "sell")
                    ) and size > 0.0:
                        if self.check_path(path):
                            trade_result = self.trade_client.place_limit_order(
                                product_id=pair,
                                time_in_force="FOK",
                                side=side,
                                price=price,
                                size=size,
                            )
                        else:
                            trade_result = {"path_not_valid": True}
                    else:
                        if (
                            "USD" in pair
                            and "USDC" not in pair
                            and "USDT" not in pair
                            and self.balances["USD"] < self.config.MIN_TRAN
                            and side == "buy"
                        ):
                            trade_result = {"no_usd": True}
                        else:
                            trade_result = {"size_too_small": True}
                except Exception as e:
                    raise e
                else:
                    if "message" in trade_result:
                        print("Trade failure...", trade_result)
                        time.sleep(10)
                        break
                    else:
                        if "no_usd" in trade_result:
                            print("no USD")
                            pass
                        elif "size_too_small" in trade_result:
                            print("size too small")
                            pass
                        elif "path_not_valid" in trade_result:
                            print("path no longer profitable")
                            break
                        else:
                            print("Trade success...", trade_result)
                            accounts = self.trade_client.get_accounts()
                            print("Updating balances...")
                            for account in accounts:
                                self.balances[account["currency"]] = float(
                                    account["available"]
                                )
                        time.sleep(0.1)

        time.sleep(1)

    def check_path(self, path) -> bool:
        # graph[use this][to buy this] I think
        #      [base][quote] = pay 1 base to get x quote
        # graph[BTC][USD] = 26000 (1 BTC results in 26000 USD)
        # graph[USD][BTC] = 0.00003846 (1 USD results in 0.00003846 BTC)
        total = self.config.MIN_TRAN
        # print(path)
        if path[-1] != "USD":
            if path[-1] + "-USD" in self.trade_pairs:
                path.append("USD")
            else:
                return False

        if len(path) < 5:
            for i, base in enumerate(path[0 : len(path) - 1]):

                try:
                    time.sleep(0.1)
                    quote = path[i + 1]
                    total *= 1 - self.config.FEE
                    total *= round(self._graph[base][quote], self.base_precision[base])
                except ZeroDivisionError:
                    return False
                except Exception as e:
                    print(e)

            if total > self.highest_total:
                self.highest_total = total

            # str_out = ""
            # for i, base in enumerate(path):
            #     if i < len(path) - 1:
            #         str_out += base + ("-{0:.8f}->").format(
            #             round(self._graph[base][path[i + 1]], self.base_precision[base])
            #         )
            #     else:
            #         str_out += path[i]

            # os.system("clear")
            # print("Current path -", str_out)
            # print("Potential revenue: ${0:.2f}".format(total))
            # print("USD balance:", self.analytics.get_balance(), "\n")
            # print(
            #     "*********** Valid path count: {0} * Session time: {1} **********".format(
            #         self._valid_path_count, datetime.now() - self._start_time
            #     )
            # )
            # print(
            #     "********************** ${0:.2f} per minute *********************\n".format(
            #         (self.analytics.get_balance() - 20.0)
            #         / ((datetime.now() - self._start_time).total_seconds() / 60)
            #     ),
            #     end="\r",
            # )

            if total - self.config.MIN_TRAN > 0.00000001:
                # TODO: put money behind it
                if self.analytics.get_balance() >= self.config.MIN_TRAN:
                    self.analytics.set_balance(
                        self.analytics.get_balance() + (total - self.config.MIN_TRAN)
                    )

                for key in path:
                    self.priority[key]["valid_count"] += 1

                self._update_priority()

                return True

        return False

    def round_down(self, value, decimals):
        with decimal.localcontext() as ctx:
            d = decimal.Decimal(value)
            ctx.rounding = decimal.ROUND_DOWN
            return round(d, decimals)
