#!/usr/bin/env python3
import markovify.text
helptext = "Outputs a markov chain from /r/conspiracy comments"

def doit(sentences=2):
  logfile = "../conspiradump.txt" #This is only here for testing and debugging.
  #Maybe we'll replace this with a server-side thing on donger.org that provides a
  #response in the form of something like "donger.org/conspiracy.php?sentences=2".
  #That would make it so we don't have to put a 1MB text file in a repo.
  #
  #We could call it "Conspiracies As A Service"

  with open(logfile) as f:
    text = f.read()

  model = markovify.text.NewlineText(text, state_size=3)
  longstring = ''

  for i in range(sentences):
    sentence = model.make_sentence(tries=20).strip()
    try:
      if sentence.endswith("." or "?"):
        longstring += "{} ".format(sentence)
      else:
        longstring += "{}. ".format(sentence)
    except AttributeError:
      continue

  return longstring.strip()

