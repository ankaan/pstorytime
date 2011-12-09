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

import os.path
import threading
import time
import gobject

from pstorytime.repeatingtimer import RepeatingTimer

class LogEntry(gobject.GObject):
  walltime = gobject.property(type=int, minimum=0)
  event = gobject.property(type=str)
  position = gobject.property(type=int, minimum=0)
  filename = gobject.property(type=str)

  @staticmethod
  def parse(line):
    # Remove last character if it is a newline.
    if len(line)>0 and line.endswith("\n"):
      line = line[:-1]

    data = line.split(' ',3)
    if len(data)==4:
      [walltime, event, position, filename] = data
      return LogEntry(walltime, event, position, filename)
    else:
      return None

  def __init__(self,walltime,event,position,filename):
    gobject.GObject.__gobject_init__(self)
    self.walltime = int(walltime)
    self.event = event
    self.position = int(position)
    self.filename = filename

  def __str__(self):
    return "{walltime} {event} {position} {filename}".format( walltime = self.walltime,
                                                              event = self.event,
                                                              position = self.position,
                                                              filename = self.filename)

class Log(object):
  def __init__(self,bus,player,directory,playlog_file,autolog_file,autolog_interval):
    self._lock = threading.RLock()

    self._bus = bus
    self._player = player

    if playlog_file == None:
      playlog_file = ".playlogfile"
    self._playlog_file = os.path.expanduser(os.path.join(directory,playlog_file))

    if autolog_file == None:
      autolog_file = playlog_file+".auto"
    self._autolog_file = os.path.expanduser(os.path.join(directory,autolog_file))

    self._playlog = self._load(self._playlog_file)
    self._pending = ""

    self._autologtimer = RepeatingTimer(autolog_interval, self._autolognow)

    # Merge in old auto save (should only be there if the last session crashed
    # while playing.)
    if os.path.isfile(self._autolog_file):
      auto = self._load(self._autolog_file)
      if len(auto)==1:
        # Get walltime of last entry in playlog, if available.
        if len(self._playlog)>0:
          logtime = self._playlog[-1].walltime
        else:
          logtime = 0
        # Get walltime of entry in autolog.
        autotime = auto[0].walltime
        # Don't merge in autolog if the entry is older than the last already in the playlog.
        if autotime>=logtime:
          self._logentry(auto[0])
      os.remove(self._autolog_file)

  def destroy(self):
    self._autologtimer.destroy()

  def getlog(self):
    with self._lock:
      return self._playlog

  def start(self, seek=False, autolog=True):
    with self._lock:
      if seek:
        self._lognow("seekto")
      else:
        self._lognow("start")
      if autolog:
        self._autologtimer.start()

  def stop(self, seek=False, loadfail=False):
    with self._lock:
      if loadfail:
        self._lognow("loadfail")
      elif seek:
        self._lognow("seekfrom")
      else:
        self._lognow("stop")
      self._autologtimer.stop()
      os.remove(self._autolog_file)

  def _lognow(self,event):
    with self._lock:
      walltime = time.time()
      (filename,position,_) = self._player.position()
      self._logentry(LogEntry(walltime,event,position,filename))

  def _load(self,logfile):
    with self._lock:
      try:
        with open(logfile,'rb') as f:
          lines = f.readlines()
        return filter(lambda e: e!=None, map(LogEntry.parse, lines))
      except:
        return []

  def _autolognow(self):
    with self._lock:
      if self._autologtimer.started():
        self._writelog()
        walltime = time.time()
        (filename,position,_) = self._player.position()
        event = LogEntry(walltime, 'auto', position, filename)
        line = str(event)+"\n"
        try:
          with open(self._autolog_file,'wb') as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        except:
          self._bus.emit("error","Failed to write to auto log: {0}".format(self._autolog_file))

  def _logentry(self,entry):
    with self._lock:
      self._playlog.append(entry)
      self._pending += str(entry)+"\n"
      self._bus.emit("playlog",entry)
      self._writelog()

  def _writelog(self):
    with self._lock:
      if self._pending != "":
        try:
          with open(self._playlog_file,'ab') as f:
            f.write(self._pending)
            f.flush()
            os.fsync(f.fileno())
            self._pending = ""
        except:
          self._bus.emit("error","Failed to write to play log, data will be included in next write: {0}".format(self._playlog_file))
