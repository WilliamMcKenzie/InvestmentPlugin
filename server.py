import socket
import requests
import threading
import time

# Server config
delay_secs = 1
connections = {}
port = 12855

# Create the server
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', port))
s.listen()

# Flipping data
flips = []
m = None
h = None
l = None

mapping = None
hourly = None
latest = None

def FetchData():
    global m, h, l, mapping, hourly, latest
    
    m = requests.get("https://prices.runescape.wiki/api/v1/osrs/mapping")
    h = requests.get("https://prices.runescape.wiki/api/v1/osrs/1h")
    l = requests.get("https://prices.runescape.wiki/api/v1/osrs/latest")
    
    mapping = m.json()
    hourly = h.json()["data"]
    latest = l.json()["data"]

def FlipCheck(delta):
    global flips

    if not m:
        return

    flips = []
    for i in mapping:
        id = str(i["id"])
        if id in hourly:
            avglow = hourly[id]["avgLowPrice"]
            avghigh = hourly[id]["avgHighPrice"]
            if avghigh and avglow and "limit" in i:
                valid_price = latest[id]["low"] <= avglow - (avglow * delta)
                valid_limit = hourly[id]["lowPriceVolume"] + hourly[id]["highPriceVolume"] >= i["limit"]
                valid_volume = hourly[id]["lowPriceVolume"] + hourly[id]["highPriceVolume"] >= 10000
                valid_profit = (hourly[id]["avgLowPrice"] - latest[id]["low"]) * i["limit"] >= 150000
                
                if valid_price and valid_limit and valid_volume and valid_profit:
                    # Append the flip, with its id, profit and how much it would cost to achieve that profit.
                    flips.append({
                        "id" : id,
                        "profit" : (hourly[id]["avgLowPrice"] - latest[id]["low"]) * i["limit"],
                        "cost" : latest[id]["low"] * i["limit"],
                        "price" : latest[id]["low"],
                        "sell" : hourly[id]["avgHighPrice"],
                        "limit" : i["limit"]
                    })
    
    flips.sort(key=lambda flip : flip["profit"], reverse=True)

def BuyItems():
    global flips, connections

    for id in connections:
        connection = connections[id]
        for flip in flips:
            if connection["slots"] > 0:
                break
                
            SendMessage(connection["socket"], f"buy 1 {flip["id"]}")
            connection["slots"] -= 1
            connection["positions"].append({
                "id" : flip["id"],
                "bought" : False,
            })

def Main():
    while True:
        FetchData()
        FlipCheck(0.05)
        BuyItems()
        time.sleep(delay_secs)

# Given a socket, send it a message
def SendMessage(socket, message):
    encoded = message.encode()
    socket.send(len(encoded).to_bytes(2, 'big') + encoded)
# Given a socket, wait for it to send you a message
def RecieveMessage(socket):
    return socket.recv(1024).decode()

def AcceptConnections():
    global connections

    while True:
        c, (address, id) = s.accept()

        # Each position will have a bought at and sell at price.
        # - Bought at price is the current price since we will buy it immedietly.
        # - Sell at price will be the price we want to sell for (Like 10% more then buy price). 
        #   We could also add a timeout if the item stays flat for too long.

        client_data = [int(data) for data in c.recv(1024).decode().split(",") if data.isdigit()]
        print(f"Recieved connection from {address}")
        print(f"GP: {client_data[0]}  SLOTS: {client_data[1]}")
        connections[id] = {
            "commands" : [],
            "socket" : c,
            "positions" : [],
            "gp" : client_data[0],
            "slots" : client_data[1],
        }

        account_thread = threading.Thread(target=ManageAccount,args=[id])
        account_thread.start()

def ManageAccount(id):
    while True:
        message = RecieveMessage(connections[id]["socket"])

        #If the message is that something bought, we can proceed to put an offer to sell it
        print(message)


main_thread = threading.Thread(target=Main)
accept_thread = threading.Thread(target=AcceptConnections)

main_thread.start()
accept_thread.start()

