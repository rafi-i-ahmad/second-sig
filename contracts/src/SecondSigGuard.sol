// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title SecondSigGuard
/// @notice Safe transaction guard that refuses risky transactions without a valid judge stamp.
/// @dev Inherit the base guard from the safe-smart-account tag matching the deployed Safe.
///      Stamp (EIP-712): { bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion }
///      Domain: { name: "SecondSig", version: "1", chainId, verifyingContract: this }
///      The Safe increments its nonce before checkTransaction: recompute the hash with nonce() - 1.
contract SecondSigGuard {
    error SecondSig__NotImplemented();
}
