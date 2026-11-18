"""
conftest.py – shared pytest fixtures for the Order-to-Audit test suite.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model


@pytest.fixture
def admin_user(db):
    User = get_user_model()
    u, _ = User.objects.get_or_create(username="test_admin", defaults={"role": "admin"})
    u.set_password("pass")
    u.save()
    return u


@pytest.fixture
def flour_item(db):
    from apps.inventory.models import Item
    item, _ = Item.objects.get_or_create(
        name="Test Flour",
        defaults={"category": "raw", "base_unit": "kg",
                  "gst_rate": Decimal("0"), "reorder_level": Decimal("10")},
    )
    return item


@pytest.fixture
def oil_item(db):
    from apps.inventory.models import Item
    item, _ = Item.objects.get_or_create(
        name="Test Oil",
        defaults={"category": "raw", "base_unit": "L",
                  "gst_rate": Decimal("0"), "reorder_level": Decimal("5")},
    )
    return item


@pytest.fixture
def fg_item(db):
    from apps.inventory.models import Item
    item, _ = Item.objects.get_or_create(
        name="Test Murukku 200g",
        defaults={"category": "fg", "base_unit": "packet",
                  "hsn_code": "2106", "gst_rate": Decimal("5.00")},
    )
    return item


@pytest.fixture
def tn_customer(db):
    from apps.sales.models import Customer
    c, _ = Customer.objects.get_or_create(
        name="Test Retailer TN",
        defaults={"customer_type": "retailer", "state_code": "TN"},
    )
    return c


@pytest.fixture
def ka_customer(db):
    from apps.sales.models import Customer
    c, _ = Customer.objects.get_or_create(
        name="Test Distributor KA",
        defaults={"customer_type": "distributor", "state_code": "KA",
                  "gstin": "29AABCD1234E1Z5"},
    )
    return c
