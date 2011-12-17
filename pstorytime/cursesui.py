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

from threading import Thread, RLock, Event
import sys
import curses
import gobject
import glib
from datetime import timedelta
from os.path import isfile, isdir, join, expanduser, dirname, basename
import select
import signal
import os

import pygst
pygst.require("0.10")

# Don't touch my arguments!
argv = sys.argv
sys.argv = []
import gst
sys.argv = argv

import argparse
import time

from pstorytime import *
from pstorytime.cmdparser import *
from pstorytime.misc import PathGen, FileLock, DummyLock, LockedException
from pstorytime.repeatingtimer import RepeatingTimer
import pstorytime.audiobookargs

class Input(object):
  HEIGHT=1

  def __init__(self,curseslock,geom,charmap,parser=None):
    self._lock = RLock()
    self._geom = geom
    self._curseslock = curseslock

    self._window = geom.newwin()
    self._window.nodelay(1)
    self._window.keypad(1)

    self._charmap = charmap
    self._parser = parser
    self._eventmap = {}

    self._key = ""
    self._update()

    self._quit = Event()
    signal.signal(signal.SIGUSR1, lambda signum, stack_frame: None)
    signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(0))

  def run(self):
    try:
      while not self._quit.is_set():
        try:
          select.select([sys.stdin],[],[sys.stdin])
        except select.error:
          pass

        if self._quit.is_set():
          break

        while True:
          with self._curseslock:
            ch = self._window.getch()
            if ch == -1:
              break
            key = curses.keyname(ch)
            self._key = key
            self._update()

          try:
            with self._lock:
              event = self._charmap[key]
              eventname = event.split()[0]
              handlers = self._eventmap.get(eventname,[])
            for fun in handlers:
              fun(event)
            if self._parser!=None and len(handlers)==0:
              self._parser.do(event)
          except (KeyError, IndexError):
            pass
    finally:
      self._quit.set()

  def quit(self):
    with self._lock:
      if not self._quit.is_set():
        self._quit.set()
        os.kill(os.getpid(), signal.SIGUSR1)

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

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        self._window.mvwin(geom.y,geom.x)
        self._window.resize(geom.h,geom.w)
        self._update()

  def _update(self):
    with self._lock:
      with self._curseslock:
        self._window.erase()
        self._window.addstr(0,0,"Key: '{0}'".format(self._key))
        self._window.refresh()

class Volume(object):
  HEIGHT = 2
  WIDTH = 6

  def __init__(self,curseslock,audiobook,geom):
    self._lock = RLock()
    self._curseslock = curseslock
    self._window = geom.newwin()
    self._gst = audiobook.gst()
    self._geom = geom
    self._gst.connect("notify::volume",self._on_volume)
    self._update()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        self._window.mvwin(geom.y,geom.x)
        self._window.resize(geom.h,geom.w)
        self._update()

  def _on_volume(self,obj,prop):
    with self._lock:
      self._update()

  def _update(self):
    with self._lock:
      try:
        vol = "{0:.0%}".format(self._gst.get_property("volume"))
      except gst.QueryError:
        vol = "--%"
      with self._curseslock:
        self._window.erase()
        self._window.addstr(0,0,"  Vol\n{0:>5}".format(vol))
        self._window.refresh()

class Status(object):
  HEIGHT = 2

  def __init__(self,curseslock,conf,audiobook,geom,interval):
    """Create the audiobook view.
    
    Arguments:
      conf        The parsed program configuration.
      audiobook   The audiobook object to create a view for.
      geom        Geometry of the window.
      interval    How often to show position while playing.
    """
    self._lock = RLock()
    self._curseslock = curseslock
    self._audiobook = audiobook
    self._geom = geom
    with self._lock:
      self._audiobook.connect("position",self._on_position)
      self._audiobook.connect("notify::playing",self._on_playing)
      self._gst = self._audiobook.gst()
      self._window = geom.newwin()
      self._timer = RepeatingTimer(interval, self._update)
      self._update()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        self._window.mvwin(geom.y,geom.x)
        self._window.resize(geom.h,geom.w)
        self._update()

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

      if self._audiobook.playing:
        state = "Playing"
      elif self._audiobook.eob:
        state = "End"
      else:
        state = "Paused"

      with self._curseslock:
        self._window.erase()
        self._window.addstr(0,0,
          "File: {filename}\n{position} / {duration} [{state}]".format(
            filename=filename,
            position=position,
            duration=duration,
            state=state)
          )
        self._window.refresh()

class Geometry(object):
  @staticmethod
  def fromWindow(window):
    return Geometry.fromSizePos(window.getmaxyx(),window.getbegyx())

  @staticmethod
  def fromSizePos(size,pos):
    return Geometry(size[0],size[1],pos[0],pos[1])

  def __init__(self,h,w,y,x):
    self.h = h
    self.w = w
    self.y = y
    self.x = x

  def newwin(self,parent=None):
    if parent==None:
      return curses.newwin( self.h,
                            self.w,
                            self.y,
                            self.x)
    else:
      return parent.subwin( self.h,
                            self.w,
                            self.y,
                            self.x)

  def __str__(self):
    return "({g.h},{g.w},{g.y},{g.x})".format(g=self)

class CursesUI(object):
  def __init__(self,conf,directory,stdscr):
    self._lock = RLock()
    self._curseslock = RLock()
    with self._lock:
      self._conf = conf
      self._window = stdscr
      self._audiobook = AudioBook(conf,directory)

      curses.curs_set(0)

      self._parser = CmdParser(self._audiobook,fifopath=conf.cmdpipe)
      self._parser.connect("quit",self._on_quit)

      gobject.threads_init()
      self._mainloop = glib.MainLoop()

      charmap = { "KEY_RESIZE":"resize",
                  "^L":"resize"}
      self._input = Input(curseslock=self._curseslock,
                          geom=self._input_geom(),
                          charmap=charmap,
                          parser=self._parser)

      self._input.register("resize",self._on_resize)

      with self._curseslock:
        self._volume = Volume(curseslock=self._curseslock,
                              audiobook=self._audiobook,
                              geom=self._volume_geom())

        self._status = Status(curseslock=self._curseslock,
                              conf=conf,
                              audiobook=self._audiobook,
                              geom=self._status_geom(),
                              interval=1)

      self._gobject_thread = Thread(target=self._mainloop.run,
                                    name="GobjectLoop")
      self._gobject_thread.setDaemon(True)

  def getGeom(self):
    with self._lock:
      return Geometry.fromWindow(self._window)

  def _input_geom(self):
    with self._lock:
      topgeom = self.getGeom()
      return Geometry(h=Input.HEIGHT,
                      w=topgeom.w,
                      y=topgeom.h-Status.HEIGHT-Input.HEIGHT,
                      x=0)

  def _volume_geom(self):
    with self._lock:
      topgeom = self.getGeom()
      return Geometry(h=Volume.HEIGHT,
                      w=Volume.WIDTH,
                      y=topgeom.h-Volume.HEIGHT,
                      x=topgeom.w-Volume.WIDTH)

  def _status_geom(self):
    with self._lock:
      topgeom = self.getGeom()
      return Geometry(h=Status.HEIGHT,
                      w=topgeom.w-Volume.WIDTH,
                      y=topgeom.h-Status.HEIGHT,
                      x=0)

  def _on_resize(self,event):
    with self._lock:
      self._update_layout()

  def _update_layout(self):
    with self._lock:
      with self._curseslock:
        self._input.setGeom(self._input_geom())
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
      self._mainloop.quit()
      self._parser.quit()
      self._audiobook.quit()
      self._input.quit()

  def run(self,filename,position):
    """Run the audiobook player.
    
    Arguments:
      filename  The filename to start playing at. (Or None to let the player
                decide.)

      position  The position to start playing at. (Or none to let the player
                decide.)
    """
    try:
      if(self._conf.autoplay):
        self._audiobook.play(filename,position)
      else:
        self._audiobook.seek(filename,position)
      self._gobject_thread.start()
      self._input.run()
    except (KeyboardInterrupt, SystemExit):
      self.quit()

def run():
  parser = pstorytime.audiobookargs.ArgumentParser(
    description="%(prog)s is a logging console audiobook player.",
    epilog="Paths can contain the strings {conf} and {audiobook}. They are replaced with the absolute path to the configuration directory and the audiobook directory respectively. Arguments can be placed in a configuration file in {conf}/config, or in any file specified on the commandline prefixed by an @ sign. Though the tilde character, {conf} and {audiobook} is not expanded in such paths.",
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

  if (not conf.noconf) and isfile(configfile):
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

if __name__ == '__main__':
  run()
