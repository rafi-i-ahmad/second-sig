// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Enum} from "safe-contracts/common/Enum.sol";
import {SecondSigTest} from "./Base.t.sol";

/// A broken guard can freeze a Safe. These check the guard can always be removed by a
/// legitimate path, and never by an illegitimate one.
contract BrickingTest is SecondSigTest {
    function _removeGuardData() internal view returns (bytes memory) {
        return abi.encodeCall(safe.setGuard, (address(0)));
    }

    function _guardSlot() internal view returns (address) {
        return address(uint160(uint256(vm.load(address(safe), GUARD_SLOT))));
    }

    /// An attacker's first move would be removing the guard.
    function test_removeGuardWithoutStampReverts() public {
        bytes32 h = _hash(address(safe), 0, _removeGuardData(), Enum.Operation.Call);
        _execReverts(address(safe), 0, _removeGuardData(), Enum.Operation.Call, _noStamp(h));
        assertEq(_guardSlot(), address(guard));
    }

    function test_removeGuardWithStampWorks() public {
        _attest(address(safe), 0, _removeGuardData(), Enum.Operation.Call);
        _exec(address(safe), 0, _removeGuardData(), Enum.Operation.Call);
        assertEq(_guardSlot(), address(0));
        // and the Safe runs normally afterwards
        address bob = makeAddr("bob");
        assertTrue(_exec(bob, 1 ether, "", Enum.Operation.Call));
    }

    /// Dead judge: every owner approves removing the guard, waits out the delay, and the Safe is free.
    function test_deadJudgeOverrideRemovesGuard() public {
        bytes32 h = _hash(address(safe), 0, _removeGuardData(), Enum.Operation.Call);
        _approveOverrideByAll(h);
        vm.roll(block.number + OVERRIDE_DELAY);
        _exec(address(safe), 0, _removeGuardData(), Enum.Operation.Call);
        assertEq(_guardSlot(), address(0));
    }

    function test_swapToNewGuardNeedsStamp() public {
        bytes memory data = abi.encodeCall(safe.setGuard, (makeAddr("evil-guard")));
        bytes32 h = _hash(address(safe), 0, data, Enum.Operation.Call);
        _execReverts(address(safe), 0, data, Enum.Operation.Call, _noStamp(h));
    }

    /// Owner changes go through the guard too, and the override quorum follows the current owners.
    function test_addedOwnerJoinsOverrideQuorum() public {
        address dana = makeAddr("dana");
        bytes memory add = abi.encodeCall(safe.addOwnerWithThreshold, (dana, 2));
        _attest(address(safe), 0, add, Enum.Operation.Call);
        _exec(address(safe), 0, add, Enum.Operation.Call);
        assertTrue(safe.isOwner(dana));

        bytes32 h = _hash(address(safe), 0, _removeGuardData(), Enum.Operation.Call);
        _approveOverrideByAll(h); // the three original owners
        assertEq(guard.overrideReadyAt(h), 0);
        vm.prank(dana);
        guard.approveOverride(h);
        assertEq(guard.overrideReadyAt(h), block.number + OVERRIDE_DELAY);
    }

    function test_addOwnerWithoutStampReverts() public {
        bytes memory add = abi.encodeCall(safe.addOwnerWithThreshold, (makeAddr("mallory"), 1));
        bytes32 h = _hash(address(safe), 0, add, Enum.Operation.Call);
        _execReverts(address(safe), 0, add, Enum.Operation.Call, _noStamp(h));
    }

    /// Reads never touch the guard.
    function test_viewsStillWork() public view {
        assertEq(safe.getThreshold(), 2);
        assertEq(safe.getOwners().length, 3);
    }
}
