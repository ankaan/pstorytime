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
from datetime import timedelta

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

class Select(object):
  def __init__(self,curseslock,geom,audiobook,parser):
    self._lock = RLock()
    self._geom = geom
    self._window = geom.newwin()
    self._curseslock = curseslock
    self._audiobook = audiobook
    self._parser = parser

    self._audiobook.connect("notify::playlog",self._on_playlog)

    self._last_entry = None

    self._logsel = LogSelect( self._window,
                              self._geom,
                              self._curseslock,
                              self._audiobook)
    self._focus = self._logsel

    self._parser.connect("event",self._on_event)
    self._update()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        self._logsel.setGeom(geom)
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self._update()

  def _on_playlog(self,ab,prop):
    with self._lock:
      if self._focus == self._logsel:
        playlog = self._audiobook.playlog
        if len(playlog)>0 and playlog[-1]!=self._last_entry:
          self._update()

  def _on_event(self,obj,event):
    data = event.split()
    if len(data)>0:
      cmd = data[0]
      if cmd=="up":
        self._focus.move(-1)

      elif cmd=="down":
        self._focus.move(1)

      elif cmd=="ppage":
        self._focus.ppage()

      elif cmd=="npage":
        self._focus.npage()

      elif cmd=="begin":
        self._focus.move_to(0)

      elif cmd=="end":
        self._focus.move_to(None)

      elif cmd=="swap_view":
        self._swap_view()

      elif cmd=="select":
        if len(data)==2:
          (rel, pos) = parse_pos(data[1]) 
          if pos == None:
            return
        else:
          rel = None
          pos = None
        self._focus.select(rel,pos)

  def _swap_view(self):
    pass

  def _update(self):
    with self._lock:
      self._focus.draw()

class LogSelect(object):
  def __init__(self,window,geom,curseslock,audiobook):
    self._lock = RLock()
    self._window = window
    self._geom = geom
    self._curseslock = curseslock
    self._audiobook = audiobook

    self._focus = None

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom

  def move(self,delta):
    with self._lock:
      playlog = self._audiobook.playlog
      self._focus = calc_focus( length = len(playlog),
                                focus = self._focus,
                                delta = delta)
      self.draw()

  def ppage(self):
    with self._lock:
      playlog = self._audiobook.playlog
      num = min(self._geom.h, len(playlog))
      self._focus = calc_ppage( length = len(playlog),
                                num = num,
                                focus = self._focus)
      self.draw()

  def npage(self):
    with self._lock:
      playlog = self._audiobook.playlog
      num = min(self._geom.h, len(playlog))
      self._focus = calc_npage( length = len(playlog),
                                num = num,
                                focus = self._focus)
      self.draw()

  def move_to(self,focus):
    with self._lock:
      playlog = self._audiobook.playlog
      self._focus = calc_focus( length = len(playlog),
                                focus = focus,
                                delta = 0)
      self.draw()

  def select(self,rel,bufpos):
    with self._lock:
      ab = self._audiobook
      playlog = ab.playlog
      if self._focus == None:
        if rel:
          ab.dseek(bufpos)
        elif rel!=None:
          ab.seek(None,bufpos)
      else:
        filename = playlog[self._focus].filename
        position = playlog[self._focus].position
        if rel:
          ab.seek(filename,position+bufpos)
        elif rel!=None:
          ab.seek(filename,bufpos)
        else:
          ab.seek(filename,position)

  def draw(self):
    with self._lock:
      if self._geom.is_sane():
        with self._curseslock:
          self._window.erase()

          playlog = self._audiobook.playlog
          num = min(self._geom.h, len(playlog))
          focus = self._focus

          if focus==None:
            start = max(0, len(playlog)-num)
          else:
            start = max(0, min(len(playlog)-num, focus - num/2))

          for i in xrange(0, num):
            # Position in playlog
            logi = i + start
            # Check if this is the currently selected line
            if logi == focus:
              mark = "-> "
              attr = curses.A_REVERSE
            else:
              mark = "   "
              attr = curses.A_NORMAL

            walltime = time.strftime("%Y-%m-%d %H:%M:%S",
              time.gmtime(playlog[logi].walltime))

            # Format all stuff before filename
            part0 = "{mark}{walltime} {event:<10}".format(
              mark = mark,
              walltime = walltime,
              event = playlog[logi].event)

            # Format all stuff after filename
            position = playlog[logi].position
            position = timedelta(microseconds=position/1000)
            position = position - timedelta(microseconds=position.microseconds)
            part2 = " {position}".format(position=position)

            # Compute maximum length of filename
            part1len = max(0, self._geom.w - 1 - len(part0) - len(part2))
            # Take the end of filename, if it is too long.
            part1 = playlog[logi].filename[-part1len:]

            # Combine into complete line.
            pad = " " * (part1len - len(part1))
            line = part0 + part1 + pad + part2

            if self._geom.h>=1:
              self._window.addnstr(i, 0, line, self._geom.w-1,attr)
          self._window.refresh()

def calc_focus(length,focus,delta):
  if focus == None:
    if delta>0:
      focus = delta-1
    else:
      focus = delta+length
  else:
    focus += delta
  
  if focus<0 or focus>=length:
    focus = None

  return focus

def calc_ppage(length,num,focus):
  if focus == None:
    focus = length-1

  if focus > length-num/2:
    focus = length-num/2

  return max(0, focus - num)

def calc_npage(length,num,focus):
  if focus == None:
    return None

  if focus < num/2:
    focus = num/2

  newfocus = focus + num
  
  if newfocus > length:
    return None
  else:
    return newfocus

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

    self._key = None

    self._quit = Event()
    signal.signal(signal.SIGUSR1, lambda signum, stack_frame: None)
    signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(0))

    self._clear_timer = RepeatingTimer(1,self._clear_key)

    self._buffer = ""

    self._update()

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
          with self._lock:
            with self._curseslock:
              ch = self._window.getch()
              if ch == -1:
                break
              key = curses.keyname(ch)
              self._key = key

          try:
            with self._lock:
              event = self._charmap[key]
              eventword = event.split()
              eventname = eventword[0]
              if eventname=="buffer":
                if eventword[1] == "store":
                  self._buffer += eventword[2]
                elif eventword[1] == "erase":
                  self._buffer = self._buffer[:-1]
                elif eventword[1] == "clear":
                  self._buffer = ""
            if self._parser!=None and eventname!="buffer":
              self._parser.do(event.format(b=self._buffer))
          except (KeyError, IndexError):
            pass

          self._update()
          self._clear_timer.start()
    finally:
      self._quit.set()

  def _clear_key(self):
    with self._lock:
      if self._clear_timer.started():
        self._clear_timer.stop()
        self._key = None
        self._update()

  def quit(self):
    with self._lock:
      self._clear_timer.destroy()
      if not self._quit.is_set():
        self._quit.set()
        os.kill(os.getpid(), signal.SIGUSR1)

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self._update()

  def _update(self):
    with self._lock:
      if self._geom.is_sane():
        with self._curseslock:
          self._window.erase()
          prefix = "> "
          if self._key!=None:
            keystr = " ({0})".format(self._key)
          else:
            keystr = ""
          maxbuf = self._geom.w - len(keystr) - len(prefix) - 1
          bufstr = self._buffer[-maxbuf:]
          spacing = " "*(maxbuf-len(bufstr))
          line = prefix+bufstr+spacing+keystr
          if self._geom.h>=1:
            self._window.addnstr(0,0,line,self._geom.w-1)
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
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
          self._update()

  def _on_volume(self,obj,prop):
    with self._lock:
      self._update()

  def _update(self):
    with self._lock:
      if self._geom.is_sane():
        try:
          vol = "{0:.0%}".format(self._gst.get_property("volume"))
        except gst.QueryError:
          vol = "--%"
        with self._curseslock:
          self._window.erase()
          if self._geom.h>=1:
            self._window.addnstr(0,0,"  Vol",self._geom.w-1)
          if self._geom.h>=2:
            self._window.addnstr(1,0,"{0:>5}".format(vol),self._geom.w-1)
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
      self._timer = RepeatingTimer(interval, self._on_timer)
      self._update()

  def quit(self):
    self._timer.destroy()

  def getGeom(self):
    with self._lock:
      return self._geom

  def setGeom(self,geom):
    with self._lock:
      with self._curseslock:
        self._geom = geom
        if self._geom.is_sane():
          self._window.resize(geom.h,geom.w)
          self._window.mvwin(geom.y,geom.x)
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

  def _on_timer(self):
    with self._lock:
      if self._timer.started():
        self._update()

  def _update(self):
    with self._lock:
      if self._geom.is_sane():
        (filename,position,duration) = self._audiobook.position()
        if filename == None:
          filename = ""

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
          prefix = "File: "
          maxchars = self._geom.w - len(prefix) - 1
          first = prefix + filename[-maxchars:]

          second = "{position} / {duration} [{state}]".format(
            position=position,
            duration=duration,
            state=state)

          self._window.erase()
          if self._geom.h>=1:
            self._window.addnstr(0,0,first,self._geom.w-1)
          if self._geom.h>=2:
            self._window.addnstr(1,0,second,self._geom.w-1)
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

  def is_sane(self):
    return self.h>0 and self.w>0 and self.y>=0 and self.x>=0

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
      self._parser.connect("event",self._on_event)

      gobject.threads_init()
      self._mainloop = glib.MainLoop()

      charmap = { "KEY_RESIZE":"resize",
                  "^L":"resize",
                  "q":"quit",
                  " ":"play_pause",
                  "KEY_LEFT":"seek -10",
                  "h":"seek -10",
                  "KEY_RIGHT":"seek +10",
                  "l":"seek +10",
                  "u":"volume +0.1",
                  "d":"volume -0.1",
                  "KEY_UP":"up",
                  "KEY_DOWN":"down",
                  "KEY_HOME":"begin",
                  "KEY_END":"end",
                  "KEY_PPAGE":"ppage",
                  "KEY_NPAGE":"npage",
                  "^I":"swap_view",
                  "^J":"select {b}",
                  "1":"buffer store 1",
                  "2":"buffer store 2",
                  "3":"buffer store 3",
                  "4":"buffer store 4",
                  "5":"buffer store 5",
                  "6":"buffer store 6",
                  "7":"buffer store 7",
                  "8":"buffer store 8",
                  "9":"buffer store 9",
                  "0":"buffer store 0",
                  ":":"buffer store :",
                  "+":"buffer store +",
                  "-":"buffer store -",
                  "=":"buffer clear",
                  "KEY_BACKSPACE":"buffer erase"}

      (volume_geom, status_geom, input_geom, select_geom) = self._compute_geom()

      self._input = Input(curseslock=self._curseslock,
                          geom=input_geom,
                          charmap=charmap,
                          parser=self._parser)

      with self._curseslock:
        self._volume = Volume(curseslock=self._curseslock,
                              audiobook=self._audiobook,
                              geom=volume_geom)

        self._status = Status(curseslock=self._curseslock,
                              conf=conf,
                              audiobook=self._audiobook,
                              geom=status_geom,
                              interval=1)

        self._select = Select(curseslock=self._curseslock,
                              geom=select_geom,
                              audiobook=self._audiobook,
                              parser=self._parser)

      self._gobject_thread = Thread(target=self._mainloop.run,
                                    name="GobjectLoop")

  def getGeom(self):
    with self._lock:
      return Geometry.fromWindow(self._window)

  def _compute_geom(self):
    with self._lock:
      topgeom = self.getGeom()
      volume_geom = Geometry( h=min(Volume.HEIGHT,topgeom.h),
                              w=min(Volume.WIDTH,topgeom.w),
                              y=max(0,topgeom.h-Volume.HEIGHT),
                              x=max(0,topgeom.w-Volume.WIDTH))

      status_geom = Geometry( h=min(Status.HEIGHT,topgeom.h),
                              w=topgeom.w-volume_geom.w,
                              y=max(0,topgeom.h-Status.HEIGHT),
                              x=0)

      statusvol_h = max(Volume.HEIGHT,Status.HEIGHT)

      input_geom = Geometry(  h=min(Input.HEIGHT,topgeom.h-statusvol_h),
                              w=topgeom.w,
                              y=max(0,topgeom.h-statusvol_h-Input.HEIGHT),
                              x=0)

      select_geom = Geometry( h=max(0,topgeom.h-statusvol_h-Input.HEIGHT),
                              w=topgeom.w,
                              y=0,
                              x=0)

      return (volume_geom,status_geom,input_geom,select_geom)
      

  def _on_event(self,obj,event):
    data = event.split()
    if len(data)>0 and data[0]=="resize":
      with self._lock:
        self._update_layout()

  def _update_layout(self):
    with self._lock:
      with self._curseslock:
        (volume_geom,status_geom,input_geom,select_geom) = self._compute_geom()
        self._input.setGeom(input_geom)
        self._volume.setGeom(volume_geom)
        self._status.setGeom(status_geom)
        self._select.setGeom(select_geom)

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
      self._status.quit()
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
      self._audiobook.gst().set_property("volume",self._conf.volume)

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

  parser.add_argument(
    "--volume",
    help="Playback volume as a float between 0 and 10.",
    default=1.0,
    type=float)

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
