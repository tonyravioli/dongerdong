#!/usr/bin/env python3
import json
import random
helptext = "Outputs a random tweet from Jaden Smith."

jadenlist = json.load(open("wisdom/jaden.json", 'r', encoding='utf-8'))
async def doit(irc, target, source):
  await irc.message(target, random.choice(jadenlist))
