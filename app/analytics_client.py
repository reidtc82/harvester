class SimulationClient:
    def __init__(self):
        self.balance = 20.0

    def get_balance(self) -> float:
        return self.balance

    def set_balance(self, new_bal) -> float:
        self.balance = new_bal
