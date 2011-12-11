# -*- coding: utf-8 -*-
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

from threading import Thread, Event
from gst import SECOND
import gobject

class CmdParser(gobject.GObject):
  __gsignals__ = {
    'quit' : (gobject.SIGNAL_RUN_LAST,
              gobject.TYPE_NONE,
              (gobject.TYPE_BOOLEAN,))
  }

  def __init__(self,audiobook,handler=None):
    gobject.GObject.__init__(self)
    self._audiobook = audiobook
    self._quit = Event()
    if handler != None:
      Thread(target=self._reader,args=(handler,),name="CmdParser").start()

  def quit(self):
    self._quit.set()

  def _reader(self,handler):
    while not self._quit.is_set():
      try:
        line = handler.readline()
      except IOError:
        break
      self.do(line)


  def do(self,line):
    ab = self._audiobook
    data = line.split()
    if len(data)>0:
      try:
        cmd = data[0]

        if cmd=="play":
          start_file = self.get_file(data)
          start_pos = self.get_pos(data)
          ab.play(start_file=start_file,start_pos=start_pos)

        if cmd=="pause":
          ab.pause()

        if cmd=="seek":
          start_file = self.get_file(data)
          start_pos = self.get_pos(data)
          ab.seek(start_file=start_file,start_pos=start_pos)

        if cmd=="dseek" and len(data)==2:
          delta = self.get_pos(data)
          if delta != None:
            ab.dseek(delta)

        if cmd=="stepfile" and len(data)==2:
          delta = int(data[1])
          new_file = ab.get_file(delta)
          if new_file!=None:
            ab.seek(start_file=new_file)

        if cmd=="play_pause" and len(data)==1:
          ab.play_pause()

        if cmd=="quit" and len(data)==1:
          self.emit("quit",False)
      except ParseFail as e:
        pass

  def get_file(self,data):
    if len(data)>=3:
      return " ".join(data[1:-1])
    else:
      return None

  def get_pos(self,data):
    if len(data)>=2:
      pos = parse_pos(data[-1])
      if pos == None:
        raise ParseFail()
      return pos
    else:
      return None

def parse_pos(raw):
  # Take care of negative positions
  if raw[0] == "-":
    sign = -1
    raw = raw[1:]
  elif raw[0] == "+":
    sign = 1
    raw = raw[1:]
  else:
    sign = 1

  for c in raw:
    if c not in ":0123456789":
      return None

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
    return None

  return sign * ((hours*60 + minutes)*60 + seconds) * SECOND

class ParseFail(Exception):
  pass
