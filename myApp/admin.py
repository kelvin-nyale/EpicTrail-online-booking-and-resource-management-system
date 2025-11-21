from django.contrib import admin
from django.apps import apps        # needed for apps.get_models()
from django.db import models       # needed for models.Field, ForeignKey, etc.
from django.utils.html import format_html
from .models import ModelStructure
from .models import Profile, Activity, Package, Booking, Room, Food, Tour, RoomType, RoomBooking, Notification, Duty, FoodOrder
from django.contrib.auth.models import User
# Register your models here.
# admin.site.register(Activity),
# admin.site.register(Package),
# admin.site.register(Booking),
# admin.site.register(Room),
# admin.site.register(Food),
# admin.site.register(Tour),
# admin.site.register(RoomType),
# admin.site.register(RoomBooking),
admin.site.register(Notification),
# admin.site.register(Duty),
# admin.site.register(FoodOrder)

from .models import MpesaTransaction

@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = ('phone', 'amount', 'mpesa_receipt_number', 'result_code', 'result_desc', 'transaction_date')

# -----------------------------
# PROFILE
# -----------------------------
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('profile_user', 'profile_phone', 'profile_photo')
    search_fields = ('profile_user__username', 'profile_phone')

# -----------------------------
# ACTIVITY
# -----------------------------
@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'activity_name', 'activity_price_per_person', 'activity_created_at')
    search_fields = ('activity_name',)
    list_filter = ('activity_created_at',)

# -----------------------------
# PACKAGE
# -----------------------------
@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('id', 'package_name', 'package_price_per_person', 'package_created_at')
    search_fields = ('package_name',)
    list_filter = ('package_created_at',)
    filter_horizontal = ('package_activities',)  # ManyToMany field

# -----------------------------
# ROOM TYPE
# -----------------------------
@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'roomType_name', 'roomType_capacity', 'roomType_price_per_night', 'roomType_total_rooms', 'roomType_available')
    search_fields = ('roomType_name',)
    list_filter = ('roomType_available',)

# -----------------------------
# ROOM
# -----------------------------
@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'room_name', 'room_room_type')
    search_fields = ('room_name',)
    list_filter = ('room_room_type',)

# -----------------------------
# ROOM BOOKING
# -----------------------------
@admin.register(RoomBooking)
class RoomBookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'roomBooking_customer_name', 'roomBooking_room_type', 'roomBooking_check_in', 'roomBooking_check_out', 'roomBooking_guests', 'roomBooking_created_at', 'total_price_display')
    search_fields = ('roomBooking_customer_name', 'roomBooking_customer_email')
    list_filter = ('roomBooking_check_in', 'roomBooking_check_out', 'roomBooking_room_type')

    def total_price_display(self, obj):
        return obj.total_price()
    total_price_display.short_description = 'Total Price'

# -----------------------------
# FOOD
# -----------------------------
@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ('id', 'food_name', 'food_price_per_person')
    search_fields = ('food_name',)

# -----------------------------
# TOUR
# -----------------------------
@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ('id', 'tour_name', 'tour_destination', 'tour_price_per_person')
    search_fields = ('tour_name', 'tour_destination')

# -----------------------------
# FOOD ORDER
# -----------------------------
@admin.register(FoodOrder)
class FoodOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'foodOrder_user', 'foodOrder_food', 'foodOrder_quantity', 'foodOrder_status', 'foodOrder_created_at', 'foodOrder_check_in', 'total_price_display')
    list_filter = ('foodOrder_status', 'foodOrder_created_at')
    search_fields = ('foodOrder_user__username', 'foodOrder_food__food_name')

    def total_price_display(self, obj):
        return obj.total_price()
    total_price_display.short_description = 'Total Price'

# -----------------------------
# DUTY MANAGEMENT
# -----------------------------
@admin.register(Duty)
class DutyAdmin(admin.ModelAdmin):
    list_display = ('id', 'duty_title', 'duty_staff', 'duty_due_date', 'duty_assigned_on', 'duty_completed')
    list_filter = ('duty_completed', 'duty_due_date')
    search_fields = ('duty_title', 'duty_staff__username')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    # Show useful fields in the bookings list
    list_display = (
        'id',
        'booking_user',
        'booking_customer_name',
        'booking_customer_email',
        'booking_check_in',
        'booking_check_out',
        'booking_pax',
        'booking_created_at',
        'amount_required_display',  # custom display for property
        'paid',
        'balance_display',          # custom display for property
    )

    # Add filters to easily find bookings
    list_filter = (
        'booking_check_in',
        'booking_check_out',
        'booking_user',
        'booking_created_at',
    )

    search_fields = ('booking_customer_name', 'booking_customer_email')

    # Display ManyToMany fields nicely
    filter_horizontal = (
        'booking_rooms',
        'booking_packages',
        'booking_activities',
        'booking_food',
        'booking_tours',
    )

    # Add readonly fields for properties
    readonly_fields = ('amount_required_display', 'balance_display', 'booking_created_at')

    # Display properties in admin
    def amount_required_display(self, obj):
        return obj.amount_required
    amount_required_display.short_description = "Total Amount"

    def balance_display(self, obj):
        return obj.balance
    balance_display.short_description = "Balance"


from django.urls import path
from django.shortcuts import render

class ModelStructureAdmin(admin.ModelAdmin):
    change_list_template = "admin/model_structure.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("", self.admin_site.admin_view(self.view_models), name="modelstructure")
        ]
        return custom + urls

    def view_models(self, request):
        app_groups = {}

        # ------------------------------------------
        # 1. USER MODEL (Merged with Profile.phone)
        # ------------------------------------------
        user_fields = []
        user_field_whitelist = ["id", "username", "email", "password"]

        for field in User._meta.get_fields():
            if field.name in user_field_whitelist:
                name = field.name
                ftype = type(field).__name__
                pk = " (PK)" if getattr(field, "primary_key", False) else ""

                user_fields.append({
                    "name": name,
                    "type": ftype,
                    "pk": pk,
                    "rel": ""
                })

        # Add phone field manually from Profile model
        user_fields.append({
            "name": "phone",
            "type": "CharField",
            "pk": "",
            "rel": f" → {Profile._meta.app_label}.{Profile.__name__}"
        })

        app_groups["auth"] = [{
            "model_name": "User",
            "fields": user_fields
        }]

        # -------------------------------------------------
        # 2. APP MODELS (ignore Django built-in models)
        # -------------------------------------------------
        excluded_apps = ["auth", "sessions", "admin", "contenttypes"]

        for model in apps.get_models():
            app_label = model._meta.app_label
            model_name = model.__name__

            if app_label in excluded_apps:
                continue

            fields = []
            for field in model._meta.get_fields():
                name = field.name
                ftype = type(field).__name__
                pk = " (PK)" if getattr(field, "primary_key", False) else ""

                rel = ""
                if hasattr(field, "related_model") and field.related_model:
                    rel = f" → {field.related_model._meta.app_label}.{field.related_model.__name__}"

                fields.append({
                    "name": name,
                    "type": ftype,
                    "pk": pk,
                    "rel": rel
                })

            if app_label not in app_groups:
                app_groups[app_label] = []

            app_groups[app_label].append({
                "model_name": model_name,
                "fields": fields
            })

        context = {
            "opts": ModelStructure._meta,
            "app_groups": app_groups,
        }

        return render(request, "admin/model_structure.html", context)


admin.site.register(ModelStructure, ModelStructureAdmin)