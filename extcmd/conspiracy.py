#!/usr/bin/env python3
import markovify.text


def doit(sentences=2):

  logfile = "../../conspiradump.txt" #This is only here for testing and debugging.

  #Maybe we'll replace this with a server-side thing on donger.org that provides a response in the form of something like "donger.org/conspiracy.php?sentences=2". That would make it so we don't have to put a 1MB text file in a repo.

  with open(logfile) as f:
    text = f.read()

  model = markovify.text.NewlineText(text, state_size=3)
  longstring = ''

  for i in range(sentences):
    sent = model.make_sentence(tries=50)
    try:
      if sent.endswith("." or "?"):
        sent = "{} ".format(sent)
      else:
        sent = "{}. ".format(sent)
      longstring = "{}{}".format(longstring,sent)
    except AttributeError:
      continue

  return longstring

def helptext():
  return "Outputs a markov chain from /r/conspiracy comments"