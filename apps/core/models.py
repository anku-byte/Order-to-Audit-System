from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class User(AbstractUser):
    class Role(models.TextChoices):
        SALESMAN = "salesman", "Salesman"
        ADMIN = "admin", "Admin"
        PRODUCTION = "production", "Production"
        ACCOUNTANT = "accountant", "Accountant"
        OWNER = "owner", "Owner"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SALESMAN)
    phone = models.CharField(max_length=20, blank=True)

    @property
    def is_salesman(self): return self.role == self.Role.SALESMAN
    @property
    def is_admin_role(self): return self.role == self.Role.ADMIN
    @property
    def is_production(self): return self.role == self.Role.PRODUCTION
    @property
    def is_accountant(self): return self.role == self.Role.ACCOUNTANT
    @property
    def is_owner(self): return self.role == self.Role.OWNER

    def can_approve_orders(self):
        return self.role in (self.Role.ADMIN, self.Role.OWNER)

    def can_view_reports(self):
        return self.role in (self.Role.ADMIN, self.Role.ACCOUNTANT, self.Role.OWNER)


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        CANCEL = "cancel", "Cancel"
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        POST = "post", "Post"

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=20, choices=Action.choices)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.action} {self.content_type} #{self.object_id} at {self.timestamp}"
