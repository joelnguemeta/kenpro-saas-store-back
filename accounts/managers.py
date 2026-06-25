from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager personnalisé pour le modèle User avec phone comme identifiant."""

    def create_user(self, phone, password=None, **extra_fields):
        """Crée un utilisateur standard. Le mot de passe est optionnel (auth OTP par email)."""
        if not phone:
            raise ValueError("Le numéro de téléphone est obligatoire.")
        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password, **extra_fields):
        """Crée un superutilisateur pour l'admin Django."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields.get("is_staff"):
            raise ValueError("Le superutilisateur doit avoir is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Le superutilisateur doit avoir is_superuser=True.")
        return self.create_user(phone, password, **extra_fields)
