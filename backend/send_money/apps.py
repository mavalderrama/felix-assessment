from django.apps import AppConfig


class SendMoneyConfig(AppConfig):  # type: ignore[misc]
    name = "send_money"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Import ORM models so Django's app registry discovers them.
        # Models live in adapters/persistence to preserve Clean Architecture layering.
        import send_money.adapters.persistence.django_models  # noqa: F401
