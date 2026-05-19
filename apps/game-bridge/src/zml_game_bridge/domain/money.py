from typing import NewType, cast

# Monetary amounts are stored as integer mPEC to avoid float/Decimal drift.
# 1 PED = 100 PEC = 100000 mPEC
# 1 mPEC = 0.001 PEC = 0.00001 PED
# Tool decay example: 0.123 PEC = 123 mPEC = 0.00123 PED
# Chat log values are in PED, so convert PED to mPEC by multiplying by 100_000.
Mpec = NewType("Mpec", int)


def mpec_to_int(value: Mpec) -> int:
    return cast(int, value)
