from django.core.management.base import BaseCommand
from api.models import User


class Command(BaseCommand):
    help = "Create a new user with properly hashed password"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username for the new user")
        parser.add_argument("password", type=str, help="Password for the new user")
        parser.add_argument(
            "--staff", action="store_true", help="Make user a staff member"
        )
        parser.add_argument(
            "--superuser", action="store_true", help="Make user a superuser"
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        is_staff = options["staff"]
        is_superuser = options["superuser"]

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'User "{username}" already exists'))
            return

        if is_superuser:
            user = User.objects.create_superuser(
                username=username,
                password=password,
            )
            self.stdout.write(
                self.style.SUCCESS(f'Superuser "{username}" created successfully')
            )
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
            )
            if is_staff:
                user.is_staff = True
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Staff user "{username}" created successfully')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'User "{username}" created successfully')
                )
