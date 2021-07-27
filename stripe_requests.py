import requests
import secret
import gc
import sqlite3 as sql

# precautionary memory stop gap
def clear_requests(req_list):
    for i in req_list:
        del i
        gc.collect()

#STRIPE API REQUESTS
class request(object):
    def __init__(self, method="get"):
        self.headers = {"Authorization": f"Bearer {secret.token}"}
        self.method = method
        self.url = "https://api.stripe.com/"
        self.data = None
        self.r = None
        self.res = None
    def send(self):
        if self.method.lower() == "get":
            self.r = requests.get(url=self.url, headers=self.headers)
        elif self.method.lower() == "post" and self.data != None:
            self.r = requests.post(url=self.url, headers=self.headers, data=self.data)
        elif self.method.lower() == "post":
            self.r = requests.post(url=self.url, headers=self.headers)
        self.res = self.r.json()
        self.error_check()
    def error_check(self):
            if self.res.get("error") != None:
                err = self.res.get("error").get("message")
                raise BaseException(err)

class get_customer(request):
    def __init__(self, customer_id):
        super().__init__("get")
        self.url = f"{self.url}/v1/customers/{customer_id}"
        self.send()

class create_customer(request):
    def __init__(self, name, email, phone=None): #, address=None):
        super().__init__(method="POST")
        self.url = f"{self.url}/v1/customers?description={name}&name={name}&email={email}"
        if phone: 
            self.url += f"&phone={phone}"
        #if address: #TODO fix address, must be split up by fields 
        #    self.url += f"&address={address}"
        self.send()

class update_customer_payment(request):
    def __init__(self, customer_id, card_num, exp_month, exp_year, cvc):
        super().__init__("post")
        #self.url = f"{self.url}v1/payment_methods?type=card&card[number]={card_num}&card[exp_month]={exp_month}&card[exp_year]={exp_year}&card[cvc]={cvc}"
        self.validity = False
        if len(exp_month) == 1:
            exp_month = f"0{exp_month}"
        if len(exp_year) == 2:
            exp_year = f"20{exp_year}"
        if len(card_num) == 16:
            self.url = f"{self.url}v1/customers/{customer_id}/sources?source[object]=card&source[number]={card_num}&source[exp_month]={exp_month}&source[exp_year]={exp_year}&source[cvc]={cvc}"
            self.send()
            if self.r.status_code == 200:
                #link_payment_method_to_customer(customer_id, self.res.get("id"))
                self.validity = True
            elif self.r.status_code == 402:
                self.validity = False
    def __call__(self):
        return self.res.get("id")
    def validity(self):
        return self.validity

class get_customer_subscriptions(request):
    def __init__(self, customer_id):
        super().__init__("get")
        self.url = f"{self.url}/v1/subscriptions?customer={customer_id}"
        self.send()
        response = self.res.get("data")
        self.data = []
        for i in range(len(response)):
            product_request = get_product(response[i].get("plan").get("product"))
            product_response = product_request.r.json()
            self.data.append({
                "product": product_response.get("name"),
                "EIN": product_response.get("metadata").get("EIN"),
                "sub_amount": response[i].get("plan").get("amount"),
                "sub_id": response[i].get("id"),
                "sub_date": response[i].get("created"),
                "sub_interval": response[i].get("items").get("data")[0].get("price").get("recurring").get("interval"),
                "lapsed_intervals": response[i].get("items").get("data")[0].get("price").get("recurring").get("interval_count"),
                "total_to_date": int(response[i].get("items").get("data")[0].get("price").get("recurring").get("interval_count")) * int(response[i].get("plan").get("amount"))
            })
    def __call__(self):
        return self.data

class get_product(request):
    def __init__(self, product_id):
        super().__init__("get")
        self.url = f"{self.url}/v1/products/{product_id}"
        self.send()

class create_product(request):
    def __init__(self, charity_name, EIN):
        super().__init__("post")
        self.product = None
        self.url = f"{self.url}/v1/products"
        self.url += f"?name=Donation to {charity_name}&metadata[EIN]={EIN}"
        self.send()
        if self.r.status_code == 200:
            self.product = self.res.get("id")
    def __call__(self):
        return self.product

class create_price(request):
    def __init__(self, product_id, amount, currency="usd", recurrance="month"):
        super().__init__("post")
        if recurrance not in ["month", "year", "week"]:
            recurrance = "month"
        self.url = f"{self.url}/v1/prices"
        self.url += f"?unit_amount={amount}&currency={currency}&product={product_id}&recurring[interval]={recurrance}"
        self.send()
    def __call__(self):
        return self.res.get("id")

class remove_subscription(request):
    def __init__(self, subscription_id):
        super().__init__("delete")
        self.url = f"{self.url}/v1/subscriptions/{subscription_id}"
    def send(self):
        self.r = requests.delete(self.url, headers=self.headers)
        if self.r.status_code == 200:
            return True
        else:
            return False

class create_subscription(request):
    def __init__(self, user_id, amount, card_num, exp_month, exp_year, cvc, ein=None, product_id=None, interval=None):
        self.subscription = None
        if ein == None:
            return "you must provide an ein or product_id"
        if user_id == None:
            self.subscription =  "you must provide a user_id"
        if amount == None:
            self.subscription =  "you must provide an amount"
        if card_num == None:
            self.subscription =  "you must provide a card number"
        if exp_month == None:
            self.subscription =  "you must provide an exp month"
        if exp_year == None:
            self.subscription =  "you must provide an exp year"
        if cvc == None:
            self.subscription =  "you must provide a cvc"
        product_id = get_product_id(prod_db, ein)
        price = create_price(product_id, amount, recurrance=interval)
        if price() == None:
            self.subscription =  "failed to create product attributes"
        payment = update_customer_payment(user_id, card_num, exp_month, exp_year, cvc)
        if payment.validity == False:
            self.subscription =  "invalid credit card"
        super().__init__(method="POST")
        self.url = f"{self.url}v1/subscriptions?customer={user_id}&items[0][price]={price()}&default_payment_method={payment()}"
        self.send()
        if self.r.status_code == 200:
            self.subscription = self.res.get("id")
        clear_requests([price, payment])
    def __call__(self):
        return self.subscription



### PRODUCT DATA ###
class product_db():
    def __init__(self):
        self.conn = sql.connect("products.sqlite3")
        self.cur = self.conn.cursor()
        try:
            #self.cur.execute("DROP TABLE IF EXISTS products;")
            self.cur.execute("CREATE TABLE products(ein TEXT, name TEXT, product_id TEXT);")
            self.conn.commit()
        except Exception as e:
            print(e)
    def get_product_id(self, ein):
        self.cur.execute("SELECT product_id FROM products WHERE ein=?", (ein,))
        return self.cur.fetchone()
    def add_product(self, ein, name, product_id):
        self.cur.execute("INSERT INTO products VALUES(?,?,?)", (ein, name, product_id))
        self.conn.commit()

def get_product_id(db, ein):
        get_ein = ein_request(ein)
        if len(get_ein.res.get("results")) == 1  and get_ein.res != None:
            result = get_ein.res.get("results")[0]
            clear_requests([get_ein])
        db_return = db.get_product_id(ein)
        if db_return == None:
            prod_req = create_product(charity_name=result.get("name"), EIN=ein)
            stripe_product_id = prod_req()
            db.add_product(ein, result.get("name"), stripe_product_id)
        else: 
            stripe_product_id = db_return[0]
        return stripe_product_id

# LOOKUP API REQUESTS
class ein_request():
    def __init__(self, ein):
        self.res = None
        self.url = f"http://{secret.l_url}/api/ein?q={ein}"
        self.r = requests.get(url=self.url)
        if self.r.status_code == 200:
            self.res = self.r.json() 
        else:
            self.res = None

# GLOBAL DATABASE INSTANTIATION
prod_db = product_db()

# TESTING
if __name__ == "__main__":
    pass
    #create_customer(name="wanker", email="wanker@stupid.com", phone="123-456-7890")
    #create_product(charity_name="stupid organization", EIN="4321")
    #update_customer_payment(customer_id="cus_JtzWnNhz7iZNHS", card_num="4242424242424242", exp_month="7", exp_year="2021", cvc=123)
    #link_payment_method_to_customer(customer_id="cus_JtzWnNhz7iZNHS", pm_id="pm_1JGBy3Kaj2eymSSLOEhw4r3y")
    #create_price(product_id="prod_JtzmqIWZ7yvYDt", amount=10000, currency="usd", recurrance="month")
    #create_subscription(user_id="cus_JtzWnNhz7iZNHS", amount=10000, card_num="4242424242424242", exp_month="7", exp_year="2021", cvc=123, ein="4321", product_id="prod_JtzmqIWZ7yvYDt", interval="month")
    
    
    #create_subscription(user_id="cus_JtzWnNhz7iZNHS", amount=1500, card_num="4242424242424242", exp_month="7", exp_year="2021", cvc=123, ein="471978930")
    #get_subs = get_customer_subscriptions(customer_id="cus_JtzWnNhz7iZNHS")
    

    #prod_db = product_db()
    #prod_db.add_product("4321", "stupid organization", "prod_JtzmqIWZ7yvYDt")
    #print(prod_db.get_product_id("4321"))
    #print(prod_db.get_product_id("1234"))
    #get_product_id(prod_db, "475522600")

