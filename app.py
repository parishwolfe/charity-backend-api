############################################
#   Charity Backend API                    #
#   author: Parish Wolfe                   #
#                                          #
############################################

import re
import secret
import base64
from datetime import timedelta, datetime
from flask import Flask, session, request, jsonify
from stripe_requests import get_customer, get_customer_subscriptions, create_subscription
import stripe_requests
app = Flask(__name__, static_folder="static")
_debug_ = True
app.secret_key = secret.encryption_key
app.permanent_session_lifetime == timedelta(minutes=5)
app.config['JSON_SORT_KEYS'] = False
from flask_sqlalchemy import SQLAlchemy
app.config ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.sqlite3'
db = SQLAlchemy(app)
class users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    pwd = db.Column(db.String(100))
    cust = db.Column(db.String(100))
    def __init__(self, name, pwd, cust):
        self.name = name
        self.pwd = pwd
        self.cust = cust
    def __repr__(self):
        return '<User %r>' % self.cust
db.create_all()

@app.route("/")
def home():
    return "Hi! maybe check the api docs?"

def response_template(status, message, data=None, username=None):
    if username == None:
        try:
            username = session["username"]
        except:
            username = "guest"
    response = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        "username": username,
        "status": status, 
        "message": message}
    if data != None:
        response["data"] = data
    return jsonify(response)

#----- AUTHORIZATION BLOCK -----#
@app.route("/login", methods=["POST"])
def login_req():
    response = login(request.headers.get("Authorization"))
    if response == False:
        return response_template("failure", "Invalid username or password", username="None"), 400
    else:
        return response_template("success", "Successful Login")

@app.route("/logout", methods=["POST"])
def logout():
    session["Authorized"] = False   
    return response_template("success", "Successful Logout")

def login(auth):
    if auth == None: 
        session["Authorized"] = False
        return False
    if "basic" in auth.lower():
        auth_string = auth.split(" ")[-1].strip()
        auth_string = base64.b64decode(auth_string).decode()
        auth_string = auth_string.split(":")
        response, user_id = check_auth_db(username=auth_string[0],password=auth_string[-1])
        if response == True:
            session["user_id"] = user_id
            session["username"] = auth_string[0]
            session["Authorized"] = True
            return True
        else:
            session["Authorized"] = False
            return False

def check_auth(auth_header):
    if session.get("Authorized") != True:
        if login(auth_header) == False:
            return False

def check_auth_db(username, password):
    response = users.query.filter_by(name=username).filter_by(pwd=password).first()
    if response == None:
        return False, None
    else:
        return True, response.cust

#----- USER ACTIONS -----#
@app.route("/whoami", methods=["GET"])
def whoami():
    if check_auth(request.headers.get("Authorization")) == False: 
        return response_template("failure", "Invalid username or password", username="None"), 400
    req = get_customer(session.get("user_id"))
    response = req.r.json()
    data = {
        "name": response.get("name"),
        "address": response.get("address"),
        "email": response.get("email"),
        "phone": response.get("phone"),
        "stripe_id": response.get("id")
    }
    return response_template("success", "Successful retrival", data=data)
    

@app.route("/onboard", methods=["POST"])
def onboard():
    message = None
    if request.args.get("name") == None and request.args.get("email") == None and request.args.get("username") == None and request.args.get("password") == None:
        return response_template("failure", "Missing required parameters")
    response = users.query.filter_by(name=request.args.get("username")).first()
    if response != None:
        return response_template("failure", "username already taken")
    make_cust = stripe_requests.create_customer(name=request.args.get("name"), email=request.args.get("email"), phone=request.args.get("phone"))#, address=request.args.get("address"), )
    you = users(request.args.get("username"), request.args.get("password"), make_cust.res.get("id"))
    db.session.add(you)
    db.session.commit()
    session["user_id"] = make_cust.res.get("id")
    session["username"] = request.args.get("username")
    session["Authorized"] = True
    return response_template("success", "Successfully created user", data={"user_id": session.get("user_id")})

@app.route("/my_subs", methods=["GET", "POST"])
def my_subscriptions():
    if check_auth(request.headers.get("Authorization")) == False: 
        return "Invalid username or password"
    ### get all subscriptions ###
    action = request.args.get("action")
    if request.method == "GET" or action == "list":
        sub_request = get_customer_subscriptions(session.get("user_id"))
        data = sub_request()
        return response_template("success", "successfully retrived subscriptions", data=data)
    ### Create subscription ###
    elif request.method == "POST":
        if action == "create":
            if session.get("last_request") != None:
                if session.get("last_request").get(request.args.get("ein")) == request.args.get("card_num")[-4:]:
                    return response_template("failure", "duplicate request received, ignoring.")
            req = create_subscription(
                user_id = session.get("user_id"),
                amount = request.args.get("amount"), 
                interval = request.args.get("interval"),
                ein = request.args.get("ein"),
                product_id = request.args.get("product_id"),
                card_num=request.args.get("card_num"),
                exp_month=request.args.get("exp_month"),
                exp_year=request.args.get("exp_year"),
                cvc=request.args.get("cvc")
            )
            session.last_request = {request.args.get("ein"): request.args.get("card_num")[-4:]}
            if req()[:3] == "sub":
                return response_template("success", "Successfully created subscription", data={"subscription_id": req.res.get("id")})
            else:
                return response_template("failure", req())
        elif action == "delete":
            if request.args.get("sub_id"):
                sub_id = request.args.get("sub_id")
                req = stripe_requests.remove_subscription(sub_id)
                if req.send() == True:
                    return response_template("success", f"Successfully deleted subscription {sub_id}")
                else:
                    return response_template("failure", f"Failed to delete subscription {sub_id}")
    return response_template("failure", "unsupported operation")






if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=_debug_)

#cspell:ignore jsonify cust XATTR
