"""
Management command: python manage.py seed
Loads Section 5 benchmark master data and opening stock.

Assumptions documented here:
- Opening FG cost: ₹35/packet (3500 paise). Rationale: typical cost for a 200g murukku
  packet with similar input prices; this is an assumption for the 50 pre-existing packets.
- Variance tolerance is EXCLUSIVE: abs(variance) > 3% flags. Exactly 3% does NOT flag.
- Seed is idempotent: running twice does not duplicate data (uses get_or_create).
- Opening stock movements are created with created_by=admin user.
"""
import os
import sys

# This file is imported as a module by the management command below.
# The actual logic is in the management command class.
