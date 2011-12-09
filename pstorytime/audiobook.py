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

from os.path import normcase, expanduser, isfile, join
import threading
import mimetypes

from pstorytime.bus import Bus
from pstorytime.log import Log
import pstorytime.player

class Config(object):
  def __init__(self):
    self.playlog_file = None         # Becomes: ".playlogfile"
    self.autolog_file = None         # Becomes self.playlogfile + ".auto"
    self.extra_extensions = ["m4b"] # Not so uncommon audiobook format that is essentially a renamed m4a
    self.autolog_interval = 60      # In seconds

class AudioBook(object):
  SECOND = pstorytime.player.Player.SECOND

  def __init__(self,conf,directory):
    self.lock = threading.RLock()
    self._playing = False

    self._conf = conf
    self._directory = normcase(expanduser(directory))
    
    self.bus = Bus()
    self._player = pstorytime.player.Player(self.bus,self._directory)
    self._log = Log(self.bus,
                    self._player,
                    self._directory,
                    self._conf.playlog_file,
                    self._conf.autolog_file,
                    self._conf.autolog_interval)

    self.bus.connect("eos",self._on_eos)

  def _on_eos(self,verify_id):
    with self._lock:
      # Verify that it is still valid: the state of the player could have
      # changed while waiting at the lock.
      if self._player.verify_eos(verify_id):
        # The player reported an end of stream, go to next file.
        next_file = self.get_file(1)
        if next_file != None:
          self._play(next_file)
        else:
          self.bus.emit("eob",verify_id)
          
  def verify_eob(self,verify_id):
    return self._player.verify_eos(verify_id)

  def _play(self, startfile = None, startpos=None, log=False, seek=False):
    with self._lock:
      # Make sure we are not playing anything.
      self._pause(log=log, seek=seek)

      # Is this a seek while the player is paused?
      paused_seek = seek and not self._playing

      # Filename loaded before doing all this.
      old_file = self._player.filename()

      if old_file == None and startfile == None:
        # First play, and no file given.
        # Try to load last entry from play log.
        playlog = self._log.getlog()
        if len(playlog)>0:
          startfile = playlog[-1].filename
          if startpos==None:
            startpos = playlog[-1].position
        else:
          # Otherwise use first file in directory.
          dirlist = self.list_files()
          if len(dirlist)>0:
            startfile = dirlist[0]
          else:
            # Nothing to play!
            self.bus.emit("error","No valid files in audiobook directory.")
          

      if startfile != None and startfile != old_file:
        # Try to load new file.
        if not self._player.load(startfile):
          # Failed to load file.
          self._log.stop(seek=seek, loadfail=True)
          self.bus.emit("playing",False)
          self._playing = False
          return False

      if startpos != None:
        self._player.seek(startpos)

      if log:
        # Log "destination", don't start autologging if this is a paused seek.
        self._log.start(seek=seek, autolog=(not paused_seek))

      if not paused_seek:
        self._player.play()

      self.bus.emit("playing",True)
      self._playing = True
      return True

  def _pause(self, log=False, seek=False):
    with self._lock:
      if self._playing:
        self._playing = False
        self._player.pause()
        if log:
          self._log.stop(seek=seek)
        self.bus.emit("playing",False)

  def play(self, startfile=None, startpos=None):
    with self.lock:
      if (not self._playing) or startfile != None or startpos != None:
        return self._play(startfile, startpos, log=True)

  def seek(self, startfile=None, startpos=None):
    with self.lock:
      return self._play(startfile, startpos, log=True, seek=True)

  def pause(self):
    with self._lock:
      self._pause(log=True)

  def play_pause(self):
    with self._lock:
      if self._playing:
        self.pause()
      else:
        self.play()

  def position(self):
    with self._lock:
      return self._player.position()

  def list_files(self):
    with self._lock:
      entries = os.listdir(self._directory)
      entries.sort()
      return filter(self._is_audio_file, entries)
  
  def _is_audio_file(self,filename):
    with self._lock:
      if not isfile(join(self._directory,filename)):
        return False

      exts = tuple(map(lambda e: '.'+e, self._conf.extra_extensions))
      if filename.endswith(exts):
        return True

      (mime, _) = mimetypes.guess_type(filename)
      if mime != None:
        data = mime.split("/",1)
        return len(data)==2 and data[0] == "audio"
      else:
        return False

  def get_file(self,delta):
    try:
      files = self.list_files()
      i = files.index(self.curfile)
      if 0 < i+delta <= len(files):
        return files[i+delta]
      else:
        return None
    except ValueError:
      return None

  def getlog(self):
    return self._log.getlog()

  def gst(self):
    return self._player.gst

  def destroy(self):
    self._log.destroy()
