from multiprocessing import Manager


class Graph(dict):
    def __init__(self, *args, **kwargs):
        super(Graph, self).__init__(*args, **kwargs)

    def __repr__(self) -> str:
        str_out = ""
        for key in self.keys():
            str_out += key + " " + str(self[key]) + "\n"

        return str_out
