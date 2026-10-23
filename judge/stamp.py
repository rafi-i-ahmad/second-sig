"""EIP-712 signing of Stamp with the judge key.

domain: { name: "SecondSig", version: "1", chainId, verifyingContract: <guard address> }
Stamp:  { bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion }
"""
