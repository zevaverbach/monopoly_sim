"""
Purpose:

1) To simulate games of Monopoly in order to determine the best strategy
2) To play Monopoly on a computer

Along those lines, here's some prior art:

http://www.tkcs-collins.com/truman/monopoly/monopoly.shtml
https://blog.ed.ted.com/2017/12/01/heres-how-to-win-at-monopoly-according-to-math-experts/


TODO: maybe instead of all these classmethods, instances?
TODO: something more graceful than Game.games[0]
TODO: store LAST_ROLL in a global constant instead of passing it around to all the `action` methods
TODO: write some tests
TODO: break up into modules
TODO: add auctions
TODO: print the reason someone decided to/not to buy a property
TODO: print whether someone is in jail or just visiting
TODO: don't allow buying of multiple houses/a hotel on a property if the other properties in the same color don't have any
"""
from abc import ABC
from collections import defaultdict
from itertools import cycle
from random import choice, shuffle
from time import sleep
from typing import cast, List, NewType, Optional, Tuple, Type

from exceptions import (
    Argument,
    CantBuyBuildings,
    CantMortgage,
    DidntFind,
    MustBeEqualAmounts,
    NoOwner,
    NotEnough,
    TooMany,
    TooManyPlayers,
    NotEnoughPlayers,
)

ALL_MONEY = 20_580
NUM_HOUSES = 32
NUM_HOTELS = 12

Doubles = NewType("Doubles", bool)

LANGUAGE = "français"
BACKUP_LANGUAGE = "English"
BUILDING_TYPES = "house", "hotel"
MAX_ROUNDS = 5000

BUILDABLE_PROPERTY_COLORS = (
    "yellow",
    "red",
    "light blue",
    "brown",
    "pink",
    "orange",
    "green",
    "dark blue",
)


class Space:
    def __repr__(self):
        if hasattr(self, "_name"):
            return self._name
        return self.__name__


class NothingHappensWhenYouLandOnItSpace(Space):
    @classmethod
    def action(self, player: "Player", _):
        pass


class Go(NothingHappensWhenYouLandOnItSpace):
    """
    should this really be a NothingHappensWhenYouLandOnItSpace?
    since you get to collect $200
    """
    pass


class Jail(NothingHappensWhenYouLandOnItSpace):
    pass


class FreeParking(NothingHappensWhenYouLandOnItSpace):
    pass


class TaxSpace(Space):
    amount = None

    @classmethod
    def action(cls, player, _):
        print(f"{player} pays bank {cls.amount} ({cls.__name__})")
        player.pay("Bank", cls.amount)


class LuxuryTax(TaxSpace):
    _name = {"français": "Impôt Supplémentaire", "deutsch": "Nachsteuer"}
    amount = 75


class IncomeTax(TaxSpace):
    # TODO: _name
    amount = 100


class GoToJail(Space):
    @classmethod
    def action(cls, player, _):
        # player.go_to_jail()
        pass


class CardSpace(Space):
    deck = None

    @classmethod
    def action(cls, player, _):
        # for lazy loading to avoid circular imports (?)
        deck = eval(cls.deck)
        card = deck.get_card()
        return card.action(player, _)


class CommunityChest(CardSpace):
    deck = "CommunityChestDeck"
    _name = {"français": "Chancellerie", "deutsch": "Kanzlei"}


class Chance(CardSpace):
    deck = "ChanceDeck"
    _name = {"français": "Chance", "deutsch": "Chance", "English": "Chance"}


class Card(ABC):
    mandatory_action = False
    cost = None
    keep = False

    @classmethod
    def action(self, player: "Player", _):
        raise NotImplementedError

    def __repr__(self):
        return self.text


class ElectedPresidentCard(Card):
    mandatory_action = True
    text = {
        "français": "Vous avez été elu president du conseil d'administration. Versez M50 à chaque joueur."
    }

    @classmethod
    def action(cls, player, _):
        print("{cls.__name__}")
        for other_player in Game.games[0].active_players:
            if other_player != player:
                print(f"{player} is paying {other_player} 50")
                player.pay(other_player, 50)


class GetOutOfJailFreeCard(Card):
    text = {
        "français": "Vous êtes libéré de prison. Cette carte peut être conservée jusqu'à ce "
        "qu'elle soit utilisée ou vendue. "
    }

    @classmethod
    def action(cls, player: "Player", _):
        print(f"{player} got a get out of jail free card")
        player.get_out_of_jail_free_card = True


class AdvanceCard(Card):
    mandatory_action = True
    kwarg = {}

    @classmethod
    def action(cls, player, _):
        print(f"the card is {cls.__name__}")
        player.advance(**cls.kwarg)


class GoToJailCard(AdvanceCard):
    text = {
        "français": "Allez en prison. Avancez tout droit en prison. Ne passez pas par la case "
        "départ. Ne recevez pas M200. "
    }
    kwarg = {"until_space_type": "Jail", "pass_go": False}


class AdvanceThreeSpacesCard(AdvanceCard):
    mandatory_action = True
    text = {"français": "Reculez de trois cases."}
    kwarg = {"num_spaces": 3}


class GoToClosestRailroadCard(AdvanceCard):
    text = {"français": "Avancez jusqu'à le chemin de fer le plus proche."}
    kwarg = {"until_space_type": "Railroad"}


class GoToBernPlaceFederaleCard(AdvanceCard):
    mandatory_action = True
    text = {
        "français": "Avancez jusqu'a Bern Place Federale. Si vous passez par la case départ, "
        "vous touchez la prime habituelle de M200. "
    }

    kwarg = {"space_index": "Berne Place Fédérale"}


class BuildingAndLoanMaturesCard(Card):
    mandatory_action = True
    text = {
        "français": "Votre immeuble et votre pret rapportent. Vous devez toucher M150.",
        "English": "Your building and loan matures. Collect M150.",
    }

    @classmethod
    def action(self, player, _):
        print(f"{self.__class__}: the bank pays {player} 150")
        Bank.pay(player, 150)


class SpeedingCard(Card):
    mandatory_action = True
    text = {"français": "Amende pour excès de vitesse. Payez M15."}

    @classmethod
    def action(cls, player, _):
        print(f"{cls.__name__}: {player} pays 15 to Bank")
        player.pay(Bank, 15)


class RepairPropertyCard(Card):
    text = {
        "français": "Vous faites des réparations sur toutes vos propriétés: Versez M25"
        " pour chaque maison M100 pour Chaque hôtel que vous possédez"
    }

    @classmethod
    def action(cls, player, _):
        num_houses, num_hotels = 0, 0
        for property in player.buildable_properties:
            num_houses += property.buildings["house"]
            num_hotels += property.buildings["hotel"]
        total_owed = sum([num_houses * 25, num_hotels * 100])
        print(f"{player} pays the bank {total_owed} for {cls.__name__}")
        player.pay(Bank, total_owed)


class Deck:
    deck = None

    @classmethod
    def shuffle(cls):
        shuffle(cls.deck)

    @classmethod
    def get_card(cls):
        card = cls.deck.pop()
        if not card.keep:
            cls.deck.insert(0, card)
        return card


class ChanceDeck(Deck):
    deck = [
        AdvanceThreeSpacesCard,
        ElectedPresidentCard,
        BuildingAndLoanMaturesCard,
        GoToBernPlaceFederaleCard,
        GoToJailCard,
        SpeedingCard,
        GoToClosestRailroadCard,
    ]


class CommunityChestDeck(Deck):
    # TODO: remove these and add the readl ones!
    deck = [GoToJailCard, SpeedingCard]


def shuffle_decks():
    for deck in (ChanceDeck, CommunityChestDeck):
        deck.shuffle()


def buy_decision(property: "Property", player: "Player"):
    return Game.games[0].buy_decision_algorithm(property, player)


class Decision:
    pass


class Property(Space):
    mortgaged = False
    owner = None
    cost = 0
    instances = []
    type = None

    def __init__(self, _name):
        self._name = _name
        self.instances.append(self)

    def __repr__(self):
        if hasattr(self, "_name"):
            return self._name[LANGUAGE]
        return str(self.__class__)

    @classmethod
    def reset(cls):
        for property in cls.instances:
            property.owner = None

    @classmethod
    def get_num_of_type(cls, type):
        return len(cls.instances_by_type()[type])

    @property
    def num_of_type(self):
        return self.get_num_of_type(self.type)

    @property
    def properties_of_type(self):
        return self.instances_by_type()[self.type]

    @classmethod
    def instances_by_type(cls):
        ibt = defaultdict(list)
        for i in cls.instances:
            ibt[i.type].append(i)
        return ibt

    def action(self, player: "Player", last_roll=None):
        if not self.owner:
            buy = buy_decision(self, player)
            if buy:
                print(f"{player} will buy {self}")
                return player.buy(self)
            print(f"{player} decided not to buy {self}")
            return
        if self.owner == player or self.mortgaged:
            print(f"{player} landed on his own property, {self}")
            return
        rent = self.calculate_rent(last_roll)
        print(f"{player} pays {self.owner} ${rent} after landing on it.")
        player.pay(self.owner, rent)

    def calculate_rent(self, _):
        if not self.owner:
            raise NoOwner


class Utility(Property):
    cost = 200
    rent = {
        0: lambda _: 0,
        1: lambda dice_total: dice_total * 4,
        2: lambda dice_total: dice_total * 10,
    }
    mortgage_cost = 75
    unmortgage_cost = 83
    type = "utility"

    def calculate_rent(self, last_roll: int):
        super().calculate_rent(last_roll)
        if not last_roll:
            return 10 * Player.roll_the_dice()[0]
        return self.rent[self.owner.owns_x_of_type(self.type)](last_roll)


class Railroad(Property):
    cost = 200
    rent = {1: 25, 2: 50, 3: 100, 4: 200}
    mortgage_cost = 100
    unmortgage_cost = 110
    type = "railroad"

    def calculate_rent(self, _):
        super().calculate_rent(_)
        owns_x_of_type = self.owner.owns_x_of_type(self.type)
        if not owns_x_of_type:
            return 0
        return self.rent[owns_x_of_type]


class BuildableProperty(Property):
    def __init__(
        self,
        _name,
        cost,
        rent,
        color,
        house_and_hotel_cost,
        mortgage_cost,
        unmortgage_cost,
    ):
        super().__init__(_name)
        self.cost = cost
        self.rent = rent
        self.house_and_hotel_cost = house_and_hotel_cost
        self.color = color
        self.type = color
        self.mortgage_cost = mortgage_cost
        self.unmortgage_cost = unmortgage_cost
        self.buildings = {"house": 0, "hotel": 0}

    def buy_building(self, building_type):
        """
        TODO: Each property within a group must be no more than one house level away from all other
         properties in that group. For example, if you own the Orange group, you can’t put a
         second house on New York Ave until you have a first house on St. James and Tennessee.
         Then you can’t put a third house on any property until you have two houses on
         all properties.
        """
        if not self.owner.owns_all_type(self.type):
            raise CantBuyBuildings

        if building_type == "hotel" and self.buildings["house"] != 4:
            raise NotEnough
        elif building_type == "house" and self.buildings["house"] == 4:
            raise TooMany

        cost = self.house_and_hotel_cost
        self.owner.check_funds(cost)
        Bank.get_building(building_type)
        self.owner.pay(Bank, cost)

        for property_ in self.properties_of_type:
            if building_type == "hotel":
                property_.buildings["house"] = 0
                property_.buildings["hotel"] = 1
            else:
                property_.buildings["house"] += 1

    def sell_buildings(self, building_type, quantity):
        if not self.buildings[building_type]:
            raise NotEnough
        if quantity % self.num_of_type:
            # TODO: this isn't right
            #  https://www.quora.com/When-can-a-player-place-a-house-in-monopoly
            raise MustBeEqualAmounts

    def mortgage(self, player: "Player"):
        if self.buildings:
            raise CantMortgage
        Bank.pay(player, self.mortgage_cost)
        self.mortgaged = True

    def un_mortgage(self, player: "Player"):
        player.pay(Bank, self.unmortgage_cost)
        self.mortgaged = False

    def calculate_rent(self, _):
        super().calculate_rent(_)
        if self.buildings["house"] or self.buildings["hotel"]:
            buildings = self.buildings
            if buildings["house"]:
                key = buildings["house"]
            else:
                key = "hotel"
        elif self.owner.owns_all_type(self.type):
            key = "monopoly"
        else:
            key = 0
        return self.rent[key]


class Board:
    spaces = [
        Go,
        BuildableProperty(
            _name={"français": "Coire Kornplatz"},
            cost=60,
            color="brown",
            rent={0: 2, "monopoly": 4, 1: 10, 2: 30, 3: 90, 4: 160, "hotel": 250},
            house_and_hotel_cost=50,
            mortgage_cost=30,
            unmortgage_cost=33,
        ),
        CommunityChest,
        BuildableProperty(
            _name={"français": "Schaffhouse Vordergasse"},
            cost=60,
            color="brown",
            rent={0: 4, "monopoly": 8, 1: 20, 2: 60, 3: 180, 4: 320, "hotel": 450},
            house_and_hotel_cost=50,
            mortgage_cost=30,
            unmortgage_cost=33,
        ),
        IncomeTax,
        Railroad(_name={"français": "Union des Chemins de Fer Privés"}),
        BuildableProperty(
            _name={"français": "Aarau Rathausplatz"},
            cost=100,
            color="light blue",
            rent={0: 6, "monopoly": 12, 1: 30, 2: 90, 3: 270, 4: 400, "hotel": 550},
            house_and_hotel_cost=50,
            mortgage_cost=50,
            unmortgage_cost=55,
        ),
        Chance,
        BuildableProperty(
            _name={"français": "Neuchâtel Place Pury"},
            cost=100,
            color="light blue",
            rent={0: 6, "monopoly": 12, 1: 30, 2: 90, 3: 270, 4: 400, "hotel": 550},
            house_and_hotel_cost=50,
            mortgage_cost=50,
            unmortgage_cost=55,
        ),
        BuildableProperty(
            _name={"français": "Thoune Hauptgasse"},
            cost=120,
            color="light blue",
            rent={0: 8, "monopoly": 16, 1: 30, 2: 100, 3: 300, 4: 400, "hotel": 600},
            house_and_hotel_cost=50,
            mortgage_cost=60,
            unmortgage_cost=66,
        ),
        Jail,
        BuildableProperty(
            _name={"français": "Bâle Steinen-Vorstadt"},
            cost=140,
            color="pink",
            rent={0: 10, "monopoly": 20, 1: 50, 2: 150, 3: 450, 4: 625, "hotel": 750},
            house_and_hotel_cost=100,
            mortgage_cost=70,
            unmortgage_cost=77,
        ),
        Utility(_name={"français": "Usines Électriques"}),
        BuildableProperty(
            _name={"français": "Soleure Hauptgasse"},
            cost=140,
            color="pink",
            rent={0: 10, "monopoly": 20, 1: 50, 2: 150, 3: 450, 4: 625, "hotel": 750},
            house_and_hotel_cost=100,
            mortgage_cost=70,
            unmortgage_cost=77,
        ),
        BuildableProperty(
            _name={"français": "Lugano Via Nassa"},
            cost=160,
            color="pink",
            rent={0: 12, "monopoly": 24, 1: 60, 2: 180, 3: 500, 4: 700, "hotel": 900},
            house_and_hotel_cost=100,
            mortgage_cost=80,
            unmortgage_cost=88,
        ),
        BuildableProperty(
            _name={"français": "Bienne Rue De Nidau"},
            cost=180,
            color="orange",
            rent={0: 14, "monopoly": 28, 1: 70, 2: 200, 3: 550, 4: 750, "hotel": 950},
            house_and_hotel_cost=100,
            mortgage_cost=90,
            unmortgage_cost=99,
        ),
        CommunityChest,
        BuildableProperty(
            _name={"français": "Fribourg Avenue de la Gare"},
            cost=180,
            color="orange",
            rent={0: 14, "monopoly": 28, 1: 70, 2: 200, 3: 550, 4: 750, "hotel": 950},
            house_and_hotel_cost=100,
            mortgage_cost=90,
            unmortgage_cost=99,
        ),
        BuildableProperty(
            _name={"français": "La Chaux-de-Fonds Avenue Louis-Robert"},
            cost=200,
            color="orange",
            rent={0: 16, "monopoly": 32, 1: 80, 2: 220, 3: 600, 4: 800, "hotel": 1_000},
            house_and_hotel_cost=100,
            mortgage_cost=100,
            unmortgage_cost=110,
        ),
        FreeParking,
        BuildableProperty(
            _name={"français": "Winterthour Bahnhofplatz"},
            cost=220,
            color="red",
            rent={0: 18, "monopoly": 39, 1: 90, 2: 250, 3: 700, 4: 875, "hotel": 1_050},
            house_and_hotel_cost=150,
            mortgage_cost=110,
            unmortgage_cost=121,
        ),
        Chance,
        BuildableProperty(
            _name={"français": "St-Gall Markplatz"},
            cost=220,
            color="red",
            rent={0: 18, "monopoly": 39, 1: 90, 2: 250, 3: 700, 4: 875, "hotel": 1_050},
            house_and_hotel_cost=150,
            mortgage_cost=110,
            unmortgage_cost=121,
        ),
        BuildableProperty(
            _name={"français": "Berne Place Fédérale"},
            cost=240,
            color="red",
            rent={
                0: 20,
                "monopoly": 40,
                1: 100,
                2: 300,
                3: 750,
                4: 925,
                "hotel": 1_100,
            },
            house_and_hotel_cost=150,
            mortgage_cost=120,
            unmortgage_cost=132,
        ),
        Railroad(_name={"français": "Tramways Interurbains"}),
        BuildableProperty(
            _name={"français": "Lucerne Weggisgasse"},
            cost=260,
            color="yellow",
            rent={
                0: 22,
                "monopoly": 34,
                1: 110,
                2: 330,
                3: 800,
                4: 975,
                "hotel": 1_150,
            },
            house_and_hotel_cost=150,
            mortgage_cost=130,
            unmortgage_cost=143,
        ),
        BuildableProperty(
            _name={"français": "Zurich Rennweg"},
            cost=260,
            color="yellow",
            rent={
                0: 22,
                "monopoly": 34,
                1: 110,
                2: 330,
                3: 800,
                4: 975,
                "hotel": 1_150,
            },
            house_and_hotel_cost=150,
            mortgage_cost=130,
            unmortgage_cost=143,
        ),
        Utility(_name={"français": "Usines Hydrauliques"}),
        BuildableProperty(
            _name={"français": "Lausanne Rue de Bourg"},
            cost=280,
            color="yellow",
            rent={
                0: 24,
                "monopoly": 48,
                1: 120,
                2: 360,
                3: 850,
                4: 1_025,
                "hotel": 1_200,
            },
            house_and_hotel_cost=150,
            mortgage_cost=140,
            unmortgage_cost=154,
        ),
        GoToJail,
        BuildableProperty(
            _name={"français": "Bâle Freie Strasse"},
            cost=300,
            color="green",
            rent={
                0: 26,
                "monopoly": 52,
                1: 130,
                2: 390,
                3: 900,
                4: 1_100,
                "hotel": 1_275,
            },
            house_and_hotel_cost=200,
            mortgage_cost=150,
            unmortgage_cost=165,
        ),
        BuildableProperty(
            _name={"français": "Genève Rue de la Croix-D'Or"},
            cost=300,
            color="green",
            rent={
                0: 26,
                "monopoly": 52,
                1: 130,
                2: 390,
                3: 900,
                4: 1_100,
                "hotel": 1_275,
            },
            house_and_hotel_cost=200,
            mortgage_cost=150,
            unmortgage_cost=165,
        ),
        CommunityChest,
        BuildableProperty(
            _name={"français": "Berne Spitalgasse"},
            cost=320,
            color="green",
            rent={
                0: 28,
                "monopoly": 56,
                1: 150,
                2: 450,
                3: 1_000,
                4: 1_200,
                "hotel": 1_400,
            },
            house_and_hotel_cost=200,
            mortgage_cost=160,
            unmortgage_cost=176,
        ),
        Railroad(_name={"français": "Association des Télépheriques"}),
        Chance,
        BuildableProperty(
            _name={"français": "Lausanne Place St. François"},
            cost=350,
            color="dark blue",
            rent={
                0: 35,
                "monopoly": 70,
                1: 175,
                2: 500,
                3: 1_100,
                4: 1_300,
                "hotel": 1_500,
            },
            house_and_hotel_cost=200,
            mortgage_cost=175,
            unmortgage_cost=193,
        ),
        LuxuryTax,
        BuildableProperty(
            _name={"français": "Zurich Paradeplatz"},
            cost=400,
            color="dark blue",
            rent={
                0: 50,
                "monopoly": 100,
                1: 200,
                2: 600,
                3: 1_400,
                4: 1_700,
                "hotel": 2_000,
            },
            house_and_hotel_cost=200,
            mortgage_cost=200,
            unmortgage_cost=220,
        ),
    ]
    SPACES_DICT = {}
    for index, space in enumerate(spaces):
        if hasattr(space, "_name"):
            space_name = space._name
        else:
            space_name = space.__name__

        if isinstance(space_name, dict):
            space_name = space._name.get(LANGUAGE) or space._name.get(BACKUP_LANGUAGE)
        SPACES_DICT[space_name] = index

    # SPACES_DICT = {space.name: space for space in spaces}
    NUM_SPACES = len(spaces)


def get_space_index(name):
    return Board.SPACES_DICT[name]


class EconomicActor:
    pass


class Bank(EconomicActor):
    money = ALL_MONEY
    NUM_HOUSES = NUM_HOUSES
    NUM_HOTELS = NUM_HOTELS

    @classmethod
    def reset(cls):
        cls.money = ALL_MONEY
        cls.NUM_HOUSES = NUM_HOUSES
        cls.NUM_HOTELS = NUM_HOTELS

    @classmethod
    def pay(cls, actor: "EconomicActor", amount: int):
        if isinstance(actor, str):
            actor = eval(actor)
        cls.money -= amount
        actor.money += amount

    @classmethod
    def get_building(cls, type_):
        cls.check_building_type(type_)
        store = cls.get_building_store(type_)
        if not store:
            raise NotEnough(f"Not enough {type_}s!")
        else:
            store -= 1

    @classmethod
    def put_building(cls, type_, quantity):
        cls.check_building_type(type_)
        store = cls.get_building_store(type_)
        store += quantity

    @staticmethod
    def check_building_type(type_):
        if type_ not in BUILDING_TYPES:
            raise TypeError

    @classmethod
    def get_building_store(cls, type_):
        return cls.NUM_HOUSES if type_ == "house" else cls.NUM_HOTELS


def get_index_of_next_space_of_type(current_space_index, until_space_type):
    space_indices_to_traverse = list(
        range(current_space_index + 1, Board.NUM_SPACES)
    ) + list(range(current_space_index))
    for index in space_indices_to_traverse:
        if isinstance(until_space_type, str):
            until_space_type = eval(until_space_type)
        if Board.spaces[index] == until_space_type or isinstance(
            Board.spaces[index], until_space_type
        ):
            return index
    raise DidntFind


def check_args(num_spaces, space_index, until_space_type):
    num_args = sum(
        1 for kwarg in (num_spaces, space_index, until_space_type) if kwarg is not None
    )
    if num_args > 1 or num_args == 0:
        raise Argument("provide either num_spaces or space_index or until_space_type")


class GetOutOfJailDecision(Decision):
    def __init__(self, player: "Player"):
        pass


def get_property_with_least_number_of_houses(properties):
    return sorted(properties, key=lambda prop: prop.buildings["house"], reverse=True)[0]


def get_property_with_no_hotels(properties):
    return sorted(properties, key=lambda prop: prop.buildings["hotel"])[0]


class Monopoly:
    def __init__(self, property_: "BuildableProperty"):
        self.properties = Property.instances_by_type()[property_.type]
        self.num_properties = len(self.properties)
        self.max_num_houses = 4 * self.num_properties
        self.max_num_hotels = self.num_properties

    def __repr__(self):
        return f"<Monopoly type={self.properties[0].type}"

    @property
    def num_houses(self):
        return sum(property.buildings["house"] for property in self.properties)

    @property
    def num_hotels(self):
        return sum(property.buildings["hotel"] for property in self.properties)

    @property
    def next_building(self) -> Tuple[Optional[str], Optional["BuildableProperty"]]:
        num_houses, num_hotels, max_num_houses, max_num_hotels = (
            self.num_houses,
            self.num_hotels,
            self.max_num_houses,
            self.max_num_hotels,
        )
        first_prop = self.properties[0]

        if not num_houses and not num_hotels:
            return "house", first_prop

        elif num_hotels == max_num_hotels:
            return None, None

        elif num_houses < max_num_houses:
            if not num_hotels:
                return (
                    "house",
                    get_property_with_least_number_of_houses(self.properties),
                )
            else:
                return "hotel", get_property_with_no_hotels(self.properties)
        elif num_houses == max_num_houses:
            return "hotel", first_prop


class Player(EconomicActor):
    in_jail = False
    bankrupt = False
    get_out_of_jail_free_card = False
    go_again = False
    current_space_index = get_space_index("Go")
    money = 0
    passed_go_times = 0
    monopolies = []

    def __str__(self):
        return self.name

    def __init__(self):
        self.name = choice([str(i) for i in range(10_000)])
        Bank.pay(self, 1_500)

    def pay(self, actor: Type["EconomicActor"], amount: int):
        if isinstance(actor, str):
            actor = eval(actor)
        self.check_funds(amount)
        self.money -= amount
        actor.money += amount

    def check_funds(self, amount):
        if amount > self.money:
            raise NotEnough

    def buy(self, property_: "Property", from_=Bank, cost=None):
        try:
            self.pay(from_, cost or property_.cost)
        except NotEnough:
            return
        property_.owner = self

        if property_.__class__.__name__ == "BuildableProperty" and self.owns_all_type(
            property_.type
        ):
            monopoly = Monopoly(property_)
            self.monopolies.append(monopoly)

    def buy_buildings_if_possible(self):
        if self.monopolies:
            print(f"{self} has {self.monopolies}")
        else:
            print(f"{self} has no monopolies.")
        for monopoly in self.monopolies:
            while True:
                next_building_type, property_ = monopoly.next_building
                if not next_building_type:
                    break
                print("next_building_type:", next_building_type, "property_:", property_)
                if not self.can_afford(property_.house_and_hotel_cost):
                    print("can't afford")
                    break
                try:
                    property_.buy_building(next_building_type)
                except NotEnough:
                    print("can't afford")
                    break
                print("bought a building")

    def take_a_turn(self):
        if self.in_jail:
            print(f"{self} is in jail")
            decision = GetOutOfJailDecision(self)
            print(decision)
            return decision
        # TODO: you can buy buildings from jail! Fix this
        self.buy_buildings_if_possible()
        num_spaces, doubles = self.roll_the_dice()
        print(f'{self} rolled', str(num_spaces))
        if doubles:
            self.go_again = True
        else:
            self.go_again = False

        self.advance(num_spaces, just_rolled=True)

    def owns_x_of_type(self, type_):
        properties_of_this_type = self.properties_by_type.get(type_)
        if properties_of_this_type is None:
            return 0
        if properties_of_this_type is None:
            return 0
        return len(properties_of_this_type)

    def owns_all_type(self, type_):
        return self.owns_x_of_type(type_) == Property.get_num_of_type(type_)

    @property
    def properties_by_type(self):
        pbt = defaultdict(list)
        for property in self.properties:
            pbt[property.type].append(property)
        return pbt

    @staticmethod
    def roll_the_dice() -> Tuple[int, Doubles]:
        die_one, die_two = choice(range(1, 7)), choice(range(1, 7))
        total = die_one + die_two
        if die_one == die_two:
            return total, cast(Doubles, True)
        return total, cast(Doubles, False)

    @property
    def assets(self):
        return self.money + self.total_property_mortgage_value

    @property
    def total_property_mortgage_value(self):
        return sum(property.mortgage_cost for property in self.properties)

    @property
    def properties(self) -> List["Property"]:
        # TODO: create an `instances` class attribute on `Property` that keeps track of them all
        #  then iterate through those instances to see which ones have an owner equal to `self`
        return [p for p in Property.instances if p.owner == self]

    @property
    def buildable_properties(self) -> List[BuildableProperty]:
        return [
            p for p in self.properties if p.__class__.__name__ == "BuildableProperty"
        ]

    def advance(
        self,
        num_spaces=None,
        space_index=None,
        until_space_type=None,
        pass_go=True,
        just_rolled=True,
    ):
        new_space_index = None
        check_args(num_spaces, space_index, until_space_type)
        if num_spaces:
            new_space_index = self.current_space_index + num_spaces
        elif space_index:
            if isinstance(space_index, str):
                space_index = get_space_index(space_index)
            new_space_index = space_index
        elif until_space_type:
            new_space_index = get_index_of_next_space_of_type(
                self.current_space_index, until_space_type
            )

        if pass_go and new_space_index >= Board.NUM_SPACES - 1:
            self.money += 200
            print(f"{self} passed go and collected 200")
            self.passed_go_times += 1
            new_space_index = new_space_index - Board.NUM_SPACES
        elif pass_go and self.current_space_index > new_space_index:
            self.money += 200
            print(f"{self} passed go and collected 200")
            self.passed_go_times += 1

        print("new_space_index", str(new_space_index))
        self.current_space_index = new_space_index

        if just_rolled:
            last_roll = num_spaces
        else:
            last_roll = None

        try:
            self.do_action_of_current_space(last_roll=last_roll)
        except NotEnough:
            # TODO: is this always right?
            # TODO: eventually make deals and mortgage prtoperties to avoid bankruptcy
            self.bankrupt = True
            print(f"{self} just went bankrupt!")

    def do_action_of_current_space(self, last_roll=None):
        space = Board.spaces[self.current_space_index]
        print(f"space is {space}")
        space.action(self, last_roll)

    def go_to_jail(self):
        self.in_jail = True
        self.current_space_index = get_space_index("Jail")

    def can_afford(self, cost):
        return self.money >= cost


class Game:
    games = []
    rounds = 0

    def __init__(self, num_players, buy_decision_algorithm, slow_down=False):
        self.slow_down = slow_down
        Bank.reset()
        shuffle_decks()
        Property.reset()
        self.buy_decision_algorithm = buy_decision_algorithm()
        # TODO: make this nicer
        if self.games:
            del self.games[0]
        self.games.append(self)
        if num_players < 2:
            raise NotEnoughPlayers
        if num_players > 8:
            raise TooManyPlayers
        self._players = [Player() for _ in range(num_players)]
        self.players = cycle(self._players)
        # TODO: roll to see who goes first, then order the players accordingly
        self.start()

    @property
    def active_players(self):
        return [player for player in self._players if not player.bankrupt]

    def start(self):
        while len(self.active_players) > 1 and self.rounds < MAX_ROUNDS:
            current_player = next(self.players)
            if not current_player.bankrupt:
                if self.slow_down:
                    sleep(3)
                print()
                print()
                current_player.take_a_turn()
            while current_player.go_again and not current_player.bankrupt:
                if self.slow_down:
                    sleep(3)
                print()
                print()
                current_player.take_a_turn()
            self.rounds += 1

    def get_rounds_played_per_player(self):
        return self.rounds / len(self._players)

    def end(self):
        for player in self._players:
            del player
