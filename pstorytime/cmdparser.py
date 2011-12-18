# -*- coding: utf-8 -*-
"""A simple parser interface for an audiobook player."""

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

from threading import Thread, Event, RLock
from gst import SECOND
import gobject
import os
from os.path import exists, expanduser

import select
import time

__all__ = [
  'CmdParser',
  'parse_pos',
  ]

class CmdParser(gobject.GObject):
  """A command parser for an audiobook player.
  
  Signals:
    quit    This signal is emitted when the quit command is parsed and it
            should cleanly shut down the audiobook player.
  """
  __gsignals__ = {
    'error' : ( gobject.SIGNAL_RUN_LAST,
                gobject.TYPE_NONE,
                (gobject.TYPE_STRING,)),
    'quit' : (gobject.SIGNAL_RUN_LAST,
              gobject.TYPE_NONE,
              tuple())
  }

  def __init__(self,audiobook,handler=None,fifopath=None):
    """Create the parser that optionally reads from a file handler or the given
    path to a fifo.

    Arguments:
      audiobook = The audiobook player object to control.
      fifopath = Path to a fifo to read from. None to ignore.
    """
    gobject.GObject.__init__(self)
    self._lock = RLock()
    self._audiobook = audiobook
    self._quit = Event()
    self._thread = Thread(target=self._reader,
                          kwargs={"fifopath":fifopath},
                          name="CmdParser")
    self._thread.setDaemon(True)
    self._thread.start()
    self._eventmap = {}

  def register(self,eventname,handler):
    with self._lock:
      handlers = self._eventmap.get(eventname,[])
      handlers.append(handler)
      self._eventmap[eventname] = handlers

  def unregister(self,eventname,handler):
    with self._lock:
      if eventname in self._eventmap:
        try:
          self._eventmap[eventname].remove(handler)
        except IndexError:
          pass
        if len(self._eventmap[eventname])==0:
          del self._eventmap[eventname]

  def quit(self):
    """Shut down the parser."""
    self._quit.set()

  def _reader(self,fifopath=None):
    """Start reading data from given file/handler.

    Arguments:
      handler   File handler to read from.
      fifopath  Path to a fifo to read from.
    """
    if fifopath!=None and len(fifopath)>0:
      # Create fifo if it does not exist.
      fifopath = expanduser(fifopath)
      if not exists(fifopath):
        os.mkfifo(fifopath,0700)

      while not self._quit.is_set():
        f = file(fifopath,'r')
        for line in f:
          self.do(line)

  def do(self,line):
    """Try to run the given command.

    Arguments:
      line  A command to run given as a string.
    """
    with self._lock:
      handlers = []
      ab = self._audiobook
      data = line.split()
      if len(data)>0:
        try:
          cmd = data[0]

          if cmd=="play":
            start_file = self._get_file(data)
            (rel, start_pos) = self._get_pos(data)
            ab.play(start_file=start_file,start_pos=start_pos)
            return True

          elif cmd=="pause":
            ab.pause()
            return True

          elif cmd=="seek":
            start_file = self._get_file(data)
            (rel, start_pos) = self._get_pos(data)
            if start_file == None and rel:
              ab.dseek(start_pos)
            else:
              ab.seek(start_file=start_file,start_pos=start_pos)
            return True

          elif cmd=="dseek" and len(data)==2:
            (rel, start_pos) = self._get_pos(data)
            if start_pos != None:
              ab.dseek(start_pos)
            return True

          elif cmd=="stepfile" and len(data)==2:
            delta = int(data[1])
            new_file = ab._get_file(delta)
            if new_file!=None:
              ab.seek(start_file=new_file,start_pos=0)
            return True

          elif cmd=="play_pause" and len(data)==1:
            ab.play_pause()
            return True

          elif (cmd=="volume" or cmd=="dvolume") and len(data)==2:
            raw = data[1]
            if raw[0] == "+" or raw[0] == "-" or cmd == "dvolume":
              gst = self._audiobook.gst()
              oldvol = gst.get_property("volume")
              volume = oldvol + float(raw)
            else:
              volume = float(raw)

            volume = max(0, min(volume, 10))
            gst.set_property("volume",volume)
            return True

          elif cmd=="quit" and len(data)==1:
            self.emit("quit")
            return True

          else:
            handlers = self._eventmap.get(cmd,[])

        except ValueError as e:
          pass

    if len(handlers)>0:
      for fun in handlers:
        fun(line)
      return True
    else:
      self.emit('error','Failed to parse: "{0}"'.format(line.strip()))
      return False

  def _get_file(self,data):
    """Parse a filename from given data.
    
    Arguments:
      data    List of strings representing each word.

    Returns:  Filename, or None if no filename was given.
    """
    if len(data)>=3:
      return " ".join(data[1:-1])
    else:
      return None

  def _get_pos(self,data):
    """Parse position.
    
    Arguments:
      data    List of strings representing each word.

    Returns:  Position, None if no position was given.

    Exceptions:
      ValueError if parsing failed.
    """
    if len(data)>=2:
      (rel, pos) = parse_pos(data[-1])
      if pos == None:
        raise ValueError()
      return (rel, pos)
    else:
      return (None,None)

def parse_pos(raw):
  """Parse position from given string.
  
  Arguments:
    raw     raw data that is parsed to a position.

  Returns:  Position of file in nanoseconds, or None
            if parsing failed.
  """

  # Take care of negative positions
  if raw[0] == "-":
    sign = -1
    raw = raw[1:]
    rel = True
  elif raw[0] == "+":
    sign = 1
    raw = raw[1:]
    rel = True
  else:
    sign = 1
    rel = False

  for c in raw:
    if c not in ":0123456789":
      return (None,None)

  parts = raw.split(":")

  seconds = 0
  minutes = 0
  hours = 0

  if len(parts) >= 1:
    seconds = int(parts[-1])
  if len(parts) >= 2:
    minutes = int(parts[-2])
  if len(parts) >= 3:
    hours = int(parts[-3])
  if len(parts) > 3:
    return (None,None)

  pos = sign * ((hours*60 + minutes)*60 + seconds) * SECOND
  return (rel, pos)
