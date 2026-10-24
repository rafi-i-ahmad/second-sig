// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Enum} from "safe-contracts/common/Enum.sol";
import {SecondSigGuard} from "../src/SecondSigGuard.sol";
import {SecondSigTest} from "./Base.t.sol";

contract OverrideTest is SecondSigTest {
    address internal constant BOB = address(0xB0B);

    function test_allOwnersPlusDelayExecutesWithoutStamp() public {
        bytes32 h = _hash(BOB, 1 ether, "", Enum.Operation.Call);
        _approveOverrideByAll(h);
        vm.roll(block.number + OVERRIDE_DELAY);
        vm.expectEmit(address(guard));
        emit SecondSigGuard.OverrideExecuted(h);
        assertTrue(_exec(BOB, 1 ether, "", Enum.Operation.Call));
        assertEq(BOB.balance, 1 ether);
    }

    function test_beforeDelayReverts() public {
        bytes32 h = _hash(BOB, 1 ether, "", Enum.Operation.Call);
        _approveOverrideByAll(h);
        uint256 readyAt = block.number + OVERRIDE_DELAY;
        vm.roll(readyAt - 1);
        _execReverts(
            BOB,
            1 ether,
            "",
            Enum.Operation.Call,
            abi.encodeWithSelector(SecondSigGuard.SecondSig__OverrideNotReady.selector, h, readyAt)
        );
    }

    function test_thresholdApprovalsAreNotEnough() public {
        bytes32 h = _hash(BOB, 1 ether, "", Enum.Operation.Call);
        for (uint256 i; i < 2; ++i) {
            vm.prank(owners[i]);
            guard.approveOverride(h);
        }
        assertEq(guard.overrideReadyAt(h), 0);
        vm.roll(block.number + OVERRIDE_DELAY + 1);
        _execReverts(BOB, 1 ether, "", Enum.Operation.Call, _noStamp(h));
    }

    function test_repeatApprovalByOneOwnerDoesNotCount() public {
        bytes32 h = _hash(BOB, 1 ether, "", Enum.Operation.Call);
        for (uint256 i; i < 3; ++i) {
            vm.prank(owners[0]);
            guard.approveOverride(h);
        }
        assertEq(guard.overrideReadyAt(h), 0);
    }

    function test_nonOwnerCannotApprove() public {
        address mallory = makeAddr("mallory");
        vm.prank(mallory);
        vm.expectRevert(abi.encodeWithSelector(SecondSigGuard.SecondSig__NotOwner.selector, mallory));
        guard.approveOverride(bytes32(uint256(1)));
    }

    function test_judgeCannotApprove() public {
        vm.prank(judge);
        vm.expectRevert(abi.encodeWithSelector(SecondSigGuard.SecondSig__NotOwner.selector, judge));
        guard.approveOverride(bytes32(uint256(1)));
    }

    function test_overrideIsPerHash() public {
        _approveOverrideByAll(_hash(BOB, 1 ether, "", Enum.Operation.Call));
        vm.roll(block.number + OVERRIDE_DELAY);
        bytes32 other = _hash(BOB, 2 ether, "", Enum.Operation.Call);
        _execReverts(BOB, 2 ether, "", Enum.Operation.Call, _noStamp(other));
    }

    function test_eventsForEachApprovalAndReadiness() public {
        bytes32 h = _hash(BOB, 1 ether, "", Enum.Operation.Call);
        for (uint256 i; i < owners.length; ++i) {
            vm.expectEmit(address(guard));
            emit SecondSigGuard.OverrideApproved(h, owners[i]);
            if (i == owners.length - 1) {
                vm.expectEmit(address(guard));
                emit SecondSigGuard.OverrideReady(h, block.number + OVERRIDE_DELAY);
            }
            vm.prank(owners[i]);
            guard.approveOverride(h);
        }
    }

    function test_zeroDelayRejectedAtDeploy() public {
        vm.expectRevert(SecondSigGuard.SecondSig__ZeroOverrideDelay.selector);
        new SecondSigGuard(address(safe), judge, JUDGE_VERSION, 0);
    }
}
