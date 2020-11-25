"""
from
[here](https://blog.ed.ted.com/2017/12/01/heres-how-to-win-at-monopoly-according-to-math-experts/):
'For every property (apart from the brown set — which, let’s be honest, is basically pointless),
it’s the third house that is really worth investing in quickly. After that, build more if you have
the money, but it’s probably worth waiting a few turns if cash is a bit tight. Since there are a
limited number of houses in the game, building three houses on properties early and then waiting
to upgrade further has the added advantage of potentially blocking the building projects of other
players. Sneaky, huh?'
'utilities are completely pointless.'
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from monopoly import Property, Player


class BuyDecision(ABC):
    @abstractmethod
    def __call__(self, property_: "Property", player: "Player"):
        pass


class BuyEverything(BuyDecision):
    def __call__(self, _, __):
        return True


class BuyIfHaveThreeTimesPrice(BuyDecision):
    def __call__(self, property_: "Property", player: "Player"):
        return player.money >= property_.cost * 3


class BuyIfDontHaveTwoPartialMonopoliesOfOtherColors(BuyDecision):
    def __call__(self, property_: "Property", player: "Player"):
        num_partial_monopolies = 0
        for property_type, properties in player.properties_by_type.items():
            if property_type in ("railroad", "utility"):
                continue
            if len(properties) == 3:
                num_partial_monopolies += 1
            if num_partial_monopolies == 3:
                print(
                    f"{player.name} isn't buying {property_} because "
                    f"they have {num_partial_monopolies} monopolies"
                )
                return False
        return True


class BuyIfOwnFewerThanFivePropertiesOrHaveOneOfThisColor(BuyDecision):
    def __call__(self, property_, player):
        num_properties = len(player.properties)
        if num_properties < 5:
            print(f"{player} wants to buy {property_}")
            return True
        for property_type, properties in player.properties_by_type.items():
            if property_type == property_.type:
                print(f"{player} wants to buy {property_}")
                return True
        print(f"{player} doesn't want to buy {property_}")
        return False


class BuyIfNoOneOwnsTypeAndIsOfTheOneTypeOwned(BuyDecision):
    """
ALGORITHM
---------
If nobody owns this type of property, buy it.
If only one player owns all owned property of this type, buy it.
If this player owns any of this type fo property, buy it.
    """

    def __call__(self, property_, player):
        properties_of_this_type = Property.instances_by_type()[property_.type]
        if not any(p.owner for p in properties_of_this_type):
            return True
        # prevent others from getting monopolies
        if (
            len(set([p.owner for p in Property.instances_by_type()[property_.type]]))
            == 1
        ):
            return True

        players_property_types = player.properties_by_type.keys()
        if player.properties and property_.type in players_property_types:
            return True
        return False
