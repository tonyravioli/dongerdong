#!/usr/bin/env python3
import json
import random
helptext = "Outputs a random tweet from Jaden Smith."

jadenlist = json.load(open("wisdom/jaden.json"))
def doit(irc, target, source):
  irc.message(target, random.choice(jadenlist))
