"""
App `inventory` — Catalogue (étape 1 du plan de construction).

Modèles : Category, Product, ProductBarcode, ProductVariant, MediaAsset,
ProductContent. Le produit minimal suffit à vendre et stocker ; les couches
riches (médias, contenu e-commerce, variantes) sont optionnelles.
"""
from django.db import models

from kenpro_store.db import AuthoredModel, TenantOwnedModel


class Category(TenantOwnedModel):
    """Catégorie, hiérarchique (arbre via parent self-référent)."""
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.name


class Product(TenantOwnedModel):
    """
    Le produit — catalogue minimal, suffisant pour vendre et stocker.
    Tout produit a une identité interne (UUID + SKU), même sans code-barres.
    """
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    STATUS_CHOICES = [
        (DRAFT, "Brouillon"),
        (ACTIVE, "Actif"),
        (ARCHIVED, "Archivé"),
    ]

    # SKU auto-généré, unique par tenant (cf. save()).
    sku = models.CharField(max_length=32, blank=True)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    base_unit = models.CharField(max_length=32, default="unité")
    # Prix plancher : le vendeur ne descend jamais en dessous (sauf promo/admin).
    floor_price = models.DecimalField(max_digits=14, decimal_places=2)
    # Coût d'achat / PMP — sert au calcul de la marge.
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Prix de vente grand public (détail).
    retail_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Prix accordé aux petits revendeurs informels.
    reseller_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Prix accordé aux grossistes (volumes importants).
    wholesale_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Prix déclaré aux autorités fiscales (DGI, douane…).
    public_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    is_published_online = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], name="unique_sku_per_tenant"),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}" if self.sku else self.name

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self) -> str:
        """
        SKU séquentiel par tenant : KP-000001, KP-000002…
        Le plancher applicatif est doublé par la contrainte d'unicité en base.
        """
        last = (
            Product.objects.filter(tenant=self.tenant, sku__startswith="KP-")
            .order_by("-sku")
            .values_list("sku", flat=True)
            .first()
        )
        next_num = (int(last.split("-")[1]) + 1) if last else 1
        return f"KP-{next_num:06d}"


class ProductBarcode(TenantOwnedModel):
    """Code(s)-barres — 0 à N par produit. Un produit sans code reste vendable."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="barcodes")
    code = models.CharField(max_length=64)
    is_primary = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Code-barres"
        verbose_name_plural = "Codes-barres"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_barcode_per_tenant"),
        ]

    def __str__(self):
        return self.code


class ProductVariant(TenantOwnedModel):
    """Variante (taille, couleur…) — optionnel. Plancher surchargeable."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=255)
    attributes = models.JSONField(default=dict, blank=True)
    sku = models.CharField(max_length=32, blank=True)
    # Override optionnel du plancher du produit parent.
    floor_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Variante"
        verbose_name_plural = "Variantes"

    def __str__(self):
        return f"{self.product.name} / {self.name}"

    @property
    def effective_floor_price(self):
        """Plancher de la variante, à défaut celui du produit parent."""
        return self.floor_price if self.floor_price is not None else self.product.floor_price


class MediaAsset(TenantOwnedModel):
    """
    Médiathèque : images et vidéos du produit. Les fichiers vont dans un
    object storage (type S3) ; la base ne garde que les références (url).
    """
    IMAGE = "image"
    VIDEO = "video"
    TYPE_CHOICES = [(IMAGE, "Image"), (VIDEO, "Vidéo")]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="media")
    type = models.CharField(max_length=8, choices=TYPE_CHOICES, default=IMAGE)
    url = models.URLField(max_length=1024)
    order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Média"
        verbose_name_plural = "Médias"
        ordering = ["order"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.product.name}"


class ProductContent(TenantOwnedModel):
    """
    Contenu riche e-commerce — couche optionnelle, 1:1 avec Product.
    Permet de préparer les futurs produits (brouillon) avant publication.
    """
    DRAFT = "draft"
    PUBLISHED = "published"
    ONLINE_STATUS_CHOICES = [(DRAFT, "Brouillon"), (PUBLISHED, "Publié")]

    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="content")
    long_description = models.TextField(blank=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.CharField(max_length=512, blank=True)
    online_status = models.CharField(max_length=16, choices=ONLINE_STATUS_CHOICES, default=DRAFT)

    class Meta:
        verbose_name = "Contenu produit"
        verbose_name_plural = "Contenus produit"

    def __str__(self):
        return f"Contenu — {self.product.name}"


# ---------------------------------------------------------------------------
# Emplacements & niveaux de stock
# ---------------------------------------------------------------------------

class Location(TenantOwnedModel):
    """Emplacement de stock : boutique, entrepôt, stand de marché."""
    SHOP = "shop"
    WAREHOUSE = "warehouse"
    STALL = "stall"
    TYPE_CHOICES = [
        (SHOP, "Boutique"),
        (WAREHOUSE, "Entrepôt"),
        (STALL, "Stand de marché"),
    ]

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=SHOP)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Emplacement"
        verbose_name_plural = "Emplacements"

    def __str__(self):
        return self.name


class StockLevel(TenantOwnedModel):
    """
    Solde de stock par produit × (variante) × emplacement.
    `quantity` est un CACHE dérivé de la somme des StockMovement — il n'est
    jamais écrit en direct par l'application métier, seulement recalculé par
    le stock ledger (cf. inventory.services.StockLedger).
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_levels")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True,
        on_delete=models.CASCADE, related_name="stock_levels",
    )
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="stock_levels")
    quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    reorder_threshold = models.DecimalField(max_digits=16, decimal_places=3, default=0)

    class Meta:
        verbose_name = "Niveau de stock"
        verbose_name_plural = "Niveaux de stock"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant", "location"],
                name="unique_stock_level",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} @ {self.location.name} = {self.quantity}"


class UnitConversion(TenantOwnedModel):
    """
    Conversion gros ↔ détail (ex. 1 carton = 12 unités).
    Acheter en carton, vendre à l'unité.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="unit_conversions")
    from_unit = models.CharField(max_length=32)
    to_unit = models.CharField(max_length=32)
    factor = models.DecimalField(max_digits=16, decimal_places=4)

    class Meta:
        verbose_name = "Conversion d'unité"
        verbose_name_plural = "Conversions d'unité"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "from_unit", "to_unit"],
                name="unique_unit_conversion",
            ),
        ]

    def __str__(self):
        return f"{self.from_unit} → {self.to_unit} (×{self.factor})"


# ---------------------------------------------------------------------------
# Mouvements de stock — source de vérité, append-only
# ---------------------------------------------------------------------------

class StockMovement(TenantOwnedModel, AuthoredModel):
    """
    Chaque entrée, sortie, transfert ou ajustement de stock. Immuable : on
    n'édite ni ne supprime le passé — on empile une écriture de correction.
    Le StockLevel se déduit de la somme des mouvements.

    `client_uuid` évite les doublons quand un stand au marché synchronise
    après une coupure réseau (réconciliation offline).
    """
    IN = "in"
    OUT = "out"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    LOSS = "loss"
    TYPE_CHOICES = [
        (IN, "Entrée"),
        (OUT, "Sortie"),
        (TRANSFER, "Transfert"),
        (ADJUSTMENT, "Ajustement"),
        (LOSS, "Perte / casse"),
    ]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True,
        on_delete=models.PROTECT, related_name="movements",
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    # Quantité signée selon le sens du mouvement (cf. signed_quantity).
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    unit = models.CharField(max_length=32, default="unité")
    reason = models.CharField(max_length=255, blank=True)
    # Lien libre vers l'origine : vente, réception, comptage…
    reference = models.CharField(max_length=255, blank=True)
    # Identifiant client pour la réconciliation offline (unique par tenant).
    client_uuid = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_uuid"],
                name="unique_movement_client_uuid",
                condition=models.Q(client_uuid__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} {self.signed_quantity} {self.unit} — {self.product.name}"

    @property
    def signed_quantity(self):
        """
        Quantité orientée : négative pour une sortie, positive sinon.
        Un ajustement porte déjà son signe dans `quantity`.
        """
        if self.type == self.OUT:
            return -abs(self.quantity)
        if self.type in (self.IN,):
            return abs(self.quantity)
        if self.type == self.LOSS:
            return -abs(self.quantity)
        # transfer / adjustment : la valeur signée est portée telle quelle.
        return self.quantity
