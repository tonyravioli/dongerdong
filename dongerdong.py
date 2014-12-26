#!/usr/bin/env python
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
channel = "#donger" # Channel
botnick = "dongerdong" # Your bots nick
healthtable = {}
pending = {}

try:
  password=sys.argv[1]
  if password=="test":
    channel=channel +"test"
    botnick=botnick +"test"
    print("In test mode.")
  else:
    print("Password set to "+ password)
except:
  password="wrong"
  print("Password not set.")

def ping(): # This is our first function! It will respond to server Pings.
  ircsock.send("PONG :pingis\n")  

def say(message):
  ircsock.send("PRIVMSG "+ channel +" :"+ message +"\n")

def health(guy,damage):
  try:
    health=healthtable[guy]
    newhealth=health-damage
    if newhealth > 100:
      newhealth = 100
    healthtable[guy]=newhealth
    health=healthtable[guy]
  except KeyError:
    health=100-damage
    if health > 100:
      health = 100
    healthtable[guy]=health
  return health

def fight(attacker,defender):
  lastMessageTime=time.time() + 60
  if attacker == defender:
    fighting = False
    say("ARE YOU RETARDED?")
    kick(attacker,"STOP HITTING YOURSELF")
    time.sleep(1)
    say("Seriously though fuck that guy.")
  elif defender == botnick:
    fighting = False
    say("FUCK YOU")
    ascii("rekt")
    kick(attacker,"LOL REALLY")
    time.sleep(1)
    say("Seriously though fuck that guy.\n")
  else:
    fighting = True
    lastturn=defender
    attackermuted=0
    defendermuted=0
    setmode("+m")
    time.sleep(2)
    reset("all")
    ascii("fight")
  
    say(attacker.upper() +" V. "+ defender.upper() +"")
    time.sleep(2)
    say("RULES:")
    time.sleep(1)
    say("1. Wait your turn. One person at a time.")
    time.sleep(1)
    say("2. That's it.")
    time.sleep(1)
    say(".")
    time.sleep(1)
    say("Use !hit to strike the other player.")
    say("Use !heal to heal yourself.")
    time.sleep(2)
    setmode("+v",attacker)
    setmode("+v",defender)
    time.sleep(.300)
    say(attacker +", you're up first.")

    invalid = False

  while fighting:
    ircmsg = ircsock.recv(2048) # receive data from the server
    ircmsg = ircmsg.strip('\n\r') # removing any unnecessary linebreaks.
    print("While fighting: " +ircmsg) # Here we print what's coming from the server whle fighting

    if time.time() > lastMessageTime+60:
      finish(attacker,defender,lastturn)
      fighting = False
      say("Timeout occurred. "+ lastturn +" wins.")

    if ircmsg.find("PRIVMSG dongerdong :") != -1:
      userhost=ircmsg.split(":")[1]
      userhost=userhost.split(" ")[0]
      invalid = True
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

    if(ircmsg.find("PRIVMSG "+ channel +" :!heal") != -1) and not invalid:
      firstguy=ircmsg.split("!")[0]
      firstguy=firstguy.split(":")[1]
      if firstguy==lastturn:
        if firstguy==attacker:
          attackermuted+=1
        if firstguy==defender:
          defendermuted+=1
        if defendermuted > 2:
          say("FUCK YOU")
          time.sleep(1)
          finish(attacker,defender,attacker)
          time.sleep(1)
          say("Seriously though fuck that guy.")
          fighting = False
        elif attackermuted > 2:
          say("FUCK YOU")
          time.sleep(1)
          finish(attacker,defender,defender)
          time.sleep(1)
          say("Seriously though fuck that guy.")
          fighting = False
        else:
          say("Wait your fucking turn or I'll kill you.")
      else:
        healroll=random.randint(22,44)
        newhealth=health(firstguy,-healroll)
        if newhealth > 99:
          say(firstguy +" heals for "+ str(healroll) +"HP, bringing them back to 100HP.")
        else:
          say(firstguy +" heals for "+ str(healroll) +"HP, bringing them to "+ str(newhealth) +"HP.")
        lastturn=firstguy
      
    if ircmsg.find("PRIVMSG "+ channel + " :!quit") != -1:
      '''fighting = False
      setmode("-v",attacker)
      setmode("-v",defender)
      setmode("-m")'''

    if (ircmsg.find("PRIVMSG "+ channel + " :!hit") != -1) and not invalid:
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
          say("FUCK YOU")
          time.sleep(1)
          finish(attacker,defender,attacker)
          say("Seriously though fuck that guy.")
          fighting = False
        elif attackermuted > 2:
          say("FUCK YOU")
          time.sleep(1)
          finish(attacker,defender,defender)
          say("Seriously though fuck that guy.")
          fighting = False
        say("Wait your fucking turn or I'll kill you.")
      else:
        damageroll=random.randint(18,39)
        criticalroll=random.randint(1,9)
        modifier=2
        instaroll=random.randint(1,40)
        if instaroll==1:
          #ascii("instakill")
          say("INSTAKILL!")
          health(secondguy,1000)
        elif criticalroll==1:
          ascii("critical")
          damage=damageroll*modifier
          secondguyhealth = health(secondguy,damage)
          firstguyhealth=healthAsString(firstguy)
          say(firstguy +" ("+ firstguyhealth +"HP) deals "+ str(damage) +" to "+ secondguy +" ("+ healthAsString(secondguy) +"HP)!")
        else:
          damage=damageroll
          secondguyhealth = health(secondguy,damage)
          firstguyhealth=healthAsString(firstguy)
          say(firstguy +" ("+ firstguyhealth +"HP) deals "+ str(damage) +" to "+ secondguy +" ("+ healthAsString(secondguy) +"HP)!")
      if health(secondguy,0)<1:
        ascii("rekt")
        say(firstguy +" REKT "+ secondguy +"!")
        finish(attacker,defender,firstguy)
        fighting = False
#      say(lastturn +", your turn.")
      lastturn=firstguy
      invalid = False

def finish(attacker,defender,winner):
  setmode("-v",attacker)
  setmode("-v",defender)
  setmode("-m")
  if winner == attacker:
    kick(defender,"REKT")
  else:
    kick(attacker,"REKT")
  reset("all")
  try:
    response=urllib2.urlopen("http://ravio.li/donger/dongerstats.php?attacker="+ attacker +"&defender=" + defender +"&winner=" + winner)
    page = response.read()
  except:
    say("Tell ravioli the stats thing failed.")
  fighting = False

def setmode(mode,user="no"):
  if "user"=="no": #Assume it's a channel mode
    ircsock.send("MODE "+ channel +" "+ mode +" \n")
  else: #Otherwise, apply to user
    ircsock.send("MODE "+ channel +" "+ mode +" "+ user +" \n")

def ascii(key):
  if key=="rekt":
    say("   ___  ______ ________")
    time.sleep(.400)
    say("  / _ \/ __/ //_/_  __/")
    time.sleep(.400)
    say(" / , _/ _// ,<   / /   ")
    time.sleep(.400)
    say("/_/|_/___/_/|_| /_/    ")
  elif key=="fight":
    say("   _______________ ________")
    time.sleep(.400)
    say("  / __/  _/ ___/ // /_  __/")
    time.sleep(.400)
    say(" / _/_/ // (_ / _  / / /   ")
    time.sleep(.400)
    say("/_/ /___/\___/_//_/ /_/    ")
  elif key=="critical":
    say("  ________  ______________________   __ ")
    time.sleep(.400)
    say(" / ___/ _ \/  _/_  __/  _/ ___/ _ | / / ")
    time.sleep(.400)
    say("/ /__/ , _// /  / / _/ // /__/ __ |/ /__")
    time.sleep(.400)
    say("\___/_/|_/___/ /_/ /___/\___/_/ |_/____/")
  else:
    say("ascii "+ key +"!")

def identify():
  ircsock.send("PRIVMSG nickserv :IDENTIFY "+ password +" \n")

def kick(asshole,kickmsg):
  ircsock.send("KICK "+ channel +" "+ asshole +" :"+ kickmsg +"\n")

def sendmsg(chan , msg): # This is the send message function, it simply sends messages to the channel.
  ircsock.send("PRIVMSG "+ chan +" :"+ msg +"\n") 

def joinchan(chan): # This function is used to join channels.
  ircsock.send("JOIN "+ chan +"\n")

def hello(): # This function responds to a user that inputs "Hello Mybot"
  say("Hello!")

def fuckyou(msg):
  firstguy=msg.split("!")[0]
  firstguy=firstguy.split(":")[1]
  say("Fuck you, "+ firstguy +".")

def bang(msg):
  firstguy=msg.split("!")[0]
  firstguy=firstguy.split(":")[1]
  say(firstguy +"!")

def healthAsString(guy):
  try:
    health=healthtable[guy]
    health=str(health)
  except KeyError:
    health=100
    health=str(health)
  lastActionTime=time.time()
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
      say("Wait your turn, "+ firstguy +".")

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
    say(firstguy +"["+ firstguyhealth +"] rolls "+ roll +", INSTANTLY KILLING "+ secondguy +"!")
    reset(secondguy)
  elif secondguyhealth==0:
    over=1
    roll=str(roll)
    damage=str(damage)
    say(firstguy +"["+ firstguyhealth +"] rolls "+ roll +", killing "+ secondguy +"!")
    reset(secondguy)
  elif damage==0:
    roll=str(roll)
    secondguyhealth=str(secondguyhealth)
    say(firstguy +"["+ firstguyhealth +"] rolls "+ roll +", missing "+ secondguy +"!")
  else:
    secondguyhealth=str(secondguyhealth)
    roll=str(roll)
    damage=str(damage)
    say(firstguy +"["+ firstguyhealth +"] rolls "+ roll +", "+ modifier +" "+ secondguy +"!")

def reset(user):
  if user=="all":
    healthtable.clear()
    #say("k.")
  else:
    try:
      healthtable[user]=100
    except KeyError:
      print "uhh..."


def fuckyou(msg):
  name=msg.split("!")[0]
  name=name.split(":")[1]
  say("fuck you, "+ name +".")



ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ircsock.connect((server, 6667)) # Here we connect to the server using the port 6667
ircsock.send("USER "+ botnick +" "+ botnick +" "+ botnick +" :This bot is a result of a tutoral covered on http://shellium.org/wiki.\n") # user authentication
ircsock.send("NICK "+ botnick +"\n") # here we actually assign the nick to the bot

time.sleep(3)
identify()
time.sleep(10)
joinchan(channel) # Join the channel using the functions we previously defined

while 1: # Be careful with these! it might send you to an infinite loop
  try:
    ircmsg = ircsock.recv(2048) # receive data from the server
    ircmsg = ircmsg.strip('\n\r') # removing any unnecessary linebreaks.
  except KeyboardInterrupt:
    say("NOT ALL THOSE WHO DONGER ARE LOST")
    print("Exiting due to keyboard interrupt")
    sys.exit(0)
  print(ircmsg) # Here we print what's coming from the server

  if ircmsg.find(":Hello "+ botnick) != -1: # If we can find "Hello Mybot" it will call the function hello()
    hello()

  if ircmsg.find("PRIVMSG dongerdong :") != -1:
    userhost=ircmsg.split(":")[1]
    userhost=userhost.split(" ")[0]
    #ircsock.send("MODE "+ channel +" +b "+ userhost  +"\n")


  if ircmsg.find(":!fight ") != -1:
    firstguy=ircmsg.split("!")[0]
    attacker=firstguy.split(":")[1]
    secondguy=ircmsg.split("fight ")[1]
    secondguy=secondguy.strip()
    if secondguy.find(botnick) != -1:
      fighting = False
      say("FUCK YOU")
      ascii("rekt")
      kick(attacker,"DON'T FUCK WITH ME")
      time.sleep(1)
      say("Seriously though fuck that guy.")
    else:
      defender=secondguy
      pending[attacker.lower()]=secondguy.lower()
      say(defender +": "+ attacker +" has challenged you. To accept, use '!accept "+ attacker +"'.")

  if ircmsg.find(":!accept ") != -1:
    firstguy=ircmsg.split("!")[0]
    firstguy=firstguy.split(":")[1]
    secondguy=ircmsg.split("accept ")[1]
    secondguy=secondguy.strip()
    try:
      if pending[secondguy.lower()]==firstguy.lower():
        if random.randint(1,2)==1:
          fight(secondguy,firstguy)
        else:
          fight(firstguy,secondguy)
        fighting = False
      else:
        say("They didn't challenge you. You can challenge them if you want.")
    except IndexError:
       say("No one has challenged you, "+ defender +".")
    except KeyError:
       say("They didn't challenge you. You can challenge them if you want (KeyError).")
      
  if ircmsg.find(" :!attack ") != -1:
    if ircmsg.find("dongerdong") != -1:
      fuckyou(ircmsg)
    else:
      attack(ircmsg)

  if ircmsg.find(" :!reset") != -1:
    reset("all")

  if ircmsg.find(" :!health ") != -1:
    secondguy=ircmsg.split("health ")[1]
    say("Their health is "+ healthAsString(secondguy) +".")    
  elif ircmsg.find(" :!health") != -1:
    firstguy=ircmsg.split("!")[0]
    firstguy=firstguy.split(":")[1]
    say("Your health is "+ healthAsString(firstguy) +".")

  if ircmsg.find(" :!help") != -1:
    say("!fight <nick> to initiate fight; !quit to bail out of a fight of someone leaves; !hit to hit, !heal to heal. !reset resets the health stats (done automagically after a fight ends anyway)")

  if ircmsg.find(" :"+ botnick +"!") != -1:
    bang(ircmsg)

  if ircmsg.find("PING :") != -1: # if the server pings us then we've got to respond!
    ping()
