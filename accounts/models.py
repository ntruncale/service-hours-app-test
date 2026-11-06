from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from . import school_year


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        TEACHER = "teacher", "Grade-level teacher"
        ADMIN = "admin", "Administrator"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    # Microsoft's permanent ID for this person. Emails can change; the oid does not.
    ms_oid = models.CharField(max_length=64, unique=True, null=True, blank=True)
    graduation_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        help_text="Students only, e.g. 2027 for the Class of 2027.",
    )

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.email or self.username

    @property
    def is_student(self) -> bool:
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self) -> bool:
        return self.role == self.Role.TEACHER

    @property
    def is_school_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def current_grade(self) -> int | None:
        if self.graduation_year is None:
            return None
        return school_year.grade_for(self.graduation_year)

    def visible_grades(self) -> list[int]:
        """Grade levels whose students this user may see on the teacher dashboard."""
        if self.is_school_admin:
            return [9, 10, 11, 12]
        if self.is_teacher:
            return sorted(self.grade_assignments.values_list("grade_level", flat=True))
        return []

    def can_view_student(self, student: "User") -> bool:
        if self.pk == student.pk:
            return True
        return student.is_student and student.current_grade in self.visible_grades()


class GradeAssignment(models.Model):
    """Which grade level a teacher supervises. A teacher may have more than one."""

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="grade_assignments",
        limit_choices_to={"role__in": [User.Role.TEACHER, User.Role.ADMIN]},
    )
    grade_level = models.PositiveSmallIntegerField(
        choices=[(g, f"Grade {g}") for g in (9, 10, 11, 12)]
    )

    class Meta:
        unique_together = [("teacher", "grade_level")]
        ordering = ["grade_level"]

    def __str__(self) -> str:
        return f"{self.teacher} - grade {self.grade_level}"
