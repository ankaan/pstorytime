import gobject
import glib
import time
import sys
from threading import Thread

from pstorytime import *
from pstorytime.parser import *
from pstorytime.poswriter import *

try:
  directory = sys.argv[1]
  config = Config()
  config.autolog_interval = 5
  config.backtrack = 10

  audiobook = AudioBook(config,directory)
  parser = CmdParser(audiobook,fifopath="/home/ankan/.pstorytime/cmdpipe")

  log_prefix = config.log_prefix
  poswriter = PosWriter(audiobook,handler=sys.stdout)

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

def on_quit(obj):
  audiobook.pause()
  parser.quit()
  poswriter.quit()
  audiobook.quit()
  mainloop.quit()

audiobook.connect("notify::eob",on_eob)
audiobook.connect("error",on_error)
parser.connect("quit",on_quit)

mainloop.run()
