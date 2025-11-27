from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError
from .models import Profile
from .models import Activity, Package, Tour, Food, Room, RoomType, RoomBooking, Booking, Notification, Duty, FoodOrder
from django.utils.dateparse import parse_date
# from django.db.models import Count, Sum
from django.db.models import F, Sum, Count, ExpressionWrapper, DecimalField
import csv, io
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.db.models.functions import ExtractMonth
from datetime import datetime
from django.utils.timezone import now
from django.utils import timezone
import calendar

# for system settings
from django.core import management
from .models import SystemSetting

# for initiating stk push
from .mpesa import initiate_stk_push
import json
import requests, base64
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse

#  for callback url
from django.views.decorators.csrf import csrf_exempt
# for displaying transactions to the admin
from django.contrib import admin

# Create your views here.

def index(request):
    return render(request, 'index.html', {'navbar': 'home'})

def register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        # Validate passwords match
        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'register.html')

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return render(request, 'register.html')
        
        # Check if email already exists (optional)
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already in use.")
            return render(request, 'register.html')

        # Create user
        user = User.objects.create_user(username=username, email=email, password=password1)
        # Store phone number in first_name temporarily (or use a profile model)
        user.first_name = phone
        user.save()

        # Log in the user
        login(request, user)
        messages.success(request, "Registration successful!")
        return redirect('login')

    return render(request, 'register.html')

# Login with username or email, then redirect based on user role:
    #   - Admin (is_superuser) → admin_dashboard
    #   - Staff (is_staff) → staff_dashboard
    #   - Others → user_dashboard
def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=identifier, password=password)

        # Try email if direct username authentication fails
        if user is None:
            try:
                user_obj = User.objects.get(email__iexact=identifier)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user:
            if not user.is_active:
                messages.error(request, "Your account is inactive. Contact admin.")
                return redirect('login')

            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")

            # Role-based redirection
            if user.is_superuser:
                return redirect('admin_dashboard')
            elif user.is_staff:
                return redirect('staff_dashboard')
            else:
                return redirect('user_dashboard')
        else:
            messages.error(request, "Invalid username/email or password.")

    return render(request, 'login.html')


# Optional: Restrict access to admins only
def is_admin(user):
    return user.is_superuser

# Helper to check if user is admin
def admin_required(user):
    return user.is_authenticated and user.is_superuser

def logout_view(request):
    logout(request)  # Ends the user session
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')  # Redirect to the login page

@login_required
@user_passes_test(admin_required)
def admin_dashboard(request):

    # 5 most recent users
    recent_users = User.objects.order_by('-date_joined')[:5]

    return render(
        request,
        'dashboard.admin.html',
        {
            'recent_users': recent_users,
        }
    )

# @login_required
# def staff_dashboard(request):
#     # Count duties/resources assigned to the logged-in staff member
#     assigned_count = Duty.objects.filter(staff=request.user).count()

#     return render(request, "dashboard.staff.html", {
#         "assigned_count": assigned_count,
#     })
@login_required
def staff_dashboard(request):
    # Count only pending duties/resources assigned to this staff member
    assigned_count = Duty.objects.filter(
        duty_staff=request.user, duty_completed=False
    ).count()
    
    # Count bookings where date is in the future or today
    upcoming_bookings_count = Booking.objects.filter(booking_check_in__gte=timezone.now()).count()

    return render(request, "dashboard.staff.html", {
        "assigned_count": assigned_count,
        "upcoming_bookings_count": upcoming_bookings_count,
    })

@login_required
def user_dashboard(request):
    user = request.user
    today = timezone.now().date()

    # ------------------------------------------
    # COUNT ONLY BOOKINGS BELONGING TO THIS USER
    # ------------------------------------------
    total_bookings = Booking.objects.filter(booking_user=user).count()

    # ------------------------------------------
    # RECENT BOOKINGS = bookings not yet ended
    # booking_check_out >= today
    # ------------------------------------------
    recent_bookings = Booking.objects.filter(
        booking_user=user,
        booking_check_out__gte=today
    ).order_by('-booking_check_in')[:5]

    # Example placeholders — adjust to your models
    total_services = (
        Activity.objects.count() +
        # Package.objects.count() +
        Tour.objects.count() +
        Room.objects.count() +
        Food.objects.count()
    )

    # If you have notifications:
    total_notifications = Notification.objects.filter(user=user, is_read=False).count()

    return render(request, 'dashboard.user.html', {
        'total_bookings': total_bookings,
        'recent_bookings': recent_bookings,
        'total_services': total_services,
        'total_notifications': total_notifications,
    })


@login_required
@user_passes_test(admin_required) 
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username').strip()
        email = request.POST.get('email').strip()
        phone = request.POST.get('phone').strip()
        password = request.POST.get('password').strip()
        role = request.POST.get('role')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('add_user')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect('add_user')

        user = User.objects.create_user(username=username, email=email, password=password)

        # Assign role
        if role == 'admin':
            user.is_superuser = True
            user.is_staff = True
        elif role == 'staff':
            user.is_staff = True
        # Normal users remain without extra flags
        user.save()
        
        # Create profile for phone
        Profile.objects.create(user=user, phone=phone)

        messages.success(request, f"User '{username}' created successfully as {role}.")
        return redirect('users')

    return render(request, 'user.add.html')

@login_required
@user_passes_test(admin_required)  # Remove this decorator if staff should also access
def view_users(request):
    query = request.GET.get('q', '').strip()

    # Fetch users and apply search
    users_list = User.objects.all().order_by('-date_joined')
    if query:
        users_list = users_list.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query)
        )

    # Paginate results (10 per page)
    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)

    return render(request, 'users.list.html', {'users': users})

@login_required
@user_passes_test(admin_required) 
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        username = request.POST.get('username').strip()
        email = request.POST.get('email').strip()
        phone = request.POST.get('phone').strip()  # optional: store in a profile model
        role = request.POST.get('role')

        # Check if username/email is unique (excluding current user)
        if User.objects.exclude(id=user_id).filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('edit_user', user_id=user_id)

        if User.objects.exclude(id=user_id).filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect('edit_user', user_id=user_id)

        # Update user info
        user.username = username
        user.email = email
        user.phone = phone

        # Reset roles
        user.is_superuser = False
        user.is_staff = False

        # Apply new role
        if role == 'admin':
            user.is_superuser = True
            user.is_staff = True
        elif role == 'staff':
            user.is_staff = True

        user.save()

        messages.success(request, f"User '{username}' updated successfully.")
        return redirect('users')

    return render(request, 'user.edit.html', {'user': user})

@login_required
@user_passes_test(admin_required) 
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"User '{username}' deleted successfully.")
        return redirect('users')

    return render(request, 'user.delete.html', {'user': user})

# Add new activity
@login_required
@user_passes_test(is_admin)
def add_activity(request):
    if request.method == 'POST':
        activity_name = request.POST.get('activity_name')
        activity_description = request.POST.get('activity_description')
        activity_price_per_person = request.POST.get('activity_price_per_person')

        # Handle image upload if provided
        activity_image = request.FILES.get('activity_image')

        if activity_name and activity_description and activity_price_per_person and activity_image:
            activity = Activity(
                activity_name=activity_name,
                activity_description=activity_description,
                activity_price_per_person=activity_price_per_person,  
                activity_image=activity_image  
            )
            activity.save()  # Save to DB
            messages.success(request, 'Activity added successfully!')
            return redirect('activity_list')
        else:
            messages.error(request, 'All fields are required.')

    return render(request, 'activity.add.html')



# View all activities
# pagination
@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def activity_list(request):
    query = request.GET.get('q', '').strip()

    # Fetch activities and apply search
    activity_list = Activity.objects.all().order_by('-activity_created_at')
    if query:
        activity_list = activity_list.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    # Paginate results (10 per page)
    paginator = Paginator(activity_list, 10)
    page_number = request.GET.get('page')
    activities = paginator.get_page(page_number)

    # Pass both activities and query to the template (for search box persistence)
    return render(
        request,
        'activity.list.html',
        {'activities': activities, 'query': query}
    )



@login_required
@user_passes_test(is_admin)
def edit_activity(request, pk):
    activity = get_object_or_404(Activity, pk=pk)

    if request.method == 'POST':
        activity.activity_name = request.POST.get('activity_name')
        activity.activity_description = request.POST.get('activity_description')
        activity.activity_price_per_person = request.POST.get('activity_price_per_person')

        # Handle new image upload if provided
        if request.FILES.get('activity_image'):
            activity.activity_image = request.FILES['activity_image']

        activity.save()
        messages.success(request, 'Activity updated successfully!')
        return redirect('activity_list')

    return render(request, 'activity_edit.html', {'activity': activity})


# Delete activity
@login_required
@user_passes_test(is_admin) 
def delete_activity(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    if request.method == 'POST':
        activity.delete()
        messages.success(request, "Activity deleted successfully.")
        return redirect('activity_list')

    return render(request, 'activity.delete.html', {'activity': activity})



@login_required
@user_passes_test(admin_required)
def add_package(request):
    if request.method == "POST":
        package_name = request.POST.get("package_name")
        package_description = request.POST.get("package_description")
        package_price_per_person = request.POST.get("package_price_per_person")

        # Safely fetch valid activities
        selected_ids = request.POST.getlist("activities")
        selected_activities = get_list_or_404(Activity, id__in=selected_ids)

        package = Package.objects.create(
            package_name=package_name,
            package_description=package_description,
            package_price_per_person=package_price_per_person
        )
        package.package_activities.set(selected_activities)  # Link only valid activities
        package.save()

        return redirect("list_packages")

    activities = Activity.objects.all()
    return render(request, "package.add.html", {"activities": activities})


@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def list_packages(request):
    query = request.GET.get('q', '').strip()

    # Fetch activities and apply search
    list_packages = Package.objects.all().order_by('-package_created_at')
    if query:
        list_packages = list_packages.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    # Paginate results (10 per page)
    paginator = Paginator(list_packages, 10)
    page_number = request.GET.get('page')
    packages = paginator.get_page(page_number)

    # Pass both activities and query to the template (for search box persistence)
    return render(
        request,
        'package.list.html',
        {'packages': packages, 'query': query}
    )

# edit package
@login_required
@user_passes_test(is_admin) 
def edit_package(request, pk):
    package = get_object_or_404(Package, pk=pk)

    if request.method == "POST":
        # Basic fields
        package.package_name = request.POST.get("package_name")
        package.package_description = request.POST.get("package_description")

        # Convert price safely
        price_input = request.POST.get("package_price_per_person")
        try:
            package.package_price_per_person = Decimal(price_input)
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid price.")
            return redirect("edit_package", pk=pk)

        # Update activities
        selected_ids = request.POST.getlist("activities")
        package_activities = Activity.objects.filter(id__in=selected_ids)
        package.package_activities.set(package_activities)

        package.save()
        messages.success(request, "Package updated successfully.")
        return redirect("list_packages")

    # Data for the form
    activities = Activity.objects.all()
    selected_activities = package.package_activities.values_list("id", flat=True)

    return render(
        request,
        "package.update.html",
        {
            "package": package,
            "activities": activities,
            "selected_activities": selected_activities,
        },
    )

@login_required
@user_passes_test(admin_required)
def delete_package(request, pk):
    package = get_object_or_404(Package, pk=pk)
    package.delete()
    messages.success(request, "Package deleted successfully!")
    return redirect('list_packages')

@login_required
@user_passes_test(admin_required)
def add_room_type(request):
    if request.method == 'POST':
        # 1. Get raw string data from POST request
        roomType_name = request.POST.get('roomType_name')
        roomType_description = request.POST.get('roomType_description')
        
        # NOTE: .get() returns None if the key is missing or an empty string if present but empty.
        # We need to explicitly check and handle invalid inputs.

        # 2. Input Validation (Checking for the missing NOT NULL field)
        if not roomType_name or roomType_name.strip() == "":
            messages.error(request, 'Error: Room Type Name is required.')
            return render(request, 'room.type.add.html', request.POST) # Re-render with existing data
        
        # 3. Type Conversion and Cleaning (Important for numeric fields)
        try:
            # Safely convert to integer, defaulting to 0 or None if conversion fails
            roomType_capacity = int(request.POST.get('roomType_capacity', 0) or 0)
            roomType_total_rooms = int(request.POST.get('roomType_total_rooms', 0) or 0)
            
            # Use float or Decimal for price, depending on your model field type
            roomType_price_per_night = float(request.POST.get('roomType_price_per_night', 0.0) or 0.0)
            
        except (ValueError, TypeError):
            # Handle non-numeric input for numeric fields
            messages.error(request, 'Error: Capacity, Price, and Total Rooms must be valid numbers.')
            return render(request, 'room.type.add.html', request.POST)


        # 4. Database Creation
        try:
            RoomType.objects.create(
                roomType_name=roomType_name.strip(), # Use .strip() to remove leading/trailing whitespace
                roomType_description=roomType_description,
                roomType_capacity=roomType_capacity,
                roomType_price_per_night=roomType_price_per_night,
                roomType_total_rooms=roomType_total_rooms
            )
            
            messages.success(request, f'Room Type "{roomType_name.strip()}" added successfully!')
            return redirect('room_types')

        except Exception as e:
            # Handle other potential database errors (e.g., unique constraint violation)
            messages.error(request, f'An unexpected error occurred during database save: {e}')
            return render(request, 'room.type.add.html', request.POST)

    # If request method is GET, just render the form
    return render(request, 'room.type.add.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def room_types(request):
    room_types = RoomType.objects.all().order_by('roomType_price_per_night')
    return render(request, 'room_type.html', {'room_types': room_types})

@login_required
@user_passes_test(admin_required)
def edit_room_type(request, pk):
    room_type = get_object_or_404(RoomType, pk=pk)

    if request.method == 'POST':
        room_type.roomType_name = request.POST.get('roomType_name')
        room_type.roomType_description = request.POST.get('roomType_description')
        room_type.roomType_capacity = request.POST.get('roomType_capacity')
        roomType_price = request.POST.get('roomType_price_per_night')
        roomType_total_rooms = request.POST.get('roomType_total_rooms')

        if not roomType_price:
            messages.error(request, "Price per night is required.")
            return render(request, 'room.type.edit.html', {'room_type': room_type})

        try:
            room_type.roomType_price_per_night = float(roomType_price)
        except ValueError:
            messages.error(request, "Please enter a valid price.")
            return render(request, 'room.type.edit.html', {'room_type': room_type})

        room_type.roomType_total_rooms = roomType_total_rooms
        room_type.save()
        messages.success(request, "Room type updated successfully!")
        return redirect('room_types')

    return render(request, 'room.type.edit.html', {'room_type': room_type})

# @login_required
# @user_passes_test(admin_required)
# def delete_room_type(request, pk):
#     if request.method == 'POST':
#         room_type = get_object_or_404(RoomType, pk=pk)
#         room_type.delete()
#         messages.success(request, "Room type deleted successfully!")
#     return redirect('room_types', {'room_type': room_type})

@login_required
@user_passes_test(admin_required)
def delete_room_type(request, pk):
    
    if request.method == 'POST':
        # Safely retrieve the object. If it doesn't exist, a 404 is raised.
        room_type = get_object_or_404(RoomType, pk=pk)
        
        # Delete the object
        room_type.delete()
        
        messages.success(request, f"Room type '{room_type.roomType_name}' deleted successfully!")
        
        # 2. Redirect the user to the list page after success
        return redirect('room_types') # Removed the redundant dictionary
        
    
    # The view should return a redirect to the list page (room_types) 
    # for any non-POST request to prevent unauthorized deletion attempts and fix the error.
    return redirect('room_types')


@login_required
@user_passes_test(is_admin) 
def add_room(request):
    if request.method == 'POST':
        room_name = request.POST.get('room_name', '').strip()
        room_type_id = request.POST.get('roomType_name')
        room_image = request.FILES.get('room_image')

        # --- 1. Server-Side Validation ---
        
        # Check if room name is provided
        if not room_name:
            messages.error(request, 'Error: Room Name is required.')
            # Re-fetch room types and re-render the form
            room_types = RoomType.objects.all()
            return render(request, 'room_add.html', {'room_types': room_types})

        # Check if room type is selected and valid
        try:
            room_type = get_object_or_404(RoomType, id=room_type_id)
        except ObjectDoesNotExist:
            messages.error(request, 'Error: Invalid Room Type selected.')
            room_types = RoomType.objects.all()
            return render(request, 'room_add.html', {'room_types': room_types})

        # --- 2. Database Creation with Error Handling ---
        try:
            Room.objects.create(
                room_name=room_name,
                room_room_type=room_type,
                room_image=room_image 
            )

            messages.success(request, f"Room '{room_name}' added successfully!")
            return redirect('list_rooms')

        except IntegrityError as e:
            # Handle unique constraint violation (e.g., room name already exists)
            # You might need to check the specific error message for clarity
            if 'unique' in str(e).lower():
                 messages.error(request, f"Error: A room named '{room_name}' already exists.")
            else:
                 # Handle other integrity errors (like NOT NULL if room_name was missing before the check)
                 messages.error(request, f"Database Error: Could not save room. {e}")

            # Re-fetch room types and re-render the form
            room_types = RoomType.objects.all()
            return render(request, 'room_add.html', {'room_types': room_types})
        
        # Handle other unexpected errors
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")
            room_types = RoomType.objects.all()
            return render(request, 'room_add.html', {'room_types': room_types})


    # GET Request: Pass available room types to the template
    room_types = RoomType.objects.all()
    return render(request, 'room_add.html', {'room_types': room_types})

# @login_required
@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def list_rooms(request):
    rooms = Room.objects.select_related('room_room_type').all() # Fetch rooms with related room types
    return render(request, 'rooms_list.html', {'rooms': rooms})


@login_required
@user_passes_test(is_admin)
def edit_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    room_types = RoomType.objects.all()

    if request.method == 'POST':

        # Update fields using correct model names
        room.room_name = request.POST.get('room_name', '').strip()

        room_type_id = request.POST.get('room_room_type')
        room.room_room_type = get_object_or_404(RoomType, id=room_type_id)

        # Image update only if uploaded
        if 'room_image' in request.FILES:
            room.room_image = request.FILES['room_image']

        room.save()

        messages.success(request, f"Room '{room.room_name}' updated successfully!")
        return redirect('list_rooms')

    return render(request, 'room_edit.html', {
        'room': room,
        'room_types': room_types
    })

@login_required
@user_passes_test(is_admin)
def delete_room(request, room_id):
    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        messages.error(request, "Room does not exist.")
        return redirect('list_rooms')

    if request.method == 'POST':
        room_name = room.room_name
        room.delete()
        messages.success(request, f"Room '{room_name}' deleted successfully!")
        return redirect('list_rooms')

    return render(request, 'room_delete.html', {'room': room})



@login_required
@user_passes_test(is_admin)
def add_tour(request):
    if request.method == 'POST':
        tour_name = request.POST.get('tour_name')
        tour_destination = request.POST.get('tour_destination')
        tour_description = request.POST.get('tour_description')
        tour_price_per_person = request.POST.get('tour_price_per_person')
        # Handle image upload if provided
        tour_image = request.FILES.get('tour_image')
        
        Tour.objects.create(
            tour_name=tour_name,
            tour_destination=tour_destination,
            tour_description=tour_description,
            tour_price_per_person=tour_price_per_person,
            tour_image=tour_image
        )
        messages.success(request, "Room added successfully!")
        return redirect('tours')
    return render(request, 'tour.add.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def tours(request):
    tours = Tour.objects.all()
    return render(request, 'tours.html', {'tours': tours})

@login_required
@user_passes_test(is_admin)
def edit_tour(request, pk):
    tour = get_object_or_404(Tour, pk=pk)
    
    if request.method == 'POST':
        tour.tour_name = request.POST.get('tour_name')
        tour.tour_destination = request.POST.get('tour_destination')
        tour.tour_description = request.POST.get('tour_description')
        tour.tour_price_per_person = request.POST.get('tour_price_per_person')
        
        # Handle image upload if provided
        if request.FILES.get('tour_image'):
            tour.tour_image = request.FILES['tour_image']
        
        tour.save()
        return redirect('tours')
    return render(request, 'tour.edit.html', {'tour': tour})

@login_required
@user_passes_test(admin_required)
def delete_tour(request, pk):
    tour = get_object_or_404(Tour, pk=pk)
    tour_name = tour.tour_name
    tour.delete()
    messages.success(request, f"Tour '{tour_name}' deleted successfully!")
    return redirect('tours')



@login_required
@user_passes_test(admin_required)
def add_food(request):
    if request.method == 'POST':
        food_name = request.POST.get('food_name')
        food_price_per_person = request.POST.get('food_price_per_person')

        Food.objects.create(
            food_name=food_name,
            food_price_per_person=food_price_per_person
        )
        messages.success(request, "Food item added successfully!")
        return redirect('food_list')
    return render(request, 'food.add.html')


@login_required
@user_passes_test(admin_required)
def food_list(request):
    foods = Food.objects.all()
    return render(request, 'food.list.html', {'foods': foods})


@login_required
@user_passes_test(admin_required)
def edit_food(request, pk):
    food = get_object_or_404(Food, pk=pk)

    if request.method == 'POST':
        food.food_name = request.POST.get('food_name')
        food.food_price_per_person = request.POST.get('food_price_per_person')
        food.save()
        messages.success(request, "Food item updated successfully!")
        return redirect('food_list')

    return render(request, 'food.edit.html', {'food': food})


@login_required
@user_passes_test(admin_required)
def delete_food(request, pk):
    food = get_object_or_404(Food, pk=pk)
    if request.method == 'POST':
        food_name = food.food_name  # store name for message
        food.delete()
        messages.success(request, f"Food item '{food_name}' deleted successfully!")
        return redirect('food_list')
    return render(request, 'food.delete.html', {'food': food})


def book_room(request, pk):
    room = get_object_or_404(RoomType, pk=pk)
    if request.method == 'POST':
        check_in = parse_date(request.POST['check_in'])
        check_out = parse_date(request.POST['check_out'])

        # Count existing overlapping bookings
        overlapping = RoomBooking.objects.filter(
            room_type=room,
            check_in__lt=check_out,
            check_out__gt=check_in
        ).count()

        if overlapping >= room.total_rooms:
            messages.error(request, "Sorry, no available rooms for the selected dates.")
            return redirect('list_rooms')

        RoomBooking.objects.create(
            room_type=room,
            customer_name=request.POST['customer_name'],
            customer_email=request.POST['customer_email'],
            check_in=check_in,
            check_out=check_out,
            guests=request.POST['guests'],
        )
        messages.success(request, "Room booked successfully!")
        return redirect('list_rooms')
    return render(request, 'room_book.html', {'room': room})


# def create_booking(request):
#     """
#     Create a booking dynamically:
#     - Validate dates (allow same-day check-in/check-out)
#     - Validate room availability
#     - Store exact pax values for activities, packages, rooms, food, tours
#     - Role-based: Admin/Staff can select everything; normal users limited to Rooms & Packages
#     - Render correct base template depending on user role
#     """
#     if request.method == "POST":
#         # --- Handle customer details ---
#         customer_name = request.user.username if request.user.is_authenticated else request.POST.get("customer_name")
#         customer_email = request.user.email if request.user.is_authenticated else request.POST.get("customer_email")

#         check_in = request.POST.get("check_in")
#         check_out = request.POST.get("check_out")
#         pax = int(request.POST.get("pax", 1))

#         selected_room_ids = request.POST.getlist("rooms")
#         selected_package_ids = request.POST.getlist("packages")
#         selected_activity_ids = request.POST.getlist("activities")
#         selected_food_ids = request.POST.getlist("food")
#         selected_tour_ids = request.POST.getlist("tours")

#         # --- Validate dates ---
#         if not check_in or not check_out:
#             messages.error(request, "Please select both check-in and check-out dates.")
#             return redirect("create_booking")

#         if check_out < check_in:  # allow same-day but not before
#             messages.error(request, "Check-out date cannot be before check-in.")
#             return redirect("create_booking")

#         # --- Validate room availability ---
#         for room_id in selected_room_ids:
#             room = get_object_or_404(Room, id=room_id)
#             overlapping = Booking.objects.filter(
#                 rooms=room,
#                 check_in__lt=check_out,
#                 check_out__gt=check_in
#             ).count()
#             if overlapping >= room.room_type.total_rooms:
#                 messages.error(request, f"Room '{room.name}' is fully booked for the selected dates.")
#                 return redirect("create_booking")

#         # --- Role-based restrictions ---
#         if not (request.user.is_staff or request.user.is_superuser):
#             selected_activity_ids = []
#             selected_food_ids = []
#             selected_tour_ids = []

#         # --- Collect per-item pax values ---
#         pax_details = {}

#         activities_pax = int(request.POST.get("activities_pax", 1))
#         if selected_activity_ids:
#             pax_details['activities'] = {'ids': selected_activity_ids, 'pax': activities_pax}

#         packages_pax = int(request.POST.get("packages_pax", 1))
#         if selected_package_ids:
#             pax_details['packages'] = {'ids': selected_package_ids, 'pax': packages_pax}

#         rooms_pax = int(request.POST.get("rooms_pax", 1))
#         if selected_room_ids:
#             pax_details['rooms'] = {'ids': selected_room_ids, 'pax': rooms_pax}

#         food_pax = int(request.POST.get("food_pax", 1))
#         if selected_food_ids:
#             pax_details['food'] = {'ids': selected_food_ids, 'pax': food_pax}

#         tours_pax = int(request.POST.get("tours_pax", 1))
#         if selected_tour_ids:
#             pax_details['tours'] = {'ids': selected_tour_ids, 'pax': tours_pax}

#         # --- Create booking ---
#         booking = Booking.objects.create(
#             user=request.user if request.user.is_authenticated else None,
#             customer_name=customer_name,
#             customer_email=customer_email,
#             check_in=check_in,
#             check_out=check_out,
#             pax=pax,
#             pax_details=pax_details
#         )

#         booking.activities.set(selected_activity_ids)
#         booking.packages.set(selected_package_ids)
#         booking.rooms.set(selected_room_ids)
#         booking.food.set(selected_food_ids)
#         booking.tours.set(selected_tour_ids)

#         # --- After booking is saved ---
#         messages.success(request, "Booking created successfully! Proceed to payment.")

#         # Redirect user to payment page
#         return redirect("pay_booking", booking_id=booking.id)

#         # messages.success(request, "Booking created successfully!")
#         # return redirect("booking_list")

#     # --- Choose base template based on role ---
#     base_template = (
#         "base.admin.html" if request.user.is_authenticated and request.user.is_superuser
#         else "base.staff.html" if request.user.is_authenticated and request.user.is_staff
#         else "base.user.html" if request.user.is_authenticated
#         else "base.html"
#     )

#     # --- Context for form rendering ---
#     context = {
#         "base_template": base_template,
#         "activities": Activity.objects.all(),
#         "packages": Package.objects.all(),
#         "rooms": Room.objects.all(),
#         "food": Food.objects.all(),
#         "tours": Tour.objects.all(),
#     }
#     return render(request, "booking_create.html", context)

# # view for booking on behalf of another user
# @login_required
# # @user_passes_test(admin_required)
# def admin_create_booking(request):
#     users = User.objects.all().order_by('username')
#     activities = Activity.objects.all()
#     packages = Package.objects.all()
#     rooms = Room.objects.all()
#     food_items = Food.objects.all()
#     tours = Tour.objects.all()

#     if request.method == "POST":
#         selected_user_id = request.POST.get('user')
#         check_in = request.POST.get('check_in')
#         check_out = request.POST.get('check_out')
#         pax = request.POST.get('pax', 1)

#         # Create the booking linked to a user
#         booking = Booking.objects.create(
#             user=User.objects.get(id=selected_user_id) if selected_user_id else None,
#             check_in=check_in,
#             check_out=check_out,
#             pax=pax,
#         )

#         # Set ManyToMany relationships
#         booking.activities.set(request.POST.getlist('activities'))
#         booking.packages.set(request.POST.getlist('packages'))
#         booking.rooms.set(request.POST.getlist('rooms'))
#         booking.food.set(request.POST.getlist('food'))
#         booking.tours.set(request.POST.getlist('tours'))

#         messages.success(request, "Booking created successfully on behalf of user.")
#         return redirect('booking_list')

#     return render(request, 'booking.create_for_user.html', {
#         'users': users,
#         'activities': activities,
#         'packages': packages,
#         'rooms': rooms,
#         'food_items': food_items,
#         'tours': tours,
#     })
# @login_required
# def admin_create_booking(request):
#     users = User.objects.all().order_by('username')
#     activities = Activity.objects.all()
#     packages = Package.objects.all()
#     rooms = Room.objects.all()
#     food_items = Food.objects.all()
#     tours = Tour.objects.all()

#     if request.method == "POST":
#         selected_user_id = request.POST.get('user')
#         check_in = request.POST.get('check_in')
#         check_out = request.POST.get('check_out')
#         pax = request.POST.get('pax', 1)

#         # Create the booking linked to a user
#         booking = Booking.objects.create(
#             user=User.objects.get(id=selected_user_id) if selected_user_id else None,
#             check_in=check_in,
#             check_out=check_out,
#             pax=pax,
#         )

#         # Set ManyToMany relationships
#         booking.activities.set(request.POST.getlist('activities'))
#         booking.packages.set(request.POST.getlist('packages'))
#         booking.rooms.set(request.POST.getlist('rooms'))
#         booking.food.set(request.POST.getlist('food'))
#         booking.tours.set(request.POST.getlist('tours'))

#         # Calculate total amount (example: sum of activities + packages)
#         total_amount = 0
#         for activity in booking.activities.all():
#             total_amount += activity.price_per_person
#         for package in booking.packages.all():
#             total_amount += package.price_per_person
#         for room in booking.rooms.all():
#             total_amount += room.room_type.price_per_night
#         for food in booking.food.all():
#             total_amount += food.price_per_person
#         for tour in booking.tours.all():
#             total_amount += tour.price_per_person

#         # Redirect to payment page
#         return redirect('pay_booking', booking_id=booking.id)

#     return render(request, 'booking.create_for_user.html', {
#         'users': users,
#         'activities': activities,
#         'packages': packages,
#         'rooms': rooms,
#         'food_items': food_items,
#         'tours': tours,
#     })

# @login_required
# def upcoming_bookings_list(request):
#     upcoming_bookings = Booking.objects.filter(
#         check_in__gte=timezone.now()
#     ).order_by('check_in')
#     return render(request, "bookings.upcoming.html", {
#         "upcoming_bookings": upcoming_bookings
#     })
# @login_required
# def upcoming_bookings_list(request):
#     upcoming_bookings = Booking.objects.filter(
#         check_in__gte=timezone.now()
#     ).order_by('check_in')

#     for booking in upcoming_bookings:
#         details = []
#         if booking.pax_details:
#             for category, data in booking.pax_details.items():
#                 ids = data.get('ids', [])
#                 pax = data.get('pax', booking.pax)

#                 # Get model class dynamically
#                 model_map = {
#                     'rooms': Room,
#                     'activities': Activity,
#                     'packages': Package,
#                     'food': Food,
#                     'tours': Tour
#                 }

#                 ModelClass = model_map.get(category)
#                 if ModelClass:
#                     items = ModelClass.objects.filter(id__in=ids)
#                     item_names = ', '.join([item.name for item in items])
#                     details.append(f"{category.title()}: {item_names} (Pax: {pax})")

#         booking.display_pax_details = details

#     base_template = (
#         "base.admin.html" if request.user.is_superuser
#         else "base.staff.html"
#     )

#     return render(request, "bookings.upcoming.html", {
#         "upcoming_bookings": upcoming_bookings,
#         "base_template": base_template
#     })



# @login_required
# def booking_list(request):
#     bookings = (
#         Booking.objects
#         .select_related('user')
#         .prefetch_related('activities', 'packages', 'rooms', 'food', 'tours')
#         .order_by('-created_at')
#     )

#     if request.user.is_superuser:
#         editable_ids = bookings.values_list('id', flat=True)
#         base_template = 'base.admin.html'
#         template_name = 'bookings.html'  # Table for superusers
#     elif request.user.is_staff:
#         editable_ids = bookings.filter(user=request.user).values_list('id', flat=True)
#         base_template = 'base.staff.html'
#         template_name = 'bookings.html'  # Table for staff
#     else:
#         bookings = bookings.filter(user=request.user)
#         editable_ids = bookings.values_list('id', flat=True)
#         base_template = 'base.user.html'
#         template_name = 'bookings.users.html'  # Cards for normal users

#     return render(request, template_name, {
#         'bookings': bookings,
#         'editable_ids': set(editable_ids),
#         'base_template': base_template,
#     })


# # Edit booking with validations
# @login_required(login_url='login')
# def edit_booking(request, pk):
#     booking = get_object_or_404(Booking, pk=pk)

#     # Restrict: Only superusers or the booking owner can edit
#     if not request.user.is_superuser and booking.user != request.user:
#         messages.error(request, "You do not have permission to edit this booking.")
#         return redirect('booking_list')

#     if request.method == "POST":
#         check_in = request.POST.get("check_in")
#         check_out = request.POST.get("check_out")
#         guests = int(request.POST.get("guests", 1))
#         selected_room_ids = request.POST.getlist("rooms")

#         # Validate dates
#         if check_in > check_out:
#             messages.error(request, "Check-out date must be after check-in.")
#             return redirect("edit_booking", pk=booking.pk)

#         # Validate room availability
#         for room_id in selected_room_ids:
#             room = get_object_or_404(Room, id=room_id)
#             overlapping = Booking.objects.filter(
#                 rooms=room,
#                 check_in__lt=check_out,
#                 check_out__gt=check_in
#             ).exclude(id=booking.id).count()

#             if overlapping >= room.room_type.total_rooms:
#                 messages.error(
#                     request,
#                     f"Room '{room.name}' is fully booked for the selected dates."
#                 )
#                 return redirect("edit_booking", pk=booking.pk)

#         # Update booking details
#         booking.check_in = check_in
#         booking.check_out = check_out
#         booking.guests = guests
#         booking.activities.set(request.POST.getlist("activities"))
#         booking.packages.set(request.POST.getlist("packages"))
#         booking.rooms.set(selected_room_ids)
#         booking.food.set(request.POST.getlist("food"))
#         booking.tours.set(request.POST.getlist("tours"))
#         booking.save()

#         messages.success(request, "Booking updated successfully!")
#         return redirect("booking_list")

#     # Role-based base template selection
#     if request.user.is_superuser:
#         base_template = "base.admin.html"
#     elif request.user.groups.filter(name="Staff").exists():
#         base_template = "base.staff.html"
#     else:
#         base_template = "base.user.html"

#     # Pass all required data
#     context = {
#         "booking": booking,
#         "activities": Activity.objects.all(),
#         "packages": Package.objects.all(),
#         "rooms": Room.objects.all(),
#         "food": Food.objects.all(),
#         "tours": Tour.objects.all(),
#         "base_template": base_template,  # 🔑 Fix: Add base_template
#     }
#     return render(request, "booking_edit.html", context)


# @login_required(login_url='login')
# def delete_booking(request, pk):
#     booking = get_object_or_404(Booking, pk=pk)

#     # Restrict: Only superusers or the booking owner can delete
#     if not request.user.is_superuser and booking.user != request.user:
#         messages.error(request, "You do not have permission to delete this booking.")
#         return redirect('booking_list')

#     booking.delete()
#     messages.success(request, "Booking deleted successfully!")
#     return redirect('booking_list')




# --------------------------
# Create Booking
# --------------------------
def create_booking(request):
    if request.method == "POST":
        # Customer details
        customer_name = request.user.username if request.user.is_authenticated else request.POST.get("customer_name")
        customer_email = request.user.email if request.user.is_authenticated else request.POST.get("customer_email")

        booking_check_in = request.POST.get("check_in")
        booking_check_out = request.POST.get("check_out")
        booking_pax = int(request.POST.get("pax", 1))

        selected_room_ids = request.POST.getlist("rooms")
        selected_package_ids = request.POST.getlist("packages")
        selected_activity_ids = request.POST.getlist("activities")
        selected_food_ids = request.POST.getlist("food")
        selected_tour_ids = request.POST.getlist("tours")

        # Validate dates
        if not booking_check_in or not booking_check_out:
            messages.error(request, "Please select both check-in and check-out dates.")
            return redirect("create_booking")

        if booking_check_out < booking_check_in:
            messages.error(request, "Check-out date cannot be before check-in.")
            return redirect("create_booking")

        # Validate room availability
        for room_id in selected_room_ids:
            room = get_object_or_404(Room, id=room_id)
            overlapping = Booking.objects.filter(
                booking_rooms=room,
                booking_check_in__lt=booking_check_out,
                booking_check_out__gt=booking_check_in
            ).count()
            if overlapping >= room.room_room_type.roomType_total_rooms:
                messages.error(request, f"Room '{room.room_name}' is fully booked for the selected dates.")
                return redirect("create_booking")

        # Role-based restrictions
        if not (request.user.is_staff or request.user.is_superuser):
            selected_activity_ids = []
            selected_food_ids = []
            selected_tour_ids = []

        # Collect per-item pax values
        booking_pax_details = {}

        activities_pax = int(request.POST.get("activities_pax", 1))
        if selected_activity_ids:
            booking_pax_details['activities'] = {'ids': selected_activity_ids, 'pax': activities_pax}

        packages_pax = int(request.POST.get("packages_pax", 1))
        if selected_package_ids:
            booking_pax_details['packages'] = {'ids': selected_package_ids, 'pax': packages_pax}

        rooms_pax = int(request.POST.get("rooms_pax", 1))
        if selected_room_ids:
            booking_pax_details['rooms'] = {'ids': selected_room_ids, 'pax': rooms_pax}

        food_pax = int(request.POST.get("food_pax", 1))
        if selected_food_ids:
            booking_pax_details['food'] = {'ids': selected_food_ids, 'pax': food_pax}

        tours_pax = int(request.POST.get("tours_pax", 1))
        if selected_tour_ids:
            booking_pax_details['tours'] = {'ids': selected_tour_ids, 'pax': tours_pax}

        # Create booking
        booking = Booking.objects.create(
            booking_user=request.user if request.user.is_authenticated else None,
            booking_customer_name=customer_name,
            booking_customer_email=customer_email,
            booking_check_in=booking_check_in,
            booking_check_out=booking_check_out,
            booking_pax=booking_pax,
            booking_pax_details=booking_pax_details
        )

        # Set ManyToMany relationships
        booking.booking_rooms.set(selected_room_ids)
        booking.booking_packages.set(selected_package_ids)
        booking.booking_activities.set(selected_activity_ids)
        booking.booking_food.set(selected_food_ids)
        booking.booking_tours.set(selected_tour_ids)

        messages.success(request, "Booking created successfully! Proceed to payment!")
        return redirect("pay_booking", booking_id=booking.id)

    # Choose base template dynamically
    base_template = (
        "base.admin.html" if request.user.is_superuser
        else "base.staff.html" if request.user.is_staff
        else "base.user.html" if request.user.is_authenticated
        else "base.html"
    )

    context = {
        "base_template": base_template,
        "activities": Activity.objects.all(),
        "packages": Package.objects.all(),
        "rooms": Room.objects.all(),
        "food": Food.objects.all(),
        "tours": Tour.objects.all(),
    }

    return render(request, "booking_create.html", context)


# --------------------------
# Admin Create Booking for Users
# --------------------------
@login_required
def admin_create_booking(request):
    # Only admins/staff should access this.
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "You are not allowed to access this page.")
        return redirect("booking_list")

    users = User.objects.all().order_by("username")
    activities = Activity.objects.all()
    packages = Package.objects.all()
    rooms = Room.objects.all()
    food_items = Food.objects.all()
    tours = Tour.objects.all()

    if request.method == "POST":
        selected_user_id = request.POST.get("user")
        booking_check_in = request.POST.get("check_in")
        booking_check_out = request.POST.get("check_out")
        booking_pax = int(request.POST.get("pax", 1))

        if not selected_user_id:
            messages.error(request, "Please select a user.")
            return redirect("admin_create_booking")

        # Create booking
        booking = Booking.objects.create(
            booking_user=User.objects.get(id=selected_user_id),
            booking_check_in=booking_check_in,
            booking_check_out=booking_check_out,
            booking_pax=booking_pax
        )

        # M2M assignments
        booking.booking_activities.set(request.POST.getlist("activities"))
        booking.booking_packages.set(request.POST.getlist("packages"))
        booking.booking_rooms.set(request.POST.getlist("rooms"))
        booking.booking_food.set(request.POST.getlist("food"))
        booking.booking_tours.set(request.POST.getlist("tours"))

        messages.success(request, "Booking created for user successfully! Proceed to payment to complete booking.")
        return redirect("pay_booking", booking_id=booking.id)

    return render(request, "booking.create_for_user.html", {
        "users": users,
        "activities": activities,
        "packages": packages,
        "rooms": rooms,
        "food_items": food_items,
        "tours": tours,
        "base_template": "base.admin.html"
    })


# --------------------------
# Bookings Payment
# --------------------------
def pay_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    if request.method == "POST":
        phone = request.POST.get("phone")
        amount = booking.amount_required  # use your model property

        # Initiate STK push

        result = initiate_stk_push(phone, amount)

        if result.get("ResponseCode") == "0":
            messages.success(request, "STK Push initiated successfully! Complete the payment on your phone.")
        else:
            messages.error(request, f"Payment initiation failed: {result.get('errorMessage', 'Unknown error')}")

        return redirect("booking_list")  # redirect after initiating payment
    
    # Select base template dynamically
    base_template = (
        "base.admin.html" if request.user.is_superuser
        else "base.staff.html" if request.user.is_staff
        else "base.user.html" if request.user.is_authenticated
        else "base.html"
    )

    return render(request, "pay_booking.html", {
        "booking": booking,
        "base_template": base_template,
        "navbar": "stk"
    })

# --------------------------
# Upcoming Bookings
# --------------------------
@login_required
def upcoming_bookings_list(request):
    upcoming_bookings = Booking.objects.filter(
        booking_check_in__gte=timezone.now()
    ).order_by("booking_check_in")

    # Add display_pax_details
    for booking in upcoming_bookings:
        details = []
        if booking.booking_pax_details:
            for category, data in booking.booking_pax_details.items():
                ids = data.get("ids", [])
                pax = data.get("pax", booking.booking_pax)
                model_map = {
                    "rooms": Room,
                    "activities": Activity,
                    "packages": Package,
                    "food": Food,
                    "tours": Tour
                }
                ModelClass = model_map.get(category)
                if ModelClass:
                    items = ModelClass.objects.filter(id__in=ids)
                    item_names = ", ".join([getattr(item, f"{category[:-1]}_name", str(item)) for item in items])
                    details.append(f"{category.title()}: {item_names} (Pax: {pax})")
        booking.display_pax_details = details

    base_template = "base.admin.html" if request.user.is_superuser else "base.staff.html"

    return render(request, "bookings.upcoming.html", {
        "upcoming_bookings": upcoming_bookings,
        "base_template": base_template
    })


# --------------------------
# Booking List
# --------------------------

# @login_required
# def booking_list(request):
#     # Prefetch related fields to reduce queries
#     bookings = Booking.objects.prefetch_related(
#         "booking_rooms",
#         "booking_activities",
#         "booking_packages",
#         "booking_food",
#         "booking_tours"
#     ).order_by("-booking_created_at")

#     today = timezone.localdate()
    
#     # Determine bookings based on role
#     if request.user.is_superuser:
#         # Admin sees all bookings
#         filtered_bookings = bookings
#         editable_ids = bookings.values_list("id", flat=True)
#     elif request.user.is_staff:
#         # Staff sees bookings that are upcoming or ongoing
#         filtered_bookings = bookings.filter(booking_check_out__gte=today)
#         editable_ids = filtered_bookings.values_list("id", flat=True)
#     else:
#         # Regular user sees only their own bookings
#         filtered_bookings = bookings.filter(booking_user=request.user)
#         editable_ids = filtered_bookings.values_list("id", flat=True)

#     # Calculate total payable for user bookings
#     total_payable = None
#     if not request.user.is_superuser and not request.user.is_staff:
#         total_payable = sum(b.amount_required for b in filtered_bookings)

#     return render(request, "bookings.html", {
#         "bookings": filtered_bookings,
#         "editable_ids": set(editable_ids),
#         "base_template": "base.admin.html" if request.user.is_superuser else
#                          "base.staff.html" if request.user.is_staff else
#                          "base.user.html",
#         "total_payable": total_payable,
#     })


@login_required
def booking_list(request):
    bookings = Booking.objects.prefetch_related(
        "booking_rooms",
        "booking_activities",
        "booking_packages",
        "booking_food",
        "booking_tours"
    ).order_by("-booking_created_at")

    # Search query
    q = request.GET.get("q")
    if q:
        bookings = bookings.filter(
            Q(booking_user__username__icontains=q) |
            Q(booking_customer_name__icontains=q) |
            Q(booking_customer_email__icontains=q)
        )

    mine = request.GET.get('mine') == '1'

    base_template = "base.user.html"
    editable_ids = []

    if request.user.is_superuser:
        base_template = "base.admin.html"
        if mine:
            bookings = bookings.filter(booking_user=request.user)
        editable_ids = bookings.values_list("id", flat=True)

    elif request.user.is_staff:
        base_template = "base.staff.html"
        if mine:
            bookings = bookings.filter(booking_user=request.user)
        else:
            bookings = bookings.filter(booking_check_out__gte=timezone.now())
        editable_ids = bookings.values_list("id", flat=True)

    else:
        bookings = bookings.filter(booking_user=request.user)
        editable_ids = bookings.values_list("id", flat=True)

    total_payable = 0
    if not request.user.is_superuser or mine:
        for booking in bookings:
            total = 0
            for activity in booking.booking_activities.all():
                total += activity.activity_price_per_person * booking.booking_pax
            for package in booking.booking_packages.all():
                total += package.package_price_per_person * booking.nights_spent
            for room in booking.booking_rooms.all():
                total += room.room_room_type.roomType_price_per_night * booking.nights_spent
            for food in booking.booking_food.all():
                total += food.food_price_per_person * booking.booking_pax
            for tour in booking.booking_tours.all():
                total += tour.tour_price_per_person

            total_payable += total

    return render(request, "bookings.html", {
        "bookings": bookings,
        "editable_ids": set(editable_ids),
        "base_template": base_template,
        "total_payable": total_payable,
        "mine": mine
    })


@login_required
def staff_bookings(request):
    # Staff + Admin: view their own bookings in CARD FORMAT
    my_bookings = Booking.objects.filter(booking_user=request.user).order_by("-booking_created_at")

    
    if request.user.is_superuser:
        base_template = "base.admin.html"
    else:
        base_template = "base.staff.html"
    

    return render(request, "staff.bookings.html", {
        "bookings": my_bookings,
        "base_template": base_template
    })

# --------------------------
# Edit Booking
# --------------------------
@login_required
def edit_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)

    # Permission
    if not request.user.is_superuser and booking.booking_user != request.user:
        messages.error(request, "You do not have permission to edit this booking.")
        return redirect("booking_list")

    if request.method == "POST":
        booking_check_in = request.POST.get("check_in")
        booking_check_out = request.POST.get("check_out")
        booking_pax = int(request.POST.get("pax", 1))
        selected_room_ids = request.POST.getlist("rooms")

        # Validate dates
        if booking_check_out < booking_check_in:
            messages.error(request, "Check-out date must be after check-in.")
            return redirect("edit_booking", pk=booking.pk)

        # Validate room availability
        for room_id in selected_room_ids:
            room = get_object_or_404(Room, id=room_id)
            overlapping = Booking.objects.filter(
                booking_rooms=room,
                booking_check_in__lt=booking_check_out,
                booking_check_out__gt=booking_check_in
            ).exclude(id=booking.id).count()
            if overlapping >= room.room_room_type.roomType_total_rooms:
                messages.error(request, f"Room '{room.room_name}' is fully booked for the selected dates.")
                return redirect("edit_booking", pk=booking.pk)

        # Update booking
        booking.booking_check_in = booking_check_in
        booking.booking_check_out = booking_check_out
        booking.booking_pax = booking_pax
        booking.booking_rooms.set(selected_room_ids)
        booking.booking_packages.set(request.POST.getlist("packages"))
        booking.booking_activities.set(request.POST.getlist("activities"))
        booking.booking_food.set(request.POST.getlist("food"))
        booking.booking_tours.set(request.POST.getlist("tours"))
        booking.save()

        messages.success(request, "Booking updated successfully!")
        return redirect("booking_list")

    # Base template
    base_template = (
        "base.admin.html" if request.user.is_superuser
        else "base.staff.html"
        if request.user.groups.filter(name="Staff").exists()
        else "base.user.html"
    )

    return render(request, "booking_edit.html", {
        "booking": booking,
        "activities": Activity.objects.all(),
        "packages": Package.objects.all(),
        "rooms": Room.objects.all(),
        "food": Food.objects.all(),
        "tours": Tour.objects.all(),
        "base_template": base_template
    })


# --------------------------
# Delete Booking
# --------------------------
@login_required
def delete_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)

    # Permission
    if not request.user.is_superuser and booking.booking_user != request.user:
        messages.error(request, "You do not have permission to delete this booking.")
        return redirect("booking_list")

    booking.delete()
    messages.success(request, "Booking deleted successfully!")
    return redirect("booking_list")

# --------------------------
# Generating Bookings Document
# --------------------------
@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def print_bookings(request):

    if request.method == "POST":
        # Get selected booking IDs for printing
        booking_ids = request.POST.getlist('booking_ids')

        # Get search query
        q = request.POST.get("q", "")

        # Base queryset
        if booking_ids:
            bookings = Booking.objects.filter(id__in=booking_ids).order_by('-booking_created_at')
        else:
            bookings = Booking.objects.all().order_by('-booking_created_at')

        # Apply search filter
        if q:
            bookings = bookings.filter(
                Q(booking_user__username__icontains=q) |
                Q(booking_customer_name__icontains=q) |
                Q(booking_customer_email__icontains=q)
            )

        total_bookings = bookings.count()
        total_payable = sum([b.amount_required for b in bookings])

        # PDF setup
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Title
        p.setFont("Helvetica-Bold", 18)
        p.drawString(50, height - 50, "EpicTrail Adventures - Bookings Report")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Summary
        y = height - 100
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, f"Total Bookings: {total_bookings}")
        p.drawString(200, y, f"Total Payable: KSh {total_payable:,.2f}")
        y -= 30

        # Table headers
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50, y, "Customer")
        p.drawString(170, y, "Booking Services")
        p.drawString(470, y, "Check-In")
        p.drawString(540, y, "Booked On")
        p.drawString(610, y, "Total KSh")
        p.setFont("Helvetica", 9)
        y -= 20

        # Helper to truncate long text
        def truncate_list(items, limit=50):
            text = ', '.join(str(i) for i in items)
            return text if len(text) <= limit else text[:limit] + '...'

        for b in bookings:
            if y < 80:  # New page if too close to bottom
                p.showPage()
                y = height - 50
                p.setFont("Helvetica", 9)

            customer = b.booking_user.username if b.booking_user else b.booking_customer_name or "Guest"
            services = truncate_list(
                list(b.booking_activities.all()) +
                list(b.booking_packages.all()) +
                list(b.booking_rooms.all()) +
                list(b.booking_food.all()) +
                list(b.booking_tours.all())
            )
            check_in = b.booking_check_in.strftime("%Y-%m-%d") if b.booking_check_in else "N/A"
            booked_on = b.booking_created_at.strftime("%Y-%m-%d") if b.booking_created_at else "N/A"
            total = f"KSh {b.amount_required:,.2f}"

            p.drawString(50, y, customer)
            p.drawString(170, y, services)
            p.drawString(470, y, check_in)
            p.drawString(540, y, booked_on)
            p.drawString(610, y, total)
            y -= 20

        p.showPage()
        p.save()

        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = "attachment; filename=Bookings_Report.pdf"
        return response

    # Redirect to bookings page if GET
    return redirect('booking_list')




@login_required
@user_passes_test(admin_required)
def notifications_view(request):
    if request.user.is_staff:
        notifications = Notification.objects.all().order_by('-created_at')
    else:
        notifications = request.user.notifications.all().order_by('-created_at')

    # Filtering
    notif_type = request.GET.get('type')
    unread = request.GET.get('unread')
    if notif_type:
        notifications = notifications.filter(type=notif_type)
    if unread:
        notifications = notifications.filter(is_read=False)

    return render(request, 'notifications.html', {'notifications': notifications})

@login_required
@user_passes_test(admin_required)
def mark_notification_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk)
    if notif.user == request.user or request.user.is_staff:
        notif.is_read = True
        notif.save()
    return redirect('notifications')


def explore(request):
    activities = Activity.objects.all()
    rooms = Room.objects.all()
    tours = Tour.objects.all()

    # Decide base template based on user authentication
    base_template = 'base.user.html' if request.user.is_authenticated else 'base.html'

    return render(request, 'explore.html', {
        'activities': activities,
        'rooms': rooms,
        'tours': tours,
        'base_template': base_template,
    })


# @login_required
# @user_passes_test(admin_required)
# def reports_analytics(request):
#     # --- Determine if admin or regular user ---
#     if request.user.is_superuser:
#         bookings = Booking.objects.all()
#         orders = FoodOrder.objects.all()
#     else:
#         today = timezone.now().date()
#         bookings = Booking.objects.filter(booking_user=request.user, booking_check_in__gte=today)
#         orders = FoodOrder.objects.filter(foodOrder_user=request.user)

#     total_bookings = bookings.count()
#     total_revenue = sum(b.amount_required for b in bookings)

#     # Food orders
#     total_orders = orders.count()
#     orders_with_total = orders.annotate(
#         order_total=ExpressionWrapper(
#             F("foodOrder_food__food_price_per_person") * F("foodOrder_quantity"),
#             output_field=DecimalField()
#         )
#     )
#     total_order_revenue = orders_with_total.aggregate(total=Sum("order_total"))["total"] or 0

#     # Revenue by category
#     revenue_activities = sum(sum(a.activity_price_per_person * b.booking_pax for a in b.booking_activities.all()) for b in bookings)
#     revenue_packages = sum(sum(p.package_price_per_person * b.booking_pax for p in b.booking_packages.all()) for b in bookings)
#     revenue_rooms = sum(sum(r.room_room_type.roomType_price_per_night * b.booking_pax * b.nights_spent for r in b.booking_rooms.all()) for b in bookings)
#     revenue_tours = sum(sum(t.tour_price_per_person * b.booking_pax for t in b.booking_tours.all()) for b in bookings)

#     # Monthly data (only for bookings)
#     monthly_data = (
#         bookings.annotate(month=ExtractMonth('booking_created_at'))
#         .values('month')
#         .annotate(total=Count('id'), revenue=Sum('paid'))
#     )
#     months = [calendar.month_abbr[i] for i in range(1, 13)]
#     monthly_bookings = [0] * 12
#     monthly_revenue = [0] * 12
#     for entry in monthly_data:
#         idx = entry['month'] - 1
#         monthly_bookings[idx] = entry['total']
#         monthly_revenue[idx] = float(entry['revenue'] or 0)

#     # Pie chart data
#     pie_labels = ["Activities", "Packages", "Rooms", "Tours", "Food Orders"]
#     pie_data = [revenue_activities, revenue_packages, revenue_rooms, revenue_tours, total_order_revenue]

#     # Top booked items
#     popular_activities = Activity.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]
#     popular_packages = Package.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]
#     popular_rooms = Room.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]
#     popular_tours = Tour.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]

#     # --- CSV Export ---
#     if request.GET.get("export") == "csv":
#         response = HttpResponse(content_type="text/csv")
#         response["Content-Disposition"] = f'attachment; filename="EpicTrail-Report_{datetime.now().strftime("%Y%m%d")}.csv"'
#         writer = csv.writer(response)

#         # Bookings
#         writer.writerow(["--- BOOKINGS REPORT ---"])
#         writer.writerow(["Customer", "Booking Date", "Guests", "Revenue (KSh)"])
#         bookings_total = 0
#         for b in bookings:
#             customer = str(b.booking_user) if b.booking_user else (b.booking_customer_name or "Guest")
#             booking_date = b.booking_created_at.strftime('%Y-%m-%d')
#             revenue = round(b.amount_required, 2)
#             bookings_total += revenue
#             writer.writerow([customer, booking_date, b.booking_pax, revenue])
#         writer.writerow(["", "", "Total Bookings Revenue", bookings_total])
#         writer.writerow([])

#         # Food orders
#         writer.writerow(["--- FOOD ORDERS REPORT ---"])
#         writer.writerow(["Customer", "Order Date", "Food Item", "Quantity", "Revenue (KSh)"])
#         food_total = 0
#         for o in orders_with_total:
#             customer = str(o.foodOrder_user) if o.foodOrder_user else "Guest"
#             order_date = o.foodOrder_created_at.strftime('%Y-%m-%d')
#             revenue = round(o.order_total, 2)
#             food_total += revenue
#             writer.writerow([customer, order_date, o.foodOrder_food.food_name, o.foodOrder_quantity, revenue])
#         writer.writerow(["", "", "", "Total Food Revenue", food_total])
#         return response

#     # --- PDF Export ---
#     if request.GET.get("export") == "pdf":
#         response = HttpResponse(content_type="application/pdf")
#         response["Content-Disposition"] = f'attachment; filename="EpicTrail-Report_{datetime.now().strftime("%Y%m%d")}.pdf"'
#         p = canvas.Canvas(response, pagesize=A4)
#         width, height = A4

#         # Title
#         p.setFont("Helvetica-Bold", 18)
#         p.drawString(50, height - 50, "EpicTrail Adventures - Analytics Report")
#         p.setFont("Helvetica", 10)
#         p.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

#         # Bookings Section
#         y = height - 110
#         p.setFont("Helvetica-Bold", 14)
#         p.drawString(50, y, "Bookings Report")
#         y -= 30
#         p.setFont("Helvetica-Bold", 12)
#         p.drawString(50, y, "Customer")
#         p.drawString(200, y, "Booking Date")
#         p.drawString(350, y, "Revenue (KSh)")
#         p.setFont("Helvetica", 10)
#         bookings_total = 0
#         for b in bookings:
#             y -= 20
#             if y < 80:
#                 p.showPage()
#                 y = height - 50
#             customer = str(b.booking_user) if b.booking_user else (b.booking_customer_name or "Guest")
#             booking_date = b.booking_created_at.strftime('%Y-%m-%d')
#             revenue = round(b.amount_required, 2)
#             bookings_total += revenue
#             p.drawString(50, y, customer)
#             p.drawString(200, y, booking_date)
#             p.drawString(350, y, f"KSh {revenue:,.2f}")
#         y -= 30
#         p.setFont("Helvetica-Bold", 12)
#         p.drawString(50, y, f"Total Bookings Revenue: KSh {bookings_total:,.2f}")

#         # Food Orders Section
#         y -= 60
#         p.setFont("Helvetica-Bold", 14)
#         p.drawString(50, y, "Food Orders Report")
#         y -= 30
#         p.setFont("Helvetica-Bold", 12)
#         p.drawString(50, y, "Customer")
#         p.drawString(200, y, "Order Date")
#         p.drawString(300, y, "Food Item")
#         p.drawString(450, y, "Revenue (KSh)")
#         p.setFont("Helvetica", 10)
#         food_total = 0
#         for o in orders_with_total:
#             y -= 20
#             if y < 80:
#                 p.showPage()
#                 y = height - 50
#             customer = str(o.foodOrder_user) if o.foodOrder_user else "Guest"
#             order_date = o.foodOrder_created_at.strftime('%Y-%m-%d')
#             revenue = round(o.order_total, 2)
#             food_total += revenue
#             p.drawString(50, y, customer)
#             p.drawString(200, y, order_date)
#             p.drawString(300, y, o.foodOrder_food.food_name)
#             p.drawString(450, y, f"KSh {revenue:,.2f}")
#         y -= 30
#         p.setFont("Helvetica-Bold", 12)
#         p.drawString(50, y, f"Total Food Revenue: KSh {food_total:,.2f}")

#         p.showPage()
#         p.save()
#         return response

#     # --- Web render ---
#     return render(request, "reports_analytics.html", {
#         "bookings": bookings,
#         "total_bookings": total_bookings,
#         "total_revenue": total_revenue,
#         "revenue_activities": revenue_activities,
#         "revenue_packages": revenue_packages,
#         "revenue_rooms": revenue_rooms,
#         "revenue_tours": revenue_tours,
#         "total_orders": total_orders,
#         "total_order_revenue": total_order_revenue,
#         "months": months,
#         "monthly_bookings": monthly_bookings,
#         "monthly_revenue": monthly_revenue,
#         "pie_labels": pie_labels,
#         "pie_data": pie_data,
#         "popular_activities": popular_activities,
#         "popular_packages": popular_packages,
#         "popular_rooms": popular_rooms,
#         "popular_tours": popular_tours,
#     })
@login_required
@user_passes_test(admin_required)
def reports_analytics(request):
    # --- Determine if admin or regular user ---
    if request.user.is_superuser:
        bookings = Booking.objects.all().order_by('-booking_created_at')
        orders = FoodOrder.objects.all().order_by('-foodOrder_created_at')
    else:
        today = timezone.now().date()
        bookings = Booking.objects.filter(booking_user=request.user, booking_check_in__gte=today)
        orders = FoodOrder.objects.filter(foodOrder_user=request.user)

    total_bookings = bookings.count()
    total_revenue = sum(b.paid for b in bookings)

    # Food orders
    total_orders = orders.count()
    orders_with_total = orders.annotate(
        order_total=ExpressionWrapper(
            F("foodOrder_food__food_price_per_person") * F("foodOrder_quantity"),
            output_field=DecimalField()
        )
    )
    total_order_revenue = orders_with_total.aggregate(total=Sum("order_total"))["total"] or 0

    # Revenue by category
    revenue_activities = sum(
        sum(a.activity_price_per_person * b.booking_pax for a in b.booking_activities.all()) for b in bookings
    )
    revenue_packages = sum(
        sum(p.package_price_per_person * b.booking_pax for p in b.booking_packages.all()) for b in bookings
    )
    revenue_rooms = sum(
        sum(r.room_room_type.roomType_price_per_night * b.booking_pax * b.nights_spent for r in b.booking_rooms.all()) for b in bookings
    )
    revenue_tours = sum(
        sum(t.tour_price_per_person * b.booking_pax for t in b.booking_tours.all()) for b in bookings
    )

    # --- Monthly data using amount_required property ---
    months = [calendar.month_abbr[i] for i in range(1, 13)]
    monthly_bookings = [0] * 12
    monthly_revenue = [0] * 12
    for b in bookings:
        month_idx = b.booking_created_at.month - 1
        monthly_bookings[month_idx] += 1
        monthly_revenue[month_idx] += float(b.paid)

    # Pie chart data
    pie_labels = ["Activities", "Packages", "Rooms", "Tours", "Food Orders"]
    pie_data = [revenue_activities, revenue_packages, revenue_rooms, revenue_tours, total_order_revenue]

    # Top booked items
    popular_activities = Activity.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]
    popular_packages = Package.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]
    popular_rooms = Room.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]
    popular_tours = Tour.objects.annotate(num_bookings=Count('booking')).order_by('-num_bookings')[:5]

    # --- CSV Export ---
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="EpicTrail-Report_{datetime.now().strftime("%Y%m%d")}.csv"'
        writer = csv.writer(response)

        # Bookings
        writer.writerow(["--- BOOKINGS REPORT ---"])
        writer.writerow(["Customer", "Booking Date", "Guests", "Revenue (KSh)"])
        bookings_total = 0
        for b in bookings:
            customer = str(b.booking_user) if b.booking_user else (b.booking_customer_name or "Guest")
            booking_date = b.booking_created_at.strftime('%Y-%m-%d')
            revenue = round(b.amount_required, 2)
            bookings_total += revenue
            writer.writerow([customer, booking_date, b.booking_pax, revenue])
        writer.writerow(["", "", "Total Bookings Revenue", bookings_total])
        writer.writerow([])

        # Food orders
        writer.writerow(["--- FOOD ORDERS REPORT ---"])
        writer.writerow(["Customer", "Order Date", "Food Item", "Quantity", "Revenue (KSh)"])
        food_total = 0
        for o in orders_with_total:
            customer = str(o.foodOrder_user) if o.foodOrder_user else "Guest"
            order_date = o.foodOrder_created_at.strftime('%Y-%m-%d')
            revenue = round(o.order_total, 2)
            food_total += revenue
            writer.writerow([customer, order_date, o.foodOrder_food.food_name, o.foodOrder_quantity, revenue])
        writer.writerow(["", "", "", "Total Food Revenue", food_total])
        return response

    # --- PDF Export ---
    if request.GET.get("export") == "pdf":
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="EpicTrail-Report_{datetime.now().strftime("%Y%m%d")}.pdf"'
        p = canvas.Canvas(response, pagesize=A4)
        width, height = A4

        # Title
        p.setFont("Helvetica-Bold", 18)
        p.drawString(50, height - 50, "EpicTrail Adventures - Analytics Report")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Bookings Section
        y = height - 110
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Bookings Report")
        y -= 30
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "Customer")
        p.drawString(200, y, "Booking Date")
        p.drawString(350, y, "Revenue (KSh)")
        p.setFont("Helvetica", 10)
        bookings_total = 0
        for b in bookings:
            y -= 20
            if y < 80:
                p.showPage()
                y = height - 50
                # Reset font after new page
                p.setFont("Helvetica", 10)

            customer = str(b.booking_user) if b.booking_user else (b.booking_customer_name or "Guest")
            booking_date = b.booking_created_at.strftime('%Y-%m-%d')
            revenue = round(b.amount_required, 2)
            bookings_total += revenue
            p.drawString(50, y, customer)
            p.drawString(200, y, booking_date)
            p.drawString(350, y, f"KSh {revenue:,.2f}")
        y -= 30
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, f"Total Bookings Revenue: KSh {bookings_total:,.2f}")

        # Food Orders Section
        y -= 60
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Food Orders Report")
        y -= 30
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "Customer")
        p.drawString(200, y, "Order Date")
        p.drawString(300, y, "Food Item")
        p.drawString(450, y, "Revenue (KSh)")
        p.setFont("Helvetica", 10)
        food_total = 0
        for o in orders_with_total:
            y -= 20
            if y < 80:
                p.showPage()
                y = height - 50
                # Reset font after new page
                p.setFont("Helvetica", 10)

            customer = str(o.foodOrder_user) if o.foodOrder_user else "Guest"
            order_date = o.foodOrder_created_at.strftime('%Y-%m-%d')
            revenue = round(o.order_total, 2)
            food_total += revenue
            p.drawString(50, y, customer)
            p.drawString(200, y, order_date)
            p.drawString(300, y, o.foodOrder_food.food_name)
            p.drawString(450, y, f"KSh {revenue:,.2f}")
        y -= 30
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, f"Total Food Revenue: KSh {food_total:,.2f}")

        p.showPage()
        p.save()
        return response

    # --- Web render ---
    return render(request, "reports_analytics.html", {
        "bookings": bookings,
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "revenue_activities": revenue_activities,
        "revenue_packages": revenue_packages,
        "revenue_rooms": revenue_rooms,
        "revenue_tours": revenue_tours,
        "total_orders": total_orders,
        "total_order_revenue": total_order_revenue,
        "months": months,
        "monthly_bookings": monthly_bookings,
        "monthly_revenue": monthly_revenue,
        "pie_labels": pie_labels,
        "pie_data": pie_data,
        "popular_activities": popular_activities,
        "popular_packages": popular_packages,
        "popular_rooms": popular_rooms,
        "popular_tours": popular_tours,
    })


# --------------------------
# Order Management Operations
# --------------------------

# Order Placement
@login_required
def place_order(request):
    foods = Food.objects.all() 

    if request.method == "POST":
        food_id = request.POST.get("food")
        quantity = int(request.POST.get("quantity"))
        check_in = request.POST.get("foodOrder_check_in")  # get date from form

        food_item = get_object_or_404(Food, id=food_id)

        order = FoodOrder.objects.create(
            foodOrder_user=request.user,
            foodOrder_food=food_item,
            foodOrder_quantity=quantity,
            foodOrder_status="pending",
            foodOrder_check_in=check_in
        )

        messages.success(request, 'Order placed successfully, Please proceed to payment! Enter phone number to complete transaction.')

        return redirect('pay_food_order', order_id=order.id)

    return render(request, "place_order.html", {"foods": foods})

# --------------------------
# Updating Orders
# --------------------------
@login_required
def update_order(request, order_id):
    # Get the order for the current user and only if it's pending
    order = get_object_or_404(FoodOrder, id=order_id, foodOrder_user=request.user, foodOrder_status='pending')
    foods = Food.objects.all()

    if request.method == "POST":
        # Get data from the form
        food_id = request.POST.get("food")
        quantity = int(request.POST.get("quantity", order.foodOrder_quantity))
        check_in = request.POST.get("foodOrder_check_in")

        # Get the selected food
        food = get_object_or_404(Food, id=food_id)

        # Update order fields
        order.foodOrder_food = food
        order.foodOrder_quantity = quantity
        order.foodOrder_check_in = check_in
        order.save()

        messages.success(request, "Order updated successfully.")
        return redirect('my_orders')

    return render(request, 'update_order.html', {
        'order': order,
        'foods': foods
    })



# --------------------------
# Admin placing orders on user behalf
# --------------------------
@login_required
@user_passes_test(is_admin)
def place_order_admin(request):
    users = User.objects.all()
    foods = Food.objects.all()

    if request.method == "POST":
        user_id = request.POST.get("user")
        food_id = request.POST.get("food")
        quantity = int(request.POST.get("quantity", 1))
        check_in = request.POST.get("check_in")

        user = User.objects.get(id=user_id) if user_id else None
        food = get_object_or_404(Food, id=food_id)

        # Create the FoodOrder
        order = FoodOrder.objects.create(
            foodOrder_user=user,
            foodOrder_food=food,
            foodOrder_quantity=quantity,
            foodOrder_check_in=check_in,
            foodOrder_status="Pending"
        )

        return redirect("pay_food_order", order_id=order.id)

        # return redirect("manage_orders")

    return render(request, "place_order_admin.html", {
        "users": users,
        "foods": foods,
        # "order": order
    })

from django.views.decorators.http import require_POST

# --------------------------
# Admin updating order status
# --------------------------
@login_required
@user_passes_test(is_admin)
@require_POST
def update_order_status(request, order_id):
    order = get_object_or_404(FoodOrder, id=order_id)
    new_status = request.POST.get('status')
    if new_status in dict(FoodOrder.STATUS_CHOICES).keys():
        order.foodOrder_status = new_status
        order.save()
        messages.success(request, f"Order #{order.id} updated to {new_status}.")
    else:
        messages.error(request, "Invalid status.")
    return redirect('manage_orders')


# --------------------------
# Food Orders Payment
# --------------------------
# @login_required
# def pay_food_order(request, order_id):
#     order = get_object_or_404(FoodOrder, id=order_id)
#     total_amount = order.total_price()

#     base_template = (
#         "base.admin.html" if request.user.is_superuser
#         else "base.staff.html" if request.user.is_staff
#         else "base.user.html"
#     )

#     if request.method == "POST":
#         phone = request.POST.get("phone")
#         response = initiate_stk_push(phone, total_amount)

#         if response.get("ResponseCode") == "0":
#             messages.success(request, "STK Push initiated! Check your phone to complete the payment.")
#         else:
#             messages.error(request, response.get("errorMessage", "Failed to initiate payment."))

#         return redirect("my_orders")

#     return render(request, "pay_food.html", {
#         "order": order,
#         "total_amount": total_amount,
#         "base_template": base_template,
#     })
@login_required
def pay_food_order(request, order_id):
    order = get_object_or_404(FoodOrder, id=order_id)
    total_amount = order.total_price()

    base_template = (
        "base.admin.html" if request.user.is_superuser
        else "base.staff.html" if request.user.is_staff
        else "base.user.html"
    )

    if request.method == "POST":
        phone = request.POST.get("phone")
        response = initiate_stk_push(phone, total_amount)

        if response.get("ResponseCode") == "0":
            messages.success(request, "STK Push initiated! Check your phone to complete the payment.")
        else:
            messages.error(request, response.get("errorMessage", "Failed to initiate payment."))

        # Redirect admin/staff to manage_orders
        if request.user.is_superuser or request.user.is_staff:
            return redirect("manage_orders")

        # Regular users continue being redirected to my_orders
        return redirect("my_orders")

    return render(request, "pay_food.html", {
        "order": order,
        "total_amount": total_amount,
        "base_template": base_template,
    })


# Admin managing all food order operations
@login_required
@user_passes_test(is_admin)
def manage_orders(request):
    orders = FoodOrder.objects.all().order_by('-foodOrder_created_at')

    # Search functionality
    q = request.GET.get("q", "")
    if q:
        orders = orders.filter(
            Q(foodOrder_user__username__icontains=q) |
            Q(foodOrder_user__email__icontains=q) |
            Q(foodOrder_food__food_name__icontains=q) |
            Q(foodOrder_status__icontains=q)  # <-- Include status
        )

    # POST actions (approve, cancel, complete)
    if request.method == "POST":
        order_id = request.POST.get("order_id")
        action = request.POST.get("action")
        order = get_object_or_404(FoodOrder, id=order_id)

        if action == "approve":
            order.foodOrder_status = "Approved"
        elif action == "cancel":
            order.foodOrder_status = "Cancelled"
        elif action == "completed":
            order.foodOrder_status = "Completed"

        order.save()
        return redirect("manage_orders")

    return render(request, "manage_orders.html", {"orders": orders})

@login_required
@user_passes_test(is_admin)
def update_order_admin(request, order_id):
    order = get_object_or_404(FoodOrder, id=order_id)
    foods = Food.objects.all()
    users = User.objects.all()

    # Add your status list (or load from DB)
    food_statuses = ["Pending", "Approved", "Completed", "Cancelled"]

    if request.method == "POST":
        # Update user (optional)
        user_id = request.POST.get("user")
        if user_id:
            order.foodOrder_user = get_object_or_404(User, id=user_id)
        else:
            order.foodOrder_user = None  # Guest

        # Update food
        food_id = request.POST.get("food")
        if food_id:
            food_item = get_object_or_404(Food, id=food_id)
            order.foodOrder_food = food_item
            order.total_price = food_item.food_price_per_person * int(request.POST.get("quantity", 1))

        # Update quantity
        quantity = int(request.POST.get("quantity", order.foodOrder_quantity))
        order.foodOrder_quantity = quantity
        if order.foodOrder_food:
            order.total_price = order.foodOrder_food.food_price_per_person * quantity

        # Update check-in date
        order.foodOrder_check_in = request.POST.get("check_in")

        # Update status (same structure as food)
        status = request.POST.get("foodOrder_status")
        if status:
            order.foodOrder_status = status

        # Save changes
        order.save()
        messages.success(request, f"Order #{order.id} updated successfully.")
        return redirect("manage_orders")

    context = {
        "order": order,
        "foods": foods,
        "users": users,
        "food_statuses": food_statuses,  # Pass to template
    }
    return render(request, "update_order_admin.html", context)


@login_required
@user_passes_test(is_admin)
def delete_order_admin(request, order_id):
    order = get_object_or_404(FoodOrder, id=order_id)
    order.delete()
    messages.success(request, f"Order #{order_id} has been deleted.")
    return redirect('manage_orders')
    

# Food menu listing
# @login_required
# def food_menu(request):
#     foods = Food.objects.all()
#     return render(request, 'food_menu.html', {'foods': foods})

# User viewing his or her placed orders only
@login_required
def my_orders(request):
    orders = FoodOrder.objects.filter(foodOrder_user=request.user)  # <-- fix here
    return render(request, 'my_orders.html', {'orders': orders})


# User udpdating his or her orders only
@login_required
def update_order(request, order_id):
    order = get_object_or_404(
        FoodOrder, 
        id=order_id, 
        foodOrder_user=request.user,
        foodOrder_status='pending'
    )

    foods = Food.objects.all()  # Fetch all food items to populate the select dropdown

    if request.method == 'POST':
        food_id = request.POST.get('food')
        quantity = int(request.POST.get('quantity', order.foodOrder_quantity))
        check_in = request.POST.get('foodOrder_check_in')

        if food_id:
            food_item = get_object_or_404(Food, id=food_id)
            order.foodOrder_food = food_item

        order.foodOrder_quantity = quantity
        order.foodOrder_check_in = check_in
        order.total_price = order.foodOrder_food.food_price_per_person * quantity
        order.save()

        messages.info(request, "Order updated.")
        return redirect('my_orders')

    return render(request, 'update_order.html', {'order': order, 'foods': foods})

# User canceling or deleting his or her orders only
@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(
        FoodOrder, 
        id=order_id, 
        foodOrder_user=request.user,  # <-- fix here
        foodOrder_status='pending'
    )
    order.foodOrder_status = 'cancelled'
    order.save()
    messages.warning(request, "Order cancelled.")
    return redirect('my_orders')

# --------------------------
# Downloading Receipt Orders
# --------------------------
@login_required
def download_order_receipt(request, order_id):
    # Ensures the user can only download their own orders
    order = get_object_or_404(FoodOrder, id=order_id, foodOrder_user=request.user)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="order_{order.id}_receipt.pdf"'

    # Small receipt size (width=250, height=450 points)
    page_width = 250
    page_height = 450
    p = canvas.Canvas(response, pagesize=(page_width, page_height))

    # Title
    p.setFont("Helvetica-Bold", 14)
    p.drawString(20, page_height - 30, "Order Receipt")

    # Starting Y position
    y = page_height - 60
    p.setFont("Helvetica", 10)

    # User info
    p.drawString(20, y, f"Customer: {order.foodOrder_user.username}")
    y -= 20
    p.drawString(20, y, f"Order ID: {order.id}")
    y -= 20
    p.drawString(20, y, f"Date Ordered: {order.foodOrder_created_at.strftime('%b %d, %Y')}")
    y -= 20

    # Check-In
    if order.foodOrder_check_in:
        p.drawString(20, y, f"Check-In: {order.foodOrder_check_in.strftime('%b %d, %Y')}")
        y -= 20

    # Optional Check-Out if your model ever includes it
    # if hasattr(order, 'foodOrder_check_out') and order.foodOrder_check_out:
    #     p.drawString(20, y, f"Check-Out: {order.foodOrder_check_out.strftime('%b %d, %Y')}")
    #     y -= 20

    # Order details
    p.drawString(20, y, f"Food: {order.foodOrder_food.food_name}")
    y -= 20
    p.drawString(20, y, f"Quantity: {order.foodOrder_quantity}")
    y -= 20
    p.drawString(20, y, f"Total: Ksh {order.total_price():.2f}")
    y -= 20
    p.drawString(20, y, f"Status: {order.foodOrder_status.title()}")

    # Footer
    p.drawString(20, 20, "Thank you for your order!")

    p.showPage()
    p.save()

    return response


# --------------------------
# Admin printing/downloading all/selected orders pdf document
# --------------------------
@login_required
@user_passes_test(is_admin)
def print_orders(request):

    # Get selected order IDs
    order_ids = request.POST.getlist('order_ids')

    # Get filter/search parameters
    q = request.POST.get("q") or request.GET.get("q", "").strip()
    status_filter = request.POST.get("status") or request.GET.get("status", "").strip()
    check_in_filter = request.POST.get("check_in") or request.GET.get("check_in", "").strip()

    # Base queryset
    if order_ids:
        orders = FoodOrder.objects.filter(id__in=order_ids)
    else:
        orders = FoodOrder.objects.all()

    # Apply search filter
    if q:
        orders = orders.filter(
            Q(foodOrder_user__username__icontains=q) |
            Q(foodOrder_food__food_name__icontains=q)
        )

    # Filter by status
    if status_filter:
        orders = orders.filter(foodOrder_status=status_filter)

    # Filter by check-in date
    if check_in_filter:
        orders = orders.filter(foodOrder_check_in=check_in_filter)

    orders = orders.order_by('-foodOrder_created_at')

    total_orders = orders.count()
    total_revenue = sum([o.total_price if not callable(o.total_price) else o.total_price() for o in orders])

    # PDF generation
    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="FoodOrders_Report.pdf"'
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Title
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, "EpicTrail Adventures - Food Orders Report")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Summary
    y = height - 100
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, f"Printed Orders: {total_orders}")
    p.drawString(200, y, f"Total Revenue: KSh {total_revenue:,.2f}")
    y -= 30

    # Table headers
    p.drawString(50, y, "User")
    p.drawString(170, y, "Food")
    p.drawString(300, y, "Qty")
    p.drawString(350, y, "Total Price")
    p.drawString(450, y, "Status")
    p.drawString(520, y, "Check-In")
    p.setFont("Helvetica", 10)

    for order in orders:
        y -= 20
        if y < 80:
            p.showPage()
            y = height - 50
        user = order.foodOrder_user.username if order.foodOrder_user else "Guest"
        food = order.foodOrder_food.food_name if order.foodOrder_food else "N/A"
        qty = str(order.foodOrder_quantity)
        total = f"KSh {order.total_price if not callable(order.total_price) else order.total_price():,.2f}"
        status = order.foodOrder_status
        checkin = order.foodOrder_check_in.strftime("%Y-%m-%d") if order.foodOrder_check_in else "N/A"

        p.drawString(50, y, user)
        p.drawString(170, y, food)
        p.drawString(300, y, qty)
        p.drawString(350, y, total)
        p.drawString(450, y, status)
        p.drawString(520, y, checkin)

    p.showPage()
    p.save()
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    return response


# --------------------------
# Duty management. Assigning duties to staff members
# --------------------------
@login_required
@user_passes_test(admin_required)
def assign_duty(request):
    staff_members = User.objects.filter(is_staff=True)

    if request.method == 'POST':
        staff_id = request.POST.get('duty_staff')
        duty_title = request.POST.get('duty_title')
        duty_description = request.POST.get('duty_description')
        duty_due_date = request.POST.get('duty_due_date')

        # Validate staff selection
        try:
            staff_member = User.objects.get(id=staff_id)
        except User.DoesNotExist:
            messages.error(request, "Selected staff member does not exist.")
            return redirect('assign_duty')

        if not duty_title or not duty_due_date:
            messages.error(request, "Duty title and due date are required.")
            return redirect('assign_duty')

        Duty.objects.create(
            duty_staff=staff_member,
            duty_title=duty_title,
            duty_description=duty_description,
            duty_due_date=duty_due_date
        )
        messages.success(request, "Duty assigned successfully.")
        return redirect('duties')

    duties = Duty.objects.all().order_by('-duty_assigned_on')  # make sure this field exists
    return render(request, 'duty.assign.html', {
        'staff_members': staff_members,
        'duties': duties
    })

# --------------------------
# Duty view listing.
# --------------------------
@login_required
@user_passes_test(admin_required)
def duties(request):
    duties = Duty.objects.all().order_by('-duty_assigned_on')  # make sure field exists
    return render(request, 'duties.html', {'duties': duties})

# --------------------------
# Duty management. updating duties assigned to staff members
# --------------------------
@login_required
def update_duty_status(request, duty_id):
    duty = get_object_or_404(Duty, id=duty_id)

    # Only assigned staff or admin can update
    if request.user != duty.duty_staff and not request.user.is_superuser:
        return HttpResponseForbidden("You are not allowed to update this duty.")

    if request.method == 'POST':
        duty.duty_completed = not duty.duty_completed  # Toggle
        duty.save()
        messages.success(
            request,
            f"Duty '{duty.duty_title}' marked as {'Completed' if duty.duty_completed else 'Pending'}."
        )
        return redirect('duties')

    return render(request, 'duty.update.html', {'duty': duty})

# --------------------------
# Duty management. Staff viewing their assigned duties
# --------------------------
@login_required
def staff_duties(request):
    duties = Duty.objects.filter(duty_staff=request.user).order_by('duty_due_date')  # use correct field name

    if request.method == "POST":
        duty_id = request.POST.get("duty_id")
        duty = get_object_or_404(Duty, id=duty_id, duty_staff=request.user)
        duty.duty_completed = not duty.duty_completed
        duty.save()
        messages.success(
            request,
            f"Duty '{duty.duty_title}' marked as {'Completed' if duty.duty_completed else 'Pending'}."
        )
        return redirect('staff_duties')

    return render(request, "duties.staff.html", {"duties": duties})


# --------------------------
# User profile management
# --------------------------
@login_required
def update_profile(request):
    # Retrieve the currently logged-in User object
    current_user = request.user 
    
    # use 'profile_user' field name for get_or_create
    profile, created = Profile.objects.get_or_create(profile_user=current_user)

    # Determine base template based on role
    if current_user.is_superuser:
        base_template = 'base.admin.html'
    elif current_user.is_staff:
        base_template = 'base.staff.html'
    else:
        base_template = 'base.user.html'

    if request.method == 'POST':
        # Retrieve form data
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        profile_photo = request.FILES.get('photo')

        # Update User fields
        current_user.username = username
        current_user.email = email

        if password:
            current_user.set_password(password)

        current_user.save()

        # Update Profile fields
        if profile_photo:
            profile.profile_photo = profile_photo
        
        profile.save() # Save the profile even if only the photo was updated

        messages.success(request, "Profile updated successfully!")

        # Checking user roles for redirects
        if current_user.is_superuser:
            return redirect('admin_dashboard')
        elif current_user.is_staff:
            return redirect('staff_dashboard')
        else: 
            return redirect('user_dashboard')

    return render(request, 'update_profile.html', {
        # Passing the objects to the template context
        'user': current_user,
        'profile': profile,
        'base_template': base_template
    })

# --------------------------
# Data Backup Management
# --------------------------
@login_required
@user_passes_test(admin_required)
def backup_data(request):
    """
    Creates a downloadable JSON backup of the database.
    """
    # Create an in-memory file
    buffer = io.StringIO()

    # Dump all data into the buffer
    management.call_command('dumpdata', format='json', indent=2, stdout=buffer)

    # Prepare HTTP response
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    response = HttpResponse(buffer.getvalue(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@login_required
@user_passes_test(admin_required)
def system_settings(request):
    settings = SystemSetting.objects.first()
    if not settings:
        settings = SystemSetting.objects.create()

    if request.method == "POST":
        settings.site_name = request.POST.get("site_name")
        settings.support_email = request.POST.get("support_email")
        settings.maintenance_mode = "maintenance_mode" in request.POST
        settings.enable_mpesa = "enable_mpesa" in request.POST
        settings.enable_stripe = "enable_stripe" in request.POST
        settings.max_daily_bookings = int(request.POST.get("max_daily_bookings", 100))
        settings.discount_rate = request.POST.get("discount_rate", 0)
        settings.save()
        return redirect("admin_dashboard")

    return render(request, "system_settings.html", {"settings": settings})


# ------------ M-Pesa Integration views ------------

# ---------- UTILITY FUNCTIONS ----------
# def generate_password():
#     """
#     Generate Lipa na M-Pesa Online password
#     """
#     timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
#     password_str = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
#     password = base64.b64encode(password_str.encode('utf-8')).decode('utf-8')
#     return password, timestamp

# def get_mpesa_access_token():
#     """
#     Get M-Pesa OAuth access token
#     """
#     token_url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
#     response = requests.get(
#         token_url,
#         auth=HTTPBasicAuth(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET)
#     )
#     response_data = response.json()
#     access_token = response_data.get("access_token")
#     if not access_token:
#         raise Exception(f"Failed to get M-Pesa access token: {response_data}")
#     return access_token

# def initiate_stk_push(phone, amount, account_reference="EpicTrail Adventures", transaction_desc="Payment"):
#     """
#     Initiate Lipa na M-Pesa STK Push
#     """
#     password, timestamp = generate_password()
#     access_token = get_mpesa_access_token()
#     stk_url = f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"

#     payload = {
#         "BusinessShortCode": settings.MPESA_SHORTCODE,
#         "Password": password,
#         "Timestamp": timestamp,
#         "TransactionType": "CustomerPayBillOnline",
#         "Amount": amount,
#         "PartyA": phone,
#         "PartyB": settings.MPESA_SHORTCODE,
#         "PhoneNumber": phone,
#         "CallBackURL": settings.CALLBACK_URL,
#         "AccountReference": account_reference,
#         "TransactionDesc": transaction_desc,
#     }

#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json"
#     }

#     response = requests.post(stk_url, json=payload, headers=headers)
#     return response.json()




# ---------- VIEWS ----------
def stk(request):
    return render(request, 'pay.html', {'navbar': 'stk'})

# def token(request):
#     token = get_mpesa_access_token()
#     return render(request, 'token.html', {"token": token})

@csrf_exempt
def mpesa_callback(request):
    """
    Safaricom will send the payment result here.
    """
    if request.method == "POST":
        data = json.loads(request.body.decode('utf-8'))
        print("M-Pesa Callback Data:", data)  # For debugging in console

        try:
            body = data.get('Body', {})
            stk_callback = body.get('stkCallback', {})

            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')

            if result_code == 0:
                # Successful transaction
                metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
                amount = None
                mpesa_receipt_number = None
                phone = None

                for item in metadata:
                    name = item.get('Name')
                    if name == 'Amount':
                        amount = item.get('Value')
                    elif name == 'MpesaReceiptNumber':
                        mpesa_receipt_number = item.get('Value')
                    elif name == 'PhoneNumber':
                        phone = item.get('Value')

                MpesaTransaction.objects.create(
                    phone=phone,
                    amount=amount,
                    mpesa_receipt_number=mpesa_receipt_number,
                    result_code=result_code,
                    result_desc=result_desc,
                )

                print("Payment Successful:", mpesa_receipt_number)
            else:
                print("Payment Failed:", result_desc)

            return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback received successfully"})

        except Exception as e:
            print("Error processing callback:", e)
            return JsonResponse({"ResultCode": 1, "ResultDesc": "Error saving transaction"})

    return JsonResponse({"ResultCode": 1, "ResultDesc": "Invalid request method"})



