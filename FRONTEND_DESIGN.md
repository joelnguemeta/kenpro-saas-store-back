# Kenpro Store — Frontend Design Brief (complet)

## Contexte du projet

**Kenpro Store** est une application SaaS multi-tenant de gestion de boutique/point de vente (POS) destinée au marché africain francophone (Cameroun, Sénégal, Côte d'Ivoire…).

- Chaque boutique = un **tenant** isolé (ses propres produits, clients, ventes, équipe)
- L'accès se fait par **téléphone (format E.164, ex: +237…)** + mot de passe ou OTP
- Les vendeurs travaillent sur **tablette ou smartphone en boutique**
- Plusieurs **emplacements physiques** par tenant : boutique, entrepôt, stand de marché
- Paiement mixte : espèces + Mobile Money (MTN MoMo, Orange Money, Wave)

L'application est entièrement pilotée par une **API REST Django** (JWT auth).

---

## Stack technique attendu

- **Framework** : React + Next.js (App Router)
- **UI** : Tailwind CSS + shadcn/ui
- **État serveur** : TanStack Query (React Query)
- **État client** : Zustand
- **Auth** : JWT — `Authorization: Bearer <access_token>`
- **Langue** : Français intégral (labels, messages, dates)
- **Priorité responsive** : tablette 10" paysage pour la caisse, smartphone portrait pour le reste

---

## Rôles utilisateurs

| Rôle | Description | Modules |
|------|-------------|---------|
| **Super Admin Kenpro** (`is_staff=true`) | Gère la plateforme entière | Back-office admin uniquement |
| **Admin boutique** | Propriétaire/gérant d'une boutique | Tout sauf back-office plateforme |
| **Vendeur / Caissier** | Vend au comptoir | Caisse POS, consultation stock, clients |
| **Technicien** | Répare les appareils | Module réparation uniquement |

---

## Modules et écrans détaillés

---

### 1. Authentification (`/auth`)

#### Écrans
- **Login** : champ téléphone (`+237…`) + mot de passe. Lien "Mot de passe oublié".
- **Mot de passe oublié** : saisie email → message de confirmation générique (l'API ne révèle pas si l'email existe).
- **Réinitialisation** : saisie du code reçu par email + nouveau mot de passe (min 8 caractères).
- **Inscription** : téléphone (obligatoire), nom complet, email, mot de passe (optionnel — auth principale par OTP).
- **Saisie PIN** : overlay/modal avec clavier numérique 4×3, demandé avant toute action sensible (suppression remise, export…). Le PIN est par membership (utilisateur × boutique), pas par compte global.

#### Règles UI
- Le champ téléphone doit accepter le format E.164 avec indicatif pays (sélecteur drapeau + code)
- Après 5 tentatives de PIN incorrectes → verrouillage 15 minutes, message "Trop de tentatives"

---

### 2. Back-office Super Admin (`/admin`)

> Réservé aux comptes `is_staff = true`. Inaccessible aux utilisateurs boutique.

#### Écrans
- **Dashboard plateforme** : nombre de tenants actifs, abonnements par statut (essai/actif/suspendu), services activés
- **Tenants** : liste (nom, pays, devise, statut actif) + création + détail
- **Plans tarifaires** : liste + création (nom, prix mensuel, description)
- **Abonnements** :
  - Liste filtrée par statut (`trial` / `active` / `suspended`)
  - Actions : Démarrer essai, Activer, Suspendre, Prolonger essai (+N jours)
  - Badge coloré par statut
- **Services métier** : activer/désactiver par tenant les modules (inventory, repair, mobilemoney…). Toggle par service.
- **Utilisateurs** : liste globale, création, consultation
- **Rôles** : liste des rôles système globaux

---

### 3. Tableau de bord boutique (`/`)

Affiché après sélection du tenant (si l'utilisateur a plusieurs memberships).

#### Widgets
- Chiffre d'affaires du jour (somme des ventes validées)
- Nombre de ventes aujourd'hui
- Alertes stock (produits sous seuil `reorder_threshold`) — badge rouge
- Tickets de réparation en cours (statuts actifs)
- Dernières ventes (5 lignes)
- Solde de dettes clients total

---

### 4. Caisse POS (`/caisse`)

> Écran principal des vendeurs. Optimisé tablette paysage.

#### Flux complet
1. **Recherche produit** : scan code-barres (caméra ou scanner USB) OU recherche textuelle (nom, SKU)
2. **Panier** : liste des lignes avec quantité, prix catalogue, prix final éditable
   - Prix final ne peut pas descendre sous le `floor_price` → erreur visuelle
   - Remise sur ligne : saisie montant → demande confirmation PIN si le modèle est dans un `PinScope`
3. **Client** : sélection client existant (recherche par nom/téléphone) OU création rapide (téléphone seulement → `is_express=true`) OU vente anonyme
4. **Validation** : bouton "Encaisser" → modal de paiement
5. **Paiement** :
   - Choix du/des mode(s) : Espèces / MTN MoMo / Orange Money / Wave / Carte / Crédit client / Acompte
   - Paiement mixte : saisir montant par mode, total restant calculé en temps réel
   - Mobile Money : saisie numéro payeur → initiation transaction → attente confirmation opérateur (statuts: initié → en attente → confirmé / échoué)
   - Crédit client : augmente la dette du client (`DebtMovement` type `sale`)
6. **Reçu** : affichage numéro de ticket (ex. TICK-000001) → bouton impression thermique (58mm/80mm) OU partage WhatsApp

#### Règles métier importantes
- Une vente validée est **immuable** — pour corriger : créer un Avoir
- Sélection de l'emplacement de déstockage (liste des `Location` du tenant)
- Canal de vente : `pos` par défaut (autres : whatsapp, online, marketplace)
- Prix appliqué selon le `pricing_tier` du client (retail/reseller/wholesale)

---

### 5. Historique des ventes (`/ventes`)

- Liste des ventes avec filtres : date, statut (draft/validated/cancelled), vendeur, canal, client
- Détail d'une vente : lignes, paiements, avoirs liés
- Statut affiché avec badge coloré
- Action "Créer un avoir" sur une vente validée

#### Avoirs (`/ventes/avoirs`)
- Liste des avoirs (référence AV-XXXXXX, date, montant, motif)
- Création d'un avoir : sélectionner la vente → choisir les lignes à retourner → quantité retournée → motif (demande client / défectueux / mauvais article / erreur de prix / autre)
- Un avoir remet en stock les articles et annule la dette client si la vente était à crédit

---

### 6. Inventaire — Catalogue (`/inventaire/produits`)

#### Produits
- **Liste** : grille ou tableau, filtres par catégorie/statut (draft/active/archived), recherche
- **Fiche produit** :
  - Identité : SKU (auto KP-000001), nom, catégorie, unité de base, statut
  - **5 niveaux de prix** :
    - Prix plancher (`floor_price`) — plancher absolu, vendeur ne peut descendre dessous
    - Prix détail (`retail_price`) — grand public
    - Prix revendeur (`reseller_price`) — petits revendeurs informels
    - Prix grossiste (`wholesale_price`) — gros volumes
    - Prix public (`public_price`) — déclaré aux autorités fiscales
    - Coût d'achat (`cost`) — pour calcul de marge
  - Codes-barres (0 à N par produit, un primaire)
  - Variantes (taille, couleur…) — chacune peut surcharger le prix plancher
  - Médias (images, vidéos) — URL vers object storage
  - Contenu e-commerce (description longue, SEO) — optionnel
  - Conversions d'unité (ex. 1 carton = 12 unités)
- **Création** : formulaire multi-étapes (identité → prix → codes-barres → variantes → médias)
- **Publication en ligne** : toggle `is_published_online`

#### Catégories
- Arbre hiérarchique (parent auto-référent)
- Vue arbre avec expand/collapse
- Création/édition inline

---

### 7. Inventaire — Stock (`/inventaire/stock`)

#### Niveaux de stock
- Tableau : produit × emplacement × quantité × seuil de réapprovisionnement
- Filtre par emplacement (boutique / entrepôt / stand)
- Indicateur couleur : vert (OK) / orange (proche seuil) / rouge (sous seuil ou rupture)

#### Mouvements de stock (`/inventaire/mouvements`)
- Journal append-only — aucune modification possible
- Types : Entrée / Sortie / Transfert / Ajustement / Perte-casse
- Filtres : type, produit, emplacement, date, auteur
- Champ `client_uuid` : idempotence pour réconciliation offline (le frontend génère un UUID avant d'envoyer)

#### Alertes stock (`/inventaire/alertes`)
- Liste des produits sous seuil `reorder_threshold` par emplacement
- Configuration alerte WhatsApp : numéro destinataire, heure d'envoi (08h/12h/18h), nombre minimum d'alertes avant envoi

#### Emplacements (`/inventaire/emplacements`)
- Liste : nom, type (boutique/entrepôt/stand), emplacement par défaut
- Création/édition

---

### 8. Clients CRM (`/clients`)

#### Liste
- Recherche par nom, téléphone
- Filtre par type (particulier/entreprise), niveau de confiance (nouveau/fiable/à risque), segment tarifaire
- Badge dette affichée si `debt_balance > 0`

#### Fiche client
- Coordonnées : nom/raison sociale, téléphone, email, NIU (B2B)
- Type : Particulier / Entreprise
- Segment tarifaire : **Détail** / **Petit revendeur** / **Grossiste** (détermine le prix par défaut à la caisse)
- Niveau de confiance : Nouveau / Fiable / À risque (badge coloré)
- Notes libres
- Solde de dette : montant + historique des mouvements (ventes à crédit, remboursements, ajustements)
- Historique des ventes du client
- Appareils confiés (si module réparation actif)

#### Mouvements de dette
- Liste append-only : type (vente à crédit / remboursement / ajustement), montant, référence, note
- Saisie d'un remboursement / ajustement manuel

---

### 9. Fournisseurs (`/fournisseurs`)

#### Fournisseurs globaux
- Liste (nom, téléphone, email)
- Création/édition — réservé aux admins
- Lier un fournisseur à la boutique avec plafond de crédit

#### Crédit fournisseur (`/fournisseurs/credit`)
- **Relevés** : liste par fournisseur (statut open/settled, solde courant)
- **Détail relevé** : écritures (append-only : débit/avoir/ajustement) + paiements
- **Écritures** : création (type + montant) — immuable après création
- **Paiements** :
  - Déclaration : montant + moyen (espèces/MTN/Orange)
  - Confirmation : passe de `declared` à `confirmed`
  - Un paiement confirmé ne peut pas être supprimé

---

### 10. Module Réparation (`/reparation`)

> Module activable par tenant via ServiceFlag.

#### Appareils (`/reparation/appareils`)
- Liste filtrée par type (téléphone/laptop/tablette/autre)
- Recherche par IMEI/série, marque, client
- Fiche appareil : marque, modèle, IMEI/série, client associé, historique des tickets

#### Tickets (`/reparation/tickets`)

**Vue kanban** (par défaut) OU vue liste, colonnes = statuts :

```
Reçu → Diagnostiqué → Devis envoyé → Devis approuvé → En cours → Testé → Prêt → Restitué
                                    ↘ Devis refusé → Rendu
                  ↘ Annulé
```

- Filtres : statut, technicien assigné, emplacement/atelier, date
- **Carte ticket** : appareil, client, technicien, panne déclarée, statut, date réception

**Détail ticket** :
- Appareil + client
- Panne déclarée
- Technicien assigné (liste des membres du tenant avec membership actif)
- Historique des statuts (append-only, avec auteur et note)
- Bouton de transition vers statut suivant (selon graphe autorisé)
- Note de transition (libre)

**Créer un ticket** : sélection appareil (existant ou nouveau) + client + panne déclarée + emplacement/atelier + date de réception

---

### 11. Mobile Money (`/mobile-money`)

- Liste des transactions MoMo liées aux ventes
- Filtres : opérateur (MTN/Orange/Wave), statut (initiée/en attente/confirmée/échouée), date
- Détail : opérateur, numéro payeur, montant, devise, référence, ID externe opérateur, raison d'échec
- Badge statut coloré : gris (initiée) / jaune (en attente) / vert (confirmée) / rouge (échouée)

---

### 12. Équipe & Accès (`/equipe`)

- **Membres** : liste (utilisateur, rôle, membership actif/expiré, a un PIN configuré)
- **Inviter un membre** : créer un membership (utilisateur existant + rôle + date d'expiration optionnelle)
- **Gestion PIN** : définir / supprimer le PIN d'un membre (son propre PIN uniquement, ou admin)
- **Périmètres PIN** (`/equipe/pin-scopes`) : choisir quels types d'objets nécessitent un PIN (ex. "Suppression de remise", "Export clients")
- **Rôles boutique** : liste, création, attribution de permissions Django

---

### 13. Paramètres boutique (`/parametres`)

- **Informations** : nom, slug, pays, devise
- **Emplacements** : gérer boutiques/entrepôts/stands
- **Alertes stock WhatsApp** : numéro, heure d'envoi, seuil minimum
- **Abonnement** : plan actuel, dates, statut

---

## Modèles de données clés à connaître

### Prix produit (5 niveaux)
```
floor_price    → plancher absolu (jamais dépassable à la baisse)
retail_price   → prix détail (grand public)
reseller_price → prix revendeur
wholesale_price → prix grossiste
public_price   → prix fiscal
cost           → coût d'achat (marge)
```
Le prix proposé à la caisse dépend du `pricing_tier` du client sélectionné.

### Cycle de vie d'une vente
```
draft → validated (immuable, ticket émis)
      → cancelled
```
Pour corriger une vente validée : **Avoir (CreditNote)**.

### Cycle de vie d'un ticket réparation
```
received → diagnosed → quote_sent → approved → in_progress → tested → ready → delivered
                                  ↘ rejected → returned
         ↘ cancelled
         ↘ returned (depuis received ou diagnosed)
```

### Mouvements de stock — types
```
in          → Entrée (réception marchandise)
out         → Sortie (vente)
transfer    → Transfert entre emplacements
adjustment  → Ajustement (inventaire)
loss        → Perte / casse
```

---

## Composants UI prioritaires

| Composant | Description |
|-----------|-------------|
| `PinPad` | Clavier numérique 4×3, overlay, compte à rebours verrouillage |
| `ProductCard` | Image, nom, SKU, stock, prix (grille POS) |
| `CartLine` | Ligne panier avec quantité éditable, prix final, remise |
| `StatusBadge` | Badge coloré selon statut (vente/ticket/transaction) |
| `StockIndicator` | Barre ou chip vert/orange/rouge selon seuil |
| `PaymentSplitter` | Saisie multi-mode de paiement avec total restant |
| `TicketKanbanCard` | Carte ticket réparation pour vue kanban |
| `PhoneInput` | Sélecteur indicatif + champ téléphone E.164 |
| `PriceInput` | Saisie montant avec devise du tenant, validation plancher |
| `ThermalReceipt` | Composant imprimable reçu 58/80mm |

---

## Contraintes importantes

### Offline-first (caisse)
- Les ventes doivent être saisissables sans connexion
- Chaque mouvement de stock génère un `client_uuid` (UUID v4) côté client avant envoi → idempotence à la réconciliation
- File d'attente locale (IndexedDB ou localStorage) pour les ventes en attente de sync

### Impression thermique
- Reçus compatibles 58mm et 80mm
- Contenu : référence ticket, date, lignes (produit × qté × prix), total, mode(s) de paiement, rendu de monnaie, nom boutique

### Multi-devise
- Toutes les valeurs monétaires s'affichent dans la devise du tenant (`XAF`, `XOF`, `GNF`…)
- Séparateurs selon locale (ex. `1 500 FCFA`)

### Sécurité PIN
- Le PIN est par **membership** (utilisateur × boutique), pas global
- Verrouillage automatique après 5 tentatives incorrectes (15 min)
- L'admin peut reset le PIN d'un membre via email

---

## API — Endpoints principaux

Base URL : `https://api.kenpro.cm/api/v1/`

```
/accounts/register/                    POST  Inscription
/accounts/password-reset/request/      POST  Mot de passe oublié (toujours 200)
/accounts/password-reset/confirm/      POST  Réinitialisation
/accounts/password/change/             POST  Changement (utilisateur connecté)
/accounts/pin-reset/request/           POST  Reset PIN (authentifié, membership propre)
/accounts/pin-reset/confirm/           POST  Confirmer reset PIN
/accounts/memberships/{id}/verify-pin/ POST  Vérifier PIN (membership propre)
/accounts/memberships/{id}/set-pin/    POST  Définir PIN (membership propre)

/inventory/products/                   CRUD  Produits
/inventory/categories/                 CRUD  Catégories
/inventory/stock-levels/               GET   Niveaux de stock
/inventory/stock-movements/            CRUD  Mouvements (append-only)
/inventory/locations/                  CRUD  Emplacements
/inventory/stock-alerts/               GET   Alertes stock

/sales/sales/                          CRUD  Ventes
/sales/lines/                          CRUD  Lignes de vente
/sales/payments/                       CRUD  Paiements
/sales/credit-notes/                   CRUD  Avoirs

/crm/customers/                        CRUD  Clients

/supplier/suppliers/                   CRUD  Fournisseurs (lecture authentifié, écriture admin)
/supplier/links/                       CRUD  Liens boutique×fournisseur
/supplier/statements/                  CRUD  Relevés de crédit
/supplier/entries/                     POST/GET  Écritures (append-only)
/supplier/credit-payments/             CRUD + confirm  Paiements fournisseur

/repair/devices/                       CRUD  Appareils
/repair/tickets/                       CRUD  Tickets
/repair/tickets/{id}/transition/       POST  Changer statut ticket
/repair/tickets/{id}/assign/           POST  Assigner technicien
/repair/tickets/{id}/history/          GET   Historique statuts

/mobilemoney/transactions/             GET   Transactions MoMo
```

Auth : `Authorization: Bearer <access_token>`
Tenant : passé via header `X-Tenant-ID` ou sous-domaine (à confirmer avec le backend)
