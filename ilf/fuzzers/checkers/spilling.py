from .checker import Checker
from ...ethereum import REVERT, INVALID


class Spilling(Checker):

    def __init__(self):
        super().__init__()


    def check(self, logger):
        for _, log in enumerate(logger.logs):
            if log.error.startswith("ilf: integer"): # over or under
                return True

        return False