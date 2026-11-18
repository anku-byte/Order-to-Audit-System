"""
Seed command: python manage.py seed

Loads all Section 5 benchmark master data:
- Users (one per role)
- Items (raw materials, packaging, finished goods)
- Unit conversions
- Customers (Retailer A / Distributor B)
- Supplier
- Opening stock movements
- BOM for Murukku 200g
- Price list

Idempotent: safe to run multiple times.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal


class Command(BaseCommand):
    help = "Seed benchmark data from Section 5 of the problem statement"

    def handle(self, *args, **options):
        self.stdout.write("Seeding database...")
        with transaction.atomic():
            self._create_users()
            self._create_items()
            self._create_unit_conversions()
            self._create_customers()
            self._create_supplier()
            self._create_opening_stock()
            self._create_bom()
            self._create_price_list()
        self.stdout.write(self.style.SUCCESS("Seed complete."))

    def _create_users(self):
        from apps.core.models import User
        users = [
            ("admin_user", "admin123", "admin", "Admin User", "admin@factory.local"),
            ("salesman_a", "pass123", "salesman", "Salesman A", "sa@factory.local"),
            ("salesman_b", "pass123", "salesman", "Salesman B", "sb@factory.local"),
            ("production", "pass123", "production", "Production Supervisor", "prod@factory.local"),
            ("accountant", "pass123", "accountant", "Accountant", "acc@factory.local"),
            ("owner", "pass123", "owner", "Owner", "owner@factory.local"),
        ]
        for username, password, role, name, email in users:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                first, *last = name.split(" ", 1)
                user.first_name = first
                user.last_name = last[0] if last else ""
                user.email = email
                user.role = role
                user.is_staff = (role == "admin")
                user.is_superuser = (role == "admin")
                user.save()
                self.stdout.write(f"  Created user: {username} (role={role})")
            else:
                self.stdout.write(f"  User exists: {username}")

    def _create_items(self):
        from apps.inventory.models import Item, ItemCategory
        items = [
            # (name, category, base_unit, hsn_code, gst_rate, reorder_level)
            ("Flour", "raw", "kg", "", Decimal("0.00"), Decimal("20")),
            ("Cooking Oil", "raw", "L", "", Decimal("0.00"), Decimal("10")),
            ("Salt and Spice Mix", "raw", "kg", "", Decimal("0.00"), Decimal("2")),
            ("200g Pouch", "pkg", "piece", "", Decimal("0.00"), Decimal("100")),
            ("Carton", "pkg", "piece", "", Decimal("0.00"), Decimal("10")),
            ("Murukku 200g", "fg", "packet", "2106", Decimal("5.00"), Decimal("20")),
        ]
        for name, category, base_unit, hsn, gst_rate, reorder in items:
            item, created = Item.objects.get_or_create(
                name=name,
                defaults=dict(
                    category=category, base_unit=base_unit,
                    hsn_code=hsn, gst_rate=gst_rate, reorder_level=reorder,
                ),
            )
            self.stdout.write(f"  {'Created' if created else 'Exists'}: Item '{name}'")

    def _create_unit_conversions(self):
        from apps.inventory.models import Item, UnitConversion
        global_conversions = [
            ("kg", "g", Decimal("1000")),
            ("g", "kg", Decimal("0.001")),
            ("L", "mL", Decimal("1000")),
            ("mL", "L", Decimal("0.001")),
        ]
        for from_u, to_u, factor in global_conversions:
            UnitConversion.objects.get_or_create(
                from_unit=from_u, to_unit=to_u, item=None,
                defaults={"factor": factor},
            )

        # Item-specific: 1 carton = 20 packets (for Murukku carton)
        try:
            carton = Item.objects.get(name="Carton")
            UnitConversion.objects.get_or_create(
                from_unit="carton", to_unit="packet", item=carton,
                defaults={"factor": Decimal("20")},
            )
        except Item.DoesNotExist:
            pass
        self.stdout.write("  Unit conversions seeded.")

    def _create_customers(self):
        from apps.sales.models import Customer
        customers = [
            # (name, type, state_code, gstin)
            ("Retailer A", "retailer", "TN", ""),
            ("Distributor B", "distributor", "KA", "29AABCD1234E1Z5"),
        ]
        for name, ctype, state, gstin in customers:
            c, created = Customer.objects.get_or_create(
                name=name,
                defaults=dict(customer_type=ctype, state_code=state, gstin=gstin, is_active=True),
            )
            self.stdout.write(f"  {'Created' if created else 'Exists'}: Customer '{name}'")

    def _create_supplier(self):
        from apps.purchasing.models import Supplier
        s, created = Supplier.objects.get_or_create(
            name="Local Supplies Co.",
            defaults=dict(state_code="TN", is_active=True),
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: Supplier")

    def _create_opening_stock(self):
        """
        Create opening StockMovement rows.
        Only creates if no opening movements exist for each item (idempotent).

        Assumption: Opening FG (Murukku 200g, 50 packets) valued at ₹35/packet (3500 paise).
        This is a reasonable estimate based on the input cost structure.
        """
        from apps.inventory.models import Item, StockMovement
        from apps.core.models import User

        try:
            admin = User.objects.get(username="admin_user")
        except User.DoesNotExist:
            admin = None

        # (item_name, qty, unit_cost_paise)
        opening = [
            ("Flour", Decimal("100"), 4200),          # 100 kg @ ₹42/kg
            ("Cooking Oil", Decimal("30"), 14000),    # 30 L @ ₹140/L
            ("Salt and Spice Mix", Decimal("5"), 20000),  # 5 kg @ ₹200/kg
            ("200g Pouch", Decimal("500"), 250),      # 500 pieces @ ₹2.50
            ("Carton", Decimal("30"), 1500),          # 30 pieces @ ₹15
            ("Murukku 200g", Decimal("50"), 3500),    # 50 packets @ ₹35 (assumption)
        ]
        for item_name, qty, unit_cost in opening:
            item = Item.objects.get(name=item_name)
            exists = StockMovement.objects.filter(item=item, movement_type="opening").exists()
            if not exists:
                StockMovement.objects.create(
                    item=item,
                    movement_type="opening",
                    qty_delta=qty,
                    unit_cost=unit_cost,
                    value=int(qty * unit_cost),
                    created_by=admin,
                    notes=f"Opening stock as per Section 5 benchmark",
                )
                self.stdout.write(f"  Opening stock: {item_name} {qty} @ {unit_cost}p")
            else:
                self.stdout.write(f"  Opening stock exists: {item_name}")

    def _create_bom(self):
        from apps.production.models import BOM, BOMLine
        from apps.inventory.models import Item

        fg = Item.objects.get(name="Murukku 200g")
        bom, created = BOM.objects.get_or_create(
            name="Murukku 200g Standard Batch",
            defaults=dict(product=fg, expected_yield=Decimal("200"), is_active=True),
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: BOM")

        bom_lines = [
            # (item_name, qty_per_batch, unit)
            ("Flour", Decimal("40"), "kg"),
            ("Cooking Oil", Decimal("10"), "L"),
            ("Salt and Spice Mix", Decimal("1.2"), "kg"),
            ("200g Pouch", Decimal("200"), "piece"),
            ("Carton", Decimal("10"), "piece"),
        ]
        for item_name, qty, unit in bom_lines:
            item = Item.objects.get(name=item_name)
            bl, created = BOMLine.objects.get_or_create(
                bom=bom, item=item,
                defaults=dict(qty_per_batch=qty, unit=unit),
            )
            self.stdout.write(f"  {'Created' if created else 'Exists'}: BOMLine {item_name}")

    def _create_price_list(self):
        from apps.sales.models import PriceList, PriceListLine
        from apps.inventory.models import Item
        from datetime import date

        fg = Item.objects.get(name="Murukku 200g")
        pl, created = PriceList.objects.get_or_create(
            name="Standard Price List",
            defaults=dict(effective_from=date.today(), is_active=True),
        )
        PriceListLine.objects.get_or_create(
            price_list=pl, item=fg,
            defaults=dict(unit_price_paise=5000),  # ₹50/packet
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: Price list (Murukku ₹50)")
