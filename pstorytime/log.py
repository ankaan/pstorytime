# -*- coding: utf-8 -*-
"""Logging abstraction."""

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
  'LogEntry',
  'Log',
  ]

from os.path import isfile, dirname, isdir
import os
import threading
import time
import gobject

from pstorytime.timer import Timer
from pstorytime.misc import withdoc

class LogEntry(gobject.GObject):
  """Each event in the playlog is represented with one of these. """
  @withdoc(gobject.property)
  def walltime(self):
    """Walltime when the event occurred. """
    return self._walltime

  @withdoc(gobject.property)
  def event(self):
    """What happened. (Start/stop/seek etc.) """
    return self._event

  @withdoc(gobject.property)
  def filename(self):
    """Which filename the event occurred in. """
    return self._filename

  @withdoc(gobject.property)
  def position(self):
    """At what position the event occurred. """
    return self._position

  @withdoc(gobject.property)
  def duration(self):
    """At what position the event occurred. """
    return self._duration

  @staticmethod
  def parse(line):
    """Parse a line of text into a LogEntry. """
    # Remove last character if it is a newline.
    if len(line)>0 and line.endswith("\n"):
      line = line[:-1]

    data = line.split(' ')
    if len(data)>=5:
      walltime = data[0]
      event = data[1]
      filename = " ".join(data[2:-2])
      position = data[-2]
      duration = data[-1]
      return LogEntry(walltime, event, filename, position, duration)
    else:
      return None

  def __init__(self,walltime,event,filename,position,duration):
    """Create a new LogEntry.
    
    Arguments:
      walltime  At what walltime did the event occur.
      event     What occurred.
      filename  In what file.
      position  At what position.
      duration  Duration of the file.
    """
    gobject.GObject.__gobject_init__(self)
    self._walltime = int(walltime)
    self._event = event
    self._filename = filename
    self._position = int(position)
    self._duration = int(duration)

  def __str__(self):
    """Convert the entry back into a string. """
    return "{e.walltime} {e.event} {e.filename} {e.position} {e.duration}".format(e=self)

class Log(gobject.GObject):
  @withdoc(gobject.property)
  def playlog(self):
    """The current playlog. """
    with self._lock:
      return self._playlog

  def __init__(self,bus,player,directory,conf):
    """Create a new log handler.

    Arguments:
      bus               Which gobject to send error events to.

      player            Which object to ask the current position of.

      directory         Directory of the audiobook.

      conf        A configuration object like that from the result of the
                  parser in pstorytime.coreparser.
    """

    gobject.GObject.__gobject_init__(self)
    self._lock = threading.RLock()

    self._bus = bus
    self._player = player

    self._playlog_file = conf.playlog_file
    self._autolog_file = conf.playlog_file+".auto"

    self._playlog = self._load(self._playlog_file)
    self._pending = ""

    self._autologtimer = Timer(conf.autolog_interval*1000, self._autolognow, repeat=True)

    # Merge in old auto save (should only be there if the last session crashed
    # while playing.)
    if isfile(self._autolog_file):
      auto = self._load(self._autolog_file)
      if len(auto)==1:
        self._logentry(auto[0])
      os.remove(self._autolog_file)

  def start(self):
    """Start autologging (or reset the timer.)"""
    with self._lock:
      self._autologtimer.start()
      self._autolognow()

  def stop(self):
    """Stop autologging and remove autolog file."""
    with self._lock:
      self._autologtimer.stop()
      if isfile(self._autolog_file):
        os.remove(self._autolog_file)

  def lognow(self,event):
    """Log an event with the given event name at the current position and time.

    Arguments:
      event   The event type to log.
    """
    with self._lock:
      walltime = time.time()
      (filename,position,duration) = self._player.position()
      self._logentry(LogEntry(walltime,event,filename,position,duration))

  def _load(self,logfile):
    """Load log from given file.

    Arguments:
      logfile   File name to load log from.

    Return:     The loaded log.
    """
    with self._lock:
      try:
        with open(logfile,'rb') as f:
          lines = f.readlines()
        # Parse lines and remove invalid ones.
        return filter(lambda e: e!=None, map(LogEntry.parse, lines))
      except IOError:
        return []

  def _autolognow(self):
    """Save current position and such to autolog file now.
    """
    with self._lock:
      # Retry writing pending entries to the play log.
      self._writelog()
      # Make sure the autolog timer is running. The autologging could have been stopped
      # while we were waiting at the lock.
      if self._autologtimer.started():
        # Update autolog
        walltime = time.time()
        (filename,position,duration) = self._player.position()
        event = LogEntry(walltime, 'auto', filename, position, duration)
        line = str(event)+"\n"
        try:
          _write_file(self._autolog_file,'wb',line)
        except IOError:
          self._bus.emit("error","Failed to write to auto log: {0}".format(self._autolog_file))

  def _logentry(self,entry):
    """Log the given entry to the playlog.

    Arguments:
      entry   The entry to add.
    """
    with self._lock:
      self._playlog.append(entry)
      self.notify("playlog")
      self._pending += str(entry)+"\n"
      self._writelog()

  def _writelog(self):
    """Write all pending log entries to file. """
    with self._lock:
      if self._pending != "":
        try:
          _write_file(self._playlog_file,'ab',self._pending)
          self._pending = ""
        except IOError as e:
          self._bus.emit("error","Failed to write to play log, data will be included in next write: {0}".format(self._playlog_file))

def _write_file(filepath,writemode,data):
  """Write given data to the given file.

  Arguments:
    filepath    Path to the file that is written to.
    writemode   What mode to open the file with.
    data        The data to write.
  """
  dirpath = dirname(filepath)
  if not isdir(dirpath) and dirpath!='':
    os.makedirs(dirpath,mode=0700)
  with open(filepath,writemode) as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())
