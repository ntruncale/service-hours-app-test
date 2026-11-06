from django.core.management.base import BaseCommand

from hours.services import process_reminders


class Command(BaseCommand):
    help = "Email reminders to supervisors and expire old approval links. Run once a day."

    def handle(self, *args, **options):
        counts = process_reminders()
        self.stdout.write(
            self.style.SUCCESS(
                f"Reminders sent: {counts['reminded']}. Expired: {counts['expired']}."
            )
        )
