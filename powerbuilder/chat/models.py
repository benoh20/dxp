import re

from django.contrib.auth.models import User
from django.db import models


def _slugify_domain(domain: str) -> str:
    """
    Convert an email domain to a safe Pinecone namespace slug.

    Rules:
    - Lowercase
    - Replace any sequence of non-alphanumeric characters with a single underscore
    - Strip leading/trailing underscores
    - Maximum 63 characters (Pinecone namespace limit)

    Examples:
        "ballotready.org"  -> "ballotready_org"
        "my-campaign.com"  -> "my_campaign_com"
        "sub.domain.co.uk" -> "sub_domain_co_uk"
    """
    slug = domain.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:63]


class Organization(models.Model):
    """
    Represents a client organisation in Powerbuilder.

    Each org gets its own isolated Pinecone namespace derived from the
    email domain used at registration.  All agent reads and writes are
    scoped to that namespace so one org can never see another's research.
    """

    name             = models.CharField(max_length=255)
    email_domain     = models.CharField(max_length=255, unique=True, db_index=True)
    pinecone_namespace = models.CharField(max_length=63, unique=True, db_index=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    is_active        = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.email_domain})"

    @classmethod
    def get_or_create_for_domain(cls, domain: str) -> "Organization":
        """
        Return the Organisation for *domain*, creating it if it does not exist.

        The name defaults to the domain until an admin edits it.  The
        pinecone_namespace is derived once at creation time and never
        changes so that existing Pinecone vectors remain reachable.
        """
        namespace = _slugify_domain(domain)
        org, _ = cls.objects.get_or_create(
            email_domain=domain,
            defaults={
                "name":               domain,
                "pinecone_namespace": namespace,
            },
        )
        return org


class UserProfile(models.Model):
    """
    Extends Django's built-in User with org membership.

    The profile is created automatically when a user registers
    (see views.register_view).  One profile per user; one org per profile.
    """

    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        org_name = self.organization.name if self.organization else "no org"
        return f"{self.user.username} @ {org_name}"

    @property
    def pinecone_namespace(self) -> str:
        """
        Convenience accessor used by views and middleware.

        Falls back to 'general' (read-only shared namespace) when the user
        has no org or their org is inactive.
        """
        if self.organization and self.organization.is_active:
            return self.organization.pinecone_namespace
        return "general"
