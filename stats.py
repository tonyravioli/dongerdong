#!/usr/bin/env python
import csv
import collections
import urllib2


statsfile='http://ravio.li/donger/stats.txt'

data=urllib2.urlopen(statsfile)

wins=[]

wins = collections.Counter()

#input_file = open('stats.txt', 'r')
input_file=data
try:
  for row in csv.reader(input_file, delimiter=','):
    try:
      wins[row[2]] += 1
    except KeyError:
      wins[row[2]] = 1

finally:
  input_file.close()

for winner,numberOfWins in wins:
  print winner + str(numberOfWins)
