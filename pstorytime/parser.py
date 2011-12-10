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

class CmdParser(object):
  def __init__(self,audiobook,handler=None):
    self._audiobook = audiobook
    self._quit = Event()
    if handler != None:
      Thread(target=self.reader,args=(handler,)).start()

  def quit(self,handler):
    self._quit.set()

  def reader(self,handler):
    while not self._quit.is_set():
      try:
        line = handler.readline()
      except:
        break
      self.do(line)


  def do(self,line):
    ab = self._audiobook
    data = line.split()
    if len(data)>0:
      cmd = data[0]
      if cmd=="play" and len(data)==1:
        ab.play()
      if cmd=="playfile" and len(data)>=2:
        filename = " ".join(data[1:])
        ab.play(start_file=filename)
      if cmd=="playpos" and len(data)==2:
        pos = int(data[1])
        ab.play(start_pos=pos)
      if cmd=="playfilepos" and len(data)>=3:
        filename = int(data[1:-1])
        pos = int(data[1:-1])
        ab.play(start_file=filename,start_pos=pos)
      if cmd=="pause" and len(data)==1:
        ab.pause()
      if cmd=="seek" and len(data)==1:
        ab.seek()
      if cmd=="seekfile" and len(data)>=2:
        filename = " ".join(data[1:])
        ab.seek(start_file=filename)
      if cmd=="seekpos" and len(data)==2:
        pos = int(data[1])
        ab.seek(start_pos=pos)
      if cmd=="seekfilepos" and len(data)>=3:
        filename = " ".join(data[1:-1])
        pos = int(data[-1])
        ab.seek(start_file=filename,start_pos=pos)
      if cmd=="dseek" and len(data)==2:
        delta = int(data[1])
        ab.dseek(delta)
      if cmd=="play_pause" and len(data)==1:
        ab.play_pause()
      if cmd=="quit" and len(data)==1:
        ab.destroy()
        self.quit()
