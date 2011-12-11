import gobject
import glib
import sys
from threading import RLock

from pstorytime import *
from pstorytime.parser import *
from pstorytime.poswriter import *

class TestUI(object):
  def __init__(self,conf,fifopath,directory):
    self._lock = RLock()
    with self._lock:
      self._audiobook = AudioBook(conf,directory)
      self._parser = CmdParser(self._audiobook,fifopath=fifopath)
      self._poswriter = PosWriter(self._audiobook,handler=sys.stdout)

      gobject.threads_init()
      self._mainloop = glib.MainLoop()

      self._audiobook.connect("notify::eob",self._on_eob)
      self._audiobook.connect("error",self._on_error)
      self._parser.connect("quit",self._on_quit)

  def _on_eob(self,obj,prop):
    with self._lock:
      if self._audiobook.eob:
        print("End of book.")

  def _on_error(self,obj,e):
    with self._lock:
      print("Error: {0}".format(e))

  def _on_quit(self,obj):
    with self._lock:
      self.quit()

  def quit(self):
    with self._lock:
      self._audiobook.pause()
      self._parser.quit()
      self._poswriter.quit()
      self._audiobook.quit()
      self._mainloop.quit()

  def run(self):
    try:
      self._mainloop.run()
    except (KeyboardInterrupt, SystemExit):
      self.quit()

if __name__ == '__main__':
  if len(sys.argv)==0:
    print("Usage: {0} <audiobookdir>".format(sys.argv[0]))
    sys.exit(1)

  directory = sys.argv[1]
  
  conf = Config()
  conf.backtrack = 10

  ui = TestUI(conf,"~/.pstorytime/cmdpipe",directory)
  ui.run()
