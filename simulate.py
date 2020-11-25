import random
import statistics
from collections import defaultdict

from monopoly import Game
from buy_decision_algos import BuyIfNoOneOwnsTypeAndIsOfTheOneTypeOwned


def get_results(results, game, attrs_to_get):
    for attr in attrs_to_get:
        attr_obj = getattr(game, attr)
        if callable(attr_obj):
            val = attr_obj()
        else:
            val = attr_obj
        results[attr].append(val)


def print_results(results, num_players):
    for attr, results_list in results.items():
        mean = statistics.mean(results_list)
        std_dev = statistics.stdev(results_list)
        print(
            f"num_players -> {num_players}, mean -> {int(mean)}, stdev -> {int(std_dev)}"
        )


def play_x_games(
    num_games=200,
    num_players=range(2, 9),
    buy_decision_algorithms=(BuyIfNoOneOwnsTypeAndIsOfTheOneTypeOwned,),
    attrs_to_get=("get_rounds_played_per_player",),
    slow_down=False,
):
    for buy_decision_algorithm in buy_decision_algorithms:
        results = defaultdict(list)

        print(buy_decision_algorithm.__name__)
        print(buy_decision_algorithm.__doc__)
        print("num games per simulation:", str(num_games))
        print("attrs to get:", attrs_to_get)

        for num_players_ in num_players:
            for i in range(num_games):
                game = Game(num_players_, buy_decision_algorithm=buy_decision_algorithm, slow_down=slow_down)
                get_results(results, game, attrs_to_get)
                game.end()

            print_results(results, num_players_)
