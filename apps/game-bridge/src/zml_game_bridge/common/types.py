from typing import NewType
# Monetary amounts are stored as integer mPEC to avoid float/Decimal drift.
# 1 PED = 100 PEC = 100000 mPEC
# 1mPEC = 0.001 PEC = 0.00001 PED
# Decay of tool example: 0.123 PEC = 123 mPEC = 0.00123 PED
# Thus, we store amounts in mPEC (milli-PEC) as integers.
# Chat log values are in PED, so convert PED → mpec by multiplying by 100_000.
Mpec = NewType("Mpec", int)
