class TooMany(Exception):
    pass


class TooManyPlayers(TooMany):
    pass


class NotEnough(Exception):
    pass


class MustBeEqualAmounts(Exception):
    pass


class Argument(Exception):
    pass


class DidntFind(Exception):
    pass


class NoOwner(Exception):
    pass


class CantMortgage(Exception):
    pass


class CantBuyBuildings(Exception):
    pass
