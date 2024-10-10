from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory, flash, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO
import random
from string import ascii_uppercase
import redis
import json
import os
import base64
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta, datetime
import requests
import re
import imghdr
from PIL import Image
import io

app = Flask(__name__)
@app.context_processor
def utility_processor():
    return dict(get_room_data=get_room_data)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)  # Set session lifetime to 7 days
app.config["SESSION_COOKIE_SECURE"] = True  # Only send cookie over HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevent JavaScript access to session cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Prevent CSRF attacks
app.config['MAX_PROFILE_SIZE'] = 5 * 1024 * 1024  # 5MB max file size
app.config['ALLOWED_IMAGE_TYPES'] = {'png', 'jpeg', 'jpg', 'gif'}
app.config['PROFILE_UPLOAD_FOLDER'] = 'profile_photos'

# Make sure to set a secure secret key
app.secret_key = "your-secure-secret-key-here"  # Replace with a real secure key in production
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit
socketio = SocketIO(app)

# Initialize Redis connection
redis_client = redis.Redis(
  host='redis-11952.c81.us-east-1-2.ec2.redns.redis-cloud.com',
  port=11952,
  password='GFik9v9s1MxGIoDdZXBYHJIUQLnjiYZS')
    
def save_profile_photo(file, username):
    """Helper function to save and process profile photos"""
    if not file:
        return None
        
    # Verify file type
    file_bytes = file.read()
    file_type = imghdr.what(None, h=file_bytes)
    
    if file_type not in app.config['ALLOWED_IMAGE_TYPES']:
        flash("Invalid image type. Allowed types: PNG, JPEG, JPG, GIF")
        return None
        
    try:
        # Process image with PIL
        image = Image.open(io.BytesIO(file_bytes))
        
        # Resize image to a reasonable size (e.g., 200x200)
        image.thumbnail((200, 200))
        
        # Generate filename and save path
        filename = f"profile_{username}.{file_type}"
        filepath = os.path.join(app.config['PROFILE_UPLOAD_FOLDER'], filename)
        
        # Save processed image
        image.save(filepath)
        
        return filename
    except Exception as e:
        flash("Error processing profile photo")
        return None

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if not redis_client.exists(f"room:{code}"):
            break
    
    return code

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if "username" not in session:
            flash("Please log in to access this page.")
            return redirect(url_for("login"))
        
        # Get user data from Redis to verify user still exists
        user_data = get_user_data(session["username"])
        if not user_data:
            session.clear()
            flash("Your session has expired. Please log in again.")
            return redirect(url_for("login"))
            
        return f(*args, **kwargs)
    return decorated_function

def redirect_if_logged_in(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" in session:
            return redirect(url_for("homepage"))
        return f(*args, **kwargs)
    return decorated_function

def get_user_data(username):
    user_data = redis_client.get(f"user:{username}")
    data = json.loads(user_data) if user_data else None
    # Ensure room_invites exists
    if data and "room_invites" not in data:
        data["room_invites"] = []
        update_user_data(username, data)
    return data

# Helper function to update user data
def update_user_data(username, data):
    redis_client.set(f"user:{username}", json.dumps(data))

def is_valid_username(username):
    return re.match("^[a-zA-Z0-9_.-]+$", username)

def is_strong_password(password):
    return len(password) >= 8 and any(c.isdigit() for c in password) and any(c.isalpha() for c in password)

@app.route("/register", methods=["GET", "POST"])
@redirect_if_logged_in
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # Input validation
        if not username or not password:
            flash("Username and password are required!")
            return redirect(url_for("register"))

        if not is_valid_username(username):
            flash("Username can only contain letters, numbers, dots, underscores, and hyphens.")
            return redirect(url_for("register"))

        if not is_strong_password(password):
            flash("Password must be at least 8 characters long and include letters and numbers.")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match!")
            return redirect(url_for("register"))

        if redis_client.exists(f"user:{username}"):
            flash("Username already exists!")
            return redirect(url_for("register"))

        # Store user in Redis
        user_data = {
            "username": username,
            "password": generate_password_hash(password),
            "friends": [],
            "friend_requests": [],
            "current_room": None,
            "online": False
        }
        redis_client.set(f"user:{username}", json.dumps(user_data))

        flash("Registration successful! Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@redirect_if_logged_in
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Input validation
        if not username or not password:
            flash("Username and password are required!")
            return redirect(url_for("login"))

        user_data = get_user_data(username)
        if not user_data:
            flash("Invalid username or password!")
            return redirect(url_for("login"))

        # Check password hash
        if not check_password_hash(user_data["password"], password):
            flash("Invalid username or password!")
            return redirect(url_for("login"))

        # Set session and update user status
        session["username"] = username
        session.permanent = True
        user_data["online"] = True
        update_user_data(username, user_data)

        return redirect(url_for("home"))  # Changed from "homepage" to "home"

    return render_template("login.html")

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        new_username = request.form.get("new_username")
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_new_password = request.form.get("confirm_new_password")
        profile_photo = request.files.get("profile_photo")
        
        user_data = get_user_data(session["username"])
        
        # Handle profile photo upload
        if profile_photo:
            filename = save_profile_photo(profile_photo, session["username"])
            if filename:
                user_data["profile_photo"] = filename
                update_user_data(session["username"], user_data)
                flash("Profile photo updated successfully!")
        
        # Rest of the existing settings logic...
        if current_password and not check_password_hash(user_data["password"], current_password):
            flash("Current password is incorrect!")
            return redirect(url_for("settings"))
        
        if new_username and new_username != session["username"]:
            if not is_valid_username(new_username):
                flash("Username can only contain letters, numbers, dots, underscores, and hyphens.")
                return redirect(url_for("settings"))
                
            if redis_client.exists(f"user:{new_username}"):
                flash("Username already exists!")
                return redirect(url_for("settings"))
                
            # Update username
            old_username = session["username"]
            user_data["username"] = new_username
            
            # Delete old key and create new one
            redis_client.delete(f"user:{old_username}")
            update_user_data(new_username, user_data)
            
            # Update username in session
            session["username"] = new_username
            flash("Username updated successfully!")
        
        if new_password:
            if not is_strong_password(new_password):
                flash("Password must be at least 8 characters long and include letters and numbers.")
                return redirect(url_for("settings"))
                
            if new_password != confirm_new_password:
                flash("New passwords do not match!")
                return redirect(url_for("settings"))
                
            # Update password
            user_data["password"] = generate_password_hash(new_password)
            update_user_data(session["username"], user_data)
            flash("Password updated successfully!")
        
        return redirect(url_for("settings"))
    
    # Get current user data for displaying profile photo
    user_data = get_user_data(session["username"])
    return render_template("settings.html", user_data=user_data)

@app.route("/logout")
@login_required
def logout():
    # Update user's online status
    user_data = get_user_data(session["username"])
    if user_data:
        user_data["online"] = False
        update_user_data(session["username"], user_data)
    
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))

@app.route("/friends")
@login_required
def friends():
    """Redirect to home page since friends page is now merged"""
    return redirect(url_for("home"))
    
def handle_friend_request(username, friend_username):
    if not redis_client.exists(f"user:{friend_username}"):
        flash("User not found!")
        return redirect(url_for("home"))
        
    if friend_username == username:
        flash("You cannot add yourself as a friend!")
        return redirect(url_for("home"))
        
    friend_data = json.loads(redis_client.get(f"user:{friend_username}"))
    if username in friend_data.get("friends", []):
        flash("Already friends!")
        return redirect(url_for("home"))
        
    friend_data.setdefault("friend_requests", []).append(username)
    redis_client.set(f"user:{friend_username}", json.dumps(friend_data))
    
    flash(f"Friend request sent to {friend_username}!")
    return redirect(url_for("home"))

@app.route("/add_friend", methods=["POST"])
@login_required
def add_friend():
    friend_username = request.form.get("friend_username")
    if not friend_username:
        flash("Please enter a username.")
        return redirect(url_for("home"))
    
    if not redis_client.exists(f"user:{friend_username}"):
        flash("User not found!")
        return redirect(url_for("home"))
    
    username = session["username"]
    if friend_username == username:
        flash("You cannot add yourself as a friend!")
        return redirect(url_for("home"))
    
    friend_data = json.loads(redis_client.get(f"user:{friend_username}"))
    
    # Check if they're already friends
    if username in friend_data.get("friends", []):
        flash("Already friends!")
        return redirect(url_for("home"))
    
    # Check if there's a pending request from the current user
    if username in friend_data.get("friend_requests", []):
        flash("You already have a pending friend request to this user!")
        return redirect(url_for("home"))
    
    # Check if there's a pending request from the target user
    user_data = json.loads(redis_client.get(f"user:{username}"))
    if friend_username in user_data.get("friend_requests", []):
        flash("This user has already sent you a friend request! Check your friend requests to accept it.")
        return redirect(url_for("home"))
    
    # Add friend request
    friend_data.setdefault("friend_requests", []).append(username)
    redis_client.set(f"user:{friend_username}", json.dumps(friend_data))
    
    flash(f"Friend request sent to {friend_username}!")
    return redirect(url_for("home"))

@app.route("/accept_friend/<username>")
@login_required
def accept_friend(username):
    current_user = session["username"]
    user_data = json.loads(redis_client.get(f"user:{current_user}"))
    
    if username not in user_data.get("friend_requests", []):
        flash("No friend request found!")
        return redirect(url_for("home"))
    
    # Add to both users' friend lists
    user_data.setdefault("friends", [])
    user_data["friend_requests"].remove(username)
    user_data["friends"].append(username)
    redis_client.set(f"user:{current_user}", json.dumps(user_data))
    
    friend_data = json.loads(redis_client.get(f"user:{username}"))
    friend_data.setdefault("friends", [])
    friend_data["friends"].append(current_user)
    redis_client.set(f"user:{username}", json.dumps(friend_data))
    
    flash(f"You are now friends with {username}!")
    return redirect(url_for("home"))

@app.route("/decline_friend/<username>")
@login_required
def decline_friend(username):
    current_user = session["username"]
    user_data = json.loads(redis_client.get(f"user:{current_user}"))
    
    if username not in user_data.get("friend_requests", []):
        flash("No friend request found!")
        return redirect(url_for("home"))
    
    # Remove the friend request
    user_data["friend_requests"].remove(username)
    redis_client.set(f"user:{current_user}", json.dumps(user_data))
    
    flash(f"Friend request from {username} declined.")
    return redirect(url_for("home"))

@app.route("/remove_friend/<username>", methods=["POST"])
@login_required
def remove_friend(username):
    current_user = session["username"]
    user_data = json.loads(redis_client.get(f"user:{current_user}"))
    
    if username not in user_data.get("friends", []):
        return jsonify({"error": "Not friends"}), 400
    
    # Remove from both users' friend lists
    user_data["friends"].remove(username)
    redis_client.set(f"user:{current_user}", json.dumps(user_data))
    
    friend_data = json.loads(redis_client.get(f"user:{username}"))
    if current_user in friend_data.get("friends", []):
        friend_data["friends"].remove(current_user)
        redis_client.set(f"user:{username}", json.dumps(friend_data))
    
    return jsonify({"success": True})

@app.route("/delete_room/<room_code>")
def delete_room(room_code):
    if "username" not in session:
        return redirect(url_for("login"))
        
    username = session["username"]
    
    if not redis_client.exists(f"room:{room_code}"):
        flash("Room does not exist.")
        return redirect(url_for("home"))
    
    room_data = json.loads(redis_client.get(f"room:{room_code}"))
    
    if room_data["created_by"] != username:
        flash("You don't have permission to delete this room.")
        return redirect(url_for("home"))
    
    # Remove room from all users who are in it
    for user in room_data["users"]:
        user_data = json.loads(redis_client.get(f"user:{user}"))
        if "rooms" in user_data and room_code in user_data["rooms"]:
            user_data["rooms"].remove(room_code)
        if user_data.get("current_room") == room_code:
            user_data["current_room"] = None
        redis_client.set(f"user:{user}", json.dumps(user_data))
    
    # Delete the room
    redis_client.delete(f"room:{room_code}")
    flash("Room successfully deleted.")
    return redirect(url_for("home"))


@app.route("/invite_to_room/<username>")
def invite_to_room(username):
    if "username" not in session:
        return redirect(url_for("login"))
    
    current_user = session["username"]
    current_room = session.get("room")
    
    if not current_room:
        flash("You're not in a room.")
        return redirect(url_for("home"))
    
    # Get the friend's data
    friend_data = get_user_data(username)
    if not friend_data:
        flash("User not found.")
        return redirect(url_for("room"))
    
    # Get current user's data to verify friendship
    user_data = get_user_data(current_user)
    if username not in user_data.get("friends", []):
        flash("You can only invite friends to rooms.")
        return redirect(url_for("room"))
    
    # Initialize room_invites if it doesn't exist
    if "room_invites" not in friend_data:
        friend_data["room_invites"] = []
    
    # Check if invite already exists
    existing_invite = next((inv for inv in friend_data["room_invites"] 
                          if inv.get("room") == current_room), None)
    
    if not existing_invite:
        # Create new invite with proper structure
        new_invite = {
            "room": current_room,
            "from": current_user,
            "timestamp": datetime.now().isoformat()
        }
        friend_data["room_invites"].append(new_invite)
        
        # Save the updated friend data
        update_user_data(username, friend_data)
        flash(f"Room invitation sent to {username}!")
    else:
        flash(f"{username} already has a pending invite to this room.")
    
    return redirect(url_for("room"))

@app.route("/accept_room_invite/<room_code>")
@login_required
def accept_room_invite(room_code):
    username = session["username"]
    user_data = get_user_data(username)
    
    # Find and remove the invite
    invite_found = False
    room_invites = user_data.get("room_invites", [])
    
    # Filter out the accepted invite
    user_data["room_invites"] = [
        inv for inv in room_invites 
        if not (inv["room"] == room_code and not invite_found and (invite_found := True))
    ]
    
    if not invite_found:
        flash("Room invite not found or already accepted.")
        return redirect(url_for("home"))
    
    # Add room to user's rooms list
    if "rooms" not in user_data:
        user_data["rooms"] = []
    if room_code not in user_data["rooms"]:
        user_data["rooms"].append(room_code)
    
    # Save the updated user data
    update_user_data(username, user_data)
    flash("Room invite accepted!")
    return redirect(url_for("room", code=room_code))

@app.route("/decline_room_invite/<room_code>")
@login_required
def decline_room_invite(room_code):
    username = session["username"]
    user_data = get_user_data(username)
    
    # Remove the invite
    user_data["room_invites"] = [inv for inv in user_data.get("room_invites", []) 
                                if inv["room"] != room_code]
    
    update_user_data(username, user_data)
    flash("Room invite declined.")
    return redirect(url_for("home"))

def handle_room_operation(username, code, create, join):
    room = code
    if create:
        room = generate_unique_code(4)
        redis_client.set(f"room:{room}", json.dumps({
            "members": 0,
            "messages": [],
            "users": [],
            "created_by": username,
        }))
    elif join and not redis_client.exists(f"room:{code}"):
        flash("Room does not exist.")
        return redirect(url_for("home"))
    
    session["room"] = room
    session["name"] = username
    
    # Update user's current room and rooms list
    user_data = json.loads(redis_client.get(f"user:{username}"))
    user_data["current_room"] = room
    if "rooms" not in user_data:
        user_data["rooms"] = []
    if room not in user_data["rooms"]:
        user_data["rooms"].append(room)
    redis_client.set(f"user:{username}", json.dumps(user_data))
    
    return redirect(url_for("room"))

def get_room_data(room_code):
    """
    Get room data from Redis and format it for template display.
    Returns None if room doesn't exist or there's an error.
    """
    try:
        if not redis_client.exists(f"room:{room_code}"):
            return None
            
        room_data = json.loads(redis_client.get(f"room:{room_code}"))
        
        # Ensure all required fields exist
        room_data.setdefault("members", 0)
        room_data.setdefault("users", [])
        room_data.setdefault("messages", [])
        room_data.setdefault("created_by", "Unknown")  # Default creator if not set
        
        return room_data
        
    except (json.JSONDecodeError, Exception) as e:
        return None

@app.route("/join_friend_room/<friend_username>")
def join_friend_room(friend_username):
    if "username" not in session:
        return redirect(url_for("login"))
    
    username = session["username"]
    user_data = json.loads(redis_client.get(f"user:{username}"))
    
    if friend_username not in user_data.get("friends", []):
        flash("User is not in your friends list.")
        return redirect(url_for("home"))
    
    friend_data = json.loads(redis_client.get(f"user:{friend_username}"))
    friend_room = friend_data.get("current_room")
    
    if not friend_room:
        flash("Friend is not in any room.")
        return redirect(url_for("home"))
    
    if not redis_client.exists(f"room:{friend_room}"):
        flash("Friend's room no longer exists.")
        return redirect(url_for("home"))
    
    session["room"] = friend_room
    session["name"] = username
    
    # Update user's current room
    user_data["current_room"] = friend_room
    redis_client.set(f"user:{username}", json.dumps(user_data))
    
    return redirect(url_for("room"))

@app.route("/room")
@login_required
def room():
    if "username" not in session:
        return redirect(url_for("login"))
        
    room = session.get("room")
    username = session.get("username")
    
    if room is None or not redis_client.exists(f"room:{room}"):
        return redirect(url_for("home"))

    # Get room data
    room_data = json.loads(redis_client.get(f"room:{room}"))
    user_data = json.loads(redis_client.get(f"user:{username}"))
    
    # Ensure required keys exist in room_data
    if "users" not in room_data:
        room_data["users"] = []
    if "messages" not in room_data:
        room_data["messages"] = []
    if "created_by" not in room_data:
        room_data["created_by"] = ""

    # Format timestamps and add friend status to messages
    for message in room_data["messages"]:
        message["is_friend"] = message["name"] in user_data.get("friends", [])
    
    # Get user list with online status and friend information
    user_list = []
    for user in room_data["users"]:
        user_profile = json.loads(redis_client.get(f"user:{user}"))
        user_list.append({
            "username": user,
            "online": user_profile.get("online", False),
            "isFriend": user in user_data.get("friends", [])
        })

    # Get friends list for invite functionality
    friends_data = []
    for friend in user_data.get("friends", []):
        if redis_client.exists(f"user:{friend}"):
            friend_data = json.loads(redis_client.get(f"user:{friend}"))
            friends_data.append({
                "username": friend,
                "online": friend_data.get("online", False),
                "current_room": friend_data.get("current_room")
            })
    
    return render_template("room.html",
                         code=room,
                         messages=room_data["messages"],
                         users=user_list,
                         username=username,
                         created_by=room_data["created_by"],
                         friends=friends_data,
                         room_data=room_data)  # Add this line to pass room_data

@socketio.on("connect")
def connect():
    room = session.get("room")
    username = session.get("username")
    if not room or not username:
        return
    if not redis_client.exists(f"room:{room}"):
        leave_room(room)
        return
    
    join_room(room)
    
    # Update user's current room and rooms list
    user_data = json.loads(redis_client.get(f"user:{username}"))
    user_data["current_room"] = room
    if "rooms" not in user_data:
        user_data["rooms"] = []
    if room not in user_data["rooms"]:
        user_data["rooms"].append(room)
    redis_client.set(f"user:{username}", json.dumps(user_data))
    
    # Update room data
    room_data = json.loads(redis_client.get(f"room:{room}"))
    room_data["members"] += 1
    if "users" not in room_data:
        room_data["users"] = []
    if username not in room_data["users"]:
        room_data["users"].append(username)
    redis_client.set(f"room:{room}", json.dumps(room_data))
    
    # Send updated user list with online status and friend information
    user_list = []
    for user in room_data["users"]:
        user_profile = json.loads(redis_client.get(f"user:{user}"))
        user_list.append({
            "username": user,
            "online": user_profile.get("online", False),
            "isFriend": user in user_data.get("friends", [])
        })
    socketio.emit("update_users", {"users": user_list}, room=room)
    
    # Send chat history to the newly connected user
    socketio.emit("chat_history", {"messages": room_data["messages"]}, room=request.sid)

@socketio.on("disconnect")
def disconnect():
    username = session.get("username")
    room = session.get("room")
    
    if not username or not room:
        return
        
    leave_room(room)
    
    # Update user profile
    if redis_client.exists(f"user:{username}"):
        user_data = json.loads(redis_client.get(f"user:{username}"))
        user_data["current_room"] = None
        redis_client.set(f"user:{username}", json.dumps(user_data))
    
    # Update room data
    if redis_client.exists(f"room:{room}"):
        room_data = json.loads(redis_client.get(f"room:{room}"))
        room_data["members"] -= 1
        
        if username in room_data["users"]:
            room_data["users"].remove(username)
        
        else:
            # Update room data and notify remaining users
            redis_client.set(f"room:{room}", json.dumps(room_data))
            
            # Send updated user list with online status and friend information
            user_list = []
            for user in room_data["users"]:
                user_profile = json.loads(redis_client.get(f"user:{user}"))
                user_list.append({
                    "username": user,
                    "online": user_profile.get("online", False),
                    "isFriend": False  # Default to false since we don't have the current user's context
                })
            socketio.emit("update_users", {"users": user_list}, room=room)

@app.route("/", methods=["POST", "GET"])
@login_required
def home():
    if "username" not in session:
        return redirect(url_for("login"))
        
    username = session["username"]
    
    # Ensure user data exists and has proper structure
    if not redis_client.exists(f"user:{username}"):
        # Initialize new user data if it doesn't exist
        user_data = {
            "rooms": [],
            "friends": [],
            "friend_requests": [],
            "online": True,
            "current_room": None
        }
        redis_client.set(f"user:{username}", json.dumps(user_data))
    else:
        user_data = json.loads(redis_client.get(f"user:{username}"))
        # Ensure all required fields exist
        if "rooms" not in user_data:
            user_data["rooms"] = []
        if "friends" not in user_data:
            user_data["friends"] = []
        if "friend_requests" not in user_data:
            user_data["friend_requests"] = []
        redis_client.set(f"user:{username}", json.dumps(user_data))
    
    if request.method == "POST":
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)
        friend_username = request.form.get("friend_username")

        # Handle friend request
        if friend_username:
            return handle_friend_request(username, friend_username)

        # Handle room operations
        if join != False and not code:
            flash("Please enter a room code.")
            return redirect(url_for("home"))
        
        return handle_room_operation(username, code, create, join)

    # Get friends data with online status and current rooms
    friends_data = []
    for friend in user_data.get("friends", []):
        if redis_client.exists(f"user:{friend}"):
            friend_data = json.loads(redis_client.get(f"user:{friend}"))
            friends_data.append({
                "username": friend,
                "online": friend_data.get("online", False),
                "current_room": friend_data.get("current_room")
            })

    return render_template("homepage.html",
                         username=username,
                         user_data=user_data,  # Explicitly pass user_data
                         friends=friends_data,
                         friend_requests=user_data.get("friend_requests", []))

@socketio.on("typing")
def handle_typing(data):
    room = session.get("room")
    if room:
        name = session.get("name")
        socketio.emit("typing", {"name": name, "isTyping": data.get("isTyping", False)}, room=room, include_self=False)

@socketio.on("message")
def message(data):
    room = session.get("room")
    if not room or not redis_client.exists(f"room:{room}"):
        return 

    content = {
        "id": str(random.randint(1000000, 9999999)),
        "name": session.get("name"),
        "message": data["data"],
        "reply_to": data.get("replyTo")
    }
    
    if "image" in data:
        try:
            image_data = base64.b64decode(data["image"].split(",")[1])
            filename = f"{room}_{random.randint(1000, 9999)}.png"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, "wb") as f:
                f.write(image_data)
            content["image"] = url_for('uploaded_file', filename=filename, _external=True)
        except Exception as e:
            content["message"] = "Failed to upload image"
    
    send(content, to=room)
    
    room_data = json.loads(redis_client.get(f"room:{room}"))
    room_data["messages"].append(content)
    redis_client.set(f"room:{room}", json.dumps(room_data))
    

@socketio.on("edit_message")
def edit_message(data):
    room = session.get("room")
    name = session.get("name")
    if not room or not redis_client.exists(f"room:{room}"):
        return

    room_data = json.loads(redis_client.get(f"room:{room}"))
    for message in room_data["messages"]:
        if message["id"] == data["messageId"] and message["name"] == name:
            message["message"] = data["newText"]
            message["edited"] = True
            redis_client.set(f"room:{room}", json.dumps(room_data))
            socketio.emit("edit_message", {"messageId": data["messageId"], "newText": data["newText"]}, room=room)
            break

@socketio.on("add_reaction")
def add_reaction(data):
    room = session.get("room")
    name = session.get("name")
    if not room or not redis_client.exists(f"room:{room}"):
        return

    room_data = json.loads(redis_client.get(f"room:{room}"))
    for message in room_data["messages"]:
        if message["id"] == data["messageId"]:
            if "reactions" not in message:
                message["reactions"] = {}
            if data["emoji"] not in message["reactions"]:
                message["reactions"][data["emoji"]] = 0
            message["reactions"][data["emoji"]] += 1
            redis_client.set(f"room:{room}", json.dumps(room_data))
            socketio.emit("update_reactions", {"messageId": data["messageId"], "reactions": message["reactions"]}, room=room)
            break

@socketio.on("delete_message")
def delete_message(data):
    room = session.get("room")
    name = session.get("name")
    if not room or not redis_client.exists(f"room:{room}"):
        return

    room_data = json.loads(redis_client.get(f"room:{room}"))
    room_data["messages"] = [msg for msg in room_data["messages"] if not (msg["id"] == data["messageId"] and msg["name"] == name)]
    redis_client.set(f"room:{room}", json.dumps(room_data))
    socketio.emit("delete_message", {"messageId": data["messageId"]}, room=room)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/profile_photos/<filename>')
def profile_photo(filename):
    return send_from_directory(app.config['PROFILE_UPLOAD_FOLDER'], filename)

if __name__ == "__main__":
    # Create upload folders if they don't exist
    for folder in [app.config['UPLOAD_FOLDER'], app.config['PROFILE_UPLOAD_FOLDER']]:
        if not os.path.exists(folder):
            os.makedirs(folder)
    
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True, host='0.0.0.0', port=port)