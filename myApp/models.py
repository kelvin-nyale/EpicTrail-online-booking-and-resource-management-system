# from django.db import models
# from django.utils import timezone
# from django.contrib.auth.models import User


# # =========================================
# # PROFILE
# # =========================================
# class Profile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE)
#     phone = models.CharField(max_length=15, blank=True, null=True)
#     photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)

#     def __str__(self):
#         return f"{self.user.username}'s Profile"


# # =========================================
# # ACTIVITY
# # =========================================
# class Activity(models.Model):
#     name = models.CharField(max_length=100)
#     description = models.TextField()
#     price_per_person = models.DecimalField(max_digits=8, decimal_places=2)
#     image = models.ImageField(upload_to='activity_images/', blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.name} – {self.price_per_person}"


# # =========================================
# # PACKAGE
# # =========================================
# class Package(models.Model):
#     name = models.CharField(max_length=100)
#     description = models.TextField()
#     activities = models.ManyToManyField(Activity, related_name='packages')
#     price_per_person = models.DecimalField(max_digits=10, decimal_places=2)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.name} – {self.price_per_person}"


# # =========================================
# # ROOM TYPE
# # =========================================
# class RoomType(models.Model):
#     name = models.CharField(max_length=100, unique=True)
#     description = models.TextField(blank=True)
#     capacity = models.PositiveIntegerField()
#     price_per_night = models.DecimalField(max_digits=8, decimal_places=2)
#     total_rooms = models.PositiveIntegerField(default=1)
#     is_available = models.BooleanField(default=True)

#     def available_rooms(self):
#         today = timezone.now().date()
#         booked = RoomBooking.objects.filter(
#             room_type=self,
#             check_in__lte=today,
#             check_out__gte=today
#         ).count()
#         return self.total_rooms - booked

#     def __str__(self):
#         return f"{self.name} – {self.price_per_night}"


# # =========================================
# # ROOM
# # =========================================
# class Room(models.Model):
#     name = models.CharField(max_length=100)
#     room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
#     image = models.ImageField(upload_to='room_images/', blank=True, null=True)

#     def __str__(self):
#         return f"{self.name} ({self.room_type.name})"


# # =========================================
# # ROOM BOOKING
# # =========================================
# class RoomBooking(models.Model):
#     room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
#     customer_name = models.CharField(max_length=150)
#     customer_email = models.EmailField()
#     check_in = models.DateField()
#     check_out = models.DateField()
#     guests = models.PositiveIntegerField()
#     created_at = models.DateTimeField(auto_now_add=True)

#     def total_price(self):
#         nights = (self.check_out - self.check_in).days
#         return nights * self.room_type.price_per_night * self.guests

#     def overlaps(self, check_in, check_out):
#         return not (check_out <= self.check_in or check_in >= self.check_out)

#     def __str__(self):
#         return f"{self.customer_name} – {self.room_type.name}"


# # =========================================
# # FOOD
# # =========================================
# class Food(models.Model):
#     name = models.CharField(max_length=100)
#     price_per_person = models.DecimalField(max_digits=10, decimal_places=2)

#     def __str__(self):
#         return f"{self.name} – {self.price_per_person}"


# # =========================================
# # TOUR
# # =========================================
# class Tour(models.Model):
#     name = models.CharField(max_length=100)
#     destination = models.CharField(max_length=100, null=True)
#     description = models.TextField()
#     price_per_person = models.DecimalField(max_digits=10, decimal_places=2)
#     image = models.ImageField(upload_to='tour_images/', blank=True, null=True)

#     def __str__(self):
#         return f"{self.name} – {self.destination}"


# # =========================================
# # BOOKING (MASTER BOOKING)
# # =========================================
# class Booking(models.Model):
#     user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
#     customer_name = models.CharField(max_length=100, blank=True, null=True)
#     customer_email = models.EmailField(blank=True, null=True)

#     activities = models.ManyToManyField(Activity, blank=True)
#     packages = models.ManyToManyField(Package, blank=True)
#     rooms = models.ManyToManyField(Room, blank=True)
#     food = models.ManyToManyField(Food, blank=True)
#     tours = models.ManyToManyField(Tour, blank=True)

#     check_in = models.DateField(blank=True, null=True)
#     check_out = models.DateField(blank=True, null=True)
#     pax = models.PositiveIntegerField(default=1)

#     pax_details = models.JSONField(blank=True, null=True)

#     created_at = models.DateTimeField(auto_now_add=True)
#     paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

#     # ----- CALCULATIONS -----
#     @property
#     def nights(self):
#         if self.check_in and self.check_out:
#             diff = (self.check_out - self.check_in).days
#             return diff if diff > 0 else 1
#         return 1

#     @property
#     def amount_required(self):
#         pax = self.pax or 1

#         def get_p(category):
#             if self.pax_details and category in self.pax_details:
#                 return self.pax_details[category].get('pax', pax)
#             return pax

#         room_cost = sum(
#             r.room_type.price_per_night * get_p('rooms') * self.nights
#             for r in self.rooms.all()
#         )
#         activity_cost = sum(
#             a.price_per_person * get_p('activities')
#             for a in self.activities.all()
#         )
#         package_cost = sum(
#             p.price_per_person * get_p('packages')
#             for p in self.packages.all()
#         )
#         food_cost = sum(
#             f.price_per_person * get_p('food')
#             for f in self.food.all()
#         )
#         tour_cost = sum(
#             t.price_per_person * get_p('tours')
#             for t in self.tours.all()
#         )

#         return room_cost + activity_cost + package_cost + food_cost + tour_cost

#     @property
#     def balance(self):
#         return self.amount_required - self.paid

#     def __str__(self):
#         return f"Booking #{self.id} – {self.customer_name or self.user}"


# # =========================================
# # NOTIFICATION
# # =========================================
# class Notification(models.Model):
#     NOTIFICATION_TYPES = [
#         ('booking', 'Booking'),
#         ('registration', 'Registration'),
#     ]

#     user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
#     message = models.CharField(max_length=255)
#     type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='booking')
#     created_at = models.DateTimeField(auto_now_add=True)
#     is_read = models.BooleanField(default=False)

#     def __str__(self):
#         return f"{self.message} – {self.type}"


# # =========================================
# # SYSTEM SETTINGS
# # =========================================
# class SystemSetting(models.Model):
#     site_name = models.CharField(max_length=100, default="Adventure Park")
#     support_email = models.EmailField(default="support@example.com")
#     maintenance_mode = models.BooleanField(default=False)
#     enable_mpesa = models.BooleanField(default=True)
#     enable_stripe = models.BooleanField(default=False)
#     max_daily_bookings = models.PositiveIntegerField(default=100)
#     discount_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

#     def __str__(self):
#         return "System Settings"


# # =========================================
# # FOOD ORDER
# # =========================================
# class FoodOrder(models.Model):
#     STATUS_CHOICES = [
#         ('pending', 'Pending'),
#         ('processing', 'Processing'),
#         ('completed', 'Completed'),
#         ('cancelled', 'Cancelled'),
#     ]

#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     food = models.ForeignKey(Food, on_delete=models.CASCADE)
#     quantity = models.PositiveIntegerField(default=1)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
#     check_in_date = models.DateField(blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def total_price(self):
#         return self.food.price_per_person * self.quantity

#     def __str__(self):
#         return f"{self.food.name} × {self.quantity}"


# # =========================================
# # DUTY
# # =========================================
# class Duty(models.Model):
#     staff = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'is_staff': True})
#     title = models.CharField(max_length=100)
#     description = models.TextField(blank=True)
#     due_date = models.DateField()
#     assigned_on = models.DateTimeField(auto_now_add=True)
#     completed = models.BooleanField(default=False)

#     def __str__(self):
#         return f"{self.title} – {self.staff.username}"


# # =========================================
# # MPESA TRANSACTION
# # =========================================
# class MpesaTransaction(models.Model):
#     phone = models.CharField(max_length=15)
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     mpesa_receipt_number = models.CharField(max_length=100)
#     result_code = models.IntegerField()
#     result_desc = models.CharField(max_length=255)
#     transaction_date = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.mpesa_receipt_number} – {self.phone}"

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal


# -----------------------------
# PROFILE
# -----------------------------
class Profile(models.Model):
    profile_user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_phone = models.CharField(max_length=15, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)

    def __str__(self):
        return f"{self.profile_user.username} - {self.profile_phone}"


# -----------------------------
# ACTIVITY
# -----------------------------
class Activity(models.Model):
    activity_name = models.CharField(max_length=100)
    activity_description = models.TextField()
    activity_price_per_person = models.DecimalField(max_digits=8, decimal_places=2)
    activity_image = models.ImageField(upload_to='activity_images/', blank=True, null=True)
    activity_created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id} - {self.activity_name} - {self.activity_price_per_person}"


# -----------------------------
# PACKAGE
# -----------------------------
class Package(models.Model):
    package_name = models.CharField(max_length=100)
    package_description = models.TextField()
    package_activities = models.ManyToManyField(Activity, related_name="package_activities")
    package_price_per_person = models.DecimalField(max_digits=10, decimal_places=2)
    package_created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        activities = ", ".join([a.activity_name for a in self.package_activities.all()])
        return f"{self.id} - {self.package_name} - [{activities}] - {self.package_price_per_person}"


# -----------------------------
# ROOM TYPE
# -----------------------------
class RoomType(models.Model):
    roomType_name = models.CharField(max_length=100, unique=True)
    roomType_description = models.TextField(blank=True)
    roomType_capacity = models.PositiveIntegerField()
    roomType_price_per_night = models.DecimalField(max_digits=8, decimal_places=2)
    roomType_total_rooms = models.PositiveIntegerField(default=1)
    roomType_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.id} - {self.roomType_name}"


# -----------------------------
# ROOM
# -----------------------------
class Room(models.Model):
    room_name = models.CharField(max_length=100)
    room_room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
    room_image = models.ImageField(upload_to='room_images/', blank=True, null=True)

    def __str__(self):
        return f"{self.id} - {self.room_name} ({self.room_room_type.roomType_name})"


# -----------------------------
# ROOM BOOKING
# -----------------------------
class RoomBooking(models.Model):
    roomBooking_room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
    roomBooking_customer_name = models.CharField(max_length=150)
    roomBooking_customer_email = models.EmailField()
    roomBooking_check_in = models.DateField()
    roomBooking_check_out = models.DateField()
    roomBooking_guests = models.PositiveIntegerField()
    roomBooking_created_at = models.DateTimeField(auto_now_add=True)

    def total_price(self):
        nights = (self.roomBooking_check_out - self.roomBooking_check_in).days
        if nights < 1:
            nights = 1
        return nights * self.roomBooking_room_type.roomType_price_per_night

    def __str__(self):
        return f"{self.id} - {self.roomBooking_customer_name} - {self.roomBooking_room_type.roomType_name}"


# -----------------------------
# FOOD
# -----------------------------
class Food(models.Model):
    food_name = models.CharField(max_length=100)
    food_price_per_person = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.id} - {self.food_name}"


# -----------------------------
# TOUR
# -----------------------------
class Tour(models.Model):
    tour_name = models.CharField(max_length=100)
    tour_destination = models.CharField(max_length=100, null=True)
    tour_description = models.TextField()
    tour_price_per_person = models.DecimalField(max_digits=10, decimal_places=2)
    tour_image = models.ImageField(upload_to='tour_images/', blank=True, null=True)

    def __str__(self):
        return f"{self.id} - {self.tour_name} - {self.tour_destination}"


# -----------------------------
# BOOKING (MASTER BOOKING)
# -----------------------------
class Booking(models.Model):
    booking_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    booking_customer_name = models.CharField(max_length=100, blank=True, null=True)
    booking_customer_email = models.EmailField(blank=True, null=True)

    booking_activities = models.ManyToManyField(Activity, blank=True)
    booking_packages = models.ManyToManyField(Package, blank=True)
    booking_rooms = models.ManyToManyField(Room, blank=True)
    booking_food = models.ManyToManyField(Food, blank=True)
    booking_tours = models.ManyToManyField(Tour, blank=True)

    booking_check_in = models.DateField(blank=True, null=True)
    booking_check_out = models.DateField(blank=True, null=True)
    booking_pax = models.PositiveIntegerField(default=1)

    booking_pax_details = models.JSONField(blank=True, null=True)

    booking_created_at = models.DateTimeField(auto_now_add=True)
    paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def nights_spent(self):
        if self.booking_check_in and self.booking_check_out:
            days = (self.booking_check_out - self.booking_check_in).days
            return max(days, 1)
        return 1

    @property
    def amount_required(self):
        pax = self.booking_pax

        # Rooms
        room_cost = sum(
            room.room_room_type.roomType_price_per_night * pax * self.nights_spent
            for room in self.booking_rooms.all()
        )

        activities_cost = sum(
            a.activity_price_per_person * pax for a in self.booking_activities.all()
        )

        package_cost = sum(
            p.package_price_per_person * pax for p in self.booking_packages.all()
        )

        food_cost = sum(
            f.food_price_per_person * pax for f in self.booking_food.all()
        )

        tour_cost = sum(
            t.tour_price_per_person * pax for t in self.booking_tours.all()
        )

        return room_cost + activities_cost + package_cost + food_cost + tour_cost

    @property
    def balance(self):
        return self.amount_required - self.paid

    def __str__(self):
        return f"Booking #{self.id} - {self.booking_customer_name or 'Guest'}"


# -----------------------------
# NOTIFICATION
# -----------------------------
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('booking', 'Booking'),
        ('registration', 'Registration'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_notifications")
    message = models.CharField(max_length=255)
    type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.id} - {self.message}"


# -----------------------------
# SYSTEM SETTINGS
# -----------------------------
class SystemSetting(models.Model):
    site_name = models.CharField(max_length=100, default="EpicTrail Adventures")
    support_email = models.EmailField(default="support@epictrail.co.ke")
    maintenance_mode = models.BooleanField(default=False)
    enable_mpesa = models.BooleanField(default=True)
    enable_stripe = models.BooleanField(default=False)
    max_daily_bookings = models.PositiveIntegerField(default=100)
    discount_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    def __str__(self):
        return "System Settings"


# -----------------------------
# FOOD ORDER
# -----------------------------
class FoodOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    foodOrder_user = models.ForeignKey(User, on_delete=models.CASCADE)
    foodOrder_food = models.ForeignKey(Food, on_delete=models.CASCADE)
    foodOrder_quantity = models.PositiveIntegerField(default=1)
    foodOrder_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    foodOrder_created_at = models.DateTimeField(auto_now_add=True)
    foodOrder_check_in = models.DateField(null=True, blank=True)

    def total_price(self):
        return self.foodOrder_food.food_price_per_person * self.foodOrder_quantity

    def __str__(self):
        return f"{self.id} - {self.foodOrder_food.food_name} x{self.foodOrder_quantity}"

# -----------------------------
# DUTIES MANAGEMENT
# -----------------------------
class Duty(models.Model):
    duty_staff = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'is_staff': True}
    )
    duty_title = models.CharField(max_length=100)
    duty_description = models.TextField(blank=True)
    duty_due_date = models.DateField()
    duty_assigned_on = models.DateTimeField(auto_now_add=True)
    duty_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.id} - {self.duty_title} → {self.duty_staff.username}"

# -----------------------------
# MPESA TRANSACTION
# -----------------------------
class MpesaTransaction(models.Model):
    phone = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mpesa_receipt_number = models.CharField(max_length=100)
    result_code = models.IntegerField()
    result_desc = models.CharField(max_length=255)
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mpesa_receipt_number} - {self.phone}"

# -----------------------------
# VIEWING THE MODEL STRUCTURES IN THE DJANGO ADMIN
# -----------------------------
# class ModelStructure(models.Model):
#     class Meta:
#         verbose_name = "Model Structure"
#         verbose_name_plural = "Model Structures"
#         managed = False