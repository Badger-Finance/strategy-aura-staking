import pytest
from brownie import (
    StrategyAuraStaking,
    TheVault,
    interface,
    accounts,
    chain
)
from helpers.constants import MaxUint256
from dotmap import DotMap
from rich.console import Console
from pycoingecko import CoinGeckoAPI
from _setup.config import (
    WANT,
    PID,
    WHALE_ADDRESS,
    PERFORMANCE_FEE_GOVERNANCE,
    PERFORMANCE_FEE_STRATEGIST,
    WITHDRAWAL_FEE,
    MANAGEMENT_FEE,
    ON_CHAIN_PRICER,
    GRAVIAURA_WHALE
)
from helpers.time import days

console = Console()


## Accounts ##
@pytest.fixture
def deployer():
    return accounts[0]


@pytest.fixture
def user():
    return accounts[9]


## Fund the account
@pytest.fixture
def want(deployer):
    TOKEN_ADDRESS = WANT
    token = interface.IERC20Detailed(TOKEN_ADDRESS)
    WHALE = accounts.at(WHALE_ADDRESS, force=True)  ## Address with tons of token

    token.transfer(deployer, token.balanceOf(WHALE), {"from": WHALE})
    return token


@pytest.fixture
def strategist():
    return accounts[1]


@pytest.fixture
def keeper():
    return accounts[2]


@pytest.fixture
def guardian():
    return accounts[3]


@pytest.fixture
def governance():
    return accounts[4]


@pytest.fixture
def treasury():
    return accounts[5]


@pytest.fixture
def proxyAdmin():
    return accounts[6]


@pytest.fixture
def randomUser():
    return accounts[7]


@pytest.fixture
def badgerTree():
    return accounts[8]


@pytest.fixture
def deployed(
    want,
    deployer,
    strategist,
    keeper,
    guardian,
    governance,
    proxyAdmin,
    randomUser,
    badgerTree,
):
    """
    Deploys, vault and test strategy, mock token and wires them up.
    """
    want = want

    vault = TheVault.deploy({"from": deployer})
    vault.initialize(
        want,
        governance,
        keeper,
        guardian,
        governance,
        strategist,
        badgerTree,
        "",
        "",
        [
            PERFORMANCE_FEE_GOVERNANCE,
            PERFORMANCE_FEE_STRATEGIST,
            WITHDRAWAL_FEE,
            MANAGEMENT_FEE,
        ],
        {"from": deployer},
    )
    vault.setStrategist(deployer, {"from": governance})
    # NOTE: TheVault starts unpaused

    strategy = StrategyAuraStaking.deploy({"from": deployer})
    strategy.initialize(vault, PID, ON_CHAIN_PRICER)
    # NOTE: Strategy starts unpaused

    vault.setStrategy(strategy, {"from": governance})

    return DotMap(
        deployer=deployer,
        vault=vault,
        strategy=strategy,
        want=want,
        governance=governance,
        proxyAdmin=proxyAdmin,
        randomUser=randomUser,
        performanceFeeGovernance=PERFORMANCE_FEE_GOVERNANCE,
        performanceFeeStrategist=PERFORMANCE_FEE_STRATEGIST,
        withdrawalFee=WITHDRAWAL_FEE,
        managementFee=MANAGEMENT_FEE,
        badgerTree=badgerTree,
    )


## Contracts ##
@pytest.fixture
def vault(deployed):
    return deployed.vault


@pytest.fixture
def strategy(deployed):
    return deployed.strategy


@pytest.fixture
def tokens(deployed):
    return [deployed.want]


### Fees ###
@pytest.fixture
def performanceFeeGovernance(deployed):
    return deployed.performanceFeeGovernance


@pytest.fixture
def performanceFeeStrategist(deployed):
    return deployed.performanceFeeStrategist


@pytest.fixture
def withdrawalFee(deployed):
    return deployed.withdrawalFee


@pytest.fixture
def balancer_vault(deployed):
    return interface.IBalancerVault(deployed.strategy.BALANCER_VAULT())


@pytest.fixture
def graviaura_whale():
    return accounts.at(GRAVIAURA_WHALE, force=True)


@pytest.fixture
def graviaura(deployed):
    return interface.IVault(deployed.strategy.GRAVIAURA())


@pytest.fixture
def weth(deployed):
    return interface.IWETH9(deployed.strategy.WETH())


@pytest.fixture
def pricer(deployed):
    return interface.IOnChainPricing(deployed.strategy.pricer())


@pytest.fixture
def setup_share_math(deployer, vault, want, governance):

    depositAmount = int(want.balanceOf(deployer) * 0.5)
    assert depositAmount > 0
    want.approve(vault.address, MaxUint256, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    vault.earn({"from": governance})

    return DotMap(depositAmount=depositAmount)


@pytest.fixture
def topup_rewards(deployer, strategy):
    booster = interface.IBooster(strategy.BOOSTER())

    def inner():
        booster.earmarkRewards(PID, {"from": deployer})

    return inner


@pytest.fixture
def make_graviaura_pool_profitable(balancer_vault, graviaura_whale, deployed, graviaura, pricer, state_setup):
    strat = deployed.strategy

    (_, aura) = strat.balanceOfRewards()
    aura_amount = aura[1]

    amount_deposit = aura_amount / graviaura.getPricePerFullShare() * 1e18
    swap_quote = pricer.findOptimalSwap(strat.AURA(), strat.GRAVIAURA(), aura_amount)
    assert swap_quote[0] == 6 # Confirm that swap comes from aura -> weth -> graviAura
    amount_swap = swap_quote[1]

    if amount_deposit > amount_swap:
        # Sell graviAURA for WETH to imbalance pool
        deposit_amount = graviaura.balanceOf(graviaura_whale) // 4 ## Can only buy up to 30% of pool
        swap = (strat.AURABAL_GRAVIAURA_WETH_POOL_ID(), 0, graviaura.address, strat.WETH(), deposit_amount, 0)
        fund = (graviaura_whale, False, graviaura_whale, False)
        graviaura.approve(balancer_vault, MaxUint256, {'from': graviaura_whale})
        balancer_vault.swap(swap, fund, 0, MaxUint256, {'from': graviaura_whale})

        swap_quote = pricer.findOptimalSwap(strat.AURA(), strat.GRAVIAURA(), aura_amount)
        assert swap_quote[0] == 6 # Confirm that swap comes from aura -> weth -> graviAura
        assert swap_quote[1] > amount_deposit


@pytest.fixture
def make_graviaura_pool_unprofitable(balancer_vault, deployed, graviaura, weth, user, state_setup):
    strat = deployed.strategy
    # Check if pool is already balanced for graviAURA within 2%
    ids = ["aura-bal", "gravitationally-bound-aura", "weth"]
    prices = CoinGeckoAPI().get_price(ids, "usd")
    balances = balancer_vault.getPoolTokens(strat.AURABAL_GRAVIAURA_WETH_POOL_ID())[1]
    balances_usd = []
    for i, balance in enumerate(balances):
        balances_usd.append(prices[ids[i]]["usd"] * (balance / 1e18))

    # Check if pool is unbalanced for graviAURA (Less graviAURA than wETH in USD terms)
    if balances_usd[1] > balances_usd[2]:
        # Buy graviAURA from WETH to imbalance pool
        deposit_amount_usd = balances_usd[1] - balances_usd[2] * 2
        deposit_amount = int((deposit_amount_usd / prices[ids[2]]["usd"]) * 1e18)
        weth.deposit({"value": deposit_amount, "from": user})
        assert weth.balanceOf(user) == deposit_amount
        swap = (strat.AURABAL_GRAVIAURA_WETH_POOL_ID(), 0, weth.address, graviaura.address, deposit_amount, 0)
        fund = (user.address, False, user.address, False)
        weth.approve(balancer_vault, MaxUint256, {'from': user})
        balancer_vault.swap(swap, fund, 0, MaxUint256, {'from': user})


@pytest.fixture
def state_setup(deployer, vault, want, keeper, topup_rewards):
    startingBalance = want.balanceOf(deployer)
    depositAmount = int(startingBalance * 0.8)
    assert depositAmount > 0

    want.approve(vault, MaxUint256, {"from": deployer})
    vault.deposit(depositAmount, {"from": deployer})

    chain.sleep(days(1))
    chain.mine()

    vault.earn({"from": keeper})

    # Earmark rewards before harvesting
    chain.sleep(days(1))
    topup_rewards()

    chain.sleep(days(1))
    chain.mine()


## Forces reset before each test
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass
