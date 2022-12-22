// SPDX-License-Identifier: MIT

pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import {IERC20Upgradeable} from "@openzeppelin-contracts-upgradeable/token/ERC20/IERC20Upgradeable.sol";
import {MathUpgradeable} from "@openzeppelin-contracts-upgradeable/math/MathUpgradeable.sol";
import {SafeMathUpgradeable} from "@openzeppelin-contracts-upgradeable/math/SafeMathUpgradeable.sol";
import {SafeERC20Upgradeable} from "@openzeppelin-contracts-upgradeable/token/ERC20/SafeERC20Upgradeable.sol";
import {BaseStrategy} from "@badger-finance/BaseStrategy.sol";

import {IVault} from "../interfaces/badger/IVault.sol";
import {IAsset} from "../interfaces/balancer/IAsset.sol";
import {IBalancerVault, JoinKind} from "../interfaces/balancer/IBalancerVault.sol";
import {IBooster} from "../interfaces/aura/IBooster.sol";
import {IAuraToken} from "../interfaces/aura/IAuraToken.sol";
import {IBaseRewardPool} from "../interfaces/aura/IBaseRewardPool.sol";

contract StrategyAuraStaking is BaseStrategy {
    using SafeMathUpgradeable for uint256;
    using SafeERC20Upgradeable for IERC20Upgradeable;

    uint256 public pid;
    IBaseRewardPool public baseRewardPool;

    uint256 public constant REWARD_MULTIPLIER_DENOMINATOR = 10000;

    bool public claimRewardsOnWithdrawAll;
    uint256 public balEthBptToAuraBalMinOutBps;

    IBooster public constant BOOSTER =
        IBooster(0xA57b8d98dAE62B26Ec3bcC4a365338157060B234);

    IVault public constant GRAVIAURA =
        IVault(0xBA485b556399123261a5F9c95d413B4f93107407);
    IVault public constant BAURABAL =
        IVault(0x37d9D2C6035b744849C15F1BFEE8F268a20fCBd8);

    IBalancerVault public constant BALANCER_VAULT =
        IBalancerVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);

    IAuraToken public constant AURA =
        IAuraToken(0xC0c293ce456fF0ED870ADd98a0828Dd4d2903DBF);

    IERC20Upgradeable public constant AURABAL =
        IERC20Upgradeable(0x616e8BfA43F920657B3497DBf40D6b1A02D4608d);
    IERC20Upgradeable public constant WETH =
        IERC20Upgradeable(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20Upgradeable public constant BAL =
        IERC20Upgradeable(0xba100000625a3754423978a60c9317c58a424e3D);
    IERC20Upgradeable public constant BALETH_BPT =
        IERC20Upgradeable(0x5c6Ee304399DBdB9C8Ef030aB642B10820DB8F56);

    bytes32 public constant BAL_ETH_POOL_ID =
        0x5c6ee304399dbdb9c8ef030ab642b10820db8f56000200000000000000000014;
    bytes32 public constant AURABAL_BALETH_BPT_POOL_ID =
        0x3dd0843a028c86e0b760b1a76929d1c5ef93a2dd000200000000000000000249;

    /// @dev Initialize the Strategy with security settings as well as tokens
    /// @notice Proxies will set any non constant variable you declare as default value
    /// @dev add any extra changeable variable at end of initializer as shown
    function initialize(address _vault, uint256 _pid) public initializer {
        __BaseStrategy_init(_vault);

        (address lptoken, , , address crvRewards, , ) = BOOSTER.poolInfo(_pid);
        require(lptoken == IVault(_vault).token(), "token mismatch");

        want = lptoken;
        pid = _pid;

        baseRewardPool = IBaseRewardPool(crvRewards);

        claimRewardsOnWithdrawAll = true;
        balEthBptToAuraBalMinOutBps = 9500; // max 5% slippage

        // Approvals
        IERC20Upgradeable(lptoken).safeApprove(
            address(BOOSTER),
            type(uint256).max
        );

        BAL.safeApprove(address(BALANCER_VAULT), type(uint256).max);
        BALETH_BPT.safeApprove(address(BALANCER_VAULT), type(uint256).max);

        AURABAL.safeApprove(address(BAURABAL), type(uint256).max);
        AURA.approve(address(GRAVIAURA), type(uint256).max);
    }

    function setPid(uint256 _pid) external {
        _onlyGovernance();
        require(balanceOfPool() == 0, "cannot change pid if pending deposits");

        (address lptoken, , , address crvRewards, , ) = BOOSTER.poolInfo(_pid);
        require(lptoken == want, "token mismatch");

        pid = _pid;
        baseRewardPool = IBaseRewardPool(crvRewards);
    }

    function setClaimRewardsOnWithdrawAll(bool _claimRewardsOnWithdrawAll)
        external
    {
        _onlyGovernanceOrStrategist();
        claimRewardsOnWithdrawAll = _claimRewardsOnWithdrawAll;
    }

    function setBalEthBptToAuraBalMinOutBps(uint256 _minOutBps) external {
        _onlyGovernanceOrStrategist();
        require(_minOutBps <= MAX_BPS, "Invalid minOutBps");

        balEthBptToAuraBalMinOutBps = _minOutBps;
    }

    /// @dev Return the name of the strategy
    function getName() external pure override returns (string memory) {
        return "StrategyAuraStaking";
    }

    /// @dev Return a list of protected tokens
    /// @notice It's very important all tokens that are meant to be in the strategy to be marked as protected
    /// @notice this provides security guarantees to the depositors they can't be sweeped away
    function getProtectedTokens()
        public
        view
        virtual
        override
        returns (address[] memory)
    {
        address[] memory protectedTokens = new address[](3);
        protectedTokens[0] = want;
        protectedTokens[1] = address(AURA);
        protectedTokens[2] = address(BAL);
        return protectedTokens;
    }

    /// @dev Deposit `_amount` of want, investing it to earn yield
    function _deposit(uint256 _amount) internal override {
        BOOSTER.deposit(pid, _amount, true);
    }

    /// @dev Withdraw all funds, this is used for migrations, most of the time for emergency reasons
    function _withdrawAll() internal override {
        uint256 poolBalance = balanceOfPool();
        if (poolBalance > 0) {
            baseRewardPool.withdrawAllAndUnwrap(claimRewardsOnWithdrawAll);
        }
    }

    /// @dev Withdraw `_amount` of want, so that it can be sent to the vault / depositor
    /// @notice just unlock the funds and return the amount you could unlock
    function _withdrawSome(uint256 _amount)
        internal
        override
        returns (uint256)
    {
        uint256 wantBalance = balanceOfWant();
        if (_amount > wantBalance) {
            uint256 toWithdraw = _amount.sub(wantBalance);
            baseRewardPool.withdrawAndUnwrap(toWithdraw, false);
        }
        return MathUpgradeable.min(_amount, balanceOfWant());
    }

    /// @dev Does this function require `tend` to be called?
    function _isTendable() internal pure override returns (bool) {
        return false; // Change to true if the strategy should be tended
    }

    function _harvest()
        internal
        override
        returns (TokenAmount[] memory harvested)
    {
        baseRewardPool.getReward();

        // Rewards are handled like this:
        // BAL  --> BAL/ETH BPT --> AURABAL --> B-AURABAL (emitted)
        // AURA --> GRAVIAURA (emitted)
        harvested = new TokenAmount[](2);
        harvested[0].token = address(BAURABAL);
        harvested[1].token = address(GRAVIAURA);

        // BAL --> BAL/ETH BPT --> AURABAL --> B-AURABAL
        uint256 balBalance = BAL.balanceOf(address(this));
        uint256 auraBalEarned;
        if (balBalance > 0) {
            // Deposit BAL --> BAL/ETH BPT
            IAsset[] memory assets = new IAsset[](2);
            assets[0] = IAsset(address(BAL));
            assets[1] = IAsset(address(WETH));
            uint256[] memory maxAmountsIn = new uint256[](2);
            maxAmountsIn[0] = balBalance;
            maxAmountsIn[1] = 0;

            BALANCER_VAULT.joinPool(
                BAL_ETH_POOL_ID,
                address(this),
                address(this),
                IBalancerVault.JoinPoolRequest({
                    assets: assets,
                    maxAmountsIn: maxAmountsIn,
                    userData: abi.encode(
                        JoinKind.EXACT_TOKENS_IN_FOR_BPT_OUT,
                        maxAmountsIn,
                        0 // minOut
                    ),
                    fromInternalBalance: false
                })
            );

            // Swap BAL/ETH BPT --> AURABAL
            uint256 balEthBptBalance = IERC20Upgradeable(BALETH_BPT).balanceOf(
                address(this)
            );

            IBalancerVault.FundManagement memory fundManagement = IBalancerVault
                .FundManagement({
                    sender: address(this),
                    fromInternalBalance: false,
                    recipient: payable(address(this)),
                    toInternalBalance: false
                });
            IBalancerVault.SingleSwap memory singleSwap = IBalancerVault
                .SingleSwap({
                    poolId: AURABAL_BALETH_BPT_POOL_ID,
                    kind: IBalancerVault.SwapKind.GIVEN_IN,
                    assetIn: IAsset(address(BALETH_BPT)),
                    assetOut: IAsset(address(AURABAL)),
                    amount: balEthBptBalance,
                    userData: new bytes(0)
                });
            uint256 minOut = (balEthBptBalance * balEthBptToAuraBalMinOutBps) /
                MAX_BPS;
            auraBalEarned = BALANCER_VAULT.swap(
                singleSwap,
                fundManagement,
                minOut,
                type(uint256).max
            );

            // AURABAL --> B-AURABAL
            BAURABAL.deposit(auraBalEarned);
            uint256 bAuraBalBalance = BAURABAL.balanceOf(address(this));

            harvested[0].amount = bAuraBalBalance;
            _processExtraToken(address(BAURABAL), bAuraBalBalance);
        }

        // AURA --> graviAURA
        uint256 auraBalance = AURA.balanceOf(address(this));
        if (auraBalance > 0) {
            GRAVIAURA.deposit(auraBalance);
            uint256 graviAuraBalance = GRAVIAURA.balanceOf(address(this));

            harvested[1].amount = graviAuraBalance;
            _processExtraToken(address(GRAVIAURA), graviAuraBalance);
        }

        // Report harvest
        _reportToVault(0);
    }

    // Example tend is a no-op which returns the values, could also just revert
    function _tend() internal override returns (TokenAmount[] memory tended) {
        revert("no op");
    }

    /// @dev Return the balance (in want) that the strategy has invested somewhere
    function balanceOfPool() public view override returns (uint256) {
        return baseRewardPool.balanceOf(address(this));
    }

    /// @dev Return the balance of rewards that the strategy has accrued
    /// @notice Used for offChain APY and Harvest Health monitoring
    function balanceOfRewards()
        external
        view
        override
        returns (TokenAmount[] memory rewards)
    {
        uint256 balEarned = baseRewardPool.earned(address(this));

        rewards = new TokenAmount[](2);
        rewards[0] = TokenAmount(address(BAL), balEarned);
        rewards[1] = TokenAmount(
            address(AURA),
            getMintableAuraRewards(balEarned)
        );
    }

    /// @notice Returns the expected amount of AURA to be minted given an amount of BAL rewards
    /// @dev ref: https://etherscan.io/address/0xc0c293ce456ff0ed870add98a0828dd4d2903dbf#code#F1#L86
    function getMintableAuraRewards(uint256 _balAmount)
        public
        view
        returns (uint256 amount)
    {
        uint256 modifiedBalAmount = _getModifiedRewardsFromMultiplier(
            _balAmount
        );
        // NOTE: Only correct if AURA.minterMinted() == 0
        //       minterMinted is a private var in the contract, so we can't access it directly
        uint256 emissionsMinted = AURA.totalSupply() - AURA.INIT_MINT_AMOUNT();

        uint256 cliff = emissionsMinted.div(AURA.reductionPerCliff());
        uint256 totalCliffs = AURA.totalCliffs();

        if (cliff < totalCliffs) {
            uint256 reduction = totalCliffs.sub(cliff).mul(5).div(2).add(700);
            amount = modifiedBalAmount.mul(reduction).div(totalCliffs);

            uint256 amtTillMax = AURA.EMISSIONS_MAX_SUPPLY().sub(
                emissionsMinted
            );
            if (amount > amtTillMax) {
                amount = amtTillMax;
            }
        }
    }

    /// @notice Returns the amount of BAL rewards to be considered for AURA minting based on the resepctive
    ///         rewards pool's multiplier.
    /// @dev ref: https://etherscan.io/address/0xA57b8d98dAE62B26Ec3bcC4a365338157060B234#code#F32#L724
    function _getModifiedRewardsFromMultiplier(uint256 _balAmount)
        internal
        view
        returns (uint256 modifiedBalAmount)
    {
        modifiedBalAmount = _balAmount
            .mul(BOOSTER.getRewardMultipliers(address(baseRewardPool)))
            .div(REWARD_MULTIPLIER_DENOMINATOR);
    }
}
