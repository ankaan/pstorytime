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

import os
import string
import time
import threading
from os.path import *

from mplayer import *
from pstorytime import *

class AudioBook(object):
  def __init__(self,directory):
    self.lock = threading.RLock()
    with self.lock:
      self.directory = normcase(expanduser(directory))
      self.curfile = None
      self.curlength = 0.0
      if not isdir(directory):
        e = IOError()
        e.errno = 2
        e.strerror = "No such file or directory"
        e.filename = directory
        raise e

      self.playlogfile = ".pstorylog"
      self.autologfile = self.playlogfile+".auto"

      # Load play log from file.
      self.playlog = self._loadlog(self.playlogfile)

      # Merge in old auto save (should only be there if last session crashed while playing.)
      if isfile(self.autologfile):
        auto = self._loadlog(self.autologfile)
        if len(auto)==1:
          self._rawlog(auto[0])
        os.remove(self.autologfile)

      self.playing = False

      # Set up mplayer.
      self.player = Player(stdout=PIPE, stderr=PIPE, autospawn=False)


      ### Beginning of ugly hack. ################################
      baseargs = self.player._base_args

      # "-really-quiet" changed to "-quiet" (needed to spot when mplayer fails to load files.)
      try:
        i = baseargs.index("-really-quiet")
        baseargs = baseargs[:i] + ("-quiet",) + baseargs[i+1:]
      except ValueError:
        pass

      # "-noconfig all" removed all together (we want to use ordinary mplayer config.)
      for i in xrange(0,len(baseargs)-1):
        if baseargs[i] == "-noconfig" and baseargs[i+1] == "all":
          baseargs = baseargs[:i] + baseargs[i+2:]
          break

      self.player._base_args = baseargs
      ### End of ugly hack. ######################################


      # Fix args.
      self.player.args = ['-msglevel', 'global=6', '-include', '~/.pstorytime/mplayer.conf']

      self.player.stdout.connect(self._handle_stdout)
      self.player.stderr.connect(self._handle_stderr)

      self.player.spawn()

  # Listen for events from mplayer.
  def _handle_stdout(self,data):
    print("stdout: {0}".format(data))
    if data == 'Starting playback...':
      self._startComplete()
    elif data.startswith('EOF code:'):
      self._fileDone()

  def _handle_stderr(self,data):
    print("stderr: {0}".format(data))
    if data == 'Failed to recognize file format.':
      self._fileDone()

  def _fileDone(self):
    nextfile = self.getFile(1)
    if nextfile != None:
      self._play(nextfile)
    else:
      self._endOfBook()

  def _endOfBook(self):
    self._lognow("end",self.curlength)

  def _startComplete(self):
    pass

  def listFiles(self):
    entries = os.listdir(self.directory)
    entries.sort()
    return filter(lambda e: isfile(join(self.directory,e)),entries)

  def play(self, startfile = None, startpos = None):
    return self._play(startfile, startpos, log=True)

  def _play(self, startfile = None, startpos = None, log = False):
    if (not self.playing) or startfile != None or startpos != None:
      self._pause(log = log)
      self.playing = True

      # Load state from play log
      if startfile == None and self.curfile == None:
        # Try to load last state from play log.
        if len(self.playlog) > 0:
          (_,_,pos,startfile) = self.playlog[-1]
          if startpos == None:
            startpos = pos
        # Or if the play log is empty, play the first file in the book.
        else:
          files = self.listFiles()
          if len(files) > 0:
            startfile = files[0]
      
      # Change file
      if startfile != None:
        self.curfile = startfile

      # Load file if necessary, otherwise unpause if not playing anything.
      if self.curfile != self.player.filename:
        path = join(self.directory,self.curfile)
        self.player.loadfile(path)
      elif self.player.paused:
        self.player.pause()

      self.curlength = self.player.length

      # Set position in file.
      if startpos != None:
        if startpos < -self.curlength:
          # Position is in a file further back
          prevfile = self._getFile(-1)
          if prevfile == None:
            # Start playing where we are, in the beginning of the first file.
            pass
          else:
            self._play(prevfile, self.curlength-startpos)
        elif startpos < 0:
          # Position relative to the end of the file
          self.player.time_pos = self.curlength-startpos
        elif startpos < self.curlength:
          # Position relative to the beginning of the file
          self.player.time_pos = startpos
        else:
          # Position is in a file further on
          nextfile = self._getFile(1)
          if nextfile == None:
            self._endOfBook()
          else:
            self._play(nextfile, startpos-self.curlength)

      # Update play log.
      self._lognow("start",self.player.time_pos)
      # TODO: Update auto save, start autosaving.
          

  def pause(self):
    self._pause(log = True)

  def _pause(self, log = False):
    if self.playing:
      self.playing = False
      if not self.player.paused:
        # Pause playback
        self.player.pause()

      # Update play log.
      self._lognow("stop",self.player.time_pos)
      # TODO: Remove autosave, stop autosaving.
      #pos = self.player.time_pos

  def playpause(self):
    if self.playing:
      self.pause()
    else:
      self.play()

  def status(self):
    return  { "playing"   : self.playing
            , "directory" : self.directory
            , "curfile"   : self.curfile
            , "curlength" : self.curlength
            , "position"  : self.player.time_pos
            , "volume"    : self.player.volume
            , "speed"     : self.player.speed
            }

  def vol(self,v):
    self.player.volume = v

  def dvol(self,dv):
    self.player.volume = Step(dv)

  def speed(self,s):
    self.player.speed = s

  def dspeed(self,ds):
    self.player.speed = Step(ds)

  def getFile(self,d):
    try:
      files = self.listFiles()
      i = files.index(self.curfile)
      if 0 < i+d <= len(files):
        return files[i+d]
      else:
        return None
    except ValueError:
      return None

  def getlog(self):
    return self.playlog[:]

  def _autolognow(self):
    pos = self.player.time_pos
    if pos != None and self.curfile != None:
      walltime = time.time()
      data = map(str, (walltime, "auto", pos, self.curfile))
      path = join(self.directory,self.autologfile)
      line = string.join(data)
      try:
        with open(path,'wb') as f:
          f.write(line)
          f.flush()
          os.fsync(f.fileno())
      except:
        # Do not retry. Autosaving will be done again soon anyway.
        pass 
        # TODO: Notify user of failure?
    else:
      self._autologstop()

  def _autologstop(self):
    os.remove(self.autologfile)

  def _lognow(self,event,pos):
    assert self.curfile != None, 'Curfile not set when writing to the play log.'
    assert len(event.split()) == 1, 'The event name used when writing to log must be exactly one word.'
    walltime = time.time()
    self._rawlog(map(str, (walltime, event, pos, self.curfile)))

  def _rawlog(self,data):
    assert len(data) == 4, "_rawlog takes a tuple of 4 elements."
    path = join(self.directory,self.playlogfile)
    self.playlog.append(data)
    line = string.join(data)+"\n"
    try:
      with open(path,'ab') as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    except:
      pass
      # TODO: Notify user of failure?
      # TODO: Retry write.

  def _loadlog(self,logfile):
    path = join(self.directory,logfile)
    try:
      with open(path,'rb') as f:
        lines = f.readlines()
      return map(lambda line: tuple(line.split(' ',3)), lines)
    except:
      return []
