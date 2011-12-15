# -*- coding: utf-8 -*-
"""A console interface based on curses. """

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

from threading import Thread, RLock
import sys
import curses
import gobject
import glib
from datetime import timedelta
from os.path import isfile, isdir, join, expanduser, dirname, basename

import pygst
pygst.require("0.10")

# Don't touch my arguments!
argv = sys.argv
sys.argv = []
import gst
sys.argv = argv

import argparse

from pstorytime import *
from pstorytime.cmdparser import *
from pstorytime.misc import PathGen, FileLock, DummyLock, LockedException
from pstorytime.repeatingtimer import RepeatingTimer
import pstorytime.audiobookargs

class Input(object):
  def __init__(self,window,charmap,parser=None):
    self._lock = RLock()
    self._window = window
    self._charmap = charmap
    self._parser = parser
    self._eventmap = {}
    self._thread = Thread(target=self._run,
                          name="Input")
    self._thread.setDaemon(True)

  def _run(self):
    key = curses.keyname(self._window.getch())
    try:
      with self._lock:
        event = self._charmap[key]
        eventname = event.split()[0]
        handlers = self._eventmap[eventname]
      for fun in handlers:
        fun(event)
      if parser!=None and len(handlers)==0:
        parser.do(event)
    except (KeyError, IndexError):
      pass

  def register(self,eventname,handler):
    with self._lock:
      self._eventmap.get(eventname,[]).append(handler)

  def unregister(self,eventname,handler):
    with self._lock:
      if eventname in self._eventmap:
        try:
          self._eventmap[eventname].remove(handler)
        except IndexError:
          pass
        if len(self._eventmap[eventname])==0:
          del self._eventmap[eventname]

class Volume(object):
  HEIGHT = 1
  WIDTH = 6

  def __init__(self,audiobook,geom):
    self._lock = RLock()
    self._gst = audiobook.gst()
    self._window = geom.newwin()
    self._update()
    self._gst.connect("notify::volume",self._on_volume)

  def getGeom(self):
    with self._lock:
      return Geom.fromWindow(self._window)

  def setGeom(self,geom):
    with self._lock:
      self._window.resize(geom.h,geom.w)
      self._window.mvwin(geom.y,geom.x)

  def _on_volume(self,obj,prop):
    with self._lock:
      self._update()

  def _update(self):
    with self._lock:
      try:
        vol = "{0:.0%}".format(self._gst.get_property("volume"))
      except gst.QueryError:
        vol = "--%"
      self._window.erase()
      self._window.addstr(0,0,"{0:>5}".format(vol))
      self._window.refresh()

class Status(object):
  def __init__(self,conf,audiobook,geom,interval):
    """Create the audiobook view.
    
    Arguments:
      conf        The parsed program configuration.
      audiobook   The audiobook object to create a view for.
      geom        Geometry of the window.
      interval    How often to show position while playing.
    """
    self._lock = RLock()
    self._audiobook = audiobook
    with self._lock:
      self._audiobook.connect("position",self._on_position)
      self._audiobook.connect("notify::playing",self._on_playing)
      self._gst = self._audiobook.gst()
      self._window = geom.newwin()
      self._timer = RepeatingTimer(interval, self._update)
      self._update()

  def getGeom(self):
    return Geom.fromWindow(self._window)

  def setGeom(self,geom):
    self._window.resize(geom.h,geom.w)
    self._window.mvwin(geom.y,geom.x)

  def _on_playing(self,ab,prop):
    """Playing state updated.
    
    Arguments:
      ab    The audiobook that this is a view for.
      prop  The property that was updated.
    """
    with self._lock:
      if ab.playing and (not self._timer.started()):
        self._timer.start()
      if (not ab.playing) and self._timer.started():
        self._timer.stop()

  def _on_position(self,ab):
    """A hint has been received that it is a good idea to update the position information.
    
    Arguments:
      ab    The audiobook that this is a view for.
    """
    with self._lock:
      self._update()

  def _update(self):
    with self._lock:
      (filename,position,duration) = self._audiobook.position()

      position = timedelta(microseconds=position/1000)
      position = position - timedelta(microseconds=position.microseconds)

      duration = timedelta(microseconds=duration/1000)
      duration = duration - timedelta(microseconds=duration.microseconds)

      self._window.erase()
      self._window.addstr(0,0,
        "{filename}: {position} / {duration}".format( filename=filename,
                                                      position=position,
                                                      duration=duration)
        )
      self._window.refresh()

class Geometry(object):
  @staticmethod
  def fromWindow(window):
    return Geometry.fromSizePos(window.getmaxyx(),
                                window.getyx())

  @staticmethod
  def fromSizePos(size,pos):
    return Geometry(size[0],size[1],pos[0],pos[1])

  def __init__(self,h,w,y,x):
    self.h = h
    self.w = w
    self.y = y
    self.x = x

  def newwin(self):
    return curses.newwin( self.h,
                          self.w,
                          self.y,
                          self.x)

class CursesUI(object):
  def __init__(self,conf,directory,stdscr):
    self._lock = RLock()
    with self._lock:
      self._conf = conf
      self._window = stdscr
      self._audiobook = AudioBook(conf,directory)

      self._parser = CmdParser(self._audiobook,fifopath=conf.cmdpipe)
      self._parser.connect("quit",self._on_quit)

      gobject.threads_init()
      self._mainloop = glib.MainLoop()

      charmap = { curses.KEY_RESIZE : "resize" }
      self._input = Input(window=self._window,
                          charmap=charmap,
                          parser=self._parser)
      self._input.register("resize",self._on_resize)

      topgeom = Geometry.fromWindow(self._window)

      self._volume = Volume(audiobook=self._audiobook,
                            geom=self._volume_geom())

      self._status = Status(conf=conf,
                            audiobook=self._audiobook,
                            geom=self._status_geom(),
                            interval=1)

  def _volume_geom(self):
    topgeom = Geometry.fromWindow(self._window)
    return Geometry(h=Volume.HEIGHT,
                    w=Volume.WIDTH,
                    y=topgeom.h-Volume.HEIGHT,
                    x=topgeom.w-Volume.WIDTH)

  def _status_geom(self):
    topgeom = Geometry.fromWindow(self._window)
    return Geometry(h=1,
                    w=topgeom.w-Volume.WIDTH,
                    y=topgeom.h-1,
                    x=0)

  def _on_resize(event):
    self._update_layout()

  def _update_layout():
    self._volume.setGeom(self._volume_geom())
    self._status.setGeom(self._status_geom())

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
      self._audiobook.quit()
      self._mainloop.quit()

  def run(self,filename,position):
    """Run the audiobook player.
    
    Arguments:
      filename  The filename to start playing at. (Or None to let the player
                decide.)

      position  The position to start playing at. (Or none to let the player
                decide.)
    """
    try:
      if(conf.autoplay):
        self._audiobook.play(filename,position)
      else:
        self._audiobook.seek(filename,position)
      self._mainloop.run()
    except (KeyboardInterrupt, SystemExit):
      self.quit()

if __name__ == '__main__':
  parser = pstorytime.audiobookargs.ArgumentParser(
    description="%(prog)s is a logging console audiobook player.",
    epilog="Paths can contain the strings {conf} and {audiobook}. They are replaced with the absolute path to the configuration directory and the audiobook directory respectively.",
    add_help=True,
    parents=[pstorytime.audiobookargs.audiobookargs],
    fromfile_prefix_chars="@",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    conflict_handler='resolve')

  parser.add_argument(
    "--cmdpipe",
    help="Path to a pipe that commands are read from relative to current directory. See section on paths.",
    default="")

  parser.add_argument(
    "--playlog-file",
    help="Path to the file to save playlog in relative to current directory. See section on paths.",
    default="{conf}/logs/{audiobook}/.playlog")

  parser.add_argument(
    "--conf-dir",
    help="Configuration directory",
    default="~/.pstorytime")

  parser.add_argument(
    "path",
    help="Audiobook directory, possibly including a file to start playing at.",
    nargs='?',
    default=".")

  parser.add_argument(
    "position",
    help="Position to start playing at.",
    nargs='?',
    action=pstorytime.audiobookargs.Position)

  parser.add_argument(
    "--noconf",
    help="Do not read default config file.",
    action='store_true')

  parser.add_argument(
    "--autoplay",
    help="Start playing when the audiobook is started.",
    dest='autoplay',
    type=bool)

  conf = parser.parse_args()

  configfile = expanduser(join(conf.conf_dir,"config"))

  if (not conf.read_conf) and isfile(configfile):
    conf = parser.parse_args(["@"+configfile])
    conf = parser.parse_args(namespace=conf)

  if isfile(conf.path):
    directory = dirname(conf.path)
    filename = basename(conf.path)
  elif isdir(conf.path):
    directory = conf.path
    filename = None
  else:
    print("No such file or directory: {0}".format(conf.path))
    exit(1)

  gen = PathGen(conf.conf_dir,directory)
  conf.playlog_file = gen.gen(conf.playlog_file)
  conf.cmdpipe = gen.gen(conf.cmdpipe)

  if conf.cmdpipe==None or conf.cmdpipe=="":
    pipelock = DummyLock()
  else:
    pipelock = FileLock(conf.cmdpipe+".lock")

  dirlock = FileLock(conf.playlog_file+".lock")

  try:
    with pipelock:
      with dirlock:
        def run(stdscr):
          ui = CursesUI(conf,directory,stdscr)
          ui.run(filename,conf.position)
        curses.wrapper(run)
  except LockedException:
    print("Error: Another instance is already using the same files.")
    sys.exit(1)

