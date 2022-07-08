from brownie import *
from helpers.constants import MaxUint256


def test_are_you_trying(deployer, vault, strategy, want, governance, topup_rewards):
    """
    Verifies that you set up the Strategy properly
    """
    # Setup
    startingBalance = want.balanceOf(deployer)
    depositAmount = startingBalance // 2

    assert depositAmount >= 0
    # End Setup

    # Deposit
    assert want.balanceOf(vault) == 0

    want.approve(vault, MaxUint256, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    available = vault.available()
    assert available > 0

    vault.earn({"from": governance})

    chain.sleep(10000 * 13)  # Mine so we get some interest
    topup_rewards()

    ## TEST 1: Does the want get used in any way?
    assert want.balanceOf(vault) == depositAmount - available

    # Did the strategy do something with the asset?
    assert want.balanceOf(strategy) < available

    # Use this if it should invest all
    assert want.balanceOf(strategy) == 0

    ## TEST 2: Is the Harvest profitable?
    harvest = strategy.harvest({"from": governance})
    event = harvest.events["Harvested"]
    assert event["amount"] == 0

    ## TEST 3: Does the strategy emit anything?
    events = harvest.events["TreeDistribution"]

    assert len(events) == 2
    assert events[0]["token"] == strategy.BAURABAL()
    assert events[0]["amount"] > 0

    assert events[1]["token"] == strategy.GRAVIAURA()
    assert events[1]["amount"] > 0
