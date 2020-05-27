"""
Purpose:

1) To simulate games of Monopoly in order to determine the best strategy
2) To play Monopoly on a computer


Along those lines, here's some prior art:

http://www.tkcs-collins.com/truman/monopoly/monopoly.shtml


# TODO: maybe instead of all these classmethods, instances?
# TODO: something more graceful than Game.games[0]
# TODO: store LAST_ROLL in a global constant instead of passing it around to all the `action` methods
"""
from abc import abstractmethod, ABC
from collections import defaultdict
from itertools import cycle
from random import shuffle, choice
from time import sleep
from typing import Type, NewType, Tuple, cast, List

from exceptions import TooManyPlayers, NotEnough, DidntFind, Argument, NoOwner, CantMortgage, \
    CantBuyBuildings, TooMany, MustBeEqualAmounts

Doubles = NewType("Doubles", bool)

LANGUAGE = "français"
BACKUP_LANGUAGE = "English"
BUILDING_TYPES = "house", "hotel"


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
    pass


class Jail(NothingHappensWhenYouLandOnItSpace):
    pass


class FreeParking(NothingHappensWhenYouLandOnItSpace):
    pass


class TaxSpace(Space):
    amount = None

    @classmethod
    def action(cls, player, _):
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
        for other_player in Game.games[0].active_players:
            if other_player != player:
                player.pay(other_player, 50)


class GetOutOfJailFreeCard(Card):
    text = {
        "français": "Vous êtes libéré de prison. Cette carte peut être conservée jusqu'à ce "
        "qu'elle soit utilisée ou vendue. "
    }

    @classmethod
    def action(cls, player: "Player", _):
        player.get_out_of_jail_free_card = True


class AdvanceCard(Card):
    mandatory_action = True
    kwarg = {}

    @classmethod
    def action(cls, player, _):
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
        Bank.pay(player, 150)


class SpeedingCard(Card):
    mandatory_action = True
    text = {"français": "Amende pour excès de vitesse. Payez M15."}

    @classmethod
    def action(cls, player, _):
        player.pay(Bank, 15)


class RepairPropertyCard(Card):
    text = {
        "français": "Vous faites des réparations sur toutes vos propriétés: Versez M25"
        " pour chaque maison M100 pour Chque hôtel que vous possédez"
    }

    @classmethod
    def action(cls, player, _):



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
    if property.cost > player.assets:
        print(f"{player} doesn't have enough to buy {property}.")
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
            return self._name
        return str(self.__class__)

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
                return player.buy(self)
        if self.mortgaged:
            return
        return player.pay(self.owner, self.calculate_rent(last_roll))

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
        return self.rent[self.owner.owns_x_of_type(self)](last_roll)


class Railroad(Property):
    cost = 200
    rent = {1: 25, 2: 50, 3: 100, 4: 200}
    mortgage_cost = 100
    unmortgage_cost = 110
    type = "railroad"

    def calculate_rent(self, _):
        super().calculate_rent(_)
        owns_x_of_type = self.owner.owns_x_of_type(self)
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

    def buy_buildings(self, building_type, quantity=None):
        """
        TODO: Each property within a group must be no more than one house level away from all other
         properties in that group. For example, if you own the Orange group, you can’t put a
         second house on New York Ave until you have a first house on St. James and Tennessee.
         Then you can’t put a third house on any property until you have two houses on
         all properties.
        """
        if not self.owner.owns_all_type(self.type):
            raise CantBuyBuildings
        quantity = quantity or 1

        if building_type == "hotel" and self.buildings["house"] != 4:
            raise NotEnough
        elif building_type == "house" and (self.buildings["house"] + quantity) > 4:
            raise TooMany

        total_buildings = quantity * self.num_of_type
        cost = self.house_and_hotel_cost * total_buildings
        self.owner.check_funds(cost)
        Bank.get_buildings(building_type, total_buildings)
        self.owner.pay(Bank, cost)

        for property_ in self.properties_of_type:
            if building_type == "hotel":
                property_.buildings["house"] = 0
                property_.buildings["hotel"] = 1
            else:
                property_.buildings["house"] += quantity

    def sell_buildings(self, building_type, quantity):
        if not self.buildings[building_type]:
            raise NotEnough
        if quantity % self.num_of_type:
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
        if self.buildings:
            key = self.buildings
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
            _name={"deutsche": "Aarau Rathausplatz"},
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
        Utility(_name="Usines Électriques"),
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
            _name={"italian": "Lugano Via Nassa"},
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
        Railroad(_name="Tramways Interurbains"),
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
        Utility(_name="Usines Hydrauliques"),
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
        Railroad(_name="Association des Télépheriques"),
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
    def __repr__(self):
        return f"<{self.name} money=${self.money}>"


class Bank(EconomicActor):
    name = "Bank"
    money = 20_580
    NUM_HOUSES = 32
    NUM_HOTELS = 12

    @classmethod
    def pay(cls, actor: "EconomicActor", amount: int):
        if isinstance(actor, str):
            actor = eval(actor)
        if amount > cls.money:
            raise NotEnough
        cls.money -= amount
        actor.money += amount

    @classmethod
    def get_buildings(cls, type_, quantity=None):
        cls.check_building_type(type_)
        to_check = cls.get_building_store(type_)
        if type_ == "hotel":
            quantity = 1

        if to_check < quantity:
            raise NotEnough(f"Not enough {type_}s!")
        else:
            to_check -= quantity

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


class Player(EconomicActor):
    in_jail = False
    bankrupt = False
    get_out_of_jail_free_card = False
    go_again = False
    current_space_index = get_space_index("Go")
    money = 0

    def __init__(self, name):
        self.name = name
        Bank.pay(self, 1_500)

    def pay(self, actor: Type["EconomicActor"], amount: int):
        if isinstance(actor, str):
            actor = eval(actor)
        print(actor, amount, self.money)
        self.check_funds(amount)
        print(f"{self} is paying {actor} ${amount}")
        self.money -= amount
        actor.money += amount

    def check_funds(self, amount):
        if amount > self.money:
            raise NotEnough

    def buy(self, property_: "Property", from_=Bank, cost=None):
        try:
            self.pay(from_, cost or property_.cost)
        except NotEnough:
            print(f"{self.name} does not have enough to buy {property_._name}")
            return
        property_.owner = self
        print(f"{self.name} bought {property_._name}")
        sleep(0.2)

    def take_a_turn(self):
        if self.in_jail:
            return GetOutOfJailDecision(self)
        num_spaces, doubles = self.roll_the_dice()
        if doubles:
            self.go_again = True
        else:
            self.go_again = False

        self.advance(num_spaces, just_rolled=True)

    def owns_x_of_type(self, type_):
        properties_of_this_type = self.properties_by_type.get(type_)
        if properties_of_this_type is None:
            return 0
        return len(properties_of_this_type)

    def owns_all_type(self, type_):
        return self.owns_x_of_type(type_) == Property.get_num_of_type(type)

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
            new_space_index = new_space_index - Board.NUM_SPACES
        elif pass_go and self.current_space_index > new_space_index:
            self.money += 200

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
            print(f"{self.name} went bankrupt!")
            self.bankrupt = True

    def do_action_of_current_space(self, last_roll=None):
        space = Board.spaces[self.current_space_index]
        space.action(self, last_roll)

    def go_to_jail(self):
        self.in_jail = True
        self.current_space_index = get_space_index("Jail")


class Game:
    games = []
    rounds = 0

    def __init__(self, *player_names, buy_decision_algorithm=None):
        def return_true(_, __):
            return True

        self.buy_decision_algorithm = buy_decision_algorithm or return_true
        self.games.append(self)
        if len(player_names) > 8:
            raise TooManyPlayers
        self._players = [Player(player_name) for player_name in player_names]
        self.players = cycle(self._players)
        # TODO: roll to see who goes first, then order the players accordingly
        shuffle_decks()
        self.next()

    @property
    def active_players(self):
        return [player for player in self._players if not player.bankrupt]

    def next(self):
        while len(self.active_players) > 1:
            current_player = next(self.players)
            if not current_player.bankrupt:
                current_player.take_a_turn()
            while current_player.go_again:
                current_player.take_a_turn()
            self.rounds += 1
            if self.rounds > 500:
                break
        self.end()

    def end(self):
        print(self.active_players[0], "is the winner!")
        print(f"It took {self.rounds} rounds.")


game = Game("Bot", "Ro", "Francis", buy_decision_algorithm=None)
