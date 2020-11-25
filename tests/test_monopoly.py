from monopoly import Bank, NUM_HOUSES, NUM_HOTELS, ALL_MONEY, Property, Player
import pytest


def test_bank_reset():
    Bank.reset()
    assert Bank.NUM_HOTELS == NUM_HOTELS
    assert Bank.NUM_HOUSES == NUM_HOUSES
    assert Bank.money == ALL_MONEY


def test_property_reset():
    Property.reset()
    assert all(p.owner is None for p in Property.instances)


def test_roll_the_dice():
    for i in range(200):
        num, doubles = Player.roll_the_dice()
        assert 2 <= num <= 12
        assert isinstance(doubles, bool)
