import gobject
import glib
import time
import sys
from threading import Thread
from os.path import abspath, expanduser, join

from pstorytime import *
from pstorytime.parser import *
from pstorytime.poswriter import *

try:
  directory = sys.argv[1]
  config = Config()
  config.autolog_interval = 5

  audiobook = AudioBook(config,directory)
  parser = CmdParser(audiobook,handler=sys.stdin)

  log_prefix = config.log_prefix
  posdump_file = ".posdump"
  posdump_file = abspath(expanduser(join(directory,posdump_file)))
  posdump_file = abspath(expanduser(join(log_prefix, posdump_file[1:])))
  poswriter = PosWriter(audiobook,filename=posdump_file)

  gobject.threads_init()
  mainloop = glib.MainLoop()
except Exception as e:
  print(e)
  sys.exit(1)

def on_eob(obj,prop):
  if obj.eob:
    print("EOB")

def on_error(obj,e):
  print("Error: {0}".format(e))

def on_quit(obj,error):
  audiobook.pause()
  parser.quit()
  poswriter.quit()
  audiobook.quit()
  mainloop.quit()
  print("closing session")

audiobook.connect("notify::eob",on_eob)
audiobook.connect("error",on_error)
parser.connect("quit",on_quit)

mainloop.run()
