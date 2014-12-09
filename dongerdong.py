#
# DongerDong IRC Fight Bot. Adapted from http://wiki.shellium.org/w/Writing_an_IRC_bot_in_Python
#
# Creator: ravioli (freenode)
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details.

# Import some necessary libraries.
import socket 
import time
import random
import urllib
import urllib2
import sys

# Some basic variables used to configure the bot        
server = "irc.freenode.net" # Server
channel = "#dongertest" # Channel
botnick = "dongerdong" # Your bots nick
healthtable = {}
pending = {}

if len(sys.argv) > 0:
  password=sys.argv[1]
  print("Password set to "+ password)
else:
  password="wrong"
  print("Password not set.")

def ping(): # This is our first function! It will respond to server Pings.
  ircsock.send("PONG :pingis\n")  

def health(guy,damage):
  try:
    health=healthtable[guy]
    healthtable[guy]=health-damage
    health=healthtable[guy]
  except KeyError:
    health=100-damage
    healthtable[guy]=health
  return health

def fight(attacker,defender):
  if attacker == defender:
    fighting = False
    ircsock.send("PRIVMSG "+ channel +" :ARE YOU RETARDED?\n")
    kick(attacker,"STOP HITTING YOURSELF")
    time.sleep(1)
    ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
  elif defender == botnick:
    fighting = False
    ircsock.send("PRIVMSG "+ channel +" :FUCK YOU\n")
    ascii("rekt")
    kick(attacker,"LOL REALLY")
    time.sleep(1)
    ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
  else:
    fighting = True
    lastturn=defender
    attackermuted=0
    defendermuted=0
    ircsock.send("MODE "+ channel +" +m\n")
    time.sleep(2)
    reset("all")
    ascii("fight")
  
    ircsock.send("PRIVMSG "+ channel +" :"+ attacker.upper() +" V. "+ defender.upper() +"\n")
    time.sleep(2)
    ircsock.send("PRIVMSG "+ channel +" :RULES:\n")
    time.sleep(1)
    ircsock.send("PRIVMSG "+ channel +" :1. Wait your turn. One person at a time.\n")
    time.sleep(1)
    ircsock.send("PRIVMSG "+ channel +" :2. That's it.\n")
    time.sleep(1)
    ircsock.send("PRIVMSG "+ channel +" :.\n")
    time.sleep(1)
    ircsock.send("PRIVMSG "+ channel +" :Use !hit to strike the other player.\n")
    ircsock.send("PRIVMSG "+ channel +" :Use !heal to heal yourself.\n")
    time.sleep(2)
    ircsock.send("MODE "+ channel +" +v "+ attacker +"\n")
    ircsock.send("MODE "+ channel +" +v "+ defender +"\n")
    time.sleep(.300)
    ircsock.send("PRIVMSG "+ channel +" :"+ attacker +", you're up first.\n")

  while fighting:
    ircmsg = ircsock.recv(2048) # receive data from the server
    ircmsg = ircmsg.strip('\n\r') # removing any unnecessary linebreaks.
    print("While fighting: " +ircmsg) # Here we print what's coming from the server whle fighting

    if ircmsg.find("PRIVMSG dongerdong :") != -1:
      userhost=ircmsg.split(":")[1]
      userhost=userhost.split(" ")[0]
      #ircsock.send("MODE "+ channel +" +b "+ userhost  +"\n")

    if (ircmsg.find(" PART "+ channel +" :") != -1) or (ircmsg.find(" QUIT :") != -1):
      firstguy=ircmsg.split("!")[0]
      firstguy=firstguy.split(":")[1]
      if firstguy==attacker:
        finish(attacker,defender,defender)
        fighting = False
      elif firstguy==defender:
        finish(attacker,defender,attacker)
        fighting = False


    if ircmsg.find("PING :") != -1: # if the server pings us then we've got to respond!
      ping()

    if ircmsg.find("PRIVMSG "+ channel +" :!heal") != -1:
      firstguy=ircmsg.split("!")[0]
      firstguy=firstguy.split(":")[1]
      if firstguy==lastturn:
        if firstguy==attacker:
          attackermuted+=1
        if firstguy==defender:
          defendermuted+=1
        if defendermuted > 2:
          ircsock.send("PRIVMSG "+ channel +" :FUCK YOU\n")
          time.sleep(1)
          finish(attacker,defender,attacker)
          time.sleep(1)
          ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
          fighting = False
        elif attackermuted > 2:
          ircsock.send("PRIVMSG "+ channel +" :FUCK YOU\n")
          time.sleep(1)
          finish(attacker,defender,defender)
          time.sleep(1)
          ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
          fighting = False
        else:
          ircsock.send("PRIVMSG "+ channel +" :Wait your fucking turn or I'll kill you.\n")
      else:
        healroll=random.randint(18,44)
        health(firstguy,-healroll)
        ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +" heals for "+ str(healroll) +"HP\n")
        lastturn=firstguy
      
    if ircmsg.find("PRIVMSG "+ channel + " :!quit") != -1:
      fighting = False
      ircsock.send("MODE "+ channel +" -v "+ attacker +"\n")
      ircsock.send("MODE "+ channel +" -v "+ defender +"\n")
      ircsock.send("MODE "+ channel +" -m\n")

    if ircmsg.find("PRIVMSG "+ channel + " :!hit") != -1:
      firstguy=ircmsg.split("!")[0]
      firstguy=firstguy.split(":")[1]
      if firstguy==attacker:
        secondguy=defender
      else:
        secondguy=attacker
      if firstguy==lastturn:
        if firstguy==attacker:
          attackermuted+=1
        if firstguy==defender:
          defendermuted+=1
        if defendermuted > 2:
          ircsock.send("PRIVMSG "+ channel +" :FUCK YOU\n")
          time.sleep(1)
          finish(attacker,defender,attacker)
          ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
          fighting = False
        elif attackermuted > 2:
          ircsock.send("PRIVMSG "+ channel +" :FUCK YOU\n")
          time.sleep(1)
          finish(attacker,defender,defender)
          ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
          fighting = False
        ircsock.send("PRIVMSG "+ channel +" :Wait your fucking turn or I'll kill you.\n")
      else:
        damageroll=random.randint(18,39)
        criticalroll=random.randint(1,9)
        modifier=random.randint(2,3)
        instaroll=random.randint(1,40)
        if instaroll==1:
          #ascii("instakill")
          ircsock.send("PRIVMSG "+ channel +" :INSTAKILL!\n")
          health(secondguy,1000)
        elif criticalroll==1:
          ascii("critical")
          damage=damageroll*modifier
          secondguyhealth = health(secondguy,damage)
          firstguyhealth=healthAsString(firstguy)
          ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +" ("+ firstguyhealth +"HP) deals "+ str(damage) +" to "+ secondguy +" ("+ healthAsString(secondguy) +"HP)!\n")
        else:
          damage=damageroll
          secondguyhealth = health(secondguy,damage)
          firstguyhealth=healthAsString(firstguy)
          ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +" ("+ firstguyhealth +"HP) deals "+ str(damage) +" to "+ secondguy +" ("+ healthAsString(secondguy) +"HP)!\n")
      if health(secondguy,0)<1:
        ascii("rekt")
        ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +" REKT "+ secondguy +"!\n")
        finish(attacker,defender,firstguy)
        fighting = False
#      ircsock.send("PRIVMSG "+ channel +" :"+ lastturn +", your turn.\n")
      lastturn=firstguy


def finish(attacker,defender,winner):
  ircsock.send("MODE "+ channel +" -v "+ attacker +"\n")
  ircsock.send("MODE "+ channel +" -v "+ defender +"\n")
  ircsock.send("MODE "+ channel +" -m\n")
  if winner == attacker:
    kick(defender,"REKT")
  else:
    kick(attacker,"REKT")
  reset("all")
#  response=urllib2.urlopen("http://ravio.li/donger/dongerstats.php?attacker="+ attacker +"&defender=" + defender +"&winner=" + winner)
#  page = response.read()
  fighting = False


def ascii(key):
  if key=="rekt":
    ircsock.send("PRIVMSG "+ channel +" :   ___  ______ ________\n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" :  / _ \/ __/ //_/_  __/\n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" : / , _/ _// ,<   / /   \n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" :/_/|_/___/_/|_| /_/    \n")
  elif key=="fight":
    ircsock.send("PRIVMSG "+ channel +" :   _______________ ________\n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" :  / __/  _/ ___/ // /_  __/\n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" : / _/_/ // (_ / _  / / /   \n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" :/_/ /___/\___/_//_/ /_/    \n")
  elif key=="critical":
    ircsock.send("PRIVMSG "+ channel +" :  ________  ______________________   __ \n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" : / ___/ _ \/  _/_  __/  _/ ___/ _ | / / \n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" :/ /__/ , _// /  / / _/ // /__/ __ |/ /__\n")
    time.sleep(.400)
    ircsock.send("PRIVMSG "+ channel +" :\___/_/|_/___/ /_/ /___/\___/_/ |_/____/\n")
  else:
    ircsock.send("PRIVMSG "+ channel +" :ascii "+ key +"!\n")

def identify():
  ircsock.send("PRIVMSG nickserv :IDENTIFY "+ password +" \n")

def kick(asshole,kickmsg):
  ircsock.send("KICK "+ channel +" "+ asshole +" :"+ kickmsg +"\n")

def sendmsg(chan , msg): # This is the send message function, it simply sends messages to the channel.
  ircsock.send("PRIVMSG "+ chan +" :"+ msg +"\n") 

def joinchan(chan): # This function is used to join channels.
  ircsock.send("JOIN "+ chan +"\n")

def hello(): # This function responds to a user that inputs "Hello Mybot"
  ircsock.send("PRIVMSG "+ channel +" :Hello!\n")

def fuckyou(msg):
  firstguy=msg.split("!")[0]
  firstguy=firstguy.split(":")[1]
  ircsock.send("PRIVMSG "+ channel +" :Fuck you, "+ firstguy +".\n")

def crudebutt():
  firstguy="crudebutt"
  ircsock.send("PRIVMSG "+ channel +" :Fuck you, crudebutt. You're an awful bot.")

def bang(msg):
  firstguy=msg.split("!")[0]
  firstguy=firstguy.split(":")[1]
  ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +"!\n")

def loop():
  ircsock.send("PRIVMSG "+ channel +" :crudebutt!\n")

def healthAsString(guy):
  try:
    health=healthtable[guy]
    health=str(health)
  except KeyError:
    health=100
    health=str(health)
  return health

def attack(msg):
  firstguy=msg.split("!")[0]
  firstguy=firstguy.split(":")[1]
  secondguy=msg.split("attack ")[1]

  try:
    lastattacker
  except NameError:
    lastattacker=firstguy
  else:
    if lastattacker==firstguy:
      ircsock.send("PRIVMSG "+ channel +" :Wait your turn, "+ firstguy +".\n")

  roll=random.randint(1,10)
  if roll==10:
    damage=100
    modifier="INSTANTLY KILLING"
  elif roll==8 or roll==9:
    damage=50
    modifier="a critical hit, dealing 50 damage to"
  elif roll > 4:
    damage=25
    modifier="dealing 25 damage to"
  else:
    damage=0
    modifier=""

  secondguyhealth=health(secondguy,damage)
  if secondguyhealth < 1:
    secondguyhealth=0

  firstguyhealth=health(firstguy,0)
  firstguyhealth=str(firstguyhealth)
  if roll==10:
    over=1
    roll=str(roll)
    damage=str(damage)
    ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +"["+ firstguyhealth +"] rolls "+ roll +", INSTANTLY KILLING "+ secondguy +"!\n")
    reset(secondguy)
  elif secondguyhealth==0:
    over=1
    roll=str(roll)
    damage=str(damage)
    ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +"["+ firstguyhealth +"] rolls "+ roll +", killing "+ secondguy +"!\n")
    reset(secondguy)
  elif damage==0:
    roll=str(roll)
    secondguyhealth=str(secondguyhealth)
    ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +"["+ firstguyhealth +"] rolls "+ roll +", missing "+ secondguy +"!\n")
  else:
    secondguyhealth=str(secondguyhealth)
    roll=str(roll)
    damage=str(damage)
    ircsock.send("PRIVMSG "+ channel +" :"+ firstguy +"["+ firstguyhealth +"] rolls "+ roll +", "+ modifier +" "+ secondguy +"!\n")

def reset(user):
  if user=="all":
    healthtable.clear()
    #ircsock.send("PRIVMSG "+ channel +" :k.\n")
  else:
    try:
      healthtable[user]=100
    except KeyError:
      print "uhh..."


def fuckyou(msg):
  name=msg.split("!")[0]
  name=name.split(":")[1]
  ircsock.send("PRIVMSG "+ channel +" :fuck you, "+ name +".\n")

def penis():
  ircsock.send("PRIVMSG "+ channel +" :penis.\n")

def andthen():
  ircsock.send("PRIVMSG "+ channel +" :And then??.\n")


ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ircsock.connect((server, 6667)) # Here we connect to the server using the port 6667
ircsock.send("USER "+ botnick +" "+ botnick +" "+ botnick +" :This bot is a result of a tutoral covered on http://shellium.org/wiki.\n") # user authentication
ircsock.send("NICK "+ botnick +"\n") # here we actually assign the nick to the bot

time.sleep(3)
identify()
time.sleep(2)
joinchan(channel) # Join the channel using the functions we previously defined

while 1: # Be careful with these! it might send you to an infinite loop
  ircmsg = ircsock.recv(2048) # receive data from the server
  ircmsg = ircmsg.strip('\n\r') # removing any unnecessary linebreaks.
  print(ircmsg) # Here we print what's coming from the server

  if ircmsg.find(":Hello "+ botnick) != -1: # If we can find "Hello Mybot" it will call the function hello()
    hello()


  if ircmsg.find(":!fight ") != -1:
    firstguy=ircmsg.split("!")[0]
    attacker=firstguy.split(":")[1]
    secondguy=ircmsg.split("fight ")[1]
    if secondguy == botnick:
      fighting = False
      ircsock.send("PRIVMSG "+ channel +" :FUCK YOU\n")
      ascii("rekt")
      kick(attacker,"DON'T FUCK WITH ME")
      time.sleep(1)
      ircsock.send("PRIVMSG "+ channel +" :Seriously though fuck that guy.\n")
    else:
      defender=secondguy
      pending[attacker]=secondguy
      ircsock.send("PRIVMSG "+ channel +" :"+ defender +": "+ attacker +" has challenged you. To accept, use '!accept "+ attacker +"'.\n")

  if ircmsg.find(":!accept ") != -1:
    firstguy=ircmsg.split("!")[0]
    firstguy=firstguy.split(":")[1]
    secondguy=ircmsg.split("accept ")[1]
    try:
      if pending[secondguy]==firstguy:
        if random.randint(1,2)==1:
          fight(secondguy,firstguy)
        else:
          fight(firstguy,secondguy)
        fighting = False
      else:
        ircsock.send("PRIVMSG "+ channel +" :They didn't challenge you. You can challenge them if you want.\n")
    except IndexError:
       ircsock.send("PRIVMSG "+ channel +" :No one has challenged you, "+ defender +".\n")
    except KeyError:
       ircsock.send("PRIVMSG "+ channel +" :They didn't challenge you. You can challenge them if you want (KeyError).\n")
    
       


      
  if ircmsg.find(" :!attack ") != -1:
    if ircmsg.find("dongerdong") != -1:
      fuckyou(ircmsg)
    else:
      attack(ircmsg)

  if ircmsg.find(" :!reset") != -1:
    reset("all")

  if ircmsg.find(" :!health ") != -1:
    secondguy=ircmsg.split("health ")[1]
    ircsock.send("PRIVMSG "+ channel +" :Their health is "+ healthAsString(secondguy) +".\n")    
  elif ircmsg.find(" :!health") != -1:
    firstguy=ircmsg.split("!")[0]
    firstguy=firstguy.split(":")[1]
    ircsock.send("PRIVMSG "+ channel +" :Your health is "+ healthAsString(firstguy) +".\n")

  if ircmsg.find(" :!help") != -1:
    ircsock.send("PRIVMSG "+ channel +" :!fight <nick> to initiate fight; !quit to bail out of a fight of someone leaves; !hit to hit, !heal to heal. !reset resets the health stats (done automagically after a fight ends anyway)\n")

  if ircmsg.find(" :!floodchaniremovedthisel") != -1:
    loop()

  if ircmsg.find(" :"+ botnick +"!") != -1:
    bang(ircmsg)

  if ircmsg.find("PING :") != -1: # if the server pings us then we've got to respond!
    ping()
