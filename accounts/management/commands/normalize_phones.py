"""
Normalise en E.164 les numéros des comptes existants (créés avant la
normalisation systématique). Ignore les numéros invalides et signale
les collisions (deux comptes qui aboutiraient au même numéro).

Usage :
    python manage.py normalize_phones           # simulation (dry-run)
    python manage.py normalize_phones --apply   # applique les changements
"""
from django.core.management.base import BaseCommand

from accounts.models import User
from accounts.phone import normalize_phone_or_none


class Command(BaseCommand):
    help = "Normalise les numéros de téléphone des utilisateurs en E.164."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Applique (défaut : dry-run)")

    def handle(self, *args, **options):
        apply = options["apply"]
        changed = skipped = collisions = 0

        for user in User.objects.all():
            normalized = normalize_phone_or_none(user.phone)
            if normalized is None:
                self.stdout.write(self.style.WARNING(f"  invalide, ignoré : {user.phone!r}"))
                skipped += 1
                continue
            if normalized == user.phone:
                continue
            if User.objects.filter(phone=normalized).exclude(pk=user.pk).exists():
                self.stdout.write(self.style.ERROR(
                    f"  COLLISION : {user.phone!r} → {normalized!r} existe déjà — à fusionner manuellement"
                ))
                collisions += 1
                continue
            self.stdout.write(f"  {user.phone!r} → {normalized!r}")
            if apply:
                user.phone = normalized
                user.save(update_fields=["phone"])
            changed += 1

        mode = "appliqué" if apply else "dry-run (relancer avec --apply)"
        self.stdout.write(self.style.SUCCESS(
            f"{changed} modifié(s), {skipped} invalide(s), {collisions} collision(s) — {mode}"
        ))
