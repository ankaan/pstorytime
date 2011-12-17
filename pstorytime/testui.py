# -*- coding: utf-8 -*-
"""A simple test user interface for the audiobook API. """

#
# Copyright (C) 2011 Anders Engström <ankan@ankan.eu>
#
# This file is part of pstorytime.
#
# pstorytime is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pstorytime is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pstorytime.  If not, see <http://www.gnu.org/licenses/>.

__all__ = [
  'TestUI',
  ]

import gobject
import glib
import sys
from threading import RLock

from pstorytime import *
from pstorytime.cmdparser import *
from pstorytime.poswriter import *
from pstorytime.misc import PathGen, FileLock, LockedException

class TestUI(object):
  """A simple test user interface for the audiobook API. """
  def __init__(self,conf,fifopath,directory):
    """Create the user interface.

    Argements:
      conf        The audiobook configuration to use.
      fifopath    Path to the fifo to read commands from.
      directory   The directory where the audiobook is found.
    """
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
    """The end of the audiobook have been reached.

    Arguments:
      obj   The audiobook player.
      prop  The property that was changed.
    """
    with self._lock:
      # Make sure that we are still at the end of the book.
      # This could have changed while we waited at the lock.
      if self._audiobook.eob:
        print("End of book.")

  def _on_error(self,obj,e):
    """An error was received.

    Argements:
      obj   The audiobook player.
      e     The error message as a string.
    """
    with self._lock:
      print("Error: {0}".format(e))

  def _on_quit(self,obj):
    """The user asked to shut down the player.
    
    Arguments:
      obj   The parser interface.
    """
    with self._lock:
      self.quit()

  def quit(self):
    """Shut down the audiobook player.
    """
    with self._lock:
      self._audiobook.pause()
      self._parser.quit()
      self._poswriter.quit()
      self._audiobook.quit()
      self._mainloop.quit()

  def run(self):
    """Run the audiobook player."""
    try:
      self._mainloop.run()
    except (KeyboardInterrupt, SystemExit):
      self.quit()

if __name__ == '__main__':
  # Read audiobook directory
  if len(sys.argv)==0:
    print("Usage: {0} <audiobookdir>".format(sys.argv[0]))
    sys.exit(1)
  directory = sys.argv[1]

  class Config(object):
    pass
  conf = Config()

  conf.backtrack = None
  conf.extensions = []
  conf.autolog_interval = 60

  pathgen = PathGen("~/.pstorytime",directory)
  conf.playlog_file = pathgen.gen(".playlog")

  cmdpipe = "~/.pstorytime/cmdpipe"
  
  pipelock = FileLock(cmdpipe+".lock")
  dirlock = FileLock(conf.playlog_file+".lock")

  try:
    with pipelock:
      with dirlock:
        ui = TestUI(conf,cmdpipe,directory)
        ui.run()
  except LockedException:
    print "Error: Another instance is already using the same files."
    sys.exit(1)

